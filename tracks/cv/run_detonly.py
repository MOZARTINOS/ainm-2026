"""
NorgesGruppen detection-only pipeline — NM i AI 2026
Pure detection, category_id=0 for all (max score 0.70).
Optimized for speed on L4 GPU.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from ensemble_boxes import weighted_boxes_fusion


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TILE_SIZE = 1280
OVERLAP = 0.15
CONF_THRESH = 0.01
WBF_IOU_THRESH = 0.5
WBF_SKIP_BOX_THRESH = 0.001
MIN_BOX_AREA = 100
SKIP_TILE_THRESHOLD = 1280


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def letterbox(img: np.ndarray, new_shape: int = 1280):
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


def preprocess_tile(tile: np.ndarray, use_fp16: bool = False):
    img, scale, pad_x, pad_y = letterbox(tile, TILE_SIZE)
    img = img[:, :, ::-1].astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))[None]
    if use_fp16:
        img = img.astype(np.float16)
    return img, scale, pad_x, pad_y


def decode_yolo_output(output: np.ndarray, conf_thresh: float):
    preds = np.asarray(output[0], dtype=np.float32).T  # (N, 5)
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


def generate_tiles(img_h: int, img_w: int, tile_size: int, overlap: float):
    stride = int(tile_size * (1 - overlap))
    for y in range(0, max(1, img_h - tile_size // 2), stride):
        for x in range(0, max(1, img_w - tile_size // 2), stride):
            yield x, y


def run_detector(session, img_bgr, input_name, det_fp16):
    img_h, img_w = img_bgr.shape[:2]

    # Fast path: small image
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

    # SAHI tiling
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
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    images_dir = Path(args.input)
    output_path = Path(args.output)
    weights_dir = Path(__file__).parent / "weights"

    # Load detector
    onnx_path = weights_dir / "yolov8m_single.onnx"
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(onnx_path), sess_options=sess_opts, providers=providers)

    det_input = session.get_inputs()[0]
    input_name = det_input.name
    det_fp16 = det_input.type == "tensor(float16)"

    # Collect images
    image_paths = sorted(
        [p for p in images_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    )

    predictions = []

    for img_path in image_paths:
        image_id = int(img_path.stem.split("_")[-1])
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            continue

        detections = run_detector(session, img_bgr, input_name, det_fp16)

        for det in detections:
            x1, y1, x2, y2, score = det
            w = x2 - x1
            h = y2 - y1
            if w * h < MIN_BOX_AREA:
                continue
            predictions.append({
                "image_id": image_id,
                "category_id": 0,
                "bbox": [round(float(x1), 2), round(float(y1), 2),
                         round(float(w), 2), round(float(h), 2)],
                "score": round(float(score), 6),
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(output_path), "w") as f:
        json.dump(predictions, f)


if __name__ == "__main__":
    main()
