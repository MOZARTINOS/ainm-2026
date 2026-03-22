"""
NorgesGruppen object detection pipeline — NM i AI 2026
Variant A: Multi-class YOLOv8s (nc=356) with SAHI tiling.
Single model does both detection AND classification. No separate classifier needed.

python run.py --input /data/images --output /output/predictions.json
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
OVERLAP = 0.25            # 25% overlap — best from grid search
CONF_THRESH = 0.02        # Lower = more recall = better mAP (grid search v2)
WBF_IOU_THRESH = 0.45     # Lower = less merging = preserves dense detections (grid search v2)
WBF_SKIP_BOX_THRESH = 0.001
MIN_BOX_AREA = 50
SKIP_TILE_THRESHOLD = 1280


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def letterbox(img, new_shape=1280):
    """Resize + pad image to square."""
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
    """BGR HWC uint8 → RGB CHW float [0,1] with batch dim."""
    img, scale, pad_x, pad_y = letterbox(tile, TILE_SIZE)
    img = img[:, :, ::-1].astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))[None]
    if use_fp16:
        img = img.astype(np.float16)
    return img, scale, pad_x, pad_y


def decode_multiclass_output(output, conf_thresh, num_classes=356):
    """
    Decode YOLOv8 multi-class output tensor.
    Shape: (1, 4+num_classes, N) → array of [x1,y1,x2,y2,score,class_id].
    """
    preds = np.asarray(output[0], dtype=np.float32).T  # (N, 4+num_classes)
    if preds.shape[0] == 0:
        return np.empty((0, 6), dtype=np.float32)

    # Extract box coordinates
    cx, cy, w, h = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]

    # Class scores: columns 4 onwards
    class_scores = preds[:, 4:]  # (N, num_classes)

    # Best class per detection
    class_ids = np.argmax(class_scores, axis=1)
    class_confs = class_scores[np.arange(len(class_scores)), class_ids]

    # Filter by confidence
    mask = class_confs > conf_thresh
    if not np.any(mask):
        return np.empty((0, 6), dtype=np.float32)

    cx, cy, w, h = cx[mask], cy[mask], w[mask], h[mask]
    class_ids = class_ids[mask]
    class_confs = class_confs[mask]

    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2

    return np.stack([x1, y1, x2, y2, class_confs, class_ids.astype(np.float32)], axis=1)


def generate_tiles(img_h, img_w, tile_size, overlap):
    """Yield (x_start, y_start) for SAHI-style tiling."""
    stride = int(tile_size * (1 - overlap))
    for y in range(0, max(1, img_h - tile_size // 2), stride):
        for x in range(0, max(1, img_w - tile_size // 2), stride):
            yield x, y


def run_detector(session, img_bgr, input_name, det_fp16, num_classes=356):
    """SAHI tiled detection with per-class WBF merge."""
    img_h, img_w = img_bgr.shape[:2]

    # Fast path: small image
    if img_h <= SKIP_TILE_THRESHOLD and img_w <= SKIP_TILE_THRESHOLD:
        inp, scale, pad_x, pad_y = preprocess_tile(img_bgr, use_fp16=det_fp16)
        raw = session.run(None, {input_name: inp})[0]
        dets = decode_multiclass_output(raw, CONF_THRESH, num_classes)
        if len(dets) == 0:
            return np.empty((0, 6), dtype=np.float32)
        # Unpad coordinates
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
        dets = decode_multiclass_output(raw, CONF_THRESH, num_classes)

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

            box_area = (fx2 - fx1) * (fy2 - fy1)
            if box_area < MIN_BOX_AREA:
                continue

            all_boxes_norm.append([fx1 / img_w, fy1 / img_h, fx2 / img_w, fy2 / img_h])
            all_scores.append(float(det[4]))
            all_labels.append(int(det[5]))

    if len(all_boxes_norm) == 0:
        return np.empty((0, 6), dtype=np.float32)

    # WBF merge — uses class labels for per-class merging
    boxes_out, scores_out, labels_out = weighted_boxes_fusion(
        [np.array(all_boxes_norm)],
        [np.array(all_scores)],
        [np.array(all_labels)],
        iou_thr=WBF_IOU_THRESH,
        skip_box_thr=WBF_SKIP_BOX_THRESH,
    )

    boxes_out[:, [0, 2]] *= img_w
    boxes_out[:, [1, 3]] *= img_h

    result = np.zeros((len(boxes_out), 6), dtype=np.float32)
    result[:, :4] = boxes_out
    result[:, 4] = scores_out
    result[:, 5] = labels_out

    return result


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

    # Load multi-class ONNX model
    onnx_path = weights_dir / "yolov8s_mc356.onnx"
    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    sess_opts = ort.SessionOptions()
    sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(str(onnx_path), sess_options=sess_opts, providers=providers)

    det_input = session.get_inputs()[0]
    input_name = det_input.name
    det_fp16 = det_input.type == "tensor(float16)"

    # Detect number of classes from output shape
    out_shape = session.get_outputs()[0].shape
    if out_shape and len(out_shape) >= 2:
        # Output is (1, 4+nc, N) — nc = out_shape[1] - 4
        num_classes = (out_shape[1] if out_shape[1] else 360) - 4
    else:
        num_classes = 356

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

        # TTA: collect detections from multiple augmented views
        img_h, img_w = img_bgr.shape[:2]
        tta_results = []

        # 1. Original
        tta_results.append(run_detector(session, img_bgr, input_name, det_fp16, num_classes))

        # 2. Horizontal flip
        img_flip = cv2.flip(img_bgr, 1)
        dets_flip = run_detector(session, img_flip, input_name, det_fp16, num_classes)
        if len(dets_flip) > 0:
            x1_f = img_w - dets_flip[:, 2]
            x2_f = img_w - dets_flip[:, 0]
            dets_flip[:, 0] = x1_f
            dets_flip[:, 2] = x2_f
        tta_results.append(dets_flip)

        # 3. Scaled down (0.8x) — catches objects at different scales
        scale_factor = 0.8
        img_scaled = cv2.resize(img_bgr, (int(img_w * scale_factor), int(img_h * scale_factor)))
        dets_scaled = run_detector(session, img_scaled, input_name, det_fp16, num_classes)
        if len(dets_scaled) > 0:
            dets_scaled[:, :4] /= scale_factor
        tta_results.append(dets_scaled)

        # 4. Scaled + horizontal flip
        img_scaled_flip = cv2.flip(img_scaled, 1)
        dets_sf = run_detector(session, img_scaled_flip, input_name, det_fp16, num_classes)
        if len(dets_sf) > 0:
            sw = int(img_w * scale_factor)
            x1_sf = sw - dets_sf[:, 2]
            x2_sf = sw - dets_sf[:, 0]
            dets_sf[:, 0] = x1_sf
            dets_sf[:, 2] = x2_sf
            dets_sf[:, :4] /= scale_factor
        tta_results.append(dets_sf)

        # Merge all TTA results with WBF
        all_boxes = []
        all_scores = []
        all_labels = []
        for dets in tta_results:
            if len(dets) == 0:
                all_boxes.append(np.empty((0, 4), dtype=np.float32))
                all_scores.append(np.empty((0,), dtype=np.float32))
                all_labels.append(np.empty((0,), dtype=np.int32))
                continue
            boxes_norm = dets[:, :4].copy()
            boxes_norm[:, [0, 2]] /= img_w
            boxes_norm[:, [1, 3]] /= img_h
            boxes_norm = np.clip(boxes_norm, 0.0, 1.0)
            all_boxes.append(boxes_norm)
            all_scores.append(dets[:, 4])
            all_labels.append(dets[:, 5].astype(np.int32))

        total_dets = sum(len(b) for b in all_boxes)
        if total_dets == 0:
            continue

        boxes_out, scores_out, labels_out = weighted_boxes_fusion(
            all_boxes, all_scores, all_labels,
            iou_thr=WBF_IOU_THRESH, skip_box_thr=WBF_SKIP_BOX_THRESH,
        )

        boxes_out[:, [0, 2]] *= img_bgr.shape[1]
        boxes_out[:, [1, 3]] *= img_bgr.shape[0]

        detections = np.zeros((len(boxes_out), 6), dtype=np.float32)
        detections[:, :4] = boxes_out
        detections[:, 4] = scores_out
        detections[:, 5] = labels_out

        if len(detections) == 0:
            continue

        for det in detections:
            x1, y1, x2, y2, score, class_id = det
            w = x2 - x1
            h = y2 - y1
            if w <= 0 or h <= 0:
                continue
            predictions.append({
                "image_id": image_id,
                "category_id": int(class_id),
                "bbox": [round(float(x1), 2), round(float(y1), 2),
                         round(float(w), 2), round(float(h), 2)],
                "score": round(float(score), 6),
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(output_path), "w") as f:
        json.dump(predictions, f)


if __name__ == "__main__":
    main()
