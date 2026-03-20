# CV Retrain Results — 2026-03-20

## Previous Score: 38.76%

## Changes Made

### 1. YOLOv8m Detector (was YOLOv8s)
- Model: YOLOv8m (26M params, up from 11M in YOLOv8s)
- Training: 100 epochs, single_cls=True, imgsz=1280, copy_paste=0.3, no mixup
- **mAP50: 99.3%** (was 99.0% with YOLOv8s)
- mAP50-95: 84.4%
- ONNX FP16 export: 50 MB (was 44 MB)
- A100 VM: /root/cv/runs/yolov8m_train/weights/best.onnx

| Metric   | YOLOv8s | YOLOv8m | Delta |
|----------|---------|---------|-------|
| mAP50    | ~0.990  | 0.993   | +0.003|
| mAP50-95 | unknown | 0.843   | -     |
| ONNX size| 44 MB   | 50 MB   | +6 MB |

### 2. DINOv2 with Registers (was standard DINOv2)
- Model: `vit_base_patch14_reg4_dinov2` (timm 0.9.12)
- Registers reduce artifact tokens → cleaner embeddings for retail products
- Same architecture: 86M params, 518x518 input, 768-dim output
- Weights: 330.3 MB safetensors

### 3. Multi-Angle Reference Embeddings (was single averaged embedding)
- Previous: 356 embeddings (1 per category, averaged from all angles)
- New: **1,612 embeddings** (all individual angle images preserved)
  - 1,577 real embeddings from 321 products (avg ~4.9 angles per product)
  - 35 zero-vector placeholders for unmapped categories
- Category IDs embedded in first column of ref_embeddings.npy (769 cols)
  - Avoids needing a 4th weight file (3 file limit)
- All IDs in valid range 0-355 (mapped via metadata.json + annotations.json)
- No CUSTOM IDs used (unlike previous agent's approach)

### 4. Softmax Calibration (was raw cosine similarity)
- Previous: final_score = det_score * cosine_similarity
- New: final_score = det_score * softmax(max_cosine_per_category / temperature)
- Temperature: 0.07
- Per-category max similarity across all angles → softmax probabilities
- Better calibrated scores for classification mAP

### 5. CONF_THRESH: 0.01 (was 0.02)
- Lower threshold for better recall
- Not too low (0.001 caused 540s timing with 25K+ predictions)

### 6. TTA Disabled
- Removed horizontal flip TTA (was adding ~80s)
- Without TTA: 265s; with TTA: ~345s (over limit)

### 7. FP16 ONNX Auto-Detection
- run.py auto-detects if ONNX model expects FP16 input
- Feeds FP16 tensors to match model precision

## L4 VM Test Results (from clean ZIP extraction)
| Metric | Value |
|--------|-------|
| Timing | **265s** (300s limit, 35s headroom) |
| Predictions | 10,940 |
| Images processed | 50/50 |
| Unique categories | 266 |
| Category ID range | 1-353 (valid) |
| Format | Valid JSON |

## ZIP: `norgesgruppen_final.zip`
- Location: `F:\Workfolder\NM i AI main\norgesgruppen_final.zip`
- Total uncompressed: **384.7 MB** (limit 420 MB)
- Weight files: **3** (limit 3)
- Python files: **1** (limit 10)

### Structure
```
norgesgruppen_final.zip
├── run.py                              (17 KB)
└── weights/
    ├── yolov8m_single.onnx             (50 MB)  — YOLOv8m FP16
    ├── dinov2_vitb14.safetensors       (330 MB) — DINOv2 reg4
    └── ref_embeddings.npy              (4.7 MB) — 1612×769 (cat_ids + embeds)
```

## Files on A100 (/root/cv/)
- Training run: /root/cv/runs/yolov8m_train/
- Embedding script: /root/cv/gen_embeddings_v2.py
- New weights: /root/cv/weights_v2/

## Status: READY FOR SUBMISSION (pending approval)
