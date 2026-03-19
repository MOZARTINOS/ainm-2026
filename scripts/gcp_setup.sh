#!/usr/bin/env bash
# Create a GCP Compute Engine VM with L4 GPU for NM i AI training.
# Usage: bash scripts/gcp_setup.sh [VM_NAME]
set -euo pipefail

VM_NAME="${1:-nmiai-train}"
PROJECT="ai-nm26osl-1861"
ZONE="europe-west4-a"
MACHINE_TYPE="g2-standard-8"
DISK_SIZE="100GB"
IMAGE_FAMILY="pytorch-2-6-gpu-debian-12"
IMAGE_PROJECT="deeplearning-platform-release"

echo "==> Creating VM '${VM_NAME}' in ${ZONE}..."

gcloud compute instances create "${VM_NAME}" \
  --project="${PROJECT}" \
  --zone="${ZONE}" \
  --machine-type="${MACHINE_TYPE}" \
  --accelerator=type=nvidia-l4,count=1 \
  --maintenance-policy=TERMINATE \
  --boot-disk-size="${DISK_SIZE}" \
  --boot-disk-type=pd-ssd \
  --image-family="${IMAGE_FAMILY}" \
  --image-project="${IMAGE_PROJECT}" \
  --metadata="install-nvidia-driver=True" \
  --scopes=default,storage-rw \
  --no-restart-on-failure

echo "==> VM '${VM_NAME}' created."
echo "==> Waiting for SSH to become available..."
gcloud compute ssh "${VM_NAME}" \
  --project="${PROJECT}" \
  --zone="${ZONE}" \
  --command="echo 'SSH ready. GPU:'; nvidia-smi --query-gpu=name --format=csv,noheader"

echo ""
echo "Done. To connect:  gcloud compute ssh ${VM_NAME} --project=${PROJECT} --zone=${ZONE}"
echo "To delete:         gcloud compute instances delete ${VM_NAME} --project=${PROJECT} --zone=${ZONE} -q"
