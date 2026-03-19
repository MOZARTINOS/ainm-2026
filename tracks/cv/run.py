"""
NorgesGruppen object detection pipeline — NM i AI 2026
Sandbox entry point: python run.py --images /data/images/ --output /output/predictions.json

Architecture:
  1. YOLOv8s ONNX single-class detector with SAHI tiling
  2. WBF merge of overlapping detections
  3. DINOv2 ViT-base classification via cosine-similarity kNN
"""

import argparse
import json
import math
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
TILE_SIZE = 640
OVERLAP = 0.30
CONF_THRESH = 0.001
WBF_IOU_THRESH = 0.4
WBF_SKIP_BOX_THRESH = 0.0001
DINO_MODEL_NAME = "vit_base_patch14_dinov2.lvd142m"
DINO_EMBED_DIM = 768
CROP_SIZE = 224
BATCH_SIZE = 128  # crops per forward pass through DINOv2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def letterbox(img: np.ndarray, new_shape: int = 640):
    """Resize + pad image to square, return (padded_img, scale, pad_x, pad_y)."""
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


def preprocess_tile(tile: np.ndarray) -> np.ndarray:
    """BGR HWC uint8 → RGB CHW float32 [0,1] with batch dim."""
    img, scale, pad_x, pad_y = letterbox(tile, TILE_SIZE)
    img = img[:, :, ::-1].astype(np.float32) / 255.0  # BGR→RGB, normalise
    img = np.transpose(img, (2, 0, 1))[None]           # CHW, add batch
    return img, scale, pad_x, pad_y


def decode_yolo_output(output: np.ndarray, conf_thresh: float):
    """
    Decode raw YOLOv8 output tensor (1, 5, N) → list of [x1,y1,x2,y2,score].
    For single-class detector, output has shape (1, 5, N) where row 4 is objectness.
    """
    # output shape: (1, 5, N) — transpose to (N, 5)
    preds = output[0].T  # (N, 5)
    scores = preds[:, 4]
    mask = scores > conf_thresh
    preds = preds[mask]
    if len(preds) == 0:
        return np.empty((0, 5), dtype=np.float32)

    # cx, cy, w, h → x1, y1, x2, y2
    cx, cy, w, h = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2
    return np.stack([x1, y1, x2, y2, preds[:, 4]], axis=1)


def generate_tiles(img_h: int, img_w: int, tile_size: int, overlap: float):
    """Yield (x_start, y_start) for SAHI-style tiling."""
    stride = int(tile_size * (1 - overlap))
    for y in range(0, max(1, img_h - tile_size // 2), stride):
        for x in range(0, max(1, img_w - tile_size // 2), stride):
            yield x, y


def run_detector_on_image(session: ort.InferenceSession, img_bgr: np.ndarray):
    """
    Run SAHI tiled detection on a single image.
    Returns np.ndarray of shape (M, 5): [x1, y1, x2, y2, score] in original pixel coords.
    """
    img_h, img_w = img_bgr.shape[:2]
    input_name = session.get_inputs()[0].name

    all_boxes_norm = []   # normalised [0,1] for WBF
    all_scores = []
    all_labels = []

    for tx, ty in generate_tiles(img_h, img_w, TILE_SIZE, OVERLAP):
        # Crop tile from image
        x_end = min(tx + TILE_SIZE, img_w)
        y_end = min(ty + TILE_SIZE, img_h)
        tile = img_bgr[ty:y_end, tx:x_end]

        tile_h, tile_w = tile.shape[:2]
        inp, scale, pad_x, pad_y = preprocess_tile(tile)
        raw = session.run(None, {input_name: inp})[0]
        dets = decode_yolo_output(raw, CONF_THRESH)

        for det in dets:
            # Remove letterbox padding and rescale to tile coords
            bx1 = (det[0] - pad_x) / scale
            by1 = (det[1] - pad_y) / scale
            bx2 = (det[2] - pad_x) / scale
            by2 = (det[3] - pad_y) / scale

            # Clip to tile bounds
            bx1 = max(0, bx1)
            by1 = max(0, by1)
            bx2 = min(tile_w, bx2)
            by2 = min(tile_h, by2)

            # Convert to full-image coords
            fx1 = bx1 + tx
            fy1 = by1 + ty
            fx2 = bx2 + tx
            fy2 = by2 + ty

            # Normalise for WBF
            all_boxes_norm.append([
                fx1 / img_w, fy1 / img_h,
                fx2 / img_w, fy2 / img_h,
            ])
            all_scores.append(det[4])
            all_labels.append(0)

    if len(all_boxes_norm) == 0:
        return np.empty((0, 5), dtype=np.float32)

    # WBF merge
    boxes_out, scores_out, _ = weighted_boxes_fusion(
        [np.array(all_boxes_norm)],
        [np.array(all_scores)],
        [np.array(all_labels)],
        iou_thr=WBF_IOU_THRESH,
        skip_box_thr=WBF_SKIP_BOX_THRESH,
    )

    # De-normalise back to pixel coords
    boxes_out[:, [0, 2]] *= img_w
    boxes_out[:, [1, 3]] *= img_h

    return np.concatenate([boxes_out, scores_out[:, None]], axis=1)


# ---------------------------------------------------------------------------
# Classification: DINOv2 embeddings
# ---------------------------------------------------------------------------

def load_dino_model(weights_dir: Path, device: torch.device):
    """Load DINOv2 ViT-base from timm with safetensors weights."""
    model = timm.create_model(DINO_MODEL_NAME, pretrained=False, num_classes=0)
    # Try safetensors first, then .pth
    st_path = weights_dir / "dinov2_vitb14.safetensors"
    pth_path = weights_dir / "dinov2_vitb14.pth"
    if st_path.exists():
        state_dict = load_safetensors(str(st_path))
        model.load_state_dict(state_dict, strict=False)
    elif pth_path.exists():
        state_dict = torch.load(str(pth_path), map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict, strict=False)
    else:
        # Fall back to pretrained download (won't work in sandbox without net)
        model = timm.create_model(DINO_MODEL_NAME, pretrained=True, num_classes=0)

    model = model.to(device).eval()
    return model


def extract_embeddings(model, crops: list[np.ndarray], device: torch.device) -> np.ndarray:
    """
    Extract DINOv2 embeddings for a list of BGR uint8 crops.
    Returns (N, 768) float32 numpy array, L2-normalised.
    """
    if len(crops) == 0:
        return np.empty((0, DINO_EMBED_DIM), dtype=np.float32)

    # DINOv2 normalisation (ImageNet stats)
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

    all_embeds = []
    for i in range(0, len(crops), BATCH_SIZE):
        batch_crops = crops[i : i + BATCH_SIZE]
        batch_np = []
        for crop in batch_crops:
            c = cv2.resize(crop, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_LINEAR)
            c = c[:, :, ::-1].astype(np.float32) / 255.0  # BGR→RGB
            c = np.transpose(c, (2, 0, 1))                 # CHW
            batch_np.append(c)

        batch_tensor = np.stack(batch_np)  # (B, 3, H, W)
        batch_tensor = (batch_tensor - mean) / std
        batch_tensor = torch.from_numpy(batch_tensor).to(device)

        with torch.no_grad():
            embeds = model(batch_tensor)  # (B, 768)

        embeds = embeds.cpu().numpy()
        # L2 normalise
        norms = np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-8
        embeds = embeds / norms
        all_embeds.append(embeds)

    return np.concatenate(all_embeds, axis=0)


def classify_crops(
    embeddings: np.ndarray,
    ref_embeddings: np.ndarray,
    ref_category_ids: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    kNN classification via cosine similarity.
    Returns (category_ids, classification_scores).
    """
    if len(embeddings) == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

    # cosine similarity (embeddings already L2-normalised)
    sim = embeddings @ ref_embeddings.T  # (N, num_refs)
    best_idx = np.argmax(sim, axis=1)
    best_score = sim[np.arange(len(sim)), best_idx]

    category_ids = ref_category_ids[best_idx]
    return category_ids, best_score


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=str, required=True, help="Path to images directory")
    parser.add_argument("--output", type=str, required=True, help="Path to output predictions JSON")
    args = parser.parse_args()

    images_dir = Path(args.images)
    output_path = Path(args.output)
    weights_dir = Path(__file__).parent / "weights"

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # --- Load detector ---
    onnx_path = weights_dir / "yolov8s_single.onnx"
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    det_session = ort.InferenceSession(str(onnx_path), providers=providers)

    # --- Load classifier ---
    dino_model = load_dino_model(weights_dir, device)

    # --- Load reference embeddings ---
    ref_embeds = np.load(str(weights_dir / "ref_embeddings.npy"))   # (327, 768)
    ref_cat_ids = np.load(str(weights_dir / "ref_category_ids.npy"))  # (327,)
    # L2 normalise references
    ref_norms = np.linalg.norm(ref_embeds, axis=1, keepdims=True) + 1e-8
    ref_embeds = ref_embeds / ref_norms

    # --- Collect images ---
    image_paths = sorted(
        [p for p in images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    )

    predictions = []

    for img_path in image_paths:
        image_id = int(img_path.stem)
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            continue

        # Detect
        detections = run_detector_on_image(det_session, img_bgr)
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
            crop = img_bgr[y1i:y2i, x1i:x2i]
            crops.append(crop)
            valid_dets.append(det)

        if len(crops) == 0:
            continue

        valid_dets = np.array(valid_dets)

        # Classify
        embeds = extract_embeddings(dino_model, crops, device)
        cat_ids, cls_scores = classify_crops(embeds, ref_embeds, ref_cat_ids)

        # Combine detection score * classification score
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
