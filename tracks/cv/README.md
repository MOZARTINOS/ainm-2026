# CV track

## Fast baseline ideas
- If classification: timm / torchvision pretrained model + simple CSV submission
- If detection: YOLO or DETR inference-only baseline
- If segmentation: lightweight UNet / SegFormer baseline

## First questions at reveal
- Input modality and size?
- Is training allowed/needed or inference-only enough?
- Submission = labels, json, masks, API?
- Metric = accuracy / F1 / mAP / IoU?
