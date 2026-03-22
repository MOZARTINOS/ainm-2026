# NorgesGruppen Final Submission — 2026-03-20

## ZIP: `norgesgruppen_final.zip`
- Location: `F:\Workfolder\NM i AI main\norgesgruppen_final.zip`
- Total uncompressed: **374.5 MB** (limit 420 MB)
- Weight files: 3 (limit 3)
- Python files: 1 (limit 10)

### ZIP Structure
```
norgesgruppen_final.zip
├── run.py                              (15.7 KB)
└── weights/
    ├── yolov8s_single.onnx             (43.1 MB)
    ├── dinov2_vitb14.safetensors       (330.3 MB)
    └── ref_embeddings.npy              (1.0 MB)
```

## Import Check
All imports are sandbox-safe. No blocked imports (os, sys, subprocess, pickle, requests, multiprocessing, threading, yaml, gc, getattr).

## L4 VM Test Results
- **VM**: root@REDACTED_IP (NVIDIA L4, 23 GB VRAM)
- **Images processed**: 50
- **Total predictions**: 11,189
- **Unique image IDs**: 50 (all images processed)
- **Timing**: 278s (4m38s) — **under 300s limit**
- **Output format**: Valid JSON array with {image_id, category_id, bbox:[x,y,w,h], score}

### Sample prediction
```json
{"image_id": 1, "category_id": 141, "bbox": [272.0, 486.92, 105.96, 186.62], "score": 0.714699}
```

## Pipeline Configuration
| Parameter | Value |
|---|---|
| TILE_SIZE | 1280 |
| OVERLAP | 0.20 |
| CONF_THRESH | 0.02 |
| WBF_IOU_THRESH | 0.4 |
| TTA | horizontal flip (large images only) |
| DINOv2 precision | FP16 |
| BATCH_SIZE | 256 |
| MIN_BOX_AREA | 50 |

## Timing Budget
- 278s / 300s = 93% utilization
- 22s headroom — sufficient margin
- No optimization needed (overlap/TTA reduction not required)

## Status: READY FOR SUBMISSION
ZIP is built and tested. Do NOT submit without explicit permission.
