#!/usr/bin/env bash
# Run the full training pipeline on GCP and download weights.
# Usage: bash scripts/train_on_gcp.sh [VM_NAME]
#
# Prerequisites:
#   - VM created via gcp_setup.sh
#   - Competition dataset URL set in DATA_URL below (or passed as $2)
set -euo pipefail

VM_NAME="${1:-nmiai-train}"
DATA_URL="${2:-}"  # Pass the dataset download URL as second arg if needed
PROJECT="${GCP_PROJECT:-your-gcp-project}"
ZONE="europe-west4-a"
LOCAL_WEIGHTS_DIR="tracks/cv/weights"

SSH_CMD="gcloud compute ssh ${VM_NAME} --project=${PROJECT} --zone=${ZONE} --command"

echo "==> Uploading project to VM..."
gcloud compute scp --recurse --project="${PROJECT}" --zone="${ZONE}" \
  tracks/cv "${VM_NAME}":~/cv

echo "==> Running training pipeline on VM..."
${SSH_CMD} "$(cat <<'REMOTE_SCRIPT'
set -euo pipefail
cd ~/cv

echo "--- Installing dependencies ---"
pip install -q ultralytics safetensors timm

echo "--- Downloading dataset ---"
mkdir -p data && cd data
# If the dataset zip is already present, skip download
if [ ! -f cv_coco_dataset.zip ]; then
  echo "NOTE: Place cv_coco_dataset.zip in ~/cv/data/ or set DATA_URL."
  echo "Attempting gcloud storage download..."
  # Try GCS bucket first (adjust path as needed)
  gsutil -q cp gs://${GCP_PROJECT}-data/cv_coco_dataset.zip . 2>/dev/null || true
fi

if [ -f cv_coco_dataset.zip ]; then
  unzip -qo cv_coco_dataset.zip -d coco_dataset
else
  echo "ERROR: Dataset not found. Upload manually or set correct download path."
  exit 1
fi
cd ..

# Locate annotation file and images dir
ANNOTATIONS=$(find data/coco_dataset -name "*.json" -path "*annotation*" | head -1)
IMAGES_DIR=$(find data/coco_dataset -type d -name "images" | head -1)
if [ -z "$ANNOTATIONS" ] || [ -z "$IMAGES_DIR" ]; then
  # Fallback: try common COCO layout
  ANNOTATIONS=$(find data/coco_dataset -name "*.json" | head -1)
  IMAGES_DIR=$(find data/coco_dataset -type d | grep -i "train\|image" | head -1)
fi
echo "Annotations: $ANNOTATIONS"
echo "Images dir:  $IMAGES_DIR"

echo "--- Step 1/3: Converting annotations to YOLO format ---"
python convert_annotations.py \
  --annotations "$ANNOTATIONS" \
  --images "$IMAGES_DIR" \
  --output data/yolo_dataset

echo "--- Step 2/3: Training YOLOv8s detector (single-class) ---"
python train_detector.py \
  --data data/yolo_dataset/dataset.yaml \
  --output weights/yolov8s_single.onnx \
  --epochs 100 \
  --imgsz 1280

echo "--- Step 3/3: Building DINOv2 reference embeddings ---"
mkdir -p weights
python build_embeddings.py \
  --annotations "$ANNOTATIONS" \
  --images "$IMAGES_DIR" \
  --output weights \
  --save-model

echo "--- Training complete ---"
ls -lh weights/
REMOTE_SCRIPT
)"

echo "==> Downloading trained weights from VM..."
mkdir -p "${LOCAL_WEIGHTS_DIR}"
gcloud compute scp --recurse --project="${PROJECT}" --zone="${ZONE}" \
  "${VM_NAME}":~/cv/weights/* "${LOCAL_WEIGHTS_DIR}/"

echo "==> Weights downloaded to ${LOCAL_WEIGHTS_DIR}/:"
ls -lh "${LOCAL_WEIGHTS_DIR}/"

echo ""
echo "Done. Expected files:"
echo "  ${LOCAL_WEIGHTS_DIR}/yolov8s_single.onnx      (~25MB)"
echo "  ${LOCAL_WEIGHTS_DIR}/dinov2_vitb14.safetensors (~350MB)"
echo "  ${LOCAL_WEIGHTS_DIR}/ref_embeddings.npy"
echo "  ${LOCAL_WEIGHTS_DIR}/ref_category_ids.npy"
echo ""
echo "Remember to delete the VM when done:"
echo "  gcloud compute instances delete ${VM_NAME} --project=${PROJECT} --zone=${ZONE} -q"
