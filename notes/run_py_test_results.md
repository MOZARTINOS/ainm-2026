# run.py Inference Pipeline Test Results

**Date:** 2026-03-20
**VM:** GCP A100-SXM4-40GB (root@34.10.132.71 via Hetzner relay)
**Python:** 3.12.3, PyTorch 2.7.1+cu128, onnxruntime-gpu 1.24.4, timm 0.9.12

---

## Sandbox Import Check: PASS

No blocked imports found. The script uses only:
- `argparse`, `json`, `math`, `pathlib.Path` (stdlib)
- `cv2`, `numpy`, `onnxruntime`, `timm`, `torch`, `ensemble_boxes`, `safetensors` (third-party)

None of `os`, `sys`, `subprocess`, `pickle`, `requests`, `multiprocessing` are imported.

---

## Bugs Found and Fixed

### 1. TILE_SIZE mismatch (CRITICAL)
- **Problem:** `TILE_SIZE = 640` but the ONNX model expects `[1, 3, 1280, 1280]` input.
- **Error:** `INVALID_ARGUMENT: Got invalid dimensions for input: images ... Got: 640 Expected: 1280`
- **Fix:** Changed `TILE_SIZE = 640` to `TILE_SIZE = 1280`

### 2. CROP_SIZE mismatch (CRITICAL)
- **Problem:** `CROP_SIZE = 224` but `vit_base_patch14_dinov2.lvd142m` in timm 0.9.12 expects 518x518.
- **Error:** `AssertionError: Input height (224) doesn't match model (518).`
- **Fix:** Changed `CROP_SIZE = 224` to `CROP_SIZE = 518`

### 3. image_id parsing fragile (MINOR)
- **Problem:** `int(img_path.stem)` crashes on filenames like `img_00001.jpg`.
- **Fix:** Extract digits from stem: `digits = "".join(c for c in stem if c.isdigit())`

### 4. WBF coordinate overflow (WARNING)
- **Problem:** Detections near image edges produced normalized coords > 1.0, causing WBF warnings ("X2 > 1", "X2 < X1", "Zero area box skipped").
- **Fix:** Clip full-image coords to `[0, img_w]` / `[0, img_h]` before normalization, skip degenerate boxes.

---

## Test Run Results

- **Test set:** 5 images from training set (2000x1500 to 4032x3024)
- **Execution time:** 73.5 seconds (5 images)
- **Exit code:** 0 (clean, no warnings after fixes)
- **Output:** 2379 predictions across 5 images, 200 unique categories
- **Format:** Correct -- `{"image_id": int, "category_id": int, "bbox": [x, y, w, h], "score": float}`
- **Score range:** 0.000198 -- 0.817939

### Sample output:
```json
{"image_id": 1, "category_id": 141, "bbox": [272.38, 486.87, 104.57, 187.22], "score": 0.712601}
```

---

## Timing Analysis: CONCERN

| Metric | Value |
|--------|-------|
| 5 images | 73.5s |
| Per image (avg) | 14.7s |
| Projected 50 images | ~735s |
| **Budget** | **300s** |

**The pipeline is ~2.5x too slow for the 300s budget** if the test set has ~50 images.

### Bottleneck breakdown (estimated):
- SAHI tiling: Large images (3000-4000px) generate many 1280px tiles with 30% overlap (~6-12 tiles/image)
- DINOv2 at 518x518: Each crop resized to 518x518 is expensive; ~470+ crops per image
- WBF: Negligible

### Optimization options:
1. **Reduce overlap** from 0.30 to 0.15 (fewer tiles, ~40% speedup)
2. **Increase CONF_THRESH** from 0.001 to 0.05 (fewer crops to classify)
3. **ONNX TensorRT EP**: The VM has TensorrtExecutionProvider available -- use it for detector
4. **Half precision**: Run DINOv2 in fp16 (`model.half()`)
5. **Reduce CROP_SIZE** to 224 if a model checkpoint fine-tuned at 224 is available
6. **Skip SAHI** for small images: If image fits in 1280, run single pass

---

## Weight Files Required

All must be in `weights/` subdirectory relative to `run.py`:

| File | Size | Description |
|------|------|-------------|
| `yolov8s_single.onnx` | 44 MB | Single-class detector (input 1280x1280) |
| `dinov2_vitb14.safetensors` | 331 MB | DINOv2 ViT-B/14 classification backbone |
| `ref_embeddings.npy` | 1.1 MB | Reference embeddings (327, 768) |
| `ref_category_ids.npy` | 3.0 KB | Reference category IDs (327,) |

---

## Dependencies (pip packages)

```
opencv-python
numpy
onnxruntime-gpu
timm
torch
ensemble_boxes
safetensors
```

Note: `ensemble_boxes` requires `numba` and `llvmlite` as transitive deps.
