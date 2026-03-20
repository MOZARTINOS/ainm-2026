#!/usr/bin/env python3
"""
Replay Analyzer — Run N replays for a completed round/seed,
build empirical probability distribution from final frames.

POST /replay is FREE (no query cost), returns different sim_seed each time.
This lets us approximate the ground truth distribution.
"""
import requests
import json
import numpy as np
import time
import sys
from pathlib import Path

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
NOTES_DIR = Path("F:/Workfolder/NM i AI main/repo/notes")
TERRAIN_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}
NUM_CLASSES = 6

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def run_replays(round_id, seed_index, n_replays=100, rate_limit=0.25):
    """Run n_replays for a given round/seed, return per-cell class counts."""
    counts = None
    width = height = 40

    for i in range(n_replays):
        try:
            r = requests.post(f"{BASE}/replay", headers=headers, json={
                "round_id": round_id, "seed_index": seed_index
            }, timeout=30)
            r.raise_for_status()
            data = r.json()

            if counts is None:
                height = data.get("height", 40)
                width = data.get("width", 40)
                counts = np.zeros((height, width, NUM_CLASSES))

            # Get final frame
            final = data["frames"][-1]
            grid = final["grid"]

            for y in range(len(grid)):
                for x in range(len(grid[y])):
                    class_id = TERRAIN_MAP.get(grid[y][x], 0)
                    counts[y, x, class_id] += 1

            if (i + 1) % 20 == 0:
                print(f"  Replay {i+1}/{n_replays} done", flush=True)

            time.sleep(rate_limit)

        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                print(f"  Rate limited at replay {i+1}, sleeping 10s", flush=True)
                time.sleep(10)
            else:
                print(f"  Replay {i+1} failed: {e}", flush=True)
        except Exception as e:
            print(f"  Replay {i+1} failed: {e}", flush=True)

    if counts is None:
        return None

    # Normalize to probabilities
    total = counts.sum(axis=2, keepdims=True)
    total = np.maximum(total, 1)
    probs = counts / total

    return probs, int(counts.max()), height, width


def build_replay_priors(round_id, n_replays=100):
    """Build per-terrain-type priors from replay data across all 5 seeds."""
    all_probs = {}
    terrain_probs = {t: [] for t in [10, 11, 4, 1, 5, 2, 3]}

    # Get initial grids
    r = requests.get(f"{BASE}/rounds/{round_id}", headers=headers, timeout=30)
    round_data = r.json()
    initial_states = round_data.get("initial_states", [])

    for seed in range(5):
        print(f"\nSeed {seed}:", flush=True)
        result = run_replays(round_id, seed, n_replays)
        if result is None:
            continue

        probs, n_actual, height, width = result
        all_probs[seed] = probs.tolist()

        # Aggregate by terrain type
        if seed < len(initial_states):
            ig = np.array(initial_states[seed]["grid"])
            for t_val in terrain_probs:
                mask = ig == t_val
                if mask.sum() > 0:
                    avg = probs[mask].mean(axis=0)
                    terrain_probs[t_val].append(avg)

    # Average across seeds
    print("\n=== Replay-based priors ===")
    names = ["empty", "settl", "port", "ruin", "forest", "mount"]
    final_priors = {}
    for t_val, vals in terrain_probs.items():
        if vals:
            avg = np.mean(vals, axis=0)
            final_priors[t_val] = avg
            t_name = {10: "ocean", 11: "plains", 4: "forest", 1: "settlement", 5: "mountain", 2: "port", 3: "ruin"}.get(t_val, str(t_val))
            dist = ", ".join(f"{avg[i]:.4f}" for i in range(6))
            print(f"  {t_val}: np.array([{dist}]),  # {t_name}")

    return all_probs, final_priors


def build_replay_prediction(round_id, seed_index, n_replays=200, floor=0.01):
    """Build per-cell prediction from replays — this IS the ground truth approximation."""
    result = run_replays(round_id, seed_index, n_replays)
    if result is None:
        return None

    probs, n_actual, height, width = result

    # Apply floor and normalize
    probs = np.maximum(probs, floor)
    probs = probs / probs.sum(axis=2, keepdims=True)

    return probs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--n-replays", type=int, default=100)
    parser.add_argument("--mode", choices=["priors", "predict"], default="priors")
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if args.mode == "priors":
        all_probs, priors = build_replay_priors(args.round_id, args.n_replays)
        # Save
        save_path = NOTES_DIR / f"astar_replay_priors_{args.round_id[:8]}.json"
        with open(save_path, "w") as f:
            json.dump({"round_id": args.round_id, "n_replays": args.n_replays,
                        "priors": {str(k): v.tolist() for k, v in priors.items()}}, f)
        print(f"\nSaved to {save_path}")

    elif args.mode == "predict":
        if args.seed is None:
            print("Need --seed for predict mode")
            sys.exit(1)
        probs = build_replay_prediction(args.round_id, args.seed, args.n_replays)
        if probs is not None:
            save_path = NOTES_DIR / f"astar_replay_pred_{args.round_id[:8]}_s{args.seed}.json"
            with open(save_path, "w") as f:
                json.dump(probs.tolist(), f)
            print(f"Saved prediction to {save_path}")
