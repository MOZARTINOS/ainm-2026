# NorgesGruppen Experiment Log

## 2026-03-21 09:45 CET — Overnight Training Results + Honest Val Breakthrough

### Best Combo (unfreeze + copypaste data + dropout=0.3 + label_smoothing=0.1)
- 120/120 epochs on 7308 copy-paste tiles
- **Overfit val: hybrid 0.724** (det 0.655, cls 0.884)
- Timing: 48s on L4
- ONNX: 44MB, ZIP ready

### Honest Val (unfreeze on 199 train-only images, tested on HELD-OUT 49)
- 100/100 epochs on 1468 tiles from 199 images
- **HONEST hybrid: 0.511** (det 0.502, cls 0.530)
- This is the FIRST reliable generalization estimate
- Compares to unfreeze public score: **0.516** — very close! Honest val WORKS.

### Validation Reliability Analysis
| Model | Overfit val | Honest val | Public | Overfit/Public ratio |
|-------|-----------|-----------|--------|---------------------|
| Unfreeze (1827 tiles) | 0.638 | 0.511* | **0.5160** | 0.81 |
| Copypaste (7308 tiles) | 0.736 | TBD | TBD | TBD |
| Best combo (7308 tiles) | 0.724 | TBD | TBD | TBD |
| Freeze=10 (1827 tiles) | 0.707 | TBD | 0.5004 | 0.71 |
*Honest val trained on 199 imgs only — different model, but same approach (unfreeze lr=1e-4)

**KEY INSIGHT**: Honest val (0.511) ≈ Public (0.516). Overfit val overestimates by 24-40%.
To predict public from overfit val: multiply by ~0.70-0.81 (unstable).
Honest val is the ONLY reliable predictor.

### Balanced Training — FAILURE + FIX
- **v1 FAILED**: `image_weights` and `fl_gamma` are NOT valid ultralytics 8.1.0 params!
  - Deep Research hallucinated these parameters
  - Error: `SyntaxError: 'image_weights' is not a valid YOLO argument`
- **v2 LAUNCHED**: Alternative regularization approach:
  - dropout=0.2, weight_decay=0.001, label_smoothing=0.05
  - erasing=0.2 (random erasing augmentation)
  - scale=0.4, translate=0.15, hsv_s=0.5 (stronger augmentation)
  - Running on A100, ~6 hours
- **LESSON**: Always verify Deep Research params against actual ultralytics docs!

---

## 2026-03-21 09:30 CET — All Models Simulator v2 Summary (with WBF=0.45)

### Complete Model Comparison (WBF=0.45 CONF=0.02)
| Model | det_mAP | cls_mAP | Hybrid | zero-AP cats | Public |
|-------|---------|---------|--------|-------------|--------|
| Copypaste (freeze=10, 7308 tiles) | 0.643 | 0.859 | **0.736** | 81 | TBD |
| Best combo (unfreeze+cp+dropout) | 0.655 | 0.884 | 0.724 | TBD | TBD |
| Unfreeze (1827 tiles) | 0.587 | 0.757 | 0.638* | 96 | **0.5160** |
| Freeze=10 (1827 tiles) | 0.643 | 0.859 | 0.707* | 81 | 0.5004 |
| Honest val (199 imgs) | 0.502 | 0.530 | 0.511 | TBD | — |
*WBF=0.55 for these public scores. With WBF=0.45 should improve.

### Problem Areas
1. **81-96 zero-AP categories** — 23-27% of products unrecognized
   - Root cause: 84 categories have ≤5 training annotations
   - Fix: image_weights=True + fl_gamma=1.5 (training now)
2. **Overfit val unreliable** — ratio varies 0.71 to 0.81
   - Fix: honest val (confirmed working: 0.511 ≈ public 0.516)
3. **Detection is bottleneck** — det_mAP 0.50-0.65 (70% weight)
   - SAHI helps but small objects still hard
4. **Copy-paste artifact overfitting** — model learns paste edges, not products
   - Research recommends SAM segmentation + alpha blending

---

## 2026-03-21 04:30 CET — WBF Parameter Grid Search (COPYPASTE model)

### Finding: WBF_IOU=0.45 + CONF=0.02 significantly better than defaults

| WBF_IOU | CONF=0.02 | CONF=0.05 | CONF=0.10 |
|---------|-----------|-----------|-----------|
| **0.45** | **0.736** ★ | 0.735 | 0.734 |
| 0.50 | 0.727 | 0.725 | 0.724 |
| 0.55 (old) | 0.709 | 0.708 (old) | 0.706 |
| 0.60 | 0.693 | 0.692 | 0.690 |

**Improvement: +0.028 hybrid** (0.708 → 0.736) from parameter tuning alone.
**Insight**: Lower WBF IoU = less box merging = better for dense retail shelves.
**Action**: Updated run_multiclass.py, rebuilt both copypaste.zip and unfreeze_v2.zip.

**CAUTION**: This is overfit val. Improvement may not translate fully to public.
Unfreeze went from val 0.638 → public 0.516 (ratio 0.81).
If same ratio: copypaste 0.736 × 0.81 ≈ **0.596 predicted public**.

---

## 2026-03-21 04:00 CET — Simulator v2 Full Evaluation

### All Models on Overfit Val (49 images, model SAW these images during training)

| Model | det_mAP | cls_mAP | Hybrid | zero-AP | Public Score | Val/Public Ratio |
|-------|---------|---------|--------|---------|-------------|-----------------|
| Copypaste (freeze=10, 7308 tiles) | 0.643 | 0.859 | 0.708 | 81 | TBD | TBD |
| Freeze=10 (1827 tiles) | 0.643 | 0.859 | 0.707 | 81 | 0.5004 | 0.71 |
| Unfreeze lr=1e-4 (1827 tiles) | 0.587 | 0.757 | 0.638 | 96 | **0.5160** | 0.81 |

### Key Observations
1. Overfit val is UNRELIABLE predictor of public score
   - Copypaste/Freeze=10 same val (0.708) but Freeze=10 got 0.5004 public
   - Unfreeze worst val (0.638) but BEST public (0.5160)
   - Val/Public ratio varies: 0.71 to 0.81 (unstable)

2. 81-96 categories with AP=0 across all models (23-27%)
   - These are categories with ≤5 training annotations
   - 84 categories have ≤5 annotations in full dataset

3. Copy-paste augmentation improves detection (+0.056 det_mAP) but unclear if it helps generalization

4. Unfreeze has WORSE val but BETTER generalization — suggests unfreezing backbone helps domain adaptation

### Training Status
- Best combo (unfreeze + copypaste + dropout + label_smooth): epoch 40/120
- Honest val (unfreeze on 199 train images): epoch 32/100, val mAP50=0.577
- Balanced (image_weights + fl_gamma): script ready, waiting for GPU

### Honest Val Preliminary Result
- Epoch 32: val mAP50 = 0.577 on truly held-out 49 images
- This is closer to public score (0.516) than overfit val (0.833)
- Confirms honest val is a better predictor

## 2026-03-20 — Day 1 Submissions

| # | Model | Public Score | Timing | Notes |
|---|-------|-------------|--------|-------|
| 1 | YOLOv8s nc=1 + ViT-B/14 + SAHI | 0.3876 | 345s | First approach |
| 2 | Same (bigger ZIP) | timeout | — | — |
| 3 | YOLOv8m det-only | 0.2787 | 59s | Overfits more |
| 4 | YOLOv8n + ViT-B/14 + SAHI | timeout | — | Too slow |
| 5 | YOLOv8n + ViT-B/14 NO SAHI | 0.0835 | 290s | SAHI mandatory |
| 6 | YOLOv8s nc=1 + ViT-S/14 + SAHI | 0.3381 | 258s | Smaller classifier |

## 2026-03-21 — Day 2 Submissions

| # | Model | Public Score | Timing | Notes |
|---|-------|-------------|--------|-------|
| 7 | nc=356 unfreeze lr=1e-4 | **0.5160** | 62s | ★ Selected for final |
| 8 | nc=356 freeze=10 | 0.5004 | 62s | — |
