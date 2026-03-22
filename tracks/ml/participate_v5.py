#!/usr/bin/env python3
"""
Astar Island — v5 Participation

Key improvements over v4:
1. Per-regime priors (dead/medium/hot) from R2-R6 ground truth (50 seeds total)
2. Dynamic regime detection from first observations
3. Regime detection from initial settlement count (FREE) + confirmed via queries
4. Per-seed grids from /rounds/{id} (FREE)
5. FLOOR=0.01 (docs requirement), alpha=2.0 (Dirichlet smoothing)
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
FLOOR = 0.01
NOTES_DIR = Path("F:/Workfolder/NM i AI main/repo/notes")

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# === PER-REGIME PRIORS (computed from R2-R6 ground truth, 50 seeds) ===
REGIME_PRIORS = {
    "dead": {  # settlement fraction < 5% (R3-like)
        11: np.array([0.9515, 0.0096, 0.0096, 0.0096, 0.0099, 0.0096]),
        4:  np.array([0.0247, 0.0096, 0.0096, 0.0096, 0.9367, 0.0096]),
        1:  np.array([0.6636, 0.0178, 0.0097, 0.0097, 0.2894, 0.0097]),
        5:  np.array([0.0095, 0.0095, 0.0095, 0.0095, 0.0095, 0.9524]),
        10: np.array([0.9524, 0.0095, 0.0095, 0.0095, 0.0095, 0.0095]),
        2:  np.array([0.6636, 0.0178, 0.0097, 0.0097, 0.2894, 0.0097]),
        3:  np.array([0.6636, 0.0178, 0.0097, 0.0097, 0.2894, 0.0097]),
    },
    "medium": {  # 5-15% (R4/R5-like)
        11: np.array([0.8300, 0.1041, 0.0099, 0.0108, 0.0354, 0.0099]),
        4:  np.array([0.0742, 0.1108, 0.0099, 0.0116, 0.7837, 0.0099]),
        1:  np.array([0.4534, 0.2777, 0.0098, 0.0236, 0.2256, 0.0098]),
        5:  np.array([0.0095, 0.0095, 0.0095, 0.0095, 0.0095, 0.9524]),
        10: np.array([0.9524, 0.0095, 0.0095, 0.0095, 0.0095, 0.0095]),
        2:  np.array([0.4534, 0.2777, 0.0098, 0.0236, 0.2256, 0.0098]),
        3:  np.array([0.4534, 0.2777, 0.0098, 0.0236, 0.2256, 0.0098]),
    },
    "hot": {  # >15% (R2/R6-like)
        11: np.array([0.6775, 0.2156, 0.0166, 0.0252, 0.0551, 0.0099]),
        4:  np.array([0.1285, 0.2209, 0.0139, 0.0257, 0.6012, 0.0099]),
        1:  np.array([0.3725, 0.4064, 0.0098, 0.0375, 0.1640, 0.0098]),
        5:  np.array([0.0095, 0.0095, 0.0095, 0.0095, 0.0095, 0.9524]),
        10: np.array([0.9524, 0.0095, 0.0095, 0.0095, 0.0095, 0.0095]),
        2:  np.array([0.3725, 0.4064, 0.0098, 0.0375, 0.1640, 0.0098]),
        3:  np.array([0.3725, 0.4064, 0.0098, 0.0375, 0.1640, 0.0098]),
    },
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


def detect_regime(settlement_frac):
    """Classify round into regime based on observed settlement fraction."""
    if settlement_frac < 0.05:
        return "dead"
    elif settlement_frac < 0.15:
        return "medium"
    else:
        return "hot"


def interpolate_priors(settlement_frac):
    """
    Instead of hard regime boundaries, interpolate between regime priors.
    This handles edge cases (e.g., 14% settlement = almost hot).
    """
    regime = detect_regime(settlement_frac)
    base_priors = REGIME_PRIORS[regime]

    # Interpolate at boundaries
    if 0.03 < settlement_frac < 0.07:
        # Between dead and medium
        t = (settlement_frac - 0.03) / 0.04  # 0 at 3%, 1 at 7%
        dead_p = REGIME_PRIORS["dead"]
        med_p = REGIME_PRIORS["medium"]
        return {k: (1 - t) * dead_p[k] + t * med_p[k] for k in dead_p}
    elif 0.12 < settlement_frac < 0.18:
        # Between medium and hot
        t = (settlement_frac - 0.12) / 0.06  # 0 at 12%, 1 at 18%
        med_p = REGIME_PRIORS["medium"]
        hot_p = REGIME_PRIORS["hot"]
        return {k: (1 - t) * med_p[k] + t * hot_p[k] for k in med_p}

    return {k: v.copy() for k, v in base_priors.items()}


def get_priors(regime_priors):
    """Apply floor and normalize priors."""
    priors = {}
    for t, p in regime_priors.items():
        p = np.maximum(p.copy(), FLOOR)
        p = p / p.sum()
        priors[t] = p
    return priors


def generate_optimal_viewports(grid, seed_index, num_viewports=10):
    """Greedy viewports maximizing uncovered land cells per seed's own grid."""
    ig = np.array(grid)
    H, W = ig.shape
    vp_w, vp_h = 15, 15
    land_mask = (ig != 10).astype(float)
    covered = np.zeros_like(land_mask)
    viewports = []
    offset_x = (seed_index * 3) % 5
    offset_y = (seed_index * 2) % 4

    for _ in range(num_viewports):
        uncovered = land_mask * (1 - covered)
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


def build_predictions(counts, total_obs, grid, priors,
                      width=40, height=40, alpha=2.0):
    """
    Build predictions using Dirichlet-smoothed Bayesian update.

    For each cell:
    - Prior comes from regime-specific terrain priors
    - Observations update via Dirichlet: posterior = (counts + alpha*prior) / (n + alpha)
    - alpha=2.0: with n=1 obs, prior contributes 67%; with n=5, prior 29%
    """
    ig = np.array(grid)
    predictions = np.zeros((height, width, NUM_CLASSES))

    for y in range(height):
        for x in range(width):
            terrain = int(ig[y, x])
            prior = priors.get(terrain, np.ones(NUM_CLASSES) / NUM_CLASSES)
            n = total_obs[y, x]
            if n > 0:
                # Dirichlet posterior: (counts + alpha * prior) / (n + alpha)
                predictions[y, x] = (counts[y, x] + alpha * prior) / (n + alpha)
            else:
                predictions[y, x] = prior.copy()

    predictions = np.maximum(predictions, FLOOR)
    predictions = predictions / predictions.sum(axis=2, keepdims=True)
    return predictions


def save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_settlements, regime_info):
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
    round_id = round_data["id"]
    round_number = round_data.get("round_number", "?")
    width = round_data.get("map_width", 40)
    height = round_data.get("map_height", 40)
    num_seeds = round_data.get("seeds_count", 5)
    round_weight = round_data.get("round_weight", 1.0)

    log(f"=== Round {round_number} — weight={round_weight:.4f} ===")

    # === FETCH PER-SEED INITIAL STATES (FREE!) ===
    log("Fetching per-seed initial states from /rounds/{id}...")
    round_detail = api_get(f"rounds/{round_id}")
    initial_states = round_detail.get("initial_states", [])

    if not initial_states:
        log("WARNING: No initial_states! Falling back to shared initial_grid.")
        shared_grid = round_data.get("initial_grid")
        initial_states = [{"grid": shared_grid, "settlements": []} for _ in range(num_seeds)]

    per_seed_grids = {}
    per_seed_init_settlements = {}
    for i, state in enumerate(initial_states):
        per_seed_grids[i] = np.array(state.get("grid", []))
        per_seed_init_settlements[i] = state.get("settlements", [])
        land = int((per_seed_grids[i] != 10).sum())
        n_settl = len(per_seed_init_settlements[i])
        log(f"  Seed {i}: land={land}, init_settlements={n_settl}")

    # === BUDGET CHECK ===
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining = this_round['queries_max'] - this_round['queries_used']
    log(f"Budget: {remaining}/{this_round['queries_max']} queries")

    per_seed_counts = {s: np.zeros((height, width, NUM_CLASSES)) for s in range(num_seeds)}
    per_seed_obs = {s: np.zeros((height, width)) for s in range(num_seeds)}
    per_seed_sim_settlements = {s: [] for s in range(num_seeds)}

    # === PHASE 0: REGIME DETECTION (3 queries) ===
    log("Phase 0: Regime detection (3 queries on seeds 0,1,2)...")
    detection_queries = 3
    total_land_cells = 0
    total_settl_cells = 0

    for seed in range(min(detection_queries, num_seeds)):
        ig = per_seed_grids[seed]
        # Find center of land mass
        land_ys, land_xs = np.where(ig != 10)
        if len(land_ys) > 0:
            cy = int(np.median(land_ys))
            cx = int(np.median(land_xs))
        else:
            cy, cx = height // 2, width // 2
        vx = max(0, min(cx - 7, width - 15))
        vy = max(0, min(cy - 7, height - 15))

        try:
            result = simulate(round_id, seed, vx, vy, 15, 15)
            grid = result.get("grid", [])
            vp = result.get("viewport", {})
            rx, ry = vp.get("x", vx), vp.get("y", vy)
            settlements = result.get("settlements", [])
            if settlements:
                per_seed_sim_settlements[seed] = settlements

            for dy in range(len(grid)):
                for dx in range(len(grid[dy]) if grid[dy] else 0):
                    cy_, cx_ = ry + dy, rx + dx
                    if 0 <= cy_ < height and 0 <= cx_ < width:
                        cell = grid[dy][dx]
                        class_id = TERRAIN_MAP.get(cell, 0)
                        per_seed_counts[seed][cy_, cx_, class_id] += 1
                        per_seed_obs[seed][cy_, cx_] += 1
                        if cell != 10:  # not ocean
                            total_land_cells += 1
                            if cell == 1:
                                total_settl_cells += 1
            time.sleep(0.22)
        except Exception as e:
            log(f"  Detection query failed: {e}")

    remaining -= detection_queries
    settl_frac = total_settl_cells / max(total_land_cells, 1)
    regime = detect_regime(settl_frac)
    regime_priors = interpolate_priors(settl_frac)
    priors = get_priors(regime_priors)
    log(f"Regime: {regime.upper()} (settl_frac={settl_frac:.3f}, {total_settl_cells}/{total_land_cells} cells)")

    if remaining <= 0:
        log("No queries left! Submitting with detection-only obs.")
    else:
        # === PHASE A: SYSTEMATIC COVERAGE ===
        phase_b_budget = min(5, remaining // 4)
        phase_a_budget = remaining - phase_b_budget
        queries_per_seed = phase_a_budget // num_seeds

        log(f"Phase A: {queries_per_seed} viewports x {num_seeds} seeds = {queries_per_seed * num_seeds} queries")

        for seed in range(num_seeds):
            viewports = generate_optimal_viewports(per_seed_grids[seed].tolist(), seed, queries_per_seed)

            for i, (x, y, w, h) in enumerate(viewports):
                try:
                    result = simulate(round_id, seed, x, y, w, h)
                    grid = result.get("grid", [])
                    vp = result.get("viewport", {})
                    vx, vy = vp.get("x", x), vp.get("y", y)
                    settlements = result.get("settlements", [])
                    if settlements:
                        per_seed_sim_settlements[seed].extend(settlements)

                    for dy in range(len(grid)):
                        for dx in range(len(grid[dy]) if grid[dy] else 0):
                            cy, cx = vy + dy, vx + dx
                            if 0 <= cy < height and 0 <= cx < width:
                                class_id = TERRAIN_MAP.get(grid[dy][dx], 0)
                                per_seed_counts[seed][cy, cx, class_id] += 1
                                per_seed_obs[seed][cy, cx] += 1
                    time.sleep(0.22)
                except requests.exceptions.HTTPError as e:
                    if e.response and e.response.status_code == 429:
                        log("Rate limited, sleeping 5s")
                        time.sleep(5)
                    else:
                        log(f"Query failed: {e}")
                except Exception as e:
                    log(f"Query failed: {e}")

            obs_cells = int((per_seed_obs[seed] > 0).sum())
            ig = per_seed_grids[seed]
            land = int((ig != 10).sum())
            land_obs = int(((per_seed_obs[seed] > 0) & (ig != 10)).sum())
            log(f"  Seed {seed}: land_covered={land_obs}/{land} ({100*land_obs/max(land,1):.0f}%)")

        # === PHASE B: GAP FILLING ===
        my_rounds = api_get("my-rounds")
        this_round = [r for r in my_rounds if r['id'] == round_id][0]
        remaining_b = this_round['queries_max'] - this_round['queries_used']

        if remaining_b > 0:
            log(f"Phase B: {remaining_b} gap-filling queries")
            for i in range(remaining_b):
                seed = i % num_seeds
                ig = per_seed_grids[seed]

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
                    best_ratio = 999
                    for vy in range(0, height - 15 + 1, 3):
                        for vx in range(0, width - 15 + 1, 3):
                            land_count = float((ig[vy:vy+15, vx:vx+15] != 10).sum())
                            if land_count < 5: continue
                            obs_count = float(per_seed_obs[seed][vy:vy+15, vx:vx+15].sum())
                            ratio = obs_count / land_count
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
                        per_seed_sim_settlements[seed].extend(settlements)
                    for dy in range(len(grid)):
                        for dx in range(len(grid[dy]) if grid[dy] else 0):
                            cy, cx = vy + dy, vx + dx
                            if 0 <= cy < height and 0 <= cx < width:
                                class_id = TERRAIN_MAP.get(grid[dy][dx], 0)
                                per_seed_counts[seed][cy, cx, class_id] += 1
                                per_seed_obs[seed][cy, cx] += 1
                    time.sleep(0.22)
                except Exception as e:
                    log(f"Phase B query failed: {e}")

    regime_info = {
        "settlement_fraction": settl_frac,
        "label": regime,
    }
    save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_sim_settlements, regime_info)

    # === REFINE REGIME from ALL observations ===
    all_land = 0
    all_settl = 0
    for seed in range(num_seeds):
        ig = per_seed_grids[seed]
        for y in range(height):
            for x in range(width):
                n = per_seed_obs[seed][y, x]
                if n > 0 and ig[y, x] != 10:
                    all_land += n
                    all_settl += per_seed_counts[seed][y, x, 1]
    refined_frac = all_settl / max(all_land, 1)
    refined_regime = detect_regime(refined_frac)
    if refined_regime != regime:
        log(f"Regime refined: {regime} -> {refined_regime} (frac={refined_frac:.3f})")
        regime_priors = interpolate_priors(refined_frac)
        priors = get_priors(regime_priors)
        regime = refined_regime

    # === BUILD & SUBMIT ===
    log(f"Building predictions (regime={regime}, FLOOR={FLOOR}, alpha=2.0)...")
    for seed in range(num_seeds):
        ig = per_seed_grids[seed]
        pred = build_predictions(
            per_seed_counts[seed], per_seed_obs[seed],
            ig.tolist(), priors,
            width, height, alpha=2.0
        )

        land = int((ig != 10).sum())
        land_obs = int(((per_seed_obs[seed] > 0) & (ig != 10)).sum())
        avg_obs = float(per_seed_obs[seed][per_seed_obs[seed] > 0].mean()) if land_obs > 0 else 0
        log(f"  Seed {seed}: land={land_obs}/{land} ({100*land_obs/max(land,1):.0f}%), avg_obs={avg_obs:.1f}")

        try:
            result = submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted — {result.get('status', 'ok')}")
        except Exception as e:
            log(f"  Seed {seed}: FAILED — {e}")
        time.sleep(0.5)

    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    log(f"Done! Queries: {this_round['queries_used']}/{this_round['queries_max']}, Seeds: {this_round['seeds_submitted']}")
    log(f"Regime: {regime} | FLOOR: {FLOOR} | Alpha: 2.0")


def main():
    log("=== Astar Island v5 — Per-Regime Priors ===")
    my_rounds = api_get("my-rounds")

    active = [r for r in my_rounds if r.get("status") == "active"]
    if not active:
        log("No active rounds.")
        return

    for rd in active:
        if rd['seeds_submitted'] >= rd.get('seeds_count', 5):
            log(f"Round {rd.get('round_number')} already fully submitted, skipping")
            continue
        participate(rd)


if __name__ == "__main__":
    main()
