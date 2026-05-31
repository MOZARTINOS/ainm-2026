#!/usr/bin/env bash
# =============================================================================
# NM i AI 2026 — NorgesGruppen VLM training on GCP Cloud Shell
# =============================================================================
# Paste this ENTIRE script into GCP Cloud Shell (https://shell.cloud.google.com)
# Prerequisites: authenticated as your-gcp-account in project ${GCP_PROJECT:-your-gcp-project}
#
# Usage:
#   bash cloud_shell_training.sh [DATASET_URL]
#
# If DATASET_URL is not provided, the script will try GCS bucket and prompt you.
# =============================================================================
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
VM_NAME="nmiai-train"
PROJECT="${GCP_PROJECT:-your-gcp-project}"
ZONE="europe-west4-a"
MACHINE_TYPE="g2-standard-8"      # 8 vCPUs, 32 GB RAM + 1x L4 GPU
DISK_SIZE="200GB"
IMAGE_FAMILY="pytorch-2-6-gpu-debian-12"
IMAGE_PROJECT="deeplearning-platform-release"
DATASET_URL="${1:-}"

SSH="gcloud compute ssh ${VM_NAME} --project=${PROJECT} --zone=${ZONE} --command"
SCP="gcloud compute scp --project=${PROJECT} --zone=${ZONE}"

# ── Step 0: Verify project ──────────────────────────────────────────────────
echo "==> Verifying GCP project..."
CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ "${CURRENT_PROJECT}" != "${PROJECT}" ]; then
  echo "Setting project to ${PROJECT}"
  gcloud config set project "${PROJECT}"
fi

# ── Step 1: Create VM with L4 GPU ───────────────────────────────────────────
echo "==> Checking if VM '${VM_NAME}' already exists..."
if gcloud compute instances describe "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" &>/dev/null; then
  echo "VM '${VM_NAME}' already exists. Starting if stopped..."
  gcloud compute instances start "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" 2>/dev/null || true
else
  echo "==> Creating VM '${VM_NAME}' with L4 GPU..."
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
  echo "==> VM created."
fi

# ── Step 2: Wait for SSH ────────────────────────────────────────────────────
echo "==> Waiting for VM SSH to be ready (this can take 2-3 minutes)..."
for i in $(seq 1 30); do
  if gcloud compute ssh "${VM_NAME}" --project="${PROJECT}" --zone="${ZONE}" \
    --command="echo 'SSH ready'" 2>/dev/null; then
    break
  fi
  echo "  Attempt ${i}/30 — waiting 10s..."
  sleep 10
done

# Verify GPU is available
echo "==> Checking GPU..."
${SSH} "nvidia-smi --query-gpu=name,memory.total --format=csv,noheader" || {
  echo "WARNING: GPU not detected yet. NVIDIA drivers may still be installing."
  echo "Wait a few minutes and re-run, or SSH in and check: nvidia-smi"
}

# ── Step 3: Upload training scripts ─────────────────────────────────────────
echo "==> Creating working directory on VM..."
${SSH} "mkdir -p ~/cv ~/cv/weights ~/cv/data"

echo "==> Uploading training scripts to VM..."
# We upload just the Python scripts from Cloud Shell's local storage.
# First, write them to a temp dir in Cloud Shell.
TMPDIR=$(mktemp -d)

cat > "${TMPDIR}/convert_annotations.py" << 'PYEOF'
"""Convert COCO annotations to YOLO format (single-class)."""
import argparse, json, shutil
from pathlib import Path

def coco_to_yolo_single_cls(coco_path, images_dir, output_dir):
    with open(coco_path) as f:
        coco = json.load(f)
    images_dir = Path(images_dir)
    output_dir = Path(output_dir)
    img_out = output_dir / "images" / "train"
    lbl_out = output_dir / "labels" / "train"
    img_out.mkdir(parents=True, exist_ok=True)
    lbl_out.mkdir(parents=True, exist_ok=True)
    id_to_img = {img["id"]: img for img in coco["images"]}
    img_to_anns = {}
    for ann in coco["annotations"]:
        img_to_anns.setdefault(ann["image_id"], []).append(ann)
    for img_id, img_info in id_to_img.items():
        w_img, h_img = img_info["width"], img_info["height"]
        fname = img_info["file_name"]
        src = images_dir / fname
        dst = img_out / fname
        if not dst.exists() and src.exists():
            try:
                dst.symlink_to(src.resolve())
            except OSError:
                shutil.copy2(str(src), str(dst))
        anns = img_to_anns.get(img_id, [])
        label_file = lbl_out / (Path(fname).stem + ".txt")
        lines = []
        for ann in anns:
            x, y, w, h = ann["bbox"]
            cx = max(0, min(1, (x + w/2) / w_img))
            cy = max(0, min(1, (y + h/2) / h_img))
            nw = max(0, min(1, w / w_img))
            nh = max(0, min(1, h / h_img))
            if nw > 0 and nh > 0:
                lines.append(f"0 {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
        with open(label_file, "w") as f:
            f.write("\n".join(lines))
    yaml_path = output_dir / "dataset.yaml"
    yaml_path.write_text(f"path: {output_dir.resolve()}\ntrain: images/train\nval: images/train\n\nnc: 1\nnames: ['object']\n")
    print(f"Converted {len(id_to_img)} images to YOLO format at {output_dir}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--annotations", required=True)
    p.add_argument("--images", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    coco_to_yolo_single_cls(a.annotations, a.images, a.output)
PYEOF

cat > "${TMPDIR}/train_detector.py" << 'PYEOF'
"""Train YOLOv8s single-class detector for NorgesGruppen shelf detection."""
import argparse
from pathlib import Path
from ultralytics import YOLO

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="dataset.yaml")
    p.add_argument("--output", default="weights/yolov8s_single.onnx")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--patience", type=int, default=20)
    a = p.parse_args()
    model = YOLO("yolov8s.pt")
    model.train(data=a.data, epochs=a.epochs, imgsz=a.imgsz, single_cls=True,
                copy_paste=0.3, patience=a.patience, batch=-1, workers=8,
                mosaic=1.0, mixup=0.1, degrees=10.0, scale=0.5, fliplr=0.5,
                hsv_h=0.015, hsv_s=0.5, hsv_v=0.3, name="norgesgruppen_single_cls")
    best_path = Path(model.trainer.best)
    best_model = YOLO(str(best_path))
    best_model.export(format="onnx", half=True, imgsz=a.imgsz, simplify=True)
    onnx_src = best_path.with_suffix(".onnx")
    output_path = Path(a.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx_src.rename(output_path)
    print(f"Exported ONNX model to {output_path}")

if __name__ == "__main__":
    main()
PYEOF

cat > "${TMPDIR}/build_embeddings.py" << 'PYEOF'
"""Build DINOv2 reference embeddings for kNN classification."""
import argparse, json
from pathlib import Path
import cv2, numpy as np, timm, torch

DINO_MODEL_NAME = "vit_base_patch14_dinov2.lvd142m"
CROP_SIZE = 224
BATCH_SIZE = 64

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--annotations", required=True)
    p.add_argument("--images", required=True)
    p.add_argument("--output", default="weights")
    p.add_argument("--save-model", action="store_true")
    a = p.parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    images_dir, output_dir = Path(a.images), Path(a.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(a.annotations) as f:
        coco = json.load(f)
    id_to_file = {img["id"]: img["file_name"] for img in coco["images"]}
    cat_to_anns = {}
    for ann in coco["annotations"]:
        cat_to_anns.setdefault(ann["category_id"], []).append(ann)
    print(f"Loading {DINO_MODEL_NAME}...")
    model = timm.create_model(DINO_MODEL_NAME, pretrained=True, num_classes=0)
    model = model.to(device).eval()
    if a.save_model:
        from safetensors.torch import save_file
        save_file(model.state_dict(), str(output_dir / "dinov2_vitb14.safetensors"))
        print(f"Saved model weights")
    mean = torch.tensor([0.485,0.456,0.406], device=device).view(1,3,1,1)
    std = torch.tensor([0.229,0.224,0.225], device=device).view(1,3,1,1)
    img_cache = {}
    def get_image(iid):
        if iid not in img_cache:
            fname = id_to_file.get(iid)
            if fname is None: return None
            img_cache[iid] = cv2.imread(str(images_dir / fname))
        return img_cache[iid]
    def embed_crops(crops):
        all_e = []
        for i in range(0, len(crops), BATCH_SIZE):
            batch = crops[i:i+BATCH_SIZE]
            ts = []
            for c in batch:
                c = cv2.resize(c, (CROP_SIZE,CROP_SIZE), interpolation=cv2.INTER_LINEAR)
                c = c[:,:,::-1].astype(np.float32)/255.0
                ts.append(torch.from_numpy(np.transpose(c,(2,0,1))))
            bt = torch.stack(ts).to(device)
            bt = (bt - mean) / std
            with torch.no_grad(): e = model(bt)
            e = e.cpu().numpy()
            e = e / (np.linalg.norm(e, axis=1, keepdims=True)+1e-8)
            all_e.append(e)
        return np.concatenate(all_e, axis=0)
    sorted_cats = sorted(cat_to_anns.keys())
    ref_e, ref_ids = [], []
    print(f"Processing {len(sorted_cats)} categories...")
    for cat_id in sorted_cats:
        anns = cat_to_anns[cat_id]
        crops = []
        for ann in anns:
            img = get_image(ann["image_id"])
            if img is None: continue
            x,y,w,h = [int(round(v)) for v in ann["bbox"]]
            x,y = max(0,x), max(0,y)
            x2,y2 = min(img.shape[1],x+w), min(img.shape[0],y+h)
            if x2>x and y2>y: crops.append(img[y:y2,x:x2])
            if len(crops)>=50: break
        if not crops:
            ref_e.append(np.zeros(768, dtype=np.float32))
        else:
            emb = embed_crops(crops).mean(axis=0)
            ref_e.append(emb/(np.linalg.norm(emb)+1e-8))
        ref_ids.append(cat_id)
        if len(ref_ids)%50==0: print(f"  {len(ref_ids)}/{len(sorted_cats)} done")
        if len(ref_ids)%100==0: img_cache.clear()
    np.save(str(output_dir/"ref_embeddings.npy"), np.stack(ref_e).astype(np.float32))
    np.save(str(output_dir/"ref_category_ids.npy"), np.array(ref_ids, dtype=np.int64))
    print(f"Saved {len(ref_ids)} reference embeddings to {output_dir}")

if __name__ == "__main__":
    main()
PYEOF

${SCP} "${TMPDIR}/convert_annotations.py" "${VM_NAME}":~/cv/
${SCP} "${TMPDIR}/train_detector.py" "${VM_NAME}":~/cv/
${SCP} "${TMPDIR}/build_embeddings.py" "${VM_NAME}":~/cv/
rm -rf "${TMPDIR}"
echo "==> Scripts uploaded."

# ── Step 4: Download dataset ────────────────────────────────────────────────
echo "==> Downloading dataset to VM..."
${SSH} "$(cat <<REMOTE_DATASET
set -euo pipefail
cd ~/cv/data

if [ -d coco_dataset ] && [ -n "\$(ls -A coco_dataset 2>/dev/null)" ]; then
  echo "Dataset already extracted, skipping."
  exit 0
fi

if [ ! -f cv_coco_dataset.zip ]; then
  echo "Trying GCS bucket..."
  gsutil -q cp gs://${PROJECT}-data/cv_coco_dataset.zip . 2>/dev/null && echo "Downloaded from GCS" || true
fi

if [ ! -f cv_coco_dataset.zip ] && [ -n "${DATASET_URL}" ]; then
  echo "Downloading from provided URL..."
  wget -q --show-progress -O cv_coco_dataset.zip "${DATASET_URL}"
fi

if [ ! -f cv_coco_dataset.zip ]; then
  echo ""
  echo "=========================================================="
  echo "  DATASET NOT FOUND"
  echo "=========================================================="
  echo "Please upload the dataset manually. Options:"
  echo ""
  echo "  Option A - Upload via Cloud Shell:"
  echo "    gcloud compute scp cv_coco_dataset.zip ${VM_NAME}:~/cv/data/ --project=${PROJECT} --zone=${ZONE}"
  echo ""
  echo "  Option B - Upload to GCS first, then download on VM:"
  echo "    gsutil cp cv_coco_dataset.zip gs://${PROJECT}-data/"
  echo "    Then re-run this script."
  echo ""
  echo "  Option C - If you have a direct download URL:"
  echo "    bash cloud_shell_training.sh 'https://...url...'"
  echo "=========================================================="
  exit 1
fi

echo "Extracting dataset..."
unzip -qo cv_coco_dataset.zip -d coco_dataset
echo "Dataset extracted:"
find coco_dataset -maxdepth 2 -type f | head -20
echo "..."
find coco_dataset -name "*.json" | head -5
REMOTE_DATASET
)"

# ── Step 5: Run training pipeline ───────────────────────────────────────────
echo "==> Starting training pipeline on VM (this will take 1-2 hours)..."
echo "    Monitor with: gcloud compute ssh ${VM_NAME} --project=${PROJECT} --zone=${ZONE}"
echo ""

${SSH} "$(cat <<'REMOTE_TRAIN'
set -euo pipefail
cd ~/cv

echo "=== Installing dependencies ==="
pip install -q ultralytics safetensors timm opencv-python-headless 2>&1 | tail -3

echo "=== Checking GPU ==="
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}, Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"CPU\"}')"

# Locate annotation file and images dir
ANNOTATIONS=$(find data/coco_dataset -name "*.json" -path "*annotation*" 2>/dev/null | head -1)
if [ -z "$ANNOTATIONS" ]; then
  ANNOTATIONS=$(find data/coco_dataset -name "*.json" 2>/dev/null | head -1)
fi
IMAGES_DIR=$(find data/coco_dataset -type d -name "images" 2>/dev/null | head -1)
if [ -z "$IMAGES_DIR" ]; then
  IMAGES_DIR=$(find data/coco_dataset -type d | grep -iE "train|image" | head -1)
fi

if [ -z "$ANNOTATIONS" ] || [ -z "$IMAGES_DIR" ]; then
  echo "ERROR: Could not locate annotations JSON or images directory."
  echo "Dataset contents:"
  find data/coco_dataset -maxdepth 3 -type f | head -30
  exit 1
fi

echo "Annotations: $ANNOTATIONS"
echo "Images dir:  $IMAGES_DIR"
echo "Image count: $(find "$IMAGES_DIR" -type f -name '*.jpg' -o -name '*.png' | wc -l)"

echo ""
echo "=== Step 1/3: Converting COCO -> YOLO format ==="
python convert_annotations.py \
  --annotations "$ANNOTATIONS" \
  --images "$IMAGES_DIR" \
  --output data/yolo_dataset

echo ""
echo "=== Step 2/3: Training YOLOv8s detector (single-class, imgsz=1280) ==="
python train_detector.py \
  --data data/yolo_dataset/dataset.yaml \
  --output weights/yolov8s_single.onnx \
  --epochs 100 \
  --imgsz 1280

echo ""
echo "=== Step 3/3: Building DINOv2 reference embeddings ==="
mkdir -p weights
python build_embeddings.py \
  --annotations "$ANNOTATIONS" \
  --images "$IMAGES_DIR" \
  --output weights \
  --save-model

echo ""
echo "=== Training complete ==="
echo "Output files:"
ls -lh weights/
REMOTE_TRAIN
)"

# ── Step 6: Download weights back to Cloud Shell ─────────────────────────────
echo "==> Downloading trained weights from VM..."
mkdir -p ~/nmiai_weights
${SCP} --recurse "${VM_NAME}":~/cv/weights/* ~/nmiai_weights/

echo ""
echo "==> Weights downloaded to ~/nmiai_weights/:"
ls -lh ~/nmiai_weights/

echo ""
echo "============================================================"
echo "  TRAINING COMPLETE"
echo "============================================================"
echo ""
echo "  Weights are in ~/nmiai_weights/"
echo "  Expected files:"
echo "    yolov8s_single.onnx        (~25 MB)  - YOLO detector"
echo "    dinov2_vitb14.safetensors   (~350 MB) - DINOv2 backbone"
echo "    ref_embeddings.npy                    - Reference embeddings"
echo "    ref_category_ids.npy                  - Category ID mapping"
echo ""
echo "  To download to your local machine from Cloud Shell:"
echo "    cloudshell download ~/nmiai_weights/yolov8s_single.onnx"
echo "    cloudshell download ~/nmiai_weights/dinov2_vitb14.safetensors"
echo "    cloudshell download ~/nmiai_weights/ref_embeddings.npy"
echo "    cloudshell download ~/nmiai_weights/ref_category_ids.npy"
echo ""
echo "  IMPORTANT: Delete the VM to avoid charges:"
echo "    gcloud compute instances delete ${VM_NAME} --project=${PROJECT} --zone=${ZONE} -q"
echo "============================================================"
