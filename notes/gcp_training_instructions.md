# GCP Training Instructions

Train the NorgesGruppen CV models (YOLOv8s detector + DINOv2 embeddings) on a GCP VM with L4 GPU.

## Prerequisites

- GCP Cloud Shell open at https://shell.cloud.google.com
- Authenticated as `devstar18611@gcplab.me`
- Project `ai-nm26osl-1861` selected
- Dataset file `NM_NGD_coco_dataset.zip` (~864 MB) available

## Quick Start (All-in-One)

Upload the script to Cloud Shell, then run it:

```bash
# In Cloud Shell, first upload the script using the Cloud Shell upload button
# or copy-paste the contents of scripts/cloud_shell_training.sh

# Option A: If you have a direct download URL for the dataset
bash cloud_shell_training.sh "https://YOUR_DATASET_URL_HERE"

# Option B: If the dataset is already in GCS bucket
bash cloud_shell_training.sh

# Option C: Upload dataset manually first (see below), then run
bash cloud_shell_training.sh
```

## Step-by-Step (Manual)

### 1. Create the VM

```bash
gcloud compute instances create nmiai-train \
  --project=ai-nm26osl-1861 \
  --zone=europe-west4-a \
  --machine-type=g2-standard-8 \
  --accelerator=type=nvidia-l4,count=1 \
  --maintenance-policy=TERMINATE \
  --boot-disk-size=200GB \
  --boot-disk-type=pd-ssd \
  --image-family=pytorch-2-6-gpu-debian-12 \
  --image-project=deeplearning-platform-release \
  --metadata="install-nvidia-driver=True" \
  --scopes=default,storage-rw \
  --no-restart-on-failure
```

### 2. Wait for VM + verify GPU

```bash
# Wait 2-3 minutes for NVIDIA drivers to install, then:
gcloud compute ssh nmiai-train --project=ai-nm26osl-1861 --zone=europe-west4-a \
  --command="nvidia-smi"
```

### 3. Upload dataset to VM

```bash
# From Cloud Shell (if dataset is on your local machine, upload to Cloud Shell first)
gcloud compute scp NM_NGD_coco_dataset.zip \
  nmiai-train:~/cv/data/ \
  --project=ai-nm26osl-1861 --zone=europe-west4-a
```

### 4. SSH into VM and run training

```bash
gcloud compute ssh nmiai-train --project=ai-nm26osl-1861 --zone=europe-west4-a
```

Then on the VM:

```bash
cd ~/cv/data
unzip -qo NM_NGD_coco_dataset.zip -d coco_dataset

# Find the annotations and images
ANNOTATIONS=$(find coco_dataset -name "*.json" -path "*annotation*" | head -1)
IMAGES_DIR=$(find coco_dataset -type d -name "images" | head -1)
echo "Annotations: $ANNOTATIONS"
echo "Images: $IMAGES_DIR"

cd ~/cv
pip install -q ultralytics safetensors timm opencv-python-headless

# Step 1: Convert annotations
python convert_annotations.py \
  --annotations "data/$ANNOTATIONS" \
  --images "data/$IMAGES_DIR" \
  --output data/yolo_dataset

# Step 2: Train YOLO detector (~45-60 min on L4)
python train_detector.py \
  --data data/yolo_dataset/dataset.yaml \
  --output weights/yolov8s_single.onnx \
  --epochs 100 --imgsz 1280

# Step 3: Build DINOv2 embeddings (~15-30 min on L4)
python build_embeddings.py \
  --annotations "data/$ANNOTATIONS" \
  --images "data/$IMAGES_DIR" \
  --output weights --save-model
```

### 5. Download weights

From Cloud Shell:

```bash
mkdir -p ~/nmiai_weights
gcloud compute scp --recurse \
  nmiai-train:~/cv/weights/* ~/nmiai_weights/ \
  --project=ai-nm26osl-1861 --zone=europe-west4-a

# Download to local machine
cloudshell download ~/nmiai_weights/yolov8s_single.onnx
cloudshell download ~/nmiai_weights/dinov2_vitb14.safetensors
cloudshell download ~/nmiai_weights/ref_embeddings.npy
cloudshell download ~/nmiai_weights/ref_category_ids.npy
```

### 6. Delete VM (important!)

```bash
gcloud compute instances delete nmiai-train \
  --project=ai-nm26osl-1861 --zone=europe-west4-a -q
```

## Expected Output Files

| File | Size | Purpose |
|------|------|---------|
| `yolov8s_single.onnx` | ~25 MB | Single-class product detector |
| `dinov2_vitb14.safetensors` | ~350 MB | DINOv2 backbone weights |
| `ref_embeddings.npy` | varies | Per-category reference embeddings |
| `ref_category_ids.npy` | varies | Category ID mapping |

## Estimated Training Time

- VM creation + driver install: ~5 min
- Dataset download + extract: ~5 min
- YOLO training (100 epochs, 1280px): ~45-60 min
- DINOv2 embedding build: ~15-30 min
- Total: ~1.5-2 hours

## Troubleshooting

- **nvidia-smi not found**: Wait 3-5 min after VM creation for driver install to finish
- **CUDA out of memory**: The script uses `batch=-1` (auto batch). If still OOM, SSH in and add `--imgsz 640` to reduce memory
- **Dataset not found**: Check the zip contents with `unzip -l NM_NGD_coco_dataset.zip | head -20` to see the directory structure
- **Quota error on VM creation**: Try zone `europe-west4-b` or `europe-west4-c` as alternatives
