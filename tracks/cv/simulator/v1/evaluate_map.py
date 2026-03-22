"""
Evaluate predictions against COCO ground truth.
Computes the SAME hybrid score as the competition:
  score = 0.7 * detection_mAP@0.5 + 0.3 * classification_mAP@0.5
"""
import json
import numpy as np
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
from pathlib import Path
import argparse

def evaluate(gt_path, pred_path):
    """Compute detection mAP and classification mAP."""
    with open(pred_path) as f:
        predictions = json.load(f)

    if not predictions:
        print("No predictions!")
        return 0.0, 0.0, 0.0

    # === Detection mAP (ignore category — treat all as class 0) ===
    coco_gt = COCO(str(gt_path))

    # For detection: remap all categories to 0
    det_preds = []
    for p in predictions:
        det_preds.append({
            "image_id": p["image_id"],
            "category_id": 0,  # ignore real category
            "bbox": p["bbox"],
            "score": p["score"],
        })

    # Create single-class GT
    det_gt_anns = []
    for ann in coco_gt.dataset["annotations"]:
        det_gt_anns.append({
            **ann,
            "category_id": 0,
        })
    det_gt = {
        "images": coco_gt.dataset["images"],
        "annotations": det_gt_anns,
        "categories": [{"id": 0, "name": "object"}],
    }

    # Save temp files for pycocotools
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(det_gt, f)
        det_gt_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(det_preds, f)
        det_pred_path = f.name

    det_coco_gt = COCO(det_gt_path)
    det_coco_dt = det_coco_gt.loadRes(det_pred_path)
    det_eval = COCOeval(det_coco_gt, det_coco_dt, 'bbox')
    det_eval.params.iouThrs = [0.5]  # Only IoU=0.5
    det_eval.evaluate()
    det_eval.accumulate()
    det_eval.summarize()
    det_map = det_eval.stats[0]  # mAP@0.5

    os.unlink(det_gt_path)
    os.unlink(det_pred_path)

    # === Classification mAP (with correct category_id) ===
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(predictions, f)
        cls_pred_path = f.name

    cls_coco_gt = COCO(str(gt_path))
    cls_coco_dt = cls_coco_gt.loadRes(cls_pred_path)
    cls_eval = COCOeval(cls_coco_gt, cls_coco_dt, 'bbox')
    cls_eval.params.iouThrs = [0.5]
    cls_eval.evaluate()
    cls_eval.accumulate()
    cls_eval.summarize()
    cls_map = cls_eval.stats[0]  # mAP@0.5 with categories

    os.unlink(cls_pred_path)

    # === Hybrid score ===
    hybrid = 0.7 * det_map + 0.3 * cls_map
    print(f"\n{'='*50}")
    print(f"Detection mAP@0.5:       {det_map:.4f}")
    print(f"Classification mAP@0.5:  {cls_map:.4f}")
    print(f"Hybrid score:            {hybrid:.4f}")
    print(f"  (0.7 × {det_map:.4f} + 0.3 × {cls_map:.4f})")
    print(f"{'='*50}")

    return det_map, cls_map, hybrid

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt", type=str, default="/root/cv/yolo_split/val_annotations.json")
    parser.add_argument("--pred", type=str, default="/output/predictions.json")
    args = parser.parse_args()
    evaluate(args.gt, args.pred)
