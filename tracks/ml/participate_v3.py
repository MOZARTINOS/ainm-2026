#!/usr/bin/env python3
"""
Astar Island — v3 Participation (Adaptive Regime Detection)

Key improvements:
1. Regime detection: 3 early queries → detect settlement/no-settlement world
2. Adaptive priors: interpolate between R2 (settlement) and R3 (no-settlement)
3. FLOOR=0.001
4. Observations dominate: pw shrinks fast with n, prior is just a starting point
5. Save observations to disk
"""
import requests
import time
import json
import numpy as np
from pathlib import Path

TOKEN = "YOUR_JWT_TOKEN_HERE"
BASE = "https://api.ainm.no/astar-island"
NUM_CLASSES = 6
TERRAIN_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}
CLASS_NAMES = ['empty', 'settlement', 'port', 'ruin', 'forest', 'mountain']
FLOOR = 0.001
NOTES_DIR = Path("F:/Workfolder/NM i AI main/repo/notes")

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# === TWO REGIME PRIORS ===
# R2 = "settlement world" (settlements ~20% of dynamic cells)
R2_PRIORS = {
    11: np.array([0.612, 0.186, 0.014, 0.018, 0.154, 0.015]),
    4:  np.array([0.480, 0.193, 0.012, 0.019, 0.284, 0.014]),
    1:  np.array([0.513, 0.240, 0.006, 0.022, 0.201, 0.018]),
    5:  np.array([0.424, 0.153, 0.005, 0.016, 0.176, 0.227]),
    10: np.array([0.950, 0.014, 0.006, 0.005, 0.021, 0.005]),
}

# R3 = "no-settlement world" (settlements ~0.3%)
R3_PRIORS = {
    11: np.array([0.791, 0.003, 0.000, 0.001, 0.191, 0.014]),
    4:  np.array([0.591, 0.003, 0.000, 0.001, 0.388, 0.018]),
    1:  np.array([0.711, 0.006, 0.000, 0.002, 0.275, 0.006]),
    5:  np.array([0.571, 0.002, 0.000, 0.000, 0.204, 0.222]),
    10: np.array([0.930, 0.000, 0.000, 0.000, 0.066, 0.003]),
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


def interpolate_priors(settlement_fraction):
    """
    Interpolate between R2 (settlement world) and R3 (no-settlement world).
    settlement_fraction: observed % of settlement cells in detection queries.

    >5% → pure R2 priors
    <1% → pure R3 priors
    1-5% → linear interpolation
    """
    if settlement_fraction >= 0.05:
        w_r2 = 1.0
    elif settlement_fraction <= 0.01:
        w_r2 = 0.0
    else:
        w_r2 = (settlement_fraction - 0.01) / 0.04  # linear 0→1

    priors = {}
    for t in R2_PRIORS:
        p = w_r2 * R2_PRIORS[t] + (1 - w_r2) * R3_PRIORS[t]
        p = np.maximum(p, FLOOR)
        p = p / p.sum()
        priors[t] = p

    return priors, w_r2


def find_land_center(initial_grid):
    """Find center of land mass for regime detection queries."""
    ig = np.array(initial_grid)
    land_mask = ig != 10
    if not land_mask.any():
        return 12, 12
    ys, xs = np.where(land_mask)
    cy, cx = int(np.mean(ys)), int(np.mean(xs))
    # Clamp to valid viewport origin
    cx = min(max(cx - 7, 0), ig.shape[1] - 15)
    cy = min(max(cy - 7, 0), ig.shape[0] - 15)
    return cx, cy


def generate_optimal_viewports(initial_grid, seed_index, num_viewports=10):
    """Greedy viewports maximizing uncovered land cells, with per-seed offset."""
    ig = np.array(initial_grid)
    H, W = ig.shape
    vp_w, vp_h = 15, 15
    land_mask = (ig != 10).astype(float)

    covered = np.zeros_like(land_mask)
    viewports = []
    offset_x = (seed_index * 3) % 5
    offset_y = (seed_index * 2) % 4

    for _ in range(num_viewports):
        uncovered = land_mask * (1 - covered)
        # Integral image for fast sums
        integral = np.cumsum(np.cumsum(uncovered, axis=0), axis=1)

        def region_sum(y1, x1, y2, x2):
            s = integral[y2, x2]
            if y1 > 0: s -= integral[y1-1, x2]
            if x1 > 0: s -= integral[y2, x1-1]
            if y1 > 0 and x1 > 0: s += integral[y1-1, x1-1]
            return s

        best_score = -1
        best_pos = (0, 0)
        for vy in range(0, H - vp_h + 1, 2):
            for vx in range(0, W - vp_w + 1, 2):
                ay = min(vy + offset_y, H - vp_h)
                ax = min(vx + offset_x, W - vp_w)
                score = region_sum(ay, ax, ay + vp_h - 1, ax + vp_w - 1)
                if score > best_score:
                    best_score = score
                    best_pos = (ax, ay)

        vx, vy = best_pos
        viewports.append((vx, vy, vp_w, vp_h))
        covered[vy:vy+vp_h, vx:vx+vp_w] = 1

    return viewports


def build_predictions(counts, total_obs, initial_grid, priors,
                      width=40, height=40, alpha=0.05):
    """
    Build predictions. Observations DOMINATE over priors.

    For observed cells: Dirichlet posterior with small alpha.
    Prior blending: pw = 0.5 / (n + 1) — shrinks fast.
      n=1: pw=0.25, n=2: pw=0.17, n=5: pw=0.08, n=10: pw=0.045

    For unobserved cells: use regime-adapted priors.
    """
    ig = np.array(initial_grid)
    K = NUM_CLASSES

    # Dirichlet posterior with small alpha (let observations speak)
    predictions = (counts + alpha) / (total_obs[:, :, np.newaxis] + K * alpha)

    # Unobserved cells: regime-adapted priors
    unobserved = total_obs == 0
    for y in range(height):
        for x in range(width):
            if unobserved[y, x]:
                terrain = int(ig[y, x])
                prior = priors.get(terrain)
                if prior is not None:
                    predictions[y, x] = prior.copy()
                else:
                    predictions[y, x] = 1.0 / K

    # Blend observed cells: prior weight shrinks fast with n
    for y in range(height):
        for x in range(width):
            n = total_obs[y, x]
            if n >= 1:
                terrain = int(ig[y, x])
                prior = priors.get(terrain)
                if prior is not None:
                    # pw = 0.5 / (n + 1): observations dominate quickly
                    pw = 0.5 / (n + 1)
                    predictions[y, x] = (1 - pw) * predictions[y, x] + pw * prior

    # Floor + renormalize
    predictions = np.maximum(predictions, FLOOR)
    predictions = predictions / predictions.sum(axis=2, keepdims=True)

    return predictions


def save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_settlements, regime_info):
    """Save all observation data to disk."""
    save_path = NOTES_DIR / f"astar_obs_r{round_number}.json"
    data = {"round_id": round_id, "round_number": round_number, "regime": regime_info}
    for seed in per_seed_counts:
        data[f"seed_{seed}"] = {
            "counts": per_seed_counts[seed].tolist(),
            "total_obs": per_seed_obs[seed].tolist(),
            "settlements": per_seed_settlements.get(seed, [])
        }
    with open(save_path, 'w') as f:
        json.dump(data, f)
    log(f"Observations saved to {save_path}")


def participate(round_data):
    """Full pipeline with regime detection."""
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

    ig = np.array(initial_grid)
    land_count = int((ig != 10).sum())
    log(f"Land cells: {land_count}/{width*height}")

    # Budget check
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining = this_round['queries_max'] - this_round['queries_used']
    log(f"Budget: {remaining}/{this_round['queries_max']} queries")

    if remaining <= 0:
        log("No queries! Using average priors.")
        priors, _ = interpolate_priors(0.05)  # middle ground
        pred = np.zeros((height, width, NUM_CLASSES))
        for y in range(height):
            for x in range(width):
                t = int(ig[y, x])
                pred[y, x] = priors.get(t, np.ones(NUM_CLASSES) / NUM_CLASSES)
        pred = np.maximum(pred, FLOOR)
        pred = pred / pred.sum(axis=2, keepdims=True)
        pred_list = pred.tolist()
        for seed in range(num_seeds):
            submit_prediction(round_id, seed, pred_list)
            log(f"  Seed {seed}: submitted")
        return

    per_seed_counts = {s: np.zeros((height, width, NUM_CLASSES)) for s in range(num_seeds)}
    per_seed_obs = {s: np.zeros((height, width)) for s in range(num_seeds)}
    per_seed_settlements = {s: [] for s in range(num_seeds)}

    # ========================================
    # PHASE 0: REGIME DETECTION (3 queries)
    # ========================================
    log("Phase 0: Regime detection (3 queries)...")
    cx, cy = find_land_center(initial_grid)
    total_land_cells_seen = 0
    total_settlement_cells = 0

    for detect_seed in range(min(3, num_seeds)):
        # Slightly offset each detection query
        dx = (detect_seed * 4) % 8
        dy = (detect_seed * 3) % 6
        qx = min(max(cx + dx - 4, 0), width - 15)
        qy = min(max(cy + dy - 3, 0), height - 15)

        try:
            result = simulate(round_id, detect_seed, qx, qy, 15, 15)
            grid = result.get("grid", [])
            vp = result.get("viewport", {})
            vx, vy = vp.get("x", qx), vp.get("y", qy)
            settlements = result.get("settlements", [])

            if settlements:
                per_seed_settlements[detect_seed] = settlements

            for dy2 in range(len(grid)):
                for dx2 in range(len(grid[dy2]) if grid[dy2] else 0):
                    cy2, cx2 = vy + dy2, vx + dx2
                    if 0 <= cy2 < height and 0 <= cx2 < width:
                        cell = grid[dy2][dx2]
                        class_id = TERRAIN_MAP.get(cell, 0)
                        per_seed_counts[detect_seed][cy2, cx2, class_id] += 1
                        per_seed_obs[detect_seed][cy2, cx2] += 1

                        # Count for regime detection (only land cells)
                        if int(ig[cy2, cx2]) != 10:
                            total_land_cells_seen += 1
                            if cell == 1:  # settlement
                                total_settlement_cells += 1

            time.sleep(0.3)
        except Exception as e:
            log(f"  Detection query {detect_seed} failed: {e}")

    # Determine regime
    if total_land_cells_seen > 0:
        settlement_frac = total_settlement_cells / total_land_cells_seen
    else:
        settlement_frac = 0.05  # default to middle

    priors, w_r2 = interpolate_priors(settlement_frac)
    regime_label = "SETTLEMENT" if w_r2 > 0.5 else "NO-SETTLEMENT"
    log(f"Regime: {regime_label} (settl_frac={settlement_frac:.3f}, "
        f"w_R2={w_r2:.2f}, seen={total_land_cells_seen} land cells, "
        f"{total_settlement_cells} settlements)")

    regime_info = {
        "settlement_fraction": settlement_frac,
        "w_r2": w_r2,
        "label": regime_label,
        "land_cells_seen": total_land_cells_seen,
        "settlement_cells": total_settlement_cells,
    }

    # ========================================
    # PHASE A: SYSTEMATIC COVERAGE (remaining queries)
    # ========================================
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining_a = this_round['queries_max'] - this_round['queries_used']

    # Reserve 5 for Phase B targeted queries
    phase_b_budget = min(5, remaining_a // 4)
    phase_a_budget = remaining_a - phase_b_budget
    queries_per_seed = phase_a_budget // num_seeds

    log(f"Phase A: {queries_per_seed} viewports × {num_seeds} seeds = {queries_per_seed * num_seeds} queries")

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

                for dy2 in range(len(grid)):
                    for dx2 in range(len(grid[dy2]) if grid[dy2] else 0):
                        cy2, cx2 = vy + dy2, vx + dx2
                        if 0 <= cy2 < height and 0 <= cx2 < width:
                            class_id = TERRAIN_MAP.get(grid[dy2][dx2], 0)
                            per_seed_counts[seed][cy2, cx2, class_id] += 1
                            per_seed_obs[seed][cy2, cx2] += 1

                time.sleep(0.3)
            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 429:
                    log("Rate limited, sleeping 5s")
                    time.sleep(5)
                else:
                    log(f"Query failed: {e}")
            except Exception as e:
                log(f"Query failed: {e}")

        obs_cells = int((per_seed_obs[seed] > 0).sum())
        log(f"  Seed {seed}: {obs_cells}/{width*height} covered ({100*obs_cells/(width*height):.0f}%)")

    # Save observations checkpoint
    save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_settlements, regime_info)

    # ========================================
    # PHASE B: TARGETED (fill gaps)
    # ========================================
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining_b = this_round['queries_max'] - this_round['queries_used']

    if remaining_b > 0:
        log(f"Phase B: {remaining_b} targeted gap-filling queries")
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

            # If all land covered, target least-observed regions
            if best_score <= 0:
                best_ratio = 999
                for vy in range(0, height - 15 + 1, 3):
                    for vx in range(0, width - 15 + 1, 3):
                        land = float((ig[vy:vy+15, vx:vx+15] != 10).sum())
                        if land < 5:
                            continue
                        obs = float(per_seed_obs[seed][vy:vy+15, vx:vx+15].sum())
                        ratio = obs / land
                        if ratio < best_ratio:
                            best_ratio = ratio
                            best_x, best_y = vx, vy

            try:
                result = simulate(round_id, seed, best_x, best_y, 15, 15)
                grid = result.get("grid", [])
                vp = result.get("viewport", {})
                vx, vy = vp.get("x", best_x), vp.get("y", best_y)
                settlements = result.get("settlements", [])
                if settlements:
                    per_seed_settlements[seed] = settlements

                for dy2 in range(len(grid)):
                    for dx2 in range(len(grid[dy2]) if grid[dy2] else 0):
                        cy2, cx2 = vy + dy2, vx + dx2
                        if 0 <= cy2 < height and 0 <= cx2 < width:
                            class_id = TERRAIN_MAP.get(grid[dy2][dx2], 0)
                            per_seed_counts[seed][cy2, cx2, class_id] += 1
                            per_seed_obs[seed][cy2, cx2] += 1
                time.sleep(0.3)
            except Exception as e:
                log(f"Phase B query failed: {e}")

    # Final save
    save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_settlements, regime_info)

    # ========================================
    # BUILD & SUBMIT
    # ========================================
    log(f"Building predictions (regime={regime_label}, FLOOR={FLOOR})...")
    for seed in range(num_seeds):
        pred = build_predictions(
            per_seed_counts[seed], per_seed_obs[seed],
            initial_grid, priors,
            width, height, alpha=0.05
        )

        obs_cells = int((per_seed_obs[seed] > 0).sum())
        land_obs = 0
        land_total = 0
        for y in range(height):
            for x in range(width):
                if ig[y, x] != 10:
                    land_total += 1
                    if per_seed_obs[seed][y, x] > 0:
                        land_obs += 1

        avg_obs = float(per_seed_obs[seed][per_seed_obs[seed] > 0].mean()) if obs_cells > 0 else 0
        log(f"  Seed {seed}: land_covered={land_obs}/{land_total} "
            f"({100*land_obs/max(land_total,1):.0f}%), avg_obs={avg_obs:.1f}")

        try:
            result = submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted — {result.get('status', 'ok')}")
        except Exception as e:
            log(f"  Seed {seed}: FAILED — {e}")
        time.sleep(0.5)

    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    log(f"Done! Queries: {this_round['queries_used']}/{this_round['queries_max']}")
    log(f"Regime: {regime_label} | Floor: {FLOOR} | Seeds submitted: {this_round['seeds_submitted']}")


def main():
    log("=== Astar Island v3 — Adaptive Regime Detection ===")
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
        if rd['seeds_submitted'] >= rd.get('seeds_count', 5):
            log(f"Round {rd.get('round_number')} already fully submitted, skipping")
            continue
        participate(rd)


if __name__ == "__main__":
    main()
