"""
NorgesGruppen object detection + classification pipeline — NM i AI 2026
Sandbox entry point: python run.py --input /data/images --output /output/predictions.json

Architecture:
  1. YOLOv8s ONNX single-class detector with SAHI tiling
  2. WBF merge of overlapping detections
  3. DINOv2 ViT-S/14 (reg4) classification via cosine-similarity prototypes
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import timm
import torch
from ensemble_boxes import weighted_boxes_fusion
from safetensors.torch import load_file as load_safetensors


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TILE_SIZE = 1280
OVERLAP = 0.15                # balanced coverage vs speed
CONF_THRESH = 0.02            # low for good recall
WBF_IOU_THRESH = 0.5
WBF_SKIP_BOX_THRESH = 0.001
MIN_BOX_AREA = 50             # catch small products
MAX_CROPS_PER_IMAGE = 400     # ViT-S is fast enough for more crops
SKIP_TILE_THRESHOLD = 1280

# DINOv2 ViT-S/14 with registers — 4x smaller/faster than ViT-B/14
DINO_MODEL_NAME = "vit_small_patch14_reg4_dinov2"
DINO_EMBED_DIM = 384
CROP_SIZE = 518
BATCH_SIZE = 256


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def letterbox(img, new_shape=1280):
    h, w = img.shape[:2]
    scale = new_shape / max(h, w)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    pad_w = new_shape - new_w
    pad_h = new_shape - new_h
    top = pad_h // 2
    left = pad_w // 2
    img_padded = cv2.copyMakeBorder(
        img_resized, top, pad_h - top, left, pad_w - left,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )
    return img_padded, scale, left, top


def preprocess_tile(tile, use_fp16=False):
    img, scale, pad_x, pad_y = letterbox(tile, TILE_SIZE)
    img = img[:, :, ::-1].astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))[None]
    if use_fp16:
        img = img.astype(np.float16)
    return img, scale, pad_x, pad_y


def decode_yolo_output(output, conf_thresh):
    preds = np.asarray(output[0], dtype=np.float32).T
    scores = preds[:, 4]
    mask = scores > conf_thresh
    preds = preds[mask]
    if len(preds) == 0:
        return np.empty((0, 5), dtype=np.float32)
    cx, cy, w, h = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2
    return np.stack([x1, y1, x2, y2, preds[:, 4]], axis=1)


def generate_tiles(img_h, img_w, tile_size, overlap):
    stride = int(tile_size * (1 - overlap))
    for y in range(0, max(1, img_h - tile_size // 2), stride):
        for x in range(0, max(1, img_w - tile_size // 2), stride):
            yield x, y


def run_detector(session, img_bgr, input_name, det_fp16):
    """SAHI tiled detection with WBF merge. Fast path for small images."""
    img_h, img_w = img_bgr.shape[:2]

    # Fast path: small image fits in one tile
    if img_h <= SKIP_TILE_THRESHOLD and img_w <= SKIP_TILE_THRESHOLD:
        inp, scale, pad_x, pad_y = preprocess_tile(img_bgr, use_fp16=det_fp16)
        raw = session.run(None, {input_name: inp})[0]
        dets = decode_yolo_output(raw, CONF_THRESH)
        if len(dets) == 0:
            return np.empty((0, 5), dtype=np.float32)
        dets[:, 0] = np.clip((dets[:, 0] - pad_x) / scale, 0, img_w)
        dets[:, 1] = np.clip((dets[:, 1] - pad_y) / scale, 0, img_h)
        dets[:, 2] = np.clip((dets[:, 2] - pad_x) / scale, 0, img_w)
        dets[:, 3] = np.clip((dets[:, 3] - pad_y) / scale, 0, img_h)
        valid = (dets[:, 2] > dets[:, 0]) & (dets[:, 3] > dets[:, 1])
        return dets[valid]

    # SAHI tiling path
    all_boxes_norm = []
    all_scores = []
    all_labels = []

    for tx, ty in generate_tiles(img_h, img_w, TILE_SIZE, OVERLAP):
        x_end = min(tx + TILE_SIZE, img_w)
        y_end = min(ty + TILE_SIZE, img_h)
        tile = img_bgr[ty:y_end, tx:x_end]
        tile_h, tile_w = tile.shape[:2]

        inp, scale, pad_x, pad_y = preprocess_tile(tile, use_fp16=det_fp16)
        raw = session.run(None, {input_name: inp})[0]
        dets = decode_yolo_output(raw, CONF_THRESH)

        for det in dets:
            bx1 = max(0, (det[0] - pad_x) / scale)
            by1 = max(0, (det[1] - pad_y) / scale)
            bx2 = min(tile_w, (det[2] - pad_x) / scale)
            by2 = min(tile_h, (det[3] - pad_y) / scale)

            fx1 = max(0.0, bx1 + tx)
            fy1 = max(0.0, by1 + ty)
            fx2 = min(float(img_w), bx2 + tx)
            fy2 = min(float(img_h), by2 + ty)

            if fx2 <= fx1 or fy2 <= fy1:
                continue

            all_boxes_norm.append([fx1 / img_w, fy1 / img_h, fx2 / img_w, fy2 / img_h])
            all_scores.append(float(det[4]))
            all_labels.append(0)

    if len(all_boxes_norm) == 0:
        return np.empty((0, 5), dtype=np.float32)

    boxes_out, scores_out, _ = weighted_boxes_fusion(
        [np.array(all_boxes_norm)],
        [np.array(all_scores)],
        [np.array(all_labels)],
        iou_thr=WBF_IOU_THRESH,
        skip_box_thr=WBF_SKIP_BOX_THRESH,
    )

    boxes_out[:, [0, 2]] *= img_w
    boxes_out[:, [1, 3]] *= img_h

    return np.concatenate([boxes_out, scores_out[:, None]], axis=1)


# ---------------------------------------------------------------------------
# Classification: DINOv2 ViT-S/14 embeddings
# ---------------------------------------------------------------------------

def load_dino_model(weights_dir, device):
    model = timm.create_model(DINO_MODEL_NAME, pretrained=False, num_classes=0)
    st_path = weights_dir / "dinov2_vits14.safetensors"
    if st_path.exists():
        state_dict = load_safetensors(str(st_path))
        model.load_state_dict(state_dict, strict=False)
    else:
        model = timm.create_model(DINO_MODEL_NAME, pretrained=True, num_classes=0)
    model = model.to(device).eval()
    if device.type == "cuda":
        model = model.half()
    return model


@torch.inference_mode()
def extract_embeddings(model, crops, device):
    if len(crops) == 0:
        return np.empty((0, DINO_EMBED_DIM), dtype=np.float32)

    use_fp16 = device.type == "cuda"
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

    all_embeds = []
    for i in range(0, len(crops), BATCH_SIZE):
        batch_crops = crops[i:i + BATCH_SIZE]
        batch_np = []
        for crop in batch_crops:
            c = cv2.resize(crop, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_LINEAR)
            c = c[:, :, ::-1].astype(np.float32) / 255.0
            c = np.transpose(c, (2, 0, 1))
            batch_np.append(c)

        batch_tensor = np.stack(batch_np)
        batch_tensor = (batch_tensor - mean) / std
        batch_tensor = torch.from_numpy(batch_tensor).to(device)
        if use_fp16:
            batch_tensor = batch_tensor.half()

        embeds = model(batch_tensor)
        embeds = embeds.float().cpu().numpy()
        norms = np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-8
        embeds = embeds / norms
        all_embeds.append(embeds)

    return np.concatenate(all_embeds, axis=0)


def classify_crops(embeddings, ref_embeddings, ref_category_ids, global_mean=None, tau=0.07):
    """Cosine similarity with prototype centering + temperature scaling."""
    if len(embeddings) == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

    # Prototype centering: subtract global mean from both queries and prototypes
    # This resolves the anisotropy problem in ViT embedding spaces
    if global_mean is not None:
        embeddings = embeddings - global_mean
        ref_embeddings = ref_embeddings - global_mean
        # Re-normalize after centering
        e_norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
        embeddings = embeddings / e_norms
        r_norms = np.linalg.norm(ref_embeddings, axis=1, keepdims=True) + 1e-8
        ref_embeddings = ref_embeddings / r_norms

    sim = embeddings @ ref_embeddings.T  # (N, 356)

    # Temperature-scaled softmax for calibrated scores
    logits = sim / tau
    logits -= logits.max(axis=1, keepdims=True)  # numerical stability
    exp_logits = np.exp(logits)
    probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

    best_idx = np.argmax(probs, axis=1)
    cat_ids = ref_category_ids[best_idx]
    cat_scores = probs[np.arange(len(probs)), best_idx]

    return cat_ids, cat_scores


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    images_dir = Path(args.input)
    output_path = Path(args.output)
    weights_dir = Path(__file__).parent / "weights"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # --- Load detector (ONNX with CUDA) ---
    onnx_path = weights_dir / "yolov8s_single.onnx"
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    det_session = ort.InferenceSession(str(onnx_path), sess_options=sess_opts, providers=providers)

    det_input = det_session.get_inputs()[0]
    det_input_name = det_input.name
    det_fp16 = det_input.type == "tensor(float16)"

    # --- Load classifier ---
    dino_model = load_dino_model(weights_dir, device)

    # --- Load reference embeddings ---
    ref_data = np.load(str(weights_dir / "ref_embeddings.npy"))
    if ref_data.shape[1] == DINO_EMBED_DIM + 1:
        ref_cat_ids = ref_data[:, 0].astype(np.int64)
        ref_embeds = ref_data[:, 1:]
    else:
        ref_embeds = ref_data
        ref_cat_ids = np.arange(ref_embeds.shape[0])
    ref_norms = np.linalg.norm(ref_embeds, axis=1, keepdims=True) + 1e-8
    ref_embeds = (ref_embeds / ref_norms).astype(np.float32)

    # Compute global mean for prototype centering (resolves anisotropy)
    global_mean = ref_embeds.mean(axis=0, keepdims=True)

    # --- Collect images ---
    image_paths = sorted(
        [p for p in images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    )

    predictions = []

    for img_path in image_paths:
        image_id = int(img_path.stem.split("_")[-1])
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            continue

        # SAHI tiled detection
        detections = run_detector(det_session, img_bgr, det_input_name, det_fp16)
        if len(detections) == 0:
            continue

        # Crop detections for classification
        crops = []
        valid_dets = []
        for det in detections:
            x1, y1, x2, y2, score = det
            x1i = max(0, int(round(x1)))
            y1i = max(0, int(round(y1)))
            x2i = min(img_bgr.shape[1], int(round(x2)))
            y2i = min(img_bgr.shape[0], int(round(y2)))
            if x2i <= x1i or y2i <= y1i:
                continue
            if (x2i - x1i) * (y2i - y1i) < MIN_BOX_AREA:
                continue
            crops.append(img_bgr[y1i:y2i, x1i:x2i])
            valid_dets.append(det)

        if len(crops) == 0:
            continue

        valid_dets = np.array(valid_dets)

        # Cap crops — keep highest-confidence ones
        if len(crops) > MAX_CROPS_PER_IMAGE:
            top_idx = np.argsort(valid_dets[:, 4])[::-1][:MAX_CROPS_PER_IMAGE]
            crops = [crops[i] for i in top_idx]
            valid_dets = valid_dets[top_idx]

        # Classify
        embeds = extract_embeddings(dino_model, crops, device)
        cat_ids, cls_scores = classify_crops(embeds, ref_embeds, ref_cat_ids, global_mean=global_mean)

        # Combine scores
        final_scores = valid_dets[:, 4] * cls_scores

        # Build predictions
        for j in range(len(valid_dets)):
            x1, y1, x2, y2 = valid_dets[j, :4]
            w = x2 - x1
            h = y2 - y1
            predictions.append({
                "image_id": image_id,
                "category_id": int(cat_ids[j]),
                "bbox": [round(float(x1), 2), round(float(y1), 2),
                         round(float(w), 2), round(float(h), 2)],
                "score": round(float(final_scores[j]), 6),
            })

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(output_path), "w") as f:
        json.dump(predictions, f)


if __name__ == "__main__":
    main()
