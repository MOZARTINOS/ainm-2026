"""
Build DINOv2 reference embeddings for kNN classification.
Run locally or on GCP — NOT in the competition sandbox.

Usage:
    python build_embeddings.py \
        --annotations /path/to/train_annotations.json \
        --images /path/to/train_images/ \
        --output weights/

Expects COCO-format annotations with category_id per annotation.
Builds one embedding per category by averaging all crop embeddings for that category.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import timm
import torch


DINO_MODEL_NAME = "vit_base_patch14_dinov2.lvd142m"
CROP_SIZE = 224
BATCH_SIZE = 64


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=str, required=True,
                        help="COCO annotations JSON")
    parser.add_argument("--images", type=str, required=True,
                        help="Training images directory")
    parser.add_argument("--output", type=str, default="weights",
                        help="Output directory for .npy files")
    parser.add_argument("--save-model", action="store_true",
                        help="Also save DINOv2 weights as safetensors")
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    images_dir = Path(args.images)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load annotations
    with open(args.annotations) as f:
        coco = json.load(f)

    # Build image id → filename map
    id_to_file = {img["id"]: img["file_name"] for img in coco["images"]}

    # Group annotations by category
    cat_to_anns: dict[int, list] = {}
    for ann in coco["annotations"]:
        cat_id = ann["category_id"]
        cat_to_anns.setdefault(cat_id, []).append(ann)

    # Load DINOv2
    print(f"Loading {DINO_MODEL_NAME}...")
    model = timm.create_model(DINO_MODEL_NAME, pretrained=True, num_classes=0)
    model = model.to(device).eval()

    # Optionally save weights as safetensors for sandbox use
    if args.save_model:
        from safetensors.torch import save_file as save_safetensors
        st_path = output_dir / "dinov2_vitb14.safetensors"
        save_safetensors(model.state_dict(), str(st_path))
        print(f"Saved model weights to {st_path}")

    # ImageNet normalisation
    mean = torch.tensor([0.485, 0.456, 0.406], device=device).view(1, 3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225], device=device).view(1, 3, 1, 1)

    # Cache loaded images to avoid re-reading
    img_cache: dict[int, np.ndarray] = {}

    def get_image(image_id: int) -> np.ndarray | None:
        if image_id not in img_cache:
            fname = id_to_file.get(image_id)
            if fname is None:
                return None
            img = cv2.imread(str(images_dir / fname))
            img_cache[image_id] = img
        return img_cache[image_id]

    def embed_crops(crops: list[np.ndarray]) -> np.ndarray:
        """Return L2-normalised embeddings (N, 768)."""
        all_embeds = []
        for i in range(0, len(crops), BATCH_SIZE):
            batch = crops[i : i + BATCH_SIZE]
            tensors = []
            for c in batch:
                c = cv2.resize(c, (CROP_SIZE, CROP_SIZE), interpolation=cv2.INTER_LINEAR)
                c = c[:, :, ::-1].astype(np.float32) / 255.0
                c = np.transpose(c, (2, 0, 1))
                tensors.append(torch.from_numpy(c))
            batch_t = torch.stack(tensors).to(device)
            batch_t = (batch_t - mean) / std
            with torch.no_grad():
                emb = model(batch_t)
            emb = emb.cpu().numpy()
            norms = np.linalg.norm(emb, axis=1, keepdims=True) + 1e-8
            emb = emb / norms
            all_embeds.append(emb)
        return np.concatenate(all_embeds, axis=0)

    # Build one reference embedding per category (mean of all crop embeddings)
    sorted_cats = sorted(cat_to_anns.keys())
    ref_embeddings = []
    ref_category_ids = []

    print(f"Processing {len(sorted_cats)} categories...")
    for cat_id in sorted_cats:
        anns = cat_to_anns[cat_id]
        crops = []
        for ann in anns:
            img = get_image(ann["image_id"])
            if img is None:
                continue
            x, y, w, h = [int(round(v)) for v in ann["bbox"]]
            x = max(0, x)
            y = max(0, y)
            x2 = min(img.shape[1], x + w)
            y2 = min(img.shape[0], y + h)
            if x2 <= x or y2 <= y:
                continue
            crops.append(img[y:y2, x:x2])

            # Limit crops per category to keep things manageable
            if len(crops) >= 50:
                break

        if len(crops) == 0:
            # Use zero vector as fallback
            ref_embeddings.append(np.zeros(768, dtype=np.float32))
        else:
            embeds = embed_crops(crops)
            mean_embed = embeds.mean(axis=0)
            mean_embed = mean_embed / (np.linalg.norm(mean_embed) + 1e-8)
            ref_embeddings.append(mean_embed)

        ref_category_ids.append(cat_id)
        if len(ref_category_ids) % 50 == 0:
            print(f"  {len(ref_category_ids)}/{len(sorted_cats)} categories done")

        # Clear image cache periodically
        if len(ref_category_ids) % 100 == 0:
            img_cache.clear()

    ref_embeddings = np.stack(ref_embeddings).astype(np.float32)   # (K, 768)
    ref_category_ids = np.array(ref_category_ids, dtype=np.int64)  # (K,)

    np.save(str(output_dir / "ref_embeddings.npy"), ref_embeddings)
    np.save(str(output_dir / "ref_category_ids.npy"), ref_category_ids)
    print(f"Saved {len(ref_category_ids)} reference embeddings to {output_dir}")


if __name__ == "__main__":
    main()
