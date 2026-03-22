#!/usr/bin/env python3
"""
Astar Island — Auto-Participation Daemon
NM i AI 2026

Runs continuously on Open Claw (Hetzner) to:
1. Poll for new rounds every 60 seconds
2. Auto-observe with 50 queries
3. Auto-submit predictions for all 5 seeds
4. Log scores when available

Usage:
  python auto_participate.py --token YOUR_JWT

  # With custom settings:
  python auto_participate.py --token YOUR_JWT --interval 90 --alpha 2.0
"""
import argparse
import json
import time
import traceback
import numpy as np
import requests
from datetime import datetime

BASE = "https://api.ainm.no/astar-island"
NUM_CLASSES = 6
TERRAIN_MAP = {10: 0, 11: 0, 0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
FLOOR = 0.01


def log(msg):
    print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}", flush=True)


def get_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_open_rounds(token):
    r = requests.get(f"{BASE}/rounds", headers=get_headers(token))
    r.raise_for_status()
    return [rd for rd in r.json() if rd.get("status") == "active"]


def get_budget(token):
    r = requests.get(f"{BASE}/budget", headers=get_headers(token))
    r.raise_for_status()
    return r.json()


def simulate(token, round_id, seed, x, y, w=15, h=15):
    r = requests.post(f"{BASE}/simulate", headers=get_headers(token), json={
        "round_id": round_id, "seed_index": seed,
        "viewport_x": x, "viewport_y": y, "viewport_w": w, "viewport_h": h
    })
    r.raise_for_status()
    return r.json()


def submit_prediction(token, round_id, seed, prediction):
    r = requests.post(f"{BASE}/submit", headers=get_headers(token), json={
        "round_id": round_id, "seed_index": seed, "prediction": prediction
    })
    r.raise_for_status()
    return r.json()


def get_my_rounds(token):
    r = requests.get(f"{BASE}/my-rounds", headers=get_headers(token))
    r.raise_for_status()
    return r.json()


def generate_viewports(num_seeds=5):
    """Generate observation viewports for all seeds."""
    viewports = []
    positions = [(0, 0), (13, 0), (25, 0), (0, 13), (13, 13), (25, 13), (0, 25), (25, 25)]
    for seed in range(num_seeds):
        ox = (seed * 3) % 5
        oy = (seed * 2) % 5
        for bx, by in positions:
            x = min(max(bx + ox, 0), 25)
            y = min(max(by + oy, 0), 25)
            viewports.append((seed, x, y, 15, 15))
    return viewports


def participate_in_round(token, round_data, alpha=2.0):
    """Full pipeline: observe → predict → submit."""
    round_id = round_data["id"]
    width = round_data.get("map_width", 40)
    height = round_data.get("map_height", 40)
    num_seeds = round_data.get("seeds_count", 5)

    log(f"Participating in Round {round_data.get('round_number')} (weight={round_data.get('round_weight')})")

    # Check budget
    budget = get_budget(token)
    remaining = budget.get("remaining", 0)
    if remaining <= 0:
        log("No budget remaining!")
        return

    log(f"Budget: {remaining}/50 queries")

    # Initialize counts
    counts = np.zeros((height, width, NUM_CLASSES), dtype=np.float64)
    total_obs = np.zeros((height, width), dtype=np.float64)

    # Get initial state for priors
    r = requests.get(f"{BASE}/rounds/{round_id}", headers=get_headers(token))
    round_detail = r.json()
    initial_states = round_detail.get("initial_states", [])
    initial_grid = initial_states[0]["grid"] if initial_states else None

    # Phase A: Systematic observation
    viewports = generate_viewports(num_seeds)[:min(remaining, 40)]
    log(f"Phase A: {len(viewports)} queries...")

    success = 0
    for i, (seed, x, y, w, h) in enumerate(viewports):
        try:
            result = simulate(token, round_id, seed, x, y, w, h)
            grid = result.get("grid", [])
            vp = result.get("viewport", {})
            vx, vy = vp.get("x", x), vp.get("y", y)

            for dy in range(len(grid)):
                for dx in range(len(grid[dy])):
                    cy, cx = vy + dy, vx + dx
                    if 0 <= cy < height and 0 <= cx < width:
                        class_id = TERRAIN_MAP.get(grid[dy][dx], 0)
                        counts[cy, cx, class_id] += 1
                        total_obs[cy, cx] += 1
            success += 1
            time.sleep(0.25)
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 429:
                log(f"Rate limited, sleeping 3s...")
                time.sleep(3)
            else:
                log(f"Query {i+1} failed: {e}")
        except Exception as e:
            log(f"Query {i+1} failed: {e}")

    obs_cells = (total_obs > 0).sum()
    log(f"Observed {obs_cells}/{width*height} cells ({100*obs_cells/(width*height):.1f}%)")

    # Build predictions with Dirichlet smoothing
    K = NUM_CLASSES
    predictions = (counts + alpha) / (total_obs[:, :, np.newaxis] + K * alpha)
    unobserved = total_obs == 0
    predictions[unobserved] = 1.0 / K

    # Ground truth priors from Round 2 analysis (5 seeds × 1600 cells)
    # [empty, settlement, port, ruin, forest, mountain]
    EMPIRICAL = {
        11: [0.612, 0.186, 0.014, 0.018, 0.154, 0.015],  # plains
        4:  [0.480, 0.193, 0.012, 0.019, 0.284, 0.014],  # forest
        1:  [0.513, 0.240, 0.006, 0.022, 0.201, 0.018],  # settlement
        5:  [0.424, 0.153, 0.005, 0.016, 0.176, 0.227],  # mountain
        10: [0.950, 0.014, 0.006, 0.005, 0.021, 0.005],  # ocean
    }
    if initial_grid:
        for y in range(height):
            for x in range(width):
                if not unobserved[y, x]:
                    continue
                terrain = initial_grid[y][x]
                prior = EMPIRICAL.get(terrain)
                if prior:
                    predictions[y, x] = np.array(prior)

    # Floor + renormalize
    predictions = np.maximum(predictions, FLOOR)
    predictions = predictions / predictions.sum(axis=2, keepdims=True)

    # Submit
    pred_list = predictions.tolist()
    for seed in range(num_seeds):
        try:
            result = submit_prediction(token, round_id, seed, pred_list)
            log(f"Seed {seed}: {result.get('status', 'unknown')}")
            time.sleep(0.5)
        except Exception as e:
            log(f"Seed {seed} submit failed: {e}")

    log(f"Round {round_data.get('round_number')} complete!")


def main():
    parser = argparse.ArgumentParser(description="Astar Island Auto-Participation")
    parser.add_argument("--token", required=True, help="JWT auth token")
    parser.add_argument("--interval", type=int, default=60, help="Poll interval (seconds)")
    parser.add_argument("--alpha", type=float, default=0.1, help="Dirichlet alpha")
    args = parser.parse_args()

    log("Auto-participation daemon started")
    log(f"Poll interval: {args.interval}s, Alpha: {args.alpha}")

    participated = set()

    while True:
        try:
            # Check for open rounds
            open_rounds = get_open_rounds(args.token)

            for rd in open_rounds:
                rid = rd["id"]
                if rid not in participated:
                    try:
                        participate_in_round(args.token, rd, args.alpha)
                        participated.add(rid)
                    except Exception as e:
                        log(f"Round failed: {e}")
                        traceback.print_exc()

            # Print latest scores
            try:
                my_rounds = get_my_rounds(args.token)
                for mr in my_rounds:
                    if mr.get("round_score") is not None:
                        log(f"Round {mr['round_number']}: score={mr['round_score']:.2f} rank={mr.get('rank')}")
            except Exception:
                pass

        except Exception as e:
            log(f"Poll error: {e}")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
