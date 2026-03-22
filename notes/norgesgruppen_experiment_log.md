# NorgesGruppen Experiment Log

All experiments tracked with exact parameters, results, and conclusions.

## Public Submissions (confirmed scores)

| # | Date | Model | SAHI | Classifier | CONF | OVERLAP | WBF_IoU | Public | Time | ZIP MB |
|---|------|-------|------|-----------|------|---------|---------|--------|------|--------|
| 1 | 03-20 05:44 | YOLOv8s nc=1 | 1280/0.20 | DINOv2 ViT-B/14 (335MB) | 0.02 | 0.20 | 0.4 | **0.3876** | 345s | 344.9 |
| 2 | 03-20 05:30 | Same | Same | Same | Same | Same | Same | timeout | — | 374.5 |
| 3 | 03-20 11:35 | YOLOv8m nc=1 | 1280/0.15 | None (det-only) | 0.05 | 0.15 | 0.55 | 0.2787 | 59s | 49.7 |
| 4 | 03-20 12:16 | YOLOv8n nc=1 | 1280/? | DINOv2 ViT-B/14 reg4 | ? | ? | ? | timeout | — | 347.2 |
| 5 | 03-20 12:44 | YOLOv8n nc=1 | NO SAHI | DINOv2 ViT-B/14 reg4 | 0.05 | — | — | 0.0835 | 290s | 347.2 |
| 6 | 03-20 14:48 | YOLOv8s nc=1 | 1280/0.15 | DINOv2 ViT-S/14 reg4 | 0.02 | 0.15 | 0.5 | 0.3381 | 258s | 127.8 |
| 7 | 03-21 01:18 | YOLOv8s nc=356 unfreeze | 1280/0.25 | Built-in (nc=356) | 0.05 | 0.25 | 0.55 | **0.5160** | 62s | 43.7 |
| 8 | 03-21 01:21 | YOLOv8s nc=356 freeze=10 | 1280/0.25 | Built-in (nc=356) | 0.05 | 0.25 | 0.55 | 0.5004 | 62s | 43.7 |

## Local Val Evaluations (OVERFIT — model saw val images during training)

| Experiment | Model | CONF | OVERLAP | WBF_IoU | det_mAP | cls_mAP | hybrid | time | Notes |
|-----------|-------|------|---------|---------|---------|---------|--------|------|-------|
| mc356_freeze10_ov25_c05 | freeze=10 | 0.05 | 0.25 | 0.55 | 0.583 | 0.744 | 0.631 | 55s | Grid search best |
| mc356_freeze10_ov20_c02 | freeze=10 | 0.02 | 0.20 | 0.55 | 0.583 | 0.735 | 0.622 | 45s | |
| mc356_freeze10_ov40_c05 | freeze=10 | 0.05 | 0.40 | 0.55 | 0.558 | 0.744 | 0.614 | 79s | Worse — too many tiles |
| mc356_unfreeze_ov25_c05 | unfreeze lr=1e-4 | 0.05 | 0.25 | 0.55 | 0.587 | 0.757 | **0.638** | 49s | Public: 0.5160 |
| mc356_copypaste_ov25_c05 | copypaste freeze=10 | 0.05 | 0.25 | 0.55 | 0.643 | 0.859 | **0.708** | 50s | Best val hybrid |
| mc356_copypaste_ov25_c001 | copypaste freeze=10 | 0.001 | 0.25 | 0.55 | 0.003 | 0.000 | 0.002 | >5min | BROKEN — 1.5M preds, WBF fails |
| vits14_ov15_c02 | nc=1 + ViT-S/14 | 0.02 | 0.15 | 0.5 | 0.498 | 0.145 | 0.392 | 167s | Public: 0.3381 |
| swa_fixed | averaged weights | 0.05 | 0.25 | 0.55 | 0.002 | 0.000 | 0.002 | >5min | BROKEN — BN stats |

## Training Runs

| Run | Dataset | Tiles | Architecture | freeze | lr0 | dropout | label_smooth | Epochs | Best val mAP50 | ONNX MB |
|-----|---------|-------|-------------|--------|-----|---------|-------------|--------|---------------|---------|
| yolov8s_multiclass_357 | multiclass_tiled | 1827 | YOLOv8s nc=356 | 10 | 0.01 | 0 | 0 | 200 | 0.809 | 44 |
| yolov8s_unfreeze | multiclass_tiled | 1827 | YOLOv8s nc=356 | 0 | 1e-4 | 0 | 0 | 150 | **0.833** | 44 |
| yolov8s_copypaste | copypaste | 7308 | YOLOv8s nc=356 | 10 | 0.01 | 0 | 0 | 100 | 0.989* | 44 |
| yolov8s_best_combo | copypaste | 7308 | YOLOv8s nc=356 | 0 | 1e-4 | 0.3 | 0.1 | 120 (running) | ~0.96 | — |
| yolov8s_tiled_freeze10 | single_cls_tiled | 1827 | YOLOv8s nc=1 | 10 | 0.01 | 0 | 0 | killed ep1 | — | — |

*copypaste val 0.989 heavily overfit (synthetic tiles from same images)

## Key Findings (proven by experiments)

1. **SAHI mandatory** — 0.39 → 0.08 without it (4.6x drop)
2. **nc=356 >> DINOv2** — 0.516 vs 0.388 on public (+33%)
3. **Unfreeze > freeze=10** — 0.516 vs 0.500 on public (+3%)
4. **Copy-paste augmentation** — val 0.708 vs 0.638 (+11% val)
5. **OVERLAP=0.25 optimal** — grid search confirmed
6. **CONF=0.001 BROKEN** — too many detections, WBF fails
7. **SWA BROKEN** — BatchNorm statistics destroyed
8. **YOLOv8s best size** — s > n > m on this dataset

## Failed Approaches

1. SWA (weight averaging) — BN breaks, 0 useful detections
2. YOLOv8m — worse generalization than YOLOv8s
3. YOLOv8n — too many false positives, causes timeout
4. Removing SAHI — catastrophic for small products
5. CONF=0.001 — too many detections for WBF to handle
6. DINOv2 ViT-B/14 — too slow for SAHI-generated crops (345s)

## Next Experiments to Try

- [ ] CONF=0.01 with copypaste model
- [ ] Ensemble: unfreeze + copypaste at inference (2 ONNX + WBF)
- [ ] image_weights=True + fl_gamma=1.5 in retrain
- [ ] SAM-based copy-paste (proper alpha blending)
- [ ] Multi-scale training (640px crops matching SAHI)
- [ ] TTA horizontal flip at tile level
