"""
Convert COCO annotations to YOLO format (single-class).
Creates label .txt files and a dataset.yaml for ultralytics training.

Usage:
    python convert_annotations.py \
        --annotations /path/to/train_annotations.json \
        --images /path/to/train_images/ \
        --output /path/to/yolo_dataset/
"""

import argparse
import json
from pathlib import Path


def coco_to_yolo_single_cls(coco_path: str, images_dir: str, output_dir: str):
    with open(coco_path) as f:
        coco = json.load(f)

    images_dir = Path(images_dir)
    output_dir = Path(output_dir)
    img_out = output_dir / "images" / "train"
    lbl_out = output_dir / "labels" / "train"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)

    # Build image id → info
    id_to_img = {img["id"]: img for img in coco["images"]}

    # Group annotations by image_id
    img_to_anns: dict[int, list] = {}
    for ann in coco["annotations"]:
        img_to_anns.setdefault(ann["image_id"], []).append(ann)

    # Process each image
    for img_id, img_info in id_to_img.items():
        w_img = img_info["width"]
        h_img = img_info["height"]
        fname = img_info["file_name"]

        # Symlink image
        src = images_dir / fname
        dst = img_out / fname
        if not dst.exists() and src.exists():
            try:
                dst.symlink_to(src.resolve())
            except OSError:
                # Fallback: copy on Windows if symlink fails
                import shutil
                shutil.copy2(str(src), str(dst))

        # Write YOLO labels (single class = 0)
        anns = img_to_anns.get(img_id, [])
        label_file = lbl_out / (Path(fname).stem + ".txt")
        lines = []
        for ann in anns:
            x, y, w, h = ann["bbox"]  # COCO: x, y, w, h (top-left)
            # Convert to YOLO: cx, cy, w, h (normalised)
            cx = (x + w / 2) / w_img
            cy = (y + h / 2) / h_img
            nw = w / w_img
            nh = h / h_img
            # Clip to [0, 1]
            cx = max(0, min(1, cx))
            cy = max(0, min(1, cy))
            nw = max(0, min(1, nw))
            nh = max(0, min(1, nh))
            if nw > 0 and nh > 0:
                lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        with open(label_file, "w") as f:
            f.write("\n".join(lines))

    # Write dataset.yaml
    yaml_path = output_dir / "dataset.yaml"
    yaml_content = f"""path: {output_dir.resolve()}
train: images/train
val: images/train

nc: 1
names: ['object']
"""
    with open(yaml_path, "w") as f:
        f.write(yaml_content)

    print(f"Converted {len(id_to_img)} images to YOLO format at {output_dir}")
    print(f"Dataset config: {yaml_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=str, required=True)
    parser.add_argument("--images", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    coco_to_yolo_single_cls(args.annotations, args.images, args.output)


if __name__ == "__main__":
    main()
