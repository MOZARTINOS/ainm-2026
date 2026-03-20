#!/usr/bin/env python3
"""
Astar Island — v6 Participation (REPLAY-POWERED)

THE KEY INSIGHT: POST /replay is FREE and returns full 50-step simulation
with different sim_seed each time. Running 200 replays per seed gives us
an approximation of the ground truth distribution.

Strategy:
1. Phase 0: Regime detection from 3 queries (keeps prior approach as fallback)
2. Phase 1: Run 200 replays per seed (FREE!) to build per-cell distributions
3. Phase 2: Use queries for observation-based corrections on uncertain cells
4. Submit: replay-based predictions + observation corrections

This should score 85-95+ because replay distributions ≈ ground truth.
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
N_REPLAYS = 200  # Per seed — takes ~50s per seed at 0.25s rate limit

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# Fallback regime priors (from v5)
REGIME_PRIORS = {
    "dead": {
        11: np.array([0.9515, 0.0096, 0.0096, 0.0096, 0.0099, 0.0096]),
        4:  np.array([0.0247, 0.0096, 0.0096, 0.0096, 0.9367, 0.0096]),
        1:  np.array([0.6636, 0.0178, 0.0097, 0.0097, 0.2894, 0.0097]),
        5:  np.array([0.0095, 0.0095, 0.0095, 0.0095, 0.0095, 0.9524]),
        10: np.array([0.9524, 0.0095, 0.0095, 0.0095, 0.0095, 0.0095]),
    },
    "medium": {
        11: np.array([0.8300, 0.1041, 0.0099, 0.0108, 0.0354, 0.0099]),
        4:  np.array([0.0742, 0.1108, 0.0099, 0.0116, 0.7837, 0.0099]),
        1:  np.array([0.4534, 0.2777, 0.0098, 0.0236, 0.2256, 0.0098]),
        5:  np.array([0.0095, 0.0095, 0.0095, 0.0095, 0.0095, 0.9524]),
        10: np.array([0.9524, 0.0095, 0.0095, 0.0095, 0.0095, 0.0095]),
    },
    "hot": {
        11: np.array([0.6775, 0.2156, 0.0166, 0.0252, 0.0551, 0.0099]),
        4:  np.array([0.1285, 0.2209, 0.0139, 0.0257, 0.6012, 0.0099]),
        1:  np.array([0.3725, 0.4064, 0.0098, 0.0375, 0.1640, 0.0098]),
        5:  np.array([0.0095, 0.0095, 0.0095, 0.0095, 0.0095, 0.9524]),
        10: np.array([0.9524, 0.0095, 0.0095, 0.0095, 0.0095, 0.0095]),
    },
}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def api_get(path):
    r = requests.get(f"{BASE}/{path}", headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def simulate(round_id, seed, x, y, w=15, h=15):
    r = requests.post(f"{BASE}/simulate", headers=headers, json={
        "round_id": round_id, "seed_index": seed,
        "viewport_x": x, "viewport_y": y, "viewport_w": w, "viewport_h": h
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def submit_prediction(round_id, seed, prediction):
    r = requests.post(f"{BASE}/submit", headers=headers, json={
        "round_id": round_id, "seed_index": seed, "prediction": prediction
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def run_replays_for_seed(round_id, seed_index, n_replays, height=40, width=40):
    """Run n replays, return per-cell class counts from final frames."""
    counts = np.zeros((height, width, NUM_CLASSES))
    n_success = 0

    for i in range(n_replays):
        try:
            r = requests.post(f"{BASE}/replay", headers=headers, json={
                "round_id": round_id, "seed_index": seed_index
            }, timeout=30)

            if r.status_code == 429:
                log(f"  Rate limited at replay {i+1}, sleeping 10s")
                time.sleep(10)
                continue

            r.raise_for_status()
            data = r.json()

            if "detail" in data:
                log(f"  Replay unavailable: {data['detail']}")
                return None, 0

            final = data["frames"][-1]
            grid = final["grid"]

            for y in range(min(len(grid), height)):
                for x in range(min(len(grid[y]), width)):
                    class_id = TERRAIN_MAP.get(grid[y][x], 0)
                    counts[y, x, class_id] += 1

            n_success += 1
            time.sleep(0.22)  # Stay under 5 req/s

        except Exception as e:
            if "429" in str(e):
                time.sleep(10)
            else:
                log(f"  Replay {i+1} error: {e}")
                time.sleep(1)

    return counts, n_success


def participate(round_data):
    round_id = round_data["id"]
    round_number = round_data.get("round_number", "?")
    width = round_data.get("map_width", 40)
    height = round_data.get("map_height", 40)
    num_seeds = round_data.get("seeds_count", 5)
    round_weight = round_data.get("round_weight", 1.0)

    log(f"=== Round {round_number} — weight={round_weight:.4f} ===")

    # === FETCH PER-SEED INITIAL STATES (FREE!) ===
    round_detail = api_get(f"rounds/{round_id}")
    initial_states = round_detail.get("initial_states", [])

    if not initial_states:
        shared_grid = round_data.get("initial_grid")
        initial_states = [{"grid": shared_grid, "settlements": []} for _ in range(num_seeds)]

    per_seed_grids = {}
    for i, state in enumerate(initial_states):
        per_seed_grids[i] = np.array(state.get("grid", []))
        land = int((per_seed_grids[i] != 10).sum())
        log(f"  Seed {i}: land={land}")

    # === PHASE 1: BUILD PRIORS FROM REPLAY OF PREVIOUS ROUND (FREE!) ===
    # Replay only works on completed rounds. Use most recent completed round
    # to build precise per-terrain priors, then use queries on active round.
    my_rounds = api_get("my-rounds")
    completed = sorted(
        [r for r in my_rounds if r.get("status") == "completed" and r.get("round_score")],
        key=lambda r: r["round_number"], reverse=True
    )

    replay_priors = None
    if completed:
        prev_round = completed[0]
        prev_id = prev_round["id"]
        prev_num = prev_round["round_number"]
        log(f"Phase 1: Running 50 replays on R{prev_num} for calibrated priors (FREE)...")

        # Get previous round initial states for terrain mapping
        prev_detail = api_get(f"rounds/{prev_id}")
        prev_states = prev_detail.get("initial_states", [])

        terrain_counts = {t: np.zeros(NUM_CLASSES) for t in [10, 11, 4, 1, 5, 2, 3]}
        terrain_n = {t: 0 for t in terrain_counts}
        n_success = 0

        for i in range(50):
            try:
                r = requests.post(f"{BASE}/replay", headers=headers, json={
                    "round_id": prev_id, "seed_index": i % 5
                }, timeout=30)
                if r.status_code == 429:
                    time.sleep(10)
                    continue
                r.raise_for_status()
                data = r.json()
                if "detail" in data:
                    log(f"  Replay unavailable: {data['detail']}")
                    break

                seed_idx = i % 5
                if seed_idx < len(prev_states):
                    ig = np.array(prev_states[seed_idx]["grid"])
                    final = data["frames"][-1]["grid"]
                    for y in range(40):
                        for x in range(40):
                            t = int(ig[y, x])
                            c = TERRAIN_MAP.get(final[y][x], 0)
                            if t in terrain_counts:
                                terrain_counts[t][c] += 1
                                terrain_n[t] += 1
                n_success += 1
                if (i + 1) % 10 == 0:
                    log(f"  {i+1}/50 replays done")
                time.sleep(0.3)
            except Exception as e:
                log(f"  Replay {i+1} error: {e}")
                time.sleep(2)

        if n_success >= 10:
            replay_priors = {}
            for t, counts in terrain_counts.items():
                if terrain_n[t] > 0:
                    p = counts / terrain_n[t]
                    p = np.maximum(p, FLOOR)
                    p /= p.sum()
                    replay_priors[t] = p
            log(f"  Replay priors built from {n_success} replays of R{prev_num}")
        else:
            log(f"  Only {n_success} replays succeeded, using static regime priors")

    # === PHASE 2: QUERY-BASED OBSERVATIONS + REPLAY PRIORS ===
    log("Phase 2: Query-based observations with replay-calibrated priors...")
    _participate_with_queries(round_id, round_number, width, height,
                               num_seeds, per_seed_grids, initial_states,
                               override_priors=replay_priors)

    # Final status
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    log(f"Done! Queries: {this_round['queries_used']}/{this_round['queries_max']}, Seeds: {this_round['seeds_submitted']}")


def _participate_with_queries(round_id, round_number, width, height,
                               num_seeds, per_seed_grids, initial_states,
                               override_priors=None):
    """Query-based participation with optional replay-calibrated priors."""
    # Budget check
    my_rounds = api_get("my-rounds")
    this_round = [r for r in my_rounds if r['id'] == round_id][0]
    remaining = this_round['queries_max'] - this_round['queries_used']
    log(f"Budget: {remaining}/{this_round['queries_max']} queries")

    if remaining <= 0:
        log("No queries left!")
        return

    per_seed_counts = {s: np.zeros((height, width, NUM_CLASSES)) for s in range(num_seeds)}
    per_seed_obs = {s: np.zeros((height, width)) for s in range(num_seeds)}

    # Regime detection (3 queries)
    log("Regime detection (3 queries)...")
    total_land = total_settl = 0
    for seed in range(min(3, num_seeds)):
        ig = per_seed_grids[seed]
        land_ys, land_xs = np.where(ig != 10)
        if len(land_ys) > 0:
            cy, cx = int(np.median(land_ys)), int(np.median(land_xs))
        else:
            cy, cx = height // 2, width // 2
        vx = max(0, min(cx - 7, width - 15))
        vy = max(0, min(cy - 7, height - 15))

        try:
            result = simulate(round_id, seed, vx, vy, 15, 15)
            grid = result.get("grid", [])
            vp = result.get("viewport", {})
            rx, ry = vp.get("x", vx), vp.get("y", vy)
            for dy in range(len(grid)):
                for dx in range(len(grid[dy]) if grid[dy] else 0):
                    cy_, cx_ = ry + dy, rx + dx
                    if 0 <= cy_ < height and 0 <= cx_ < width:
                        cell = grid[dy][dx]
                        class_id = TERRAIN_MAP.get(cell, 0)
                        per_seed_counts[seed][cy_, cx_, class_id] += 1
                        per_seed_obs[seed][cy_, cx_] += 1
                        if cell != 10:
                            total_land += 1
                            if cell == 1: total_settl += 1
            time.sleep(0.22)
        except Exception as e:
            log(f"  Detection query failed: {e}")

    remaining -= 3
    settl_frac = total_settl / max(total_land, 1)

    if settl_frac < 0.05:
        regime = "dead"
    elif settl_frac < 0.15:
        regime = "medium"
    else:
        regime = "hot"

    # Use replay priors if available, else fall back to static regime priors
    if override_priors:
        priors = override_priors
        log(f"Regime: {regime} (settl_frac={settl_frac:.3f}) — using REPLAY priors")
    else:
        priors_raw = REGIME_PRIORS[regime]
        priors = {}
        for t, p in priors_raw.items():
            p = np.maximum(p.copy(), FLOOR)
            priors[t] = p / p.sum()
        log(f"Regime: {regime} (settl_frac={settl_frac:.3f}) — using static priors")

    # Systematic coverage
    phase_b = min(5, remaining // 4)
    phase_a = remaining - phase_b
    qps = phase_a // num_seeds

    log(f"Phase A: {qps} viewports x {num_seeds} seeds")
    for seed in range(num_seeds):
        ig = per_seed_grids[seed]
        H, W = ig.shape
        land_mask = (ig != 10).astype(float)
        covered = (per_seed_obs[seed] > 0).astype(float)

        for _ in range(qps):
            uncovered = land_mask * (1 - np.minimum(covered, 1))
            best_score, best_x, best_y = -1, 0, 0
            for vy in range(0, H - 15 + 1, 2):
                for vx in range(0, W - 15 + 1, 2):
                    score = uncovered[vy:vy+15, vx:vx+15].sum()
                    if score > best_score:
                        best_score, best_x, best_y = score, vx, vy

            try:
                result = simulate(round_id, seed, best_x, best_y, 15, 15)
                grid = result.get("grid", [])
                vp = result.get("viewport", {})
                vx, vy = vp.get("x", best_x), vp.get("y", best_y)
                for dy in range(len(grid)):
                    for dx in range(len(grid[dy]) if grid[dy] else 0):
                        cy, cx = vy + dy, vx + dx
                        if 0 <= cy < height and 0 <= cx < width:
                            class_id = TERRAIN_MAP.get(grid[dy][dx], 0)
                            per_seed_counts[seed][cy, cx, class_id] += 1
                            per_seed_obs[seed][cy, cx] += 1
                            covered[cy, cx] = 1
                time.sleep(0.22)
            except Exception as e:
                log(f"  Query failed: {e}")

        land = int(land_mask.sum())
        obs = int(covered.sum())
        log(f"  Seed {seed}: {obs}/{land} ({100*obs/max(land,1):.0f}%)")

    # Build & submit
    log(f"Building predictions (regime={regime}, alpha=2.0)...")
    for seed in range(num_seeds):
        ig = per_seed_grids[seed]
        pred = np.zeros((height, width, NUM_CLASSES))
        for y in range(height):
            for x in range(width):
                terrain = int(ig[y, x])
                prior = priors.get(terrain, np.ones(NUM_CLASSES) / NUM_CLASSES)
                n = per_seed_obs[seed][y, x]
                if n > 0:
                    pred[y, x] = (per_seed_counts[seed][y, x] + 2.0 * prior) / (n + 2.0)
                else:
                    pred[y, x] = prior.copy()

        pred = np.maximum(pred, FLOOR)
        pred = pred / pred.sum(axis=2, keepdims=True)

        try:
            result = submit_prediction(round_id, seed, pred.tolist())
            log(f"  Seed {seed}: submitted — {result.get('status', 'ok')}")
        except Exception as e:
            log(f"  Seed {seed}: FAILED — {e}")
        time.sleep(0.5)


def main():
    log("=== Astar Island v6 — REPLAY-POWERED ===")
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
