"""
Build reference embeddings from NorgesGruppen product images.

For each product with multi-angle photos (main, front, back, left, right, top, bottom),
encode all angles with DINOv2 ViT-base and average into one vector per category.

For categories without product images, fall back to existing crop-based embeddings.

Output: ref_embeddings.npy (N_categories, 768) and ref_category_ids.npy (N_categories,)
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import timm
import torch
from safetensors.torch import load_file as load_safetensors

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DINO_MODEL_NAME = "vit_base_patch14_dinov2.lvd142m"
DINO_EMBED_DIM = 768
CROP_SIZE = 518
BATCH_SIZE = 64  # smaller batch — we process many angles

PRODUCT_IMAGES_DIR = Path("F:/Workfolder/NM i AI main/submission data/NM_NGD_product_images")
ANNOTATIONS_PATH = Path("F:/Workfolder/NM i AI main/submission data/NM_NGD_coco_dataset/train/annotations.json")
WEIGHTS_DIR = Path("F:/Workfolder/NM i AI main/repo/tracks/cv/weights")
METADATA_PATH = PRODUCT_IMAGES_DIR / "metadata.json"

ANGLE_NAMES = ["main", "front", "back", "left", "right", "top", "bottom"]


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------
def load_dino_model(weights_dir: Path, device: torch.device):
    """Load DINOv2 ViT-base from timm with safetensors weights."""
    model = timm.create_model(DINO_MODEL_NAME, pretrained=False, num_classes=0)
    st_path = weights_dir / "dinov2_vitb14.safetensors"
    pth_path = weights_dir / "dinov2_vitb14.pth"
    if st_path.exists():
        state_dict = load_safetensors(str(st_path))
        model.load_state_dict(state_dict, strict=False)
    elif pth_path.exists():
        state_dict = torch.load(str(pth_path), map_location="cpu", weights_only=True)
        model.load_state_dict(state_dict, strict=False)
    else:
        model = timm.create_model(DINO_MODEL_NAME, pretrained=True, num_classes=0)

    model = model.to(device).eval()
    if device.type == "cuda":
        model = model.half()
    return model


# ---------------------------------------------------------------------------
# Embedding extraction
# ---------------------------------------------------------------------------
@torch.inference_mode()
def encode_images(model, image_paths: list[Path], device: torch.device) -> np.ndarray:
    """Encode a list of images, return (N, 768) L2-normalized embeddings."""
    if len(image_paths) == 0:
        return np.empty((0, DINO_EMBED_DIM), dtype=np.float32)

    use_fp16 = device.type == "cuda"
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

    all_embeds = []
    for i in range(0, len(image_paths), BATCH_SIZE):
        batch_paths = image_paths[i : i + BATCH_SIZE]
        batch_np = []
        for p in batch_paths:
            img = cv2.imread(str(p))
            if img is None:
                # Use zero image as fallback
                img = np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8)
            c = cv2.resize(img, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_LINEAR)
            c = c[:, :, ::-1].astype(np.float32) / 255.0  # BGR -> RGB
            c = np.transpose(c, (2, 0, 1))  # CHW
            batch_np.append(c)

        batch_tensor = np.stack(batch_np)
        batch_tensor = (batch_tensor - mean) / std
        batch_tensor = torch.from_numpy(batch_tensor).to(device)
        if use_fp16:
            batch_tensor = batch_tensor.half()

        embeds = model(batch_tensor)
        embeds = embeds.float().cpu().numpy()
        norms = np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-8
        embeds = embeds / norms
        all_embeds.append(embeds)

    return np.concatenate(all_embeds, axis=0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    # Load annotations to get category name -> id mapping
    with open(str(ANNOTATIONS_PATH), encoding="utf-8") as f:
        ann_data = json.load(f)
    cat_name_to_id = {c["name"]: c["id"] for c in ann_data["categories"]}
    num_categories = len(ann_data["categories"])
    print(f"Total categories in annotations: {num_categories}")

    # Load product metadata for barcode -> product_name mapping
    with open(str(METADATA_PATH), encoding="utf-8") as f:
        meta = json.load(f)
    products = meta["products"]

    # Build barcode -> category_id mapping via product_name
    barcode_to_catid = {}
    for p in products:
        if not p["has_images"]:
            continue
        name = p["product_name"]
        barcode = p["product_code"]
        if name in cat_name_to_id:
            barcode_to_catid[barcode] = cat_name_to_id[name]

    print(f"Products with images mapped to categories: {len(barcode_to_catid)}")

    # Load existing embeddings as fallback for categories without product images
    old_embeds = np.load(str(WEIGHTS_DIR / "ref_embeddings.npy"))
    old_cat_ids = np.load(str(WEIGHTS_DIR / "ref_category_ids.npy"))
    old_embed_map = {}
    for idx in range(len(old_cat_ids)):
        old_embed_map[int(old_cat_ids[idx])] = old_embeds[idx]

    # Load DINOv2 model
    model = load_dino_model(WEIGHTS_DIR, device)

    # Process each product folder
    new_embed_map = {}  # category_id -> (768,) embedding
    product_folders = sorted(PRODUCT_IMAGES_DIR.iterdir())

    for folder in product_folders:
        if not folder.is_dir():
            continue
        barcode = folder.name
        if barcode not in barcode_to_catid:
            continue
        cat_id = barcode_to_catid[barcode]

        # Collect all angle images
        angle_paths = []
        for angle in ANGLE_NAMES:
            img_path = folder / f"{angle}.jpg"
            if img_path.exists():
                angle_paths.append(img_path)

        if len(angle_paths) == 0:
            continue

        # Encode all angles
        angle_embeds = encode_images(model, angle_paths, device)

        # Average all angle embeddings
        avg_embed = angle_embeds.mean(axis=0)
        # Re-normalize
        avg_embed = avg_embed / (np.linalg.norm(avg_embed) + 1e-8)

        if cat_id in new_embed_map:
            # Multiple barcodes map to same category — average
            existing = new_embed_map[cat_id]
            combined = (existing + avg_embed) / 2.0
            new_embed_map[cat_id] = combined / (np.linalg.norm(combined) + 1e-8)
        else:
            new_embed_map[cat_id] = avg_embed

    print(f"Categories with new product-image embeddings: {len(new_embed_map)}")

    # Build final embedding matrix: use new embeddings where available, old as fallback
    all_cat_ids = sorted(cat_name_to_id.values())
    final_embeds = []
    final_cat_ids = []
    new_count = 0
    old_count = 0

    for cat_id in all_cat_ids:
        if cat_id in new_embed_map:
            final_embeds.append(new_embed_map[cat_id])
            new_count += 1
        elif cat_id in old_embed_map:
            final_embeds.append(old_embed_map[cat_id])
            old_count += 1
        else:
            # No embedding at all — use zeros (should not happen)
            print(f"WARNING: No embedding for category {cat_id}")
            final_embeds.append(np.zeros(DINO_EMBED_DIM, dtype=np.float32))
        final_cat_ids.append(cat_id)

    final_embeds = np.stack(final_embeds).astype(np.float32)
    final_cat_ids = np.array(final_cat_ids, dtype=np.int64)

    print(f"Final: {new_count} new + {old_count} old = {len(final_cat_ids)} total")
    print(f"Embeddings shape: {final_embeds.shape}")

    # Save
    out_embeds_path = WEIGHTS_DIR / "ref_embeddings.npy"
    out_catids_path = WEIGHTS_DIR / "ref_category_ids.npy"
    out_data_path = WEIGHTS_DIR / "ref_data.npz"

    # Backup old files
    backup_dir = WEIGHTS_DIR / "backup_old_refs"
    backup_dir.mkdir(exist_ok=True)
    for fname in ["ref_embeddings.npy", "ref_category_ids.npy", "ref_data.npz"]:
        src = WEIGHTS_DIR / fname
        if src.exists():
            import shutil
            shutil.copy2(str(src), str(backup_dir / fname))

    np.save(str(out_embeds_path), final_embeds)
    np.save(str(out_catids_path), final_cat_ids)
    np.savez(str(out_data_path), embeddings=final_embeds, category_ids=final_cat_ids)

    print(f"Saved: {out_embeds_path}")
    print(f"Saved: {out_catids_path}")
    print(f"Saved: {out_data_path}")
    print("Done!")


if __name__ == "__main__":
    main()
