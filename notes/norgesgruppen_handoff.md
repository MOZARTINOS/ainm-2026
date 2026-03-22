# NorgesGruppen — Handoff для нового агента

## Задача
Собрать финальный ZIP для submission на NM i AI 2026 NorgesGruppen Object Detection challenge.

## Scoring
```
score = 0.7 × detection_mAP@0.5 + 0.3 × classification_mAP@0.5
```
Нет бонуса за скорость. Лимит 300 секунд на L4 GPU.

## Submission Limits
- 3 submissions/day (reset midnight UTC)
- Max 420MB uncompressed
- Max 3 weight files (.onnx, .safetensors, .npy)
- Max 10 .py files
- run.py MUST be at ZIP root

## Sandbox Environment
- Python 3.11, PyTorch 2.6.0+cu124, NVIDIA L4 24GB VRAM
- Pre-installed: ultralytics 8.1.0, onnxruntime-gpu 1.20.0, timm 0.9.12, safetensors 0.4.2, ensemble-boxes 1.0.9
- BLOCKED: os, sys, subprocess, pickle, requests, multiprocessing, threading, yaml, gc, getattr()
- Use pathlib instead of os

## run.py Contract
```bash
python run.py --input /data/images --output /output/predictions.json
```
Output: JSON array with {image_id, category_id, bbox:[x,y,w,h], score}

## Что уже сделано

### Detector (YOLOv8s)
- Trained 100 epochs, single-class, imgsz=1280, copy_paste=0.3
- mAP@0.5 = 99.0% на training set
- ONNX exported: weights/yolov8s_single.onnx (44MB)
- Location on A100 VM: /root/cv/runs/train4/weights/best.onnx

### Classification (DINOv2 ViT-base)
- timm model: vit_base_patch14_dinov2.lvd142m (input 518x518)
- Weights: weights/dinov2_vitb14.safetensors (331MB)
- Reference embeddings from multi-angle product photos (321/356 clean, 35 fallback)
- weights/ref_embeddings.npy (356 × 768)
- ref_category_ids = np.arange(356) — sequential, hardcoded in code

### run.py Optimizations Applied
- TILE_SIZE=1280, OVERLAP=0.20, CONF_THRESH=0.02
- TTA: original + horizontal flip, merge with WBF (for multi-tile images)
- FP16 DINOv2, BATCH_SIZE=256
- MIN_BOX_AREA=50
- Skip-tiling for images ≤1280px
- L4 test: 282s for 50 images

## Files
- run.py: F:/Workfolder/NM i AI main/repo/tracks/cv/run.py
- Weights: F:/Workfolder/NM i AI main/repo/tracks/cv/weights/
  - yolov8s_single.onnx (44MB) — MUST be named exactly this
  - dinov2_vitb14.safetensors (331MB)
  - ref_embeddings.npy (1MB)
- Training data: F:/Workfolder/NM i AI main/submission data/
- Product images: F:/Workfolder/NM i AI main/submission data/NM_NGD_product_images/

## GCP VMs
- L4 (test): root@REDACTED_IP (via Hetzner REDACTED_IP)
- A100 (training): root@REDACTED_IP (via Hetzner)
- SSH: ssh -i ~/.ssh/hetzner_key root@REDACTED_IP "ssh -i /root/.ssh/gcp_key root@IP 'COMMAND'"

## Что нужно сделать

### 1. Финальная проверка run.py
- Убедиться нет blocked imports
- Проверить weight paths (weights_dir = Path(__file__).parent / "weights")
- ref_category_ids: если файл не найден → np.arange(ref_embeds.shape[0])

### 2. Собрать ZIP
```
submission.zip (at root, NOT in subfolder!)
├── run.py
└── weights/
    ├── yolov8s_single.onnx      (~44 MB)
    ├── dinov2_vitb14.safetensors (~331 MB)
    └── ref_embeddings.npy        (~1 MB)
```
Total: ~376 MB < 420 MB limit. Exactly 3 weight files.

### 3. Тест на L4 VM
- Upload ZIP contents to L4
- Create /data/images with 50 test images
- Run: python run.py --input /data/images --output /output/predictions.json
- Verify: timing < 300s, valid JSON output, all images processed
- If timing > 290s — reduce OVERLAP to 0.15 or remove TTA

### 4. Потенциальные улучшения (если время есть)
- Больше overlap (0.25) если timing позволяет
- Multi-scale inference (1280 + 640)
- Conf threshold tuning

## ПРАВИЛА
- НЕ сабмитить на app.ainm.no — только подготовить ZIP
- НЕ менять training/weights — только run.py и ZIP сборка
- Результаты писать в notes/norgesgruppen_final.md
