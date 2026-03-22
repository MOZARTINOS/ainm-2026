"""
Train YOLOv8s single-class detector for NorgesGruppen shelf detection.
Run on GCP with GPU — NOT in the competition sandbox.

Usage:
    python train_detector.py --data dataset.yaml --output weights/yolov8s_single.onnx
"""

import argparse
from pathlib import Path
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=str, default="dataset.yaml",
                        help="Path to YOLO dataset.yaml")
    parser.add_argument("--output", type=str, default="weights/yolov8s_single.onnx",
                        help="Output ONNX path")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--patience", type=int, default=20)
    args = parser.parse_args()

    model = YOLO("yolov8s.pt")

    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        single_cls=True,
        copy_paste=0.3,
        patience=args.patience,
        batch=-1,          # auto batch size
        workers=8,
        mosaic=1.0,
        mixup=0.1,
        degrees=10.0,
        scale=0.5,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
        name="norgesgruppen_single_cls",
    )

    # Export best checkpoint to ONNX (FP16)
    best_path = Path(model.trainer.best)
    best_model = YOLO(str(best_path))
    best_model.export(
        format="onnx",
        half=True,
        imgsz=args.imgsz,
        simplify=True,
    )

    # Move exported ONNX to target location
    onnx_src = best_path.with_suffix(".onnx")
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx_src.rename(output_path)
    print(f"Exported ONNX model to {output_path}")


if __name__ == "__main__":
    main()
