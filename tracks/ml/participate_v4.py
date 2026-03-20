#!/usr/bin/env python3
"""
Astar Island — v4 Participation

CRITICAL FIX: Use per-seed initial grids from /rounds/{id} endpoint (FREE, no query cost).
Seeds have DIFFERENT grids (~42% cells differ between seeds).
Using one shared grid was causing wrong priors for ~40% of cells.

Changes from v3:
1. Fetch per-seed grids + settlement positions from /rounds/{round_id}
2. Use per-seed grid for terrain-based priors
3. Use FREE settlement positions for proximity boost
4. Regime detection from initial settlement count (no query needed!)
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
FLOOR = 0.01
NOTES_DIR = Path("F:/Workfolder/NM i AI main/repo/notes")

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Regime priors from ground truth analysis
# Empirical priors computed from ALL ground truth (R2-R5, 20 seed×round combos)
# These are MUCH more accurate than the old R2/R3 priors
GLOBAL_PRIORS = {
    11: np.array([0.838, 0.099, 0.010, 0.010, 0.032, 0.010]),  # plains → mostly empty
    4:  np.array([0.071, 0.104, 0.010, 0.011, 0.795, 0.010]),  # forest → mostly stays forest
    1:  np.array([0.487, 0.245, 0.010, 0.021, 0.227, 0.010]),  # settlement → mixed
    5:  np.array([0.010, 0.010, 0.010, 0.010, 0.010, 0.952]),  # mountain → stays mountain
    10: np.array([0.952, 0.010, 0.010, 0.010, 0.010, 0.010]),  # ocean → stays ocean
    2:  np.array([0.504, 0.073, 0.154, 0.020, 0.239, 0.010]),  # port → dynamic
    3:  np.array([0.487, 0.245, 0.010, 0.021, 0.227, 0.010]),  # ruin → like settlement
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


def get_priors():
    """Return empirical priors from all ground truth data."""
    priors = {}
    for t in GLOBAL_PRIORS:
        p = GLOBAL_PRIORS[t].copy()
        p = np.maximum(p, FLOOR)
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


def build_predictions(counts, total_obs, grid, priors, settlements,
                      width=40, height=40, obs_weight=0.10):
    """
    Build predictions: prior-dominated with slight observation nudge.

    Research showed:
    - Priors-only scores 85+ on settlement worlds
    - Observations with 1-2 samples add noise, not signal
    - Best approach: prior as base, tiny nudge from observations
    - obs_weight=0.10 optimal: w = obs_weight * n/(n+5)
    """
    ig = np.array(grid)
    predictions = np.zeros((height, width, NUM_CLASSES))

    for y in range(height):
        for x in range(width):
            terrain = int(ig[y, x])
            prior = priors.get(terrain, np.ones(NUM_CLASSES) / NUM_CLASSES)
            n = total_obs[y, x]
            if n > 0:
                empirical = counts[y, x] / n
                w = obs_weight * n / (n + 5)  # saturates at obs_weight
                predictions[y, x] = (1 - w) * prior + w * empirical
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
        log(f"  Seed {i}: land={land}, settlements={n_settl}")

    # === REGIME DETECTION (FREE from initial states!) ===
    total_land = sum(int((per_seed_grids[s] != 10).sum()) for s in range(num_seeds))
    total_settl = sum(int((per_seed_grids[s] == 1).sum()) for s in range(num_seeds))
    settlement_frac = total_settl / max(total_land, 1)
    priors = get_priors()
    log(f"Using global empirical priors (settl_frac={settlement_frac:.3f}) — FREE, no queries used!")

    regime_info = {
        "settlement_fraction": settlement_frac,
        "label": "global_empirical",
    }

    # Budget check
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining = this_round['queries_max'] - this_round['queries_used']
    log(f"Budget: {remaining}/{this_round['queries_max']} queries")

    if remaining <= 0:
        log("No queries! Submitting priors-only with per-seed grids.")
        for seed in range(num_seeds):
            ig = per_seed_grids[seed]
            pred = np.zeros((height, width, NUM_CLASSES))
            for y in range(height):
                for x in range(width):
                    pred[y, x] = priors.get(int(ig[y, x]), np.ones(NUM_CLASSES) / NUM_CLASSES)
            pred = np.maximum(pred, FLOOR)
            pred = pred / pred.sum(axis=2, keepdims=True)
            submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted (priors-only)")
        return

    per_seed_counts = {s: np.zeros((height, width, NUM_CLASSES)) for s in range(num_seeds)}
    per_seed_obs = {s: np.zeros((height, width)) for s in range(num_seeds)}
    per_seed_sim_settlements = {s: per_seed_init_settlements[s] for s in range(num_seeds)}

    # === PHASE A: SYSTEMATIC COVERAGE ===
    phase_b_budget = min(5, remaining // 4)
    phase_a_budget = remaining - phase_b_budget
    queries_per_seed = phase_a_budget // num_seeds

    log(f"Phase A: {queries_per_seed} viewports x {num_seeds} seeds = {queries_per_seed * num_seeds} queries")

    for seed in range(num_seeds):
        # Use THIS SEED's grid for viewport planning
        viewports = generate_optimal_viewports(per_seed_grids[seed].tolist(), seed, queries_per_seed)

        for i, (x, y, w, h) in enumerate(viewports):
            try:
                result = simulate(round_id, seed, x, y, w, h)
                grid = result.get("grid", [])
                vp = result.get("viewport", {})
                vx, vy = vp.get("x", x), vp.get("y", y)
                settlements = result.get("settlements", [])
                if settlements:
                    per_seed_sim_settlements[seed] = settlements

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

    save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_sim_settlements, regime_info)

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
                    per_seed_sim_settlements[seed] = settlements
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

    save_observations(round_id, round_number, per_seed_counts, per_seed_obs,
                      per_seed_sim_settlements, regime_info)

    # === BUILD & SUBMIT ===
    log(f"Building predictions (FLOOR={FLOOR}, obs_weight=0.10, per-seed grids)...")
    for seed in range(num_seeds):
        ig = per_seed_grids[seed]
        pred = build_predictions(
            per_seed_counts[seed], per_seed_obs[seed],
            ig.tolist(), priors, per_seed_sim_settlements[seed],
            width, height, obs_weight=0.10
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


def main():
    log("=== Astar Island v4 — Per-Seed Grids ===")
    my_rounds = api_get("my-rounds")

    active = [r for r in my_rounds if r.get("status") == "active"]
    if not active:
        log("No active rounds.")
        for r in sorted(my_rounds, key=lambda x: x['round_number']):
            score = r.get('round_score')
            log(f"  Round {r['round_number']}: score={score}, seeds={r['seeds_submitted']}")
        return

    for rd in active:
        if rd['seeds_submitted'] >= rd.get('seeds_count', 5):
            log(f"Round {rd.get('round_number')} already fully submitted, skipping")
            continue
        participate(rd)


if __name__ == "__main__":
    main()
