"""Generate DINOv2 ViT-S/14 reg4 weights + averaged reference embeddings."""
import json
import numpy as np
import torch
import timm
import cv2
from pathlib import Path
from safetensors.torch import save_file as save_safetensors

DINO_MODEL = "vit_small_patch14_reg4_dinov2"
CROP_SIZE = 518
EMBED_DIM = 384
BATCH_SIZE = 64
ANGLE_NAMES = ["main", "front", "back", "left", "right", "top", "bottom"]

PRODUCT_DIR = Path("/root/cv")
METADATA_PATH = Path("/root/cv/metadata.json")
ANNOTATIONS_PATH = Path("/root/cv/train/annotations.json")
OUTPUT_DIR = Path("/root/cv/weights_vits14")

SKIP_DIRS = {"yolo_data", "runs", "weights", "weights_v2", "weights_vits14", "train", "__pycache__"}


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Build barcode -> category_id mapping
    with open(str(ANNOTATIONS_PATH), encoding="utf-8") as f:
        ann_data = json.load(f)
    cat_name_to_id = {}
    for c in ann_data["categories"]:
        cat_name_to_id[c["name"]] = c["id"]
    num_categories = len(ann_data["categories"])
    print("Total categories:", num_categories)

    with open(str(METADATA_PATH), encoding="utf-8") as f:
        meta = json.load(f)

    barcode_to_catid = {}
    for p in meta["products"]:
        if not p.get("has_images", False):
            continue
        name = p["product_name"]
        barcode = p["product_code"]
        if name in cat_name_to_id:
            barcode_to_catid[barcode] = cat_name_to_id[name]
    print("Mapped barcodes:", len(barcode_to_catid))

    # Load model
    print("Loading", DINO_MODEL, "...")
    model = timm.create_model(DINO_MODEL, pretrained=True, num_classes=0)
    model = model.to(device).eval().half()

    # Save model weights as FP32 safetensors
    state_dict = {}
    for k, v in model.state_dict().items():
        state_dict[k] = v.float()
    st_path = OUTPUT_DIR / "dinov2_vits14.safetensors"
    save_safetensors(state_dict, str(st_path))
    sz = st_path.stat().st_size / 1024 / 1024
    print("Saved model weights:", st_path, "%.1f MB" % sz)

    # ImageNet normalization
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)

    # Process product folders -> averaged prototypes
    product_dirs = sorted([
        d for d in PRODUCT_DIR.iterdir()
        if d.is_dir() and d.name not in SKIP_DIRS and d.name[0].isdigit()
    ])

    cat_embeddings = {}  # cat_id -> averaged embedding

    for idx, pdir in enumerate(product_dirs):
        barcode = pdir.name
        if barcode not in barcode_to_catid:
            continue
        cat_id = barcode_to_catid[barcode]

        # Collect angle images
        angle_paths = []
        for angle in ANGLE_NAMES:
            img_path = pdir / ("%s.jpg" % angle)
            if img_path.exists():
                angle_paths.append(img_path)
        all_imgs = sorted([f for f in pdir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")])
        for img in all_imgs:
            if img not in angle_paths:
                angle_paths.append(img)
        if not angle_paths:
            continue

        # Encode all angles
        crops = []
        for img_path in angle_paths:
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            c = cv2.resize(img, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_LINEAR)
            c = c[:, :, ::-1].astype(np.float32) / 255.0
            c = np.transpose(c, (2, 0, 1))
            crops.append(c)
        if not crops:
            continue

        batch = np.stack(crops)
        batch = (batch - mean) / std
        batch_tensor = torch.from_numpy(batch).to(device).half()

        with torch.inference_mode():
            embeds = model(batch_tensor).float().cpu().numpy()

        norms = np.linalg.norm(embeds, axis=1, keepdims=True) + 1e-8
        embeds = embeds / norms

        # Average all angles for this category
        avg_embed = embeds.mean(axis=0)
        avg_embed = avg_embed / (np.linalg.norm(avg_embed) + 1e-8)

        if cat_id in cat_embeddings:
            existing = cat_embeddings[cat_id]
            combined = (existing + avg_embed) / 2.0
            cat_embeddings[cat_id] = combined / (np.linalg.norm(combined) + 1e-8)
        else:
            cat_embeddings[cat_id] = avg_embed

        if (idx + 1) % 50 == 0:
            print("  Processed %d/%d, %d categories" % (idx + 1, len(product_dirs), len(cat_embeddings)))

    print("Mapped %d categories from product images" % len(cat_embeddings))

    # Build final embedding matrix (356 prototypes)
    all_cat_ids = sorted(cat_name_to_id.values())
    final_embeds = []
    final_cat_ids = []

    for cat_id in all_cat_ids:
        if cat_id in cat_embeddings:
            final_embeds.append(cat_embeddings[cat_id])
        else:
            final_embeds.append(np.zeros(EMBED_DIM, dtype=np.float32))
        final_cat_ids.append(cat_id)

    final_embeds = np.stack(final_embeds).astype(np.float32)
    final_cat_ids = np.array(final_cat_ids, dtype=np.float32)

    # Combined format: first column = category_id, rest = embedding
    combined = np.column_stack([final_cat_ids, final_embeds])
    np.save(str(OUTPUT_DIR / "ref_embeddings.npy"), combined)

    mapped = len(cat_embeddings)
    zeros = num_categories - mapped
    print("Final shape:", combined.shape, "(%d real + %d zeros)" % (mapped, zeros))
    for f in OUTPUT_DIR.iterdir():
        sz = f.stat().st_size / 1024 / 1024
        print("  %s: %.1f MB" % (f.name, sz))


if __name__ == "__main__":
    main()
