import torch
_orig_load = torch.load
def _patched_load(*args, **kwargs):
    kwargs["weights_only"] = False
    return _orig_load(*args, **kwargs)
torch.load = _patched_load

from ultralytics import YOLO
model = YOLO("yolov8s.pt")
results = model.train(
    data="/root/cv/yolo_data/dataset.yaml",
    epochs=100,
    imgsz=1280,
    single_cls=True,
    batch=8,
    device=0,
    augment=True,
    mosaic=1.0,
    copy_paste=0.3,
    mixup=0.1,
    scale=0.5,
    patience=20,
    workers=4,
    project="/root/cv/runs",
    name="train"
)
model.export(format="onnx", half=True)
print("TRAINING COMPLETE")
