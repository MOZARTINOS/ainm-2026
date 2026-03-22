#!/usr/bin/env python3
"""
Train a Simple Neural Cellular Automata (NCA) on ground truth data.

Input: initial_grid (40x40x8 one-hot terrain) → Output: predicted probabilities (40x40x6)
Training data: R2-R8 ground truth (40 seed-round combinations)

The model learns spatial patterns: how initial terrain layout maps to final state distributions.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import json
import requests
import os
import time

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
NOTES_DIR = "F:/Workfolder/NM i AI main/repo/notes"
ML_DIR = "F:/Workfolder/NM i AI main/repo/tracks/ml"
headers = {"Authorization": f"Bearer {TOKEN}"}

TERRAIN_CODES = [0, 1, 2, 3, 4, 5, 10, 11]  # 8 terrain types
NUM_TERRAIN = 8
NUM_CLASSES = 6
FLOOR = 0.01


class SimpleNCA(nn.Module):
    """CNN that maps initial terrain → final state probability distribution.

    Input: (B, 8, 40, 40) — one-hot encoded initial terrain
    Output: (B, 6, 40, 40) — probability distributions per cell
    """
    def __init__(self, hidden=64):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(NUM_TERRAIN, hidden, 5, padding=2),
            nn.ReLU(),
            nn.Conv2d(hidden, hidden, 5, padding=2),
            nn.ReLU(),
            nn.Conv2d(hidden, hidden, 3, padding=1),
            nn.ReLU(),
            nn.Conv2d(hidden, hidden, 3, padding=1),
            nn.ReLU(),
            nn.Conv2d(hidden, NUM_CLASSES, 1),
        )

    def forward(self, x):
        logits = self.net(x)
        # Softmax over class dimension, with temperature
        return F.softmax(logits, dim=1)


def grid_to_onehot(grid):
    """Convert 40x40 int grid to (8, 40, 40) one-hot tensor."""
    grid = np.array(grid)
    onehot = np.zeros((NUM_TERRAIN, 40, 40), dtype=np.float32)
    for i, code in enumerate(TERRAIN_CODES):
        onehot[i] = (grid == code).astype(np.float32)
    return onehot


def collect_training_data():
    """Collect all available ground truth data for training."""
    r = requests.get(f"{BASE}/my-rounds", headers=headers)
    rounds = {rd["round_number"]: rd for rd in r.json()
              if rd["status"] == "completed" and rd.get("round_score")}

    X = []  # initial grids (one-hot)
    Y = []  # ground truth distributions

    for rn, rd in sorted(rounds.items()):
        round_id = rd["id"]

        # Get per-seed initial states
        try:
            r = requests.get(f"{BASE}/rounds/{round_id}", headers=headers, timeout=30)
            initial_states = r.json().get("initial_states", [])
        except:
            continue

        for seed in range(5):
            try:
                # Get ground truth
                r = requests.get(f"{BASE}/analysis/{round_id}/{seed}", headers=headers, timeout=30)
                if r.status_code != 200:
                    continue
                data = r.json()
                gt = np.array(data["ground_truth"])  # (40, 40, 6)

                # Get initial grid for this seed
                if seed < len(initial_states):
                    ig = initial_states[seed]["grid"]
                else:
                    ig = data.get("initial_grid", rd.get("initial_grid"))
                    if ig is None:
                        continue

                x = grid_to_onehot(ig)  # (8, 40, 40)
                y = gt.transpose(2, 0, 1)  # (6, 40, 40)

                X.append(x)
                Y.append(y)

                time.sleep(0.3)
            except Exception as e:
                print(f"  R{rn} seed {seed}: {e}")

        print(f"R{rn}: {len(X)} samples total", flush=True)

    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)


def kl_loss(pred, target):
    """KL divergence loss: KL(target || pred), matching competition metric.

    pred: (B, 6, H, W) — predicted probabilities
    target: (B, 6, H, W) — ground truth probabilities
    """
    pred = torch.clamp(pred, min=FLOOR)
    pred = pred / pred.sum(dim=1, keepdim=True)

    # Only compute loss on dynamic cells (where target has entropy > 0)
    target_entropy = -(target * torch.log(target + 1e-10)).sum(dim=1)  # (B, H, W)
    dynamic_mask = target_entropy > 0.01  # (B, H, W)

    kl = (target * torch.log((target + 1e-10) / (pred + 1e-10))).sum(dim=1)  # (B, H, W)

    # Entropy-weighted KL
    weighted_kl = (target_entropy * kl * dynamic_mask.float()).sum()
    total_entropy = (target_entropy * dynamic_mask.float()).sum()

    if total_entropy > 0:
        return weighted_kl / total_entropy
    return torch.tensor(0.0)


def train():
    print("Collecting training data...", flush=True)
    X, Y = collect_training_data()
    print(f"Training set: {len(X)} samples", flush=True)

    if len(X) < 5:
        print("Not enough training data!")
        return

    # Split: leave last round as validation
    n_val = 5  # last 5 samples (1 round)
    X_train, Y_train = X[:-n_val], Y[:-n_val]
    X_val, Y_val = X[-n_val:], Y[-n_val:]

    print(f"Train: {len(X_train)}, Val: {len(X_val)}", flush=True)

    # Convert to tensors
    X_train_t = torch.from_numpy(X_train)
    Y_train_t = torch.from_numpy(Y_train)
    X_val_t = torch.from_numpy(X_val)
    Y_val_t = torch.from_numpy(Y_val)

    # Model
    model = SimpleNCA(hidden=64)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=100, gamma=0.5)

    best_val_loss = float("inf")
    best_state = None

    for epoch in range(300):
        model.train()

        # Random batch (all data fits in memory)
        idx = np.random.permutation(len(X_train))
        batch_size = min(8, len(X_train))

        total_loss = 0
        n_batches = 0
        for start in range(0, len(idx), batch_size):
            batch_idx = idx[start:start+batch_size]
            xb = X_train_t[batch_idx]
            yb = Y_train_t[batch_idx]

            pred = model(xb)
            loss = kl_loss(pred, yb)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        scheduler.step()

        # Validation
        if (epoch + 1) % 10 == 0:
            model.eval()
            with torch.no_grad():
                val_pred = model(X_val_t)
                val_loss = kl_loss(val_pred, Y_val_t).item()

                # Compute score
                vp = val_pred.numpy().transpose(0, 2, 3, 1)  # (B, 40, 40, 6)
                vy = Y_val_t.numpy().transpose(0, 2, 3, 1)
                scores = []
                for i in range(len(vp)):
                    p = np.maximum(vp[i], FLOOR)
                    p /= p.sum(axis=2, keepdims=True)
                    te = wkl = 0
                    for y in range(40):
                        for x in range(40):
                            gt = vy[i, y, x]
                            h = -np.sum(gt * np.log(gt + 1e-10))
                            if h > 0.001:
                                kl = np.sum(gt * np.log((gt + 1e-10) / (p[y, x] + 1e-10)))
                                wkl += h * kl
                                te += h
                    wkl = wkl / te if te > 0 else 0
                    scores.append(100 * np.exp(-3 * wkl))

                avg_score = np.mean(scores)
                print(f"Epoch {epoch+1}: train_loss={total_loss/n_batches:.4f} "
                      f"val_loss={val_loss:.4f} val_score={avg_score:.1f}", flush=True)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_state = {k: v.clone() for k, v in model.state_dict().items()}

    # Save best model
    if best_state:
        model.load_state_dict(best_state)
        save_path = os.path.join(ML_DIR, "nca_model.pt")
        torch.save(best_state, save_path)
        print(f"Saved best model to {save_path} (val_loss={best_val_loss:.4f})", flush=True)

    return model


if __name__ == "__main__":
    train()
