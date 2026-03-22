"""
Create PROPER train/val split using GroupKFold by ORIGINAL IMAGE ID.
All tiles from same image go to same split - NO data leakage.
"""
import json, random, os
from pathlib import Path
from collections import defaultdict

random.seed(42)

ANN = Path("/root/cv/train/annotations.json")
SRC = Path("/root/cv/yolo_data/images/train")
OUT = Path("/root/cv/yolo_groupkfold")
VAL_RATIO = 0.2

def main():
    with open(ANN) as f:
        coco = json.load(f)

    images = coco["images"]
    annotations = coco["annotations"]
    categories = coco["categories"]

    # Group annotations by image
    img_anns = defaultdict(list)
    for ann in annotations:
        img_anns[ann["image_id"]].append(ann)

    # Shuffle images and split by IMAGE (not tile)
    random.shuffle(images)
    n_val = max(1, int(len(images) * VAL_RATIO))
    val_images = images[:n_val]
    train_images = images[n_val:]

    val_ids = set(img["id"] for img in val_images)
    train_ids = set(img["id"] for img in train_images)

    val_anns = [a for a in annotations if a["image_id"] in val_ids]
    train_anns = [a for a in annotations if a["image_id"] in train_ids]

    val_cats = set(a["category_id"] for a in val_anns)

    print(f"Train: {len(train_images)} images, {len(train_anns)} annotations")
    print(f"Val: {len(val_images)} images, {len(val_anns)} annotations")
    print(f"Categories in val: {len(val_cats)}/{len(categories)}")

    # Save COCO val annotations for mAP evaluation
    OUT.mkdir(parents=True, exist_ok=True)
    val_coco = {"images": val_images, "annotations": val_anns, "categories": categories}
    with open(OUT / "val_annotations.json", "w") as f:
        json.dump(val_coco, f)

    train_coco = {"images": train_images, "annotations": train_anns, "categories": categories}
    with open(OUT / "train_annotations.json", "w") as f:
        json.dump(train_coco, f)

    # Create val images directory (symlinks)
    val_img_dir = OUT / "val_images"
    val_img_dir.mkdir(exist_ok=True)
    for img in val_images:
        src = SRC / img["file_name"]
        dst = val_img_dir / img["file_name"]
        if src.exists() and not dst.exists():
            os.symlink(str(src), str(dst))

    # Save train image list (for tiled dataset generation)
    with open(OUT / "train_image_ids.txt", "w") as f:
        for img in train_images:
            f.write(f"{img['id']}\n")
    with open(OUT / "val_image_ids.txt", "w") as f:
        for img in val_images:
            f.write(f"{img['id']}\n")

    print(f"Saved to {OUT}/")
    print(f"Val images: {len(list(val_img_dir.iterdir()))}")

if __name__ == "__main__":
    main()
