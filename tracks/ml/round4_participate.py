#!/usr/bin/env python3
"""
Astar Island — Round 4+ Participation (improved)

Key improvements over Round 3:
1. FLOOR = 0.001 (was 0.01) — ~3 point score gain
2. Save observations to disk for resubmission
3. Smarter viewport placement: avoid ocean, maximize land coverage
4. Settlement metadata integration
"""
import requests
import time
import json
import numpy as np
from pathlib import Path

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
NUM_CLASSES = 6
TERRAIN_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}
CLASS_NAMES = ['empty', 'settlement', 'port', 'ruin', 'forest', 'mountain']
FLOOR = 0.001  # Lower floor = higher upper bound on score
NOTES_DIR = Path("F:/Workfolder/NM i AI main/repo/notes")

# Empirical priors from Round 2 ground truth
EMPIRICAL = {
    11: np.array([0.612, 0.186, 0.014, 0.018, 0.154, 0.015]),  # plains
    4:  np.array([0.480, 0.193, 0.012, 0.019, 0.284, 0.014]),  # forest
    1:  np.array([0.513, 0.240, 0.006, 0.022, 0.201, 0.018]),  # settlement
    5:  np.array([0.424, 0.153, 0.005, 0.016, 0.176, 0.227]),  # mountain
    10: np.array([0.950, 0.014, 0.006, 0.005, 0.021, 0.005]),  # ocean
    2:  np.array([0.513, 0.240, 0.006, 0.022, 0.201, 0.018]),  # port (like settlement)
    3:  np.array([0.612, 0.186, 0.014, 0.018, 0.154, 0.015]),  # ruin (like plains)
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


def find_land_cells(initial_grid):
    """Find non-ocean cell positions sorted by dynamism priority."""
    ig = np.array(initial_grid)
    # Priority: settlements > ruins > ports > plains > forest > mountain > ocean
    priority = {1: 6, 3: 5, 2: 4, 11: 3, 4: 2, 5: 1, 10: 0}
    cells = []
    for y in range(ig.shape[0]):
        for x in range(ig.shape[1]):
            p = priority.get(int(ig[y, x]), 0)
            if p > 0:
                cells.append((y, x, p))
    return cells


def generate_optimal_viewports(initial_grid, seed_index, num_viewports=10):
    """
    Generate viewports that maximize coverage of dynamic (non-ocean) cells.
    Each seed gets slightly offset viewports for diversity.
    """
    ig = np.array(initial_grid)
    H, W = ig.shape
    vp_w, vp_h = 15, 15

    # Count non-ocean cells in each possible viewport position
    land_mask = (ig != 10).astype(float)

    # Precompute integral image for fast region sums
    integral = np.cumsum(np.cumsum(land_mask, axis=0), axis=1)

    def region_sum(y1, x1, y2, x2):
        s = integral[y2, x2]
        if y1 > 0: s -= integral[y1-1, x2]
        if x1 > 0: s -= integral[y2, x1-1]
        if y1 > 0 and x1 > 0: s += integral[y1-1, x1-1]
        return s

    # Greedy: pick viewport with most uncovered land, then mark as covered
    covered = np.zeros_like(land_mask)
    viewports = []

    # Per-seed offset for diversity
    offset_x = (seed_index * 3) % 5
    offset_y = (seed_index * 2) % 4

    for _ in range(num_viewports):
        best_score = -1
        best_pos = (0, 0)

        uncovered = land_mask * (1 - covered)
        unc_integral = np.cumsum(np.cumsum(uncovered, axis=0), axis=1)

        def unc_region_sum(y1, x1, y2, x2):
            s = unc_integral[y2, x2]
            if y1 > 0: s -= unc_integral[y1-1, x2]
            if x1 > 0: s -= unc_integral[y2, x1-1]
            if y1 > 0 and x1 > 0: s += unc_integral[y1-1, x1-1]
            return s

        for vy in range(0, H - vp_h + 1, 2):
            for vx in range(0, W - vp_w + 1, 2):
                # Apply seed offset
                ay = min(vy + offset_y, H - vp_h)
                ax = min(vx + offset_x, W - vp_w)
                score = unc_region_sum(ay, ax, ay + vp_h - 1, ax + vp_w - 1)
                if score > best_score:
                    best_score = score
                    best_pos = (ax, ay)

        vx, vy = best_pos
        viewports.append((vx, vy, vp_w, vp_h))
        # Mark as covered
        covered[vy:vy+vp_h, vx:vx+vp_w] = 1

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

    # Unobserved cells: use empirical priors
    unobserved = total_obs == 0
    for y in range(height):
        for x in range(width):
            if unobserved[y, x]:
                terrain = int(ig[y, x])
                prior = EMPIRICAL.get(terrain)
                if prior is not None:
                    predictions[y, x] = prior.copy()
                else:
                    predictions[y, x] = 1.0 / NUM_CLASSES

    # Blend observed cells with empirical prior
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
    """Boost settlement/port probability near known settlements."""
    if not settlement_positions:
        return

    height, width = predictions.shape[:2]

    for s in settlement_positions:
        sx, sy = s.get('x', 0), s.get('y', 0)
        has_port = s.get('has_port', False)
        alive = s.get('alive', True)

        for dy in range(-2, 3):
            for dx in range(-2, 3):
                ny, nx = sy + dy, sx + dx
                if 0 <= ny < height and 0 <= nx < width:
                    if int(initial_grid[ny, nx]) == 10:
                        continue
                    d = abs(dy) + abs(dx)
                    if d <= 2:
                        boost = 0.04 * max(0, (3 - d) / 3)
                        if alive:
                            predictions[ny, nx, 1] += boost
                        else:
                            predictions[ny, nx, 3] += boost * 0.5  # ruin
                        predictions[ny, nx, 0] -= boost * 0.5
                        predictions[ny, nx, 4] -= boost * 0.5
                        if has_port and d <= 1:
                            predictions[ny, nx, 2] += 0.02
                            predictions[ny, nx, 0] -= 0.02

    predictions[:] = np.maximum(predictions, FLOOR / 2)


def save_observations(round_id, round_number, per_seed_counts, per_seed_obs, per_seed_settlements):
    """Save observation data to disk for potential resubmission."""
    save_path = NOTES_DIR / f"astar_obs_r{round_number}.json"
    data = {}
    for seed in per_seed_counts:
        data[f"seed_{seed}"] = {
            "counts": per_seed_counts[seed].tolist(),
            "total_obs": per_seed_obs[seed].tolist(),
            "settlements": per_seed_settlements.get(seed, [])
        }
    data["round_id"] = round_id
    data["round_number"] = round_number
    with open(save_path, 'w') as f:
        json.dump(data, f)
    log(f"Observations saved to {save_path}")


def participate(round_data):
    """Full pipeline for one round."""
    round_id = round_data["id"]
    round_number = round_data.get("round_number", "?")
    width = round_data.get("map_width", 40)
    height = round_data.get("map_height", 40)
    num_seeds = round_data.get("seeds_count", 5)
    initial_grid = round_data.get("initial_grid")
    round_weight = round_data.get("round_weight", 1.0)

    log(f"=== Round {round_number} — weight={round_weight:.4f} ===")
    log(f"Map: {width}x{height}, Seeds: {num_seeds}")

    if not initial_grid:
        detail = api_get(f"rounds/{round_id}")
        initial_grid = detail.get("initial_grid")

    # Count land cells
    ig = np.array(initial_grid)
    land_count = (ig != 10).sum()
    log(f"Land cells: {land_count}/{width*height} ({100*land_count/(width*height):.0f}%)")

    # Budget check
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining = this_round['queries_max'] - this_round['queries_used']
    log(f"Budget: {remaining}/{this_round['queries_max']} queries available")

    if remaining <= 0:
        log("No queries! Submitting priors only with FLOOR=0.001.")
        pred = np.zeros((height, width, NUM_CLASSES))
        for y in range(height):
            for x in range(width):
                t = int(ig[y, x])
                pred[y, x] = EMPIRICAL.get(t, np.ones(NUM_CLASSES) / NUM_CLASSES)
        pred = np.maximum(pred, FLOOR)
        pred = pred / pred.sum(axis=2, keepdims=True)
        pred_list = pred.tolist()
        for seed in range(num_seeds):
            result = submit_prediction(round_id, seed, pred_list)
            log(f"  Seed {seed}: {result.get('status', 'ok')}")
        return

    # Per-seed observation storage
    per_seed_counts = {s: np.zeros((height, width, NUM_CLASSES)) for s in range(num_seeds)}
    per_seed_obs = {s: np.zeros((height, width)) for s in range(num_seeds)}
    per_seed_settlements = {s: [] for s in range(num_seeds)}

    # Phase A: Systematic coverage
    queries_per_seed = min(remaining // num_seeds, 10)
    phase_a_total = queries_per_seed * num_seeds
    log(f"Phase A: {queries_per_seed} viewports × {num_seeds} seeds = {phase_a_total} queries")

    for seed in range(num_seeds):
        viewports = generate_optimal_viewports(initial_grid, seed, queries_per_seed)

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
                            class_id = TERRAIN_MAP.get(grid[dy][dx], 0)
                            per_seed_counts[seed][cy, cx, class_id] += 1
                            per_seed_obs[seed][cy, cx] += 1

                time.sleep(0.3)
            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 429:
                    log("Rate limited, sleeping 5s")
                    time.sleep(5)
                else:
                    log(f"Query failed: {e}")
            except Exception as e:
                log(f"Query failed: {e}")

        obs_cells = (per_seed_obs[seed] > 0).sum()
        log(f"  Seed {seed}: {obs_cells}/{width*height} covered ({100*obs_cells/(width*height):.0f}%), "
            f"{len(per_seed_settlements[seed])} settlements")

    # Save observations before Phase B (in case of crash)
    save_observations(round_id, round_number, per_seed_counts, per_seed_obs, per_seed_settlements)

    # Phase B: Targeted queries on highest-entropy regions
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining_b = this_round['queries_max'] - this_round['queries_used']

    if remaining_b > 0:
        log(f"Phase B: {remaining_b} targeted queries on high-entropy regions")
        for i in range(remaining_b):
            seed = i % num_seeds
            # Find region with most unobserved land cells
            uncovered_land = np.zeros((height, width))
            for y in range(height):
                for x in range(width):
                    if ig[y, x] != 10 and per_seed_obs[seed][y, x] == 0:
                        uncovered_land[y, x] = 1.0

            best_score = -1
            best_x, best_y = 0, 0
            for vy in range(0, height - 15 + 1, 2):
                for vx in range(0, width - 15 + 1, 2):
                    score = uncovered_land[vy:vy+15, vx:vx+15].sum()
                    if score > best_score:
                        best_score = score
                        best_x, best_y = vx, vy

            if best_score <= 0:
                # All covered — find region with fewest observations
                best_score = 999999
                for vy in range(0, height - 15 + 1, 3):
                    for vx in range(0, width - 15 + 1, 3):
                        region_land = (ig[vy:vy+15, vx:vx+15] != 10).sum()
                        if region_land < 5:
                            continue
                        region_obs = per_seed_obs[seed][vy:vy+15, vx:vx+15].sum()
                        score = region_obs / max(region_land, 1)
                        if score < best_score:
                            best_score = score
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
                time.sleep(0.3)
            except Exception as e:
                log(f"Phase B query failed: {e}")

    # Save final observations
    save_observations(round_id, round_number, per_seed_counts, per_seed_obs, per_seed_settlements)

    # Build and submit predictions
    log("Building predictions with FLOOR=0.001...")
    for seed in range(num_seeds):
        pred = build_predictions(
            per_seed_counts[seed], per_seed_obs[seed],
            initial_grid, per_seed_settlements[seed],
            width, height, alpha=0.1
        )

        obs_cells = (per_seed_obs[seed] > 0).sum()
        avg_obs = per_seed_obs[seed][per_seed_obs[seed] > 0].mean() if obs_cells > 0 else 0
        log(f"  Seed {seed}: {obs_cells} cells observed (avg {avg_obs:.1f} obs/cell), "
            f"min_p={pred.min():.5f}")

        try:
            result = submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted — {result.get('status', 'ok')}")
        except Exception as e:
            log(f"  Seed {seed}: FAILED — {e}")
        time.sleep(0.5)

    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    log(f"Done! Queries: {this_round['queries_used']}/{this_round['queries_max']}")


def main():
    log("Checking for active rounds...")
    my_rounds = api_get("my-rounds")

    active = [r for r in my_rounds if r.get("status") == "active"]
    if not active:
        log("No active rounds.")
        for r in sorted(my_rounds, key=lambda x: x['round_number']):
            score = r.get('round_score')
            log(f"  Round {r['round_number']}: score={score}, "
                f"seeds={r['seeds_submitted']}, queries={r['queries_used']}/{r['queries_max']}")
        return

    for rd in active:
        if rd['seeds_submitted'] > 0:
            log(f"Round {rd['round_number']} already has {rd['seeds_submitted']} submissions, skipping")
            continue
        participate(rd)


if __name__ == "__main__":
    main()
