"""
NorgesGruppen detection + classification pipeline — NM i AI 2026
Uses ultralytics directly (no ONNX) for better compatibility and TTA support.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
import timm
from safetensors.torch import load_file as load_safetensors
from ultralytics import YOLO


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CONF_THRESH = 0.01
IOU_THRESH = 0.5
IMGSZ = 1280
MIN_BOX_AREA = 100
DINO_MODEL_NAME = "vit_base_patch14_reg4_dinov2"
DINO_EMBED_DIM = 768
CROP_SIZE = 518
BATCH_SIZE = 256


# ---------------------------------------------------------------------------
# Classification: DINOv2 embeddings
# ---------------------------------------------------------------------------
def load_dino_model(weights_dir: Path, device: torch.device):
    model = timm.create_model(DINO_MODEL_NAME, pretrained=False, num_classes=0)
    st_path = weights_dir / "dinov2_vitb14.safetensors"
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
def extract_embeddings(model, crops: list[np.ndarray], device: torch.device) -> np.ndarray:
    if len(crops) == 0:
        return np.empty((0, DINO_EMBED_DIM), dtype=np.float32)

    use_fp16 = device.type == "cuda"
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

    all_embeds = []
    for i in range(0, len(crops), BATCH_SIZE):
        batch_crops = crops[i : i + BATCH_SIZE]
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


def classify_crops(
    embeddings: np.ndarray,
    ref_embeddings: np.ndarray,
    ref_category_ids: np.ndarray,
    temperature: float = 0.07,
) -> tuple[np.ndarray, np.ndarray]:
    if len(embeddings) == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

    sim = embeddings @ ref_embeddings.T
    unique_cats = np.unique(ref_category_ids)
    n_cats = len(unique_cats)

    cat_max_sims = np.full((len(embeddings), n_cats), -1.0, dtype=np.float32)
    for j, cat in enumerate(unique_cats):
        indices = np.where(ref_category_ids == cat)[0]
        cat_max_sims[:, j] = np.max(sim[:, indices], axis=1)

    logits = cat_max_sims / temperature
    logits -= logits.max(axis=1, keepdims=True)
    exp_logits = np.exp(logits)
    probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)

    best_j = np.argmax(probs, axis=1)
    cat_ids = unique_cats[best_j]
    cat_scores = probs[np.arange(len(embeddings)), best_j]

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
    device_str = "cuda" if torch.cuda.is_available() else "cpu"

    # --- Load YOLOv8 detector (ultralytics native) ---
    yolo_path = weights_dir / "yolov8n_single.pt"
    det_model = YOLO(str(yolo_path))

    # --- Load DINOv2 classifier ---
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

    # --- Collect images ---
    image_paths = sorted(
        [p for p in images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    )

    predictions = []

    for img_path in image_paths:
        image_id = int(img_path.stem.split("_")[-1])

        # Run YOLO with built-in preprocessing, NMS, and optional TTA
        results = det_model(
            str(img_path),
            device=device_str,
            imgsz=IMGSZ,
            conf=CONF_THRESH,
            iou=IOU_THRESH,
            verbose=False,
            augment=False,  # TTA — set True if time budget allows
        )

        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            continue

        boxes = results[0].boxes
        xyxy = boxes.xyxy.cpu().numpy()  # (N, 4)
        scores = boxes.conf.cpu().numpy()  # (N,)

        # Read image for cropping
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            continue

        # Crop detections for classification
        crops = []
        valid_indices = []
        for i in range(len(xyxy)):
            x1, y1, x2, y2 = xyxy[i]
            x1i = max(0, int(round(x1)))
            y1i = max(0, int(round(y1)))
            x2i = min(img_bgr.shape[1], int(round(x2)))
            y2i = min(img_bgr.shape[0], int(round(y2)))
            if x2i <= x1i or y2i <= y1i:
                continue
            if (x2i - x1i) * (y2i - y1i) < MIN_BOX_AREA:
                continue
            crop = img_bgr[y1i:y2i, x1i:x2i]
            crops.append(crop)
            valid_indices.append(i)

        if len(crops) == 0:
            continue

        # Classify
        embeds = extract_embeddings(dino_model, crops, device)
        cat_ids, cls_scores = classify_crops(embeds, ref_embeds, ref_cat_ids)

        # Build predictions
        for idx, j in enumerate(valid_indices):
            x1, y1, x2, y2 = xyxy[j]
            w = x2 - x1
            h = y2 - y1
            final_score = float(scores[j]) * float(cls_scores[idx])
            predictions.append({
                "image_id": image_id,
                "category_id": int(cat_ids[idx]),
                "bbox": [round(float(x1), 2), round(float(y1), 2),
                         round(float(w), 2), round(float(h), 2)],
                "score": round(final_score, 6),
            })

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(output_path), "w") as f:
        json.dump(predictions, f)


if __name__ == "__main__":
    main()
