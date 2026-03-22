# NorgesGruppen Simulator — Version Log

## v1.0 (2026-03-20) — Basic Evaluation
**Files**: `v1/evaluate_map.py`, `v1/create_groupkfold_split.py`

**Components**:
- GroupKFold split: 199 train / 49 val by original image_id (no tile leakage)
- pycocotools COCOeval for detection_mAP and classification_mAP
- Hybrid score: 0.7 × det_mAP + 0.3 × cls_mAP

**Known Issues**:
- Val is OVERFIT: models trained on ALL 248 images (incl. val) → inflated scores
- No confidence intervals — single-point estimate from 49 images
- No calibration — val scores don't predict public scores (ratio ~0.80 but unstable)
- No per-category breakdown — can't identify which classes fail
- No domain shift detection — unknown if test distribution matches train
- Hyperparameter tuning on val → overfits to val itself

**Calibration Data**:
| Model | Val hybrid | Public score | Ratio |
|-------|-----------|-------------|-------|
| Unfreeze | 0.638 | 0.5160 | 0.809 |
| Freeze=10 | 0.631 | 0.5004 | 0.793 |
| ViT-S/14 | 0.392 | 0.3381 | 0.863 |
| Copypaste | 0.708 | ??? | ??? |

**Usage**:
```bash
# On L4 VM:
python3 evaluate_map.py --gt /tmp/gkf_val_annotations.json --pred /output/predictions.json
```

---

## v2.0 (planned) — Honest Validation + Bootstrap + Calibration
**Status**: Deep Research in progress, implementation pending

**Planned improvements**:
- [ ] Train on 199 images ONLY, evaluate on held-out 49 (honest val)
- [ ] Bootstrap confidence intervals (1000 resamples)
- [ ] Calibration factor: val_score × 0.80 = predicted_public
- [ ] Per-category mAP breakdown
- [ ] Statistical significance testing (paired permutation)
- [ ] Store-section stratified validation
- [ ] Domain shift simulation (augmented val evaluation)
