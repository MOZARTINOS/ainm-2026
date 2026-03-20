# NorgesGruppen Day 1 Postmortem — 2026-03-20

## Submissions (5 of 6 used)

| # | Model | Config | Score | Time | Result |
|---|-------|--------|-------|------|--------|
| 1 | YOLOv8s ONNX + DINOv2 std | SAHI 20%, 356 avg embeds | **0.3876** | 345s | **BEST** |
| 2 | YOLOv8s ONNX + DINOv2 std | SAHI 20%, 356 avg embeds | timeout | — | Bigger ZIP? |
| 3 | YOLOv8m ONNX det-only | SAHI 15%, no DINOv2 | 0.2787 | 59s | Worse detector |
| 4 | YOLOv8n ONNX + DINOv2 reg4 | SAHI, 1612 multi-angle | timeout | — | Too many crops |
| 5 | YOLOv8n ONNX + DINOv2 reg4 | NO SAHI, cap 200 | 0.0835 | 290s | SAHI required |

## Key Learnings

### SAHI is CRITICAL
- Without SAHI: 0.0835 (catastrophic)
- With SAHI: 0.3876 (4.6x better)
- Images are large (2000x3000+), products are small
- Single-pass at 1280px misses most products

### YOLOv8s > YOLOv8n > YOLOv8m on test data
- All overfitted to 248 training images
- Bigger model (m) = more overfitting = worse generalization
- Smaller model (n) = more false positives = timeout from DINOv2
- YOLOv8s = best balance for this dataset

### DINOv2 classification adds ~0.10 to score
- Detection-only YOLOv8m: 0.2787
- With classification (old pipeline): 0.3876
- Classification is contributing ~0.10+ (significant)

### Timing bottleneck = DINOv2 × crop count
- SAHI generates many tiles → many detections → many DINOv2 crops
- DINOv2 ViT-base at 518x518 = ~2.6s per 200 crops on L4
- Sandbox L4 is ~1.3x slower than our test L4

## Plan for Day 2 (6 submissions)

### Approach: Optimize the working pipeline (YOLOv8s + SAHI + DINOv2)
1. Use YOLOv8s ONNX (the one that scored 0.3876)
2. Reduce SAHI overlap: 0.20 → 0.10 (fewer tiles, faster)
3. Raise CONF_THRESH: 0.02 → 0.05 (fewer crops for DINOv2)
4. Cap crops at 200 per image
5. Use DINOv2 reg4 + averaged 356 embeddings (not 1612 multi-angle)
6. Target timing: < 300s

### What NOT to do
- Don't change the base detector model
- Don't remove SAHI
- Don't use multi-angle embeddings (adds overhead, unclear benefit)
- Don't reduce CROP_SIZE (degrades classification quality)

## Files
- Best submission pipeline: the FIRST submission (344.9 MB, scored 0.3876)
- Selected for final: 0.3876 submission
- 1 submission remaining today (save for emergency)
