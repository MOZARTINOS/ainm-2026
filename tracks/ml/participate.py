#!/usr/bin/env python3
"""
Astar Island — Unified Participation Script (Round 4+)
NM i AI 2026

Improvements over Round 3:
  - FLOOR=0.001 (API accepts it, +3 score vs 0.01)
  - Save all observations to disk for post-hoc resubmission
  - Better viewport placement: skip ocean, focus on dynamic cells
  - Settlement metadata integration
  - Empirical priors from Round 2 ground truth
"""
import requests
import time
import json
import numpy as np
import os
from collections import defaultdict

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
NUM_CLASSES = 6
FLOOR = 0.001
NOTES_DIR = "F:/Workfolder/NM i AI main/repo/notes"

CLASS_NAMES = ['empty', 'settlement', 'port', 'ruin', 'forest', 'mountain']

# Ground truth empirical priors from Round 2 (5 seeds)
# [empty, settlement, port, ruin, forest, mountain]
EMPIRICAL = {
    11: np.array([0.612, 0.186, 0.014, 0.018, 0.154, 0.015]),  # plains
    4:  np.array([0.480, 0.193, 0.012, 0.019, 0.284, 0.014]),  # forest
    1:  np.array([0.513, 0.240, 0.006, 0.022, 0.201, 0.018]),  # settlement
    5:  np.array([0.424, 0.153, 0.005, 0.016, 0.176, 0.227]),  # mountain
    10: np.array([0.950, 0.014, 0.006, 0.005, 0.021, 0.005]),  # ocean
}

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


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
    """Find bounding box of non-ocean cells."""
    ig = np.array(initial_grid)
    land_mask = ig != 10
    if not land_mask.any():
        return 0, 0, 39, 39
    ys, xs = np.where(land_mask)
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def generate_viewports(initial_grid, seed_index, num_seeds=5):
    """
    Generate viewports that maximize land coverage with minimal overlap.
    Per-seed offset for diversity across seeds.
    """
    x_min, y_min, x_max, y_max = find_land_bounds(initial_grid)
    land_w = x_max - x_min + 1
    land_h = y_max - y_min + 1
    vp_w, vp_h = 15, 15

    nx = max(1, (land_w + vp_w - 1) // vp_w)
    ny = max(1, (land_h + vp_h - 1) // vp_h)

    if nx == 1:
        x_positions = [x_min]
    else:
        step_x = max(1, (land_w - vp_w) // (nx - 1))
        x_positions = [min(x_min + i * step_x, 40 - vp_w) for i in range(nx)]

    if ny == 1:
        y_positions = [y_min]
    else:
        step_y = max(1, (land_h - vp_h) // (ny - 1))
        y_positions = [min(y_min + i * step_y, 40 - vp_h) for i in range(ny)]

    # Per-seed offset for diversity
    offset_x = (seed_index * 3) % 5
    offset_y = (seed_index * 2) % 5

    viewports = []
    for vy in y_positions:
        for vx in x_positions:
            x = min(max(vx + offset_x, 0), 40 - vp_w)
            y = min(max(vy + offset_y, 0), 40 - vp_h)
            viewports.append((x, y, vp_w, vp_h))

    return viewports


def build_predictions(counts, total_obs, initial_grid, settlement_positions,
                      width=40, height=40, alpha=0.1):
    """
    Build prediction tensor:
    1. Dirichlet posterior for observed cells
    2. Empirical priors for unobserved cells
    3. Prior blending: pw = 1.4 / (n + 2)
    4. Settlement proximity boost
    5. Floor + renormalize
    """
    ig = np.array(initial_grid)

    # Dirichlet posterior
    predictions = (counts + alpha) / (total_obs[:, :, np.newaxis] + NUM_CLASSES * alpha)

    # Unobserved: empirical priors
    unobserved = total_obs == 0
    for y in range(height):
        for x in range(width):
            if unobserved[y, x]:
                t = int(ig[y, x])
                predictions[y, x] = EMPIRICAL.get(t, np.ones(NUM_CLASSES) / NUM_CLASSES).copy()

    # Blend observed cells with prior: pw = 1.4 / (n + 2)
    for y in range(height):
        for x in range(width):
            n = total_obs[y, x]
            if n >= 1:
                t = int(ig[y, x])
                prior = EMPIRICAL.get(t)
                if prior is not None:
                    pw = min(1.4 / (n + 2), 0.8)
                    predictions[y, x] = (1 - pw) * predictions[y, x] + pw * prior

    # Settlement proximity adjustment
    if settlement_positions:
        _apply_settlement_proximity(predictions, settlement_positions, ig)

    # Floor + renormalize
    predictions = np.maximum(predictions, FLOOR)
    predictions /= predictions.sum(axis=2, keepdims=True)

    return predictions


def _apply_settlement_proximity(predictions, settlements, ig):
    """Boost settlement/port probability near known settlements."""
    if not settlements:
        return

    h, w = predictions.shape[:2]
    dist_map = np.full((h, w), 999.0)
    port_nearby = np.zeros((h, w), dtype=bool)

    for s in settlements:
        sx, sy = s.get('x', 0), s.get('y', 0)
        has_port = s.get('has_port', False)
        for y in range(h):
            for x in range(w):
                d = abs(y - sy) + abs(x - sx)
                if d < dist_map[y, x]:
                    dist_map[y, x] = d
                if has_port and d <= 3:
                    port_nearby[y, x] = True

    for y in range(h):
        for x in range(w):
            if ig[y, x] == 10:
                continue
            d = dist_map[y, x]
            if d <= 2:
                boost = 0.05 * max(0, (3 - d) / 3)
                predictions[y, x, 1] += boost
                predictions[y, x, 0] -= boost * 0.5
                predictions[y, x, 4] -= boost * 0.5
                if port_nearby[y, x]:
                    predictions[y, x, 2] += 0.02
                    predictions[y, x, 0] -= 0.02

    predictions[:] = np.maximum(predictions, FLOOR / 2)


def save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_settlements, initial_grid):
    """Save all observation data to disk for post-hoc analysis and resubmission."""
    save_path = os.path.join(NOTES_DIR, f"astar_obs_r{round_number}.json")
    data = {
        "round_id": round_id,
        "round_number": round_number,
        "initial_grid": np.array(initial_grid).tolist(),
        "seeds": {}
    }
    for seed in per_seed_counts:
        data["seeds"][str(seed)] = {
            "counts": per_seed_counts[seed].tolist(),
            "total_obs": per_seed_obs[seed].tolist(),
            "settlements": per_seed_settlements.get(seed, []),
        }
    with open(save_path, 'w') as f:
        json.dump(data, f)
    log(f"Observations saved to {save_path}")


def participate(round_data):
    """Full pipeline for one round."""
    round_id = round_data["id"]
    round_num = round_data.get("round_number", "?")
    width = round_data.get("map_width", 40)
    height = round_data.get("map_height", 40)
    num_seeds = round_data.get("seeds_count", 5)
    initial_grid = round_data.get("initial_grid")

    log(f"=== Round {round_num} — weight={round_data.get('round_weight')} ===")
    log(f"Map: {width}x{height}, Seeds: {num_seeds}")

    if not initial_grid:
        detail = api_get(f"rounds/{round_id}")
        initial_grid = detail.get("initial_grid")

    remaining = round_data.get("queries_max", 50) - round_data.get("queries_used", 0)
    log(f"Budget: {remaining} queries available")

    if remaining <= 0:
        log("No queries left! Submitting priors only.")
        counts = np.zeros((height, width, NUM_CLASSES))
        total_obs = np.zeros((height, width))
        pred = build_predictions(counts, total_obs, initial_grid, [], width, height)
        for seed in range(num_seeds):
            submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted (priors only)")
        return

    per_seed_counts = {s: np.zeros((height, width, NUM_CLASSES)) for s in range(num_seeds)}
    per_seed_obs = {s: np.zeros((height, width)) for s in range(num_seeds)}
    per_seed_settlements = {s: [] for s in range(num_seeds)}

    # Phase A: Systematic coverage
    queries_per_seed = min(remaining // num_seeds, 9)
    phase_a_total = queries_per_seed * num_seeds
    log(f"Phase A: {queries_per_seed} viewports/seed × {num_seeds} seeds = {phase_a_total} queries")

    for seed in range(num_seeds):
        viewports = generate_viewports(initial_grid, seed, num_seeds)[:queries_per_seed]

        for i, (x, y, w, h) in enumerate(viewports):
            try:
                result = simulate(round_id, seed, x, y, w, h)
                grid = result.get("grid", [])
                vp = result.get("viewport", {})
                vx, vy = vp.get("x", x), vp.get("y", y)
                settlements = result.get("settlements", [])

                if settlements:
                    per_seed_settlements[seed] = settlements

                for dy in range(len(grid)):
                    for dx in range(len(grid[dy]) if grid[dy] else 0):
                        cy, cx = vy + dy, vx + dx
                        if 0 <= cy < height and 0 <= cx < width:
                            class_id = grid[dy][dx]
                            if class_id in (10, 11):
                                class_id = 0
                            if 0 <= class_id < NUM_CLASSES:
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
        log(f"  Seed {seed}: {obs_cells}/{width*height} cells covered ({100*obs_cells/(width*height):.0f}%)")

    # Phase B: Targeted queries on highest-entropy regions
    remaining_b = remaining - phase_a_total
    if remaining_b > 0:
        log(f"Phase B: {remaining_b} targeted queries")
        for i in range(remaining_b):
            seed = i % num_seeds

            # Find region with most unobserved non-ocean cells
            ig = np.array(initial_grid)
            best_score = -1
            best_x, best_y = 0, 0
            for vy in range(0, height - 15 + 1, 3):
                for vx in range(0, width - 15 + 1, 3):
                    region_score = 0
                    for dy in range(15):
                        for dx in range(15):
                            cy, cx = vy + dy, vx + dx
                            if ig[cy, cx] != 10 and per_seed_obs[seed][cy, cx] == 0:
                                region_score += 1
                    if region_score > best_score:
                        best_score = region_score
                        best_x, best_y = vx, vy

            if best_score <= 0:
                continue

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
                            class_id = grid[dy][dx]
                            if class_id in (10, 11):
                                class_id = 0
                            if 0 <= class_id < NUM_CLASSES:
                                per_seed_counts[seed][cy, cx, class_id] += 1
                                per_seed_obs[seed][cy, cx] += 1

                time.sleep(0.25)
            except Exception as e:
                log(f"Phase B query failed: {e}")

    # Save observations to disk BEFORE submitting
    save_observations(round_id, round_num, per_seed_counts, per_seed_obs,
                      per_seed_settlements, initial_grid)

    # Build and submit per-seed predictions
    log("Building predictions...")
    for seed in range(num_seeds):
        pred = build_predictions(
            per_seed_counts[seed], per_seed_obs[seed],
            initial_grid, per_seed_settlements[seed],
            width, height, alpha=0.1
        )

        obs_cells = (per_seed_obs[seed] > 0).sum()
        log(f"  Seed {seed}: {obs_cells} cells observed, "
            f"min={pred.min():.5f}, max={pred.max():.4f}")

        try:
            result = submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted — {result.get('status', 'ok')}")
        except Exception as e:
            log(f"  Seed {seed}: FAILED — {e}")
        time.sleep(0.5)

    log(f"Round {round_num} complete! Used {remaining} queries.")


def main():
    log("=== Astar Island Participation ===")
    my_rounds = api_get("my-rounds")

    active = [r for r in my_rounds if r.get("status") == "active"]
    if not active:
        log("No active rounds.")
        for r in sorted(my_rounds, key=lambda x: x['round_number']):
            log(f"  Round {r['round_number']}: status={r['status']}, "
                f"score={r.get('round_score')}, rank={r.get('rank')}")
        return

    for rd in active:
        if rd.get("queries_used", 0) < rd.get("queries_max", 50):
            participate(rd)
        else:
            log(f"Round {rd.get('round_number')} already has all queries used, skipping.")


if __name__ == "__main__":
    main()
