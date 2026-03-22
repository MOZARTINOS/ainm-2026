"""
NorgesGruppen Simulator v2 — Evaluation with Bootstrap Confidence Intervals
Usage: python evaluate_v2.py --gt val_annotations.json --pred predictions.json [--bootstrap 1000]
"""
import argparse
import json
import copy
import numpy as np
from pathlib import Path
from pycocotools.coco import COCO
from pycocotools.cocoeval import COCOeval
import tempfile


def compute_hybrid_score(gt_path, pred_path):
    """Compute hybrid score: 0.7 * det_mAP + 0.3 * cls_mAP"""
    with open(pred_path) as f:
        predictions = json.load(f)
    if not predictions:
        return 0.0, 0.0, 0.0, {}

    # --- Detection mAP (class-agnostic) ---
    coco_gt = COCO(str(gt_path))

    # Remap all categories to 0 for detection
    det_gt = copy.deepcopy(coco_gt.dataset)
    det_gt["categories"] = [{"id": 0, "name": "object"}]
    for ann in det_gt["annotations"]:
        ann["category_id"] = 0

    det_preds = copy.deepcopy(predictions)
    for p in det_preds:
        p["category_id"] = 0

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(det_gt, f)
        det_gt_path = f.name
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(det_preds, f)
        det_pred_path = f.name

    det_coco_gt = COCO(det_gt_path)
    det_coco_dt = det_coco_gt.loadRes(det_pred_path)
    det_eval = COCOeval(det_coco_gt, det_coco_dt, 'bbox')
    det_eval.params.iouThrs = [0.5]
    det_eval.evaluate()
    det_eval.accumulate()
    det_eval.summarize()
    det_map = det_eval.stats[0]

    import os
    os.unlink(det_gt_path)
    os.unlink(det_pred_path)

    # --- Classification mAP (with categories) ---
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
    cls_map = cls_eval.stats[0]

    os.unlink(cls_pred_path)

    # --- Per-category breakdown ---
    per_cat = {}
    if cls_eval.eval:
        for idx, cat_id in enumerate(cls_eval.params.catIds):
            # precision shape: [T, R, K, A, M] -> [iou, recall, cat, area, maxDet]
            p = cls_eval.eval['precision'][0, :, idx, 0, -1]
            ap = np.mean(p[p > -1]) if len(p[p > -1]) > 0 else 0.0
            per_cat[cat_id] = round(float(ap), 4)

    hybrid = 0.7 * det_map + 0.3 * cls_map
    return det_map, cls_map, hybrid, per_cat


def bootstrap_evaluation(gt_path, pred_path, n_bootstrap=1000, seed=42):
    """Image-level bootstrap resampling for confidence intervals."""
    np.random.seed(seed)

    with open(gt_path) as f:
        gt_data = json.load(f)
    with open(pred_path) as f:
        predictions = json.load(f)

    if not predictions:
        return 0.0, 0.0, 0.0, (0.0, 0.0)

    image_ids = [img["id"] for img in gt_data["images"]]
    n_images = len(image_ids)

    # Group GT annotations and predictions by image_id
    gt_by_img = {}
    for ann in gt_data["annotations"]:
        gt_by_img.setdefault(ann["image_id"], []).append(ann)

    pred_by_img = {}
    for p in predictions:
        pred_by_img.setdefault(p["image_id"], []).append(p)

    scores = []
    for b in range(n_bootstrap):
        # Sample image_ids with replacement
        sampled_ids = np.random.choice(image_ids, size=n_images, replace=True)

        # Remap to unique IDs to avoid pycocotools collisions
        new_images = []
        new_anns = []
        new_preds = []
        ann_id_counter = 1

        for i, orig_id in enumerate(sampled_ids):
            new_id = i + 1  # Sequential unique IDs

            # Find original image info
            orig_img = next(img for img in gt_data["images"] if img["id"] == orig_id)
            new_images.append({**orig_img, "id": new_id})

            # Remap GT annotations
            for ann in gt_by_img.get(orig_id, []):
                new_anns.append({**ann, "id": ann_id_counter, "image_id": new_id})
                ann_id_counter += 1

            # Remap predictions
            for p in pred_by_img.get(orig_id, []):
                new_preds.append({**p, "image_id": new_id})

        if not new_preds or not new_anns:
            scores.append(0.0)
            continue

        # Build temp COCO dataset
        temp_gt = {
            "images": new_images,
            "annotations": new_anns,
            "categories": gt_data["categories"],
        }

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(temp_gt, f)
                tgt = f.name
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(new_preds, f)
                tpred = f.name

            # Detection mAP
            det_gt_copy = copy.deepcopy(temp_gt)
            det_gt_copy["categories"] = [{"id": 0, "name": "object"}]
            for a in det_gt_copy["annotations"]:
                a["category_id"] = 0
            det_preds_copy = copy.deepcopy(new_preds)
            for p in det_preds_copy:
                p["category_id"] = 0

            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(det_gt_copy, f)
                dgt = f.name
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(det_preds_copy, f)
                dpred = f.name

            coco_dgt = COCO(dgt)
            coco_ddt = coco_dgt.loadRes(dpred)
            det_eval = COCOeval(coco_dgt, coco_ddt, 'bbox')
            det_eval.params.iouThrs = [0.5]
            det_eval.evaluate()
            det_eval.accumulate()
            det_eval.summarize()
            det_map = det_eval.stats[0]

            # Classification mAP
            coco_cgt = COCO(tgt)
            coco_cdt = coco_cgt.loadRes(tpred)
            cls_eval = COCOeval(coco_cgt, coco_cdt, 'bbox')
            cls_eval.params.iouThrs = [0.5]
            cls_eval.evaluate()
            cls_eval.accumulate()
            cls_eval.summarize()
            cls_map = cls_eval.stats[0]

            hybrid = 0.7 * det_map + 0.3 * cls_map
            scores.append(hybrid)

            os.unlink(tgt)
            os.unlink(tpred)
            os.unlink(dgt)
            os.unlink(dpred)
        except Exception:
            scores.append(0.0)

    scores = np.array(scores)
    mean = np.mean(scores)
    ci_low = np.percentile(scores, 2.5)
    ci_high = np.percentile(scores, 97.5)

    return mean, ci_low, ci_high, scores


def main():
    parser = argparse.ArgumentParser(description="NorgesGruppen Simulator v2")
    parser.add_argument("--gt", type=str, required=True, help="COCO GT annotations JSON")
    parser.add_argument("--pred", type=str, required=True, help="Predictions JSON")
    parser.add_argument("--bootstrap", type=int, default=0, help="Bootstrap iterations (0=skip)")
    args = parser.parse_args()

    print("=" * 60)
    print("NorgesGruppen Simulator v2")
    print("=" * 60)

    # Standard evaluation
    det_map, cls_map, hybrid, per_cat = compute_hybrid_score(args.gt, args.pred)
    print(f"\nDetection mAP@0.5:       {det_map:.4f}")
    print(f"Classification mAP@0.5:  {cls_map:.4f}")
    print(f"Hybrid score:            {hybrid:.4f}")
    print(f"  (0.7 × {det_map:.4f} + 0.3 × {cls_map:.4f})")

    # Per-category breakdown (top 10 worst)
    if per_cat:
        sorted_cats = sorted(per_cat.items(), key=lambda x: x[1])
        print(f"\nWorst 10 categories (by cls AP):")
        for cat_id, ap in sorted_cats[:10]:
            print(f"  cat_{cat_id}: AP={ap:.4f}")
        print(f"Best 5 categories:")
        for cat_id, ap in sorted_cats[-5:]:
            print(f"  cat_{cat_id}: AP={ap:.4f}")
        zero_cats = sum(1 for _, ap in per_cat.items() if ap == 0.0)
        print(f"Categories with AP=0: {zero_cats}/{len(per_cat)}")

    # Bootstrap confidence intervals
    if args.bootstrap > 0:
        print(f"\nBootstrap ({args.bootstrap} iterations)...")
        mean, ci_low, ci_high, scores = bootstrap_evaluation(
            args.gt, args.pred, n_bootstrap=args.bootstrap
        )
        print(f"Bootstrap mean:  {mean:.4f}")
        print(f"95% CI:          [{ci_low:.4f}, {ci_high:.4f}]")
        print(f"CI width:        {ci_high - ci_low:.4f}")
        print(f"Std dev:         {np.std(scores):.4f}")

    print("=" * 60)


if __name__ == "__main__":
    main()
