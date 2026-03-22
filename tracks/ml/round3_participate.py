#!/usr/bin/env python3
"""
Astar Island — Round 3 Participation
Optimized strategy: skip ocean, focus on dynamic cells.

Query budget: 50 queries, 5 seeds
Strategy:
  Phase A (45 queries): 9 viewports per seed, positioned to avoid ocean borders
  Phase B (5 queries): 1 targeted query per seed on highest-entropy region

Settlement metadata: use to adjust per-cell priors near settlements.
"""
import requests
import time
import json
import numpy as np
from collections import defaultdict

TOKEN = "YOUR_JWT_TOKEN_HERE"
BASE = "https://api.ainm.no/astar-island"
NUM_CLASSES = 6
# Simulation grid: 0=empty, 1=settlement, 2=port, 3=ruin, 4=forest, 5=mountain
TERRAIN_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}
CLASS_NAMES = ['empty', 'settlement', 'port', 'ruin', 'forest', 'mountain']
FLOOR = 0.01

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Ground truth priors from Round 2 analysis
# [empty, settlement, port, ruin, forest, mountain]
EMPIRICAL = {
    11: np.array([0.612, 0.186, 0.014, 0.018, 0.154, 0.015]),  # plains
    4:  np.array([0.480, 0.193, 0.012, 0.019, 0.284, 0.014]),  # forest
    1:  np.array([0.513, 0.240, 0.006, 0.022, 0.201, 0.018]),  # settlement
    5:  np.array([0.424, 0.153, 0.005, 0.016, 0.176, 0.227]),  # mountain
    10: np.array([0.950, 0.014, 0.006, 0.005, 0.021, 0.005]),  # ocean
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def api_get(path):
    r = requests.get(f"{BASE}/{path}", headers=headers)
    r.raise_for_status()
    return r.json()


def simulate(round_id, seed, x, y, w=15, h=15):
    r = requests.post(f"{BASE}/simulate", headers=headers, json={
        "round_id": round_id, "seed_index": seed,
        "viewport_x": x, "viewport_y": y, "viewport_w": w, "viewport_h": h
    })
    r.raise_for_status()
    return r.json()


def submit_prediction(round_id, seed, prediction):
    r = requests.post(f"{BASE}/submit", headers=headers, json={
        "round_id": round_id, "seed_index": seed, "prediction": prediction
    })
    r.raise_for_status()
    return r.json()


def find_land_bounds(initial_grid):
    """Find the bounding box of non-ocean cells to focus observations."""
    ig = np.array(initial_grid)
    land_mask = ig != 10
    if not land_mask.any():
        return 0, 0, 39, 39

    ys, xs = np.where(land_mask)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def generate_smart_viewports(initial_grid, seed_index, num_seeds=5):
    """
    Generate viewports that:
    1. Focus on land (skip ocean borders)
    2. Maximize coverage with minimal overlap
    3. Offset by seed for diversity
    """
    x_min, y_min, x_max, y_max = find_land_bounds(initial_grid)

    # Land area dimensions
    land_w = x_max - x_min + 1
    land_h = y_max - y_min + 1

    # Calculate optimal grid of 15x15 viewports to cover land area
    vp_w, vp_h = 15, 15

    # Number of viewports needed in each dimension
    nx = max(1, (land_w + vp_w - 1) // vp_w)
    ny = max(1, (land_h + vp_h - 1) // vp_h)

    # Generate positions with even spacing
    if nx == 1:
        x_positions = [x_min]
    else:
        step_x = max(1, (land_w - vp_w) // (nx - 1)) if nx > 1 else 0
        x_positions = [min(x_min + i * step_x, 40 - vp_w) for i in range(nx)]

    if ny == 1:
        y_positions = [y_min]
    else:
        step_y = max(1, (land_h - vp_h) // (ny - 1)) if ny > 1 else 0
        y_positions = [min(y_min + i * step_y, 40 - vp_h) for i in range(ny)]

    # Per-seed offset for diversity (2-3 pixels)
    offset_x = (seed_index * 3) % 5
    offset_y = (seed_index * 2) % 5

    viewports = []
    for vy in y_positions:
        for vx in x_positions:
            x = min(max(vx + offset_x, 0), 40 - vp_w)
            y = min(max(vy + offset_y, 0), 40 - vp_h)
            viewports.append((x, y, vp_w, vp_h))

    return viewports


def compute_entropy_map(counts, total_obs):
    """Compute per-cell entropy from current observations."""
    h, w = total_obs.shape
    entropy = np.zeros((h, w))
    alpha = 1.0
    K = NUM_CLASSES

    for y in range(h):
        for x in range(w):
            if total_obs[y, x] == 0:
                entropy[y, x] = np.log(K)  # max entropy for unobserved
            else:
                p = (counts[y, x] + alpha) / (total_obs[y, x] + K * alpha)
                entropy[y, x] = -np.sum(p * np.log(p + 1e-10))

    return entropy


def build_predictions(counts, total_obs, initial_grid, settlement_positions,
                      width=40, height=40, alpha=2.0):
    """
    Build prediction tensor using:
    1. Dirichlet smoothing for observed cells
    2. Empirical priors for unobserved cells
    3. Settlement proximity adjustment
    4. Probability floor + renormalization
    """
    K = NUM_CLASSES
    ig = np.array(initial_grid)

    # Dirichlet posterior
    predictions = (counts + alpha) / (total_obs[:, :, np.newaxis] + K * alpha)

    # Unobserved cells: use empirical priors based on initial terrain
    unobserved = total_obs == 0
    for y in range(height):
        for x in range(width):
            if unobserved[y, x]:
                terrain = int(ig[y, x])
                prior = EMPIRICAL.get(terrain)
                if prior is not None:
                    predictions[y, x] = prior.copy()
                else:
                    predictions[y, x] = 1.0 / K

    # Blend ALL observed cells with empirical prior
    # Optimal blend from simulation: pw = 1.4 / (n + 2)
    for y in range(height):
        for x in range(width):
            n = total_obs[y, x]
            if n >= 1:
                terrain = int(ig[y, x])
                prior = EMPIRICAL.get(terrain)
                if prior is not None:
                    pw = min(1.4 / (n + 2), 0.8)
                    predictions[y, x] = (1 - pw) * predictions[y, x] + pw * prior

    # Settlement proximity adjustment
    if settlement_positions:
        _apply_settlement_proximity(predictions, settlement_positions, ig)

    # Floor + renormalize
    predictions = np.maximum(predictions, FLOOR)
    predictions = predictions / predictions.sum(axis=2, keepdims=True)

    return predictions


def _apply_settlement_proximity(predictions, settlement_positions, initial_grid):
    """
    Adjust predictions based on settlement metadata.
    Cells near settlements get higher settlement probability.
    Cells near settlements with has_port → higher port probability.
    """
    if not settlement_positions:
        return

    height, width = predictions.shape[:2]

    # Build distance-to-nearest-settlement map
    dist_map = np.full((height, width), 999.0)
    port_nearby = np.zeros((height, width), dtype=bool)

    for s in settlement_positions:
        sx, sy = s.get('x', 0), s.get('y', 0)
        has_port = s.get('has_port', False)
        pop = s.get('population', 1.0)

        for y in range(height):
            for x in range(width):
                d = abs(y - sy) + abs(x - sx)
                if d < dist_map[y, x]:
                    dist_map[y, x] = d
                if has_port and d <= 3:
                    port_nearby[y, x] = True

    # Adjust: cells near settlements get settlement boost
    for y in range(height):
        for x in range(width):
            if initial_grid[y, x] == 10:  # skip ocean
                continue

            d = dist_map[y, x]
            if d <= 2:
                # Near settlement: boost settlement & port probability
                boost = 0.05 * max(0, (3 - d) / 3)
                predictions[y, x, 1] += boost  # settlement
                predictions[y, x, 0] -= boost * 0.5
                predictions[y, x, 4] -= boost * 0.5
                if port_nearby[y, x]:
                    predictions[y, x, 2] += 0.02  # port
                    predictions[y, x, 0] -= 0.02

    # Clamp to positive
    predictions[:] = np.maximum(predictions, FLOOR / 2)


def participate(round_data):
    """Full pipeline for one round."""
    round_id = round_data["id"]
    width = round_data.get("map_width", 40)
    height = round_data.get("map_height", 40)
    num_seeds = round_data.get("seeds_count", 5)
    initial_grid = round_data.get("initial_grid")

    log(f"Round {round_data.get('round_number')} — weight={round_data.get('round_weight')}")
    log(f"Map: {width}x{height}, Seeds: {num_seeds}")

    if not initial_grid:
        log("No initial grid! Trying /rounds/{id}")
        detail = api_get(f"rounds/{round_id}")
        initial_grid = detail.get("initial_grid")

    budget = api_get("budget")
    remaining = budget.get("queries_max", 50) - budget.get("queries_used", 0)
    log(f"Budget: {remaining} queries available")

    if remaining <= 0:
        log("No queries! Submitting with priors only.")
        counts = np.zeros((height, width, NUM_CLASSES))
        total_obs = np.zeros((height, width))
        pred = build_predictions(counts, total_obs, initial_grid, [], width, height)
        pred_list = pred.tolist()
        for seed in range(num_seeds):
            result = submit_prediction(round_id, seed, pred_list)
            log(f"  Seed {seed}: {result.get('status', 'ok')}")
        return

    # Per-seed counts (each seed has its own simulation)
    per_seed_counts = {s: np.zeros((height, width, NUM_CLASSES)) for s in range(num_seeds)}
    per_seed_obs = {s: np.zeros((height, width)) for s in range(num_seeds)}
    per_seed_settlements = {s: [] for s in range(num_seeds)}

    # Phase A: Systematic coverage (9 viewports × 5 seeds = 45 queries)
    queries_per_seed = min(remaining // num_seeds, 9)
    log(f"Phase A: {queries_per_seed} viewports per seed = {queries_per_seed * num_seeds} queries")

    for seed in range(num_seeds):
        viewports = generate_smart_viewports(initial_grid, seed, num_seeds)
        viewports = viewports[:queries_per_seed]

        for i, (x, y, w, h) in enumerate(viewports):
            try:
                result = simulate(round_id, seed, x, y, w, h)
                grid = result.get("grid", [])
                vp = result.get("viewport", {})
                vx, vy = vp.get("x", x), vp.get("y", y)
                settlements = result.get("settlements", [])

                # Store settlement metadata
                if settlements:
                    per_seed_settlements[seed] = settlements

                # Update counts
                for dy in range(len(grid)):
                    for dx in range(len(grid[dy]) if grid[dy] else 0):
                        cy, cx = vy + dy, vx + dx
                        if 0 <= cy < height and 0 <= cx < width:
                            class_id = TERRAIN_MAP.get(grid[dy][dx], 0)
                            per_seed_counts[seed][cy, cx, class_id] += 1
                            per_seed_obs[seed][cy, cx] += 1

                time.sleep(0.25)
            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 429:
                    log("Rate limited, sleeping 3s")
                    time.sleep(3)
                else:
                    log(f"Query failed: {e}")
            except Exception as e:
                log(f"Query failed: {e}")

        obs_cells = (per_seed_obs[seed] > 0).sum()
        log(f"  Seed {seed}: {obs_cells}/{width*height} cells covered "
            f"({100*obs_cells/(width*height):.0f}%), "
            f"{len(per_seed_settlements[seed])} settlements found")

    # Phase B: Targeted queries for highest entropy regions
    budget_after = api_get("budget")
    remaining_b = budget_after.get("queries_max", 50) - budget_after.get("queries_used", 0)

    if remaining_b > 0:
        log(f"Phase B: {remaining_b} targeted queries")
        for i in range(remaining_b):
            seed = i % num_seeds
            entropy = compute_entropy_map(per_seed_counts[seed], per_seed_obs[seed])

            # Find highest-entropy 15x15 region
            best_score = -1
            best_x, best_y = 0, 0
            for vy in range(0, height - 15 + 1, 3):
                for vx in range(0, width - 15 + 1, 3):
                    region = entropy[vy:vy+15, vx:vx+15].sum()
                    if region > best_score:
                        best_score = region
                        best_x, best_y = vx, vy

            try:
                result = simulate(round_id, seed, best_x, best_y, 15, 15)
                grid = result.get("grid", [])
                vp = result.get("viewport", {})
                vx, vy = vp.get("x", best_x), vp.get("y", best_y)
                settlements = result.get("settlements", [])
                if settlements:
                    per_seed_settlements[seed] = settlements

                for dy in range(len(grid)):
                    for dx in range(len(grid[dy]) if grid[dy] else 0):
                        cy, cx = vy + dy, vx + dx
                        if 0 <= cy < height and 0 <= cx < width:
                            class_id = TERRAIN_MAP.get(grid[dy][dx], 0)
                            per_seed_counts[seed][cy, cx, class_id] += 1
                            per_seed_obs[seed][cy, cx] += 1
                time.sleep(0.25)
            except Exception as e:
                log(f"Phase B query failed: {e}")

    # Build and submit per-seed predictions
    log("Building per-seed predictions...")
    for seed in range(num_seeds):
        pred = build_predictions(
            per_seed_counts[seed], per_seed_obs[seed],
            initial_grid, per_seed_settlements[seed],
            width, height, alpha=0.1
        )

        obs_cells = (per_seed_obs[seed] > 0).sum()
        log(f"  Seed {seed}: {obs_cells} cells observed, "
            f"min={pred.min():.4f}, max={pred.max():.4f}")

        try:
            result = submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted — {result.get('status', 'ok')}")
        except Exception as e:
            log(f"  Seed {seed}: FAILED — {e}")
        time.sleep(0.5)

    budget_final = api_get("budget")
    log(f"Done! Queries used: {budget_final.get('queries_used')}/{budget_final.get('queries_max')}")


def main():
    log("Checking for active rounds...")
    my_rounds = api_get("my-rounds")

    active = [r for r in my_rounds if r.get("status") == "active"]
    if not active:
        log("No active rounds found.")
        for r in my_rounds:
            log(f"Round {r['round_number']}: score={r.get('round_score')}, rank={r.get('rank')}")
        return

    for rd in active:
        participate(rd)


if __name__ == "__main__":
    main()
