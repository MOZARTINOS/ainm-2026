#!/usr/bin/env python3
"""
Astar Island v7 — Replay-Powered Participation.

Strategy:
1. Find the most recent COMPLETED round with similar regime
2. Run 200 replays per seed on that round → per-cell distributions
3. Use those as informative priors for the ACTIVE round
4. Spend 50 queries on the active round for observation-based corrections
5. Blend replay priors + observations via Dirichlet update

Key insight: 20 replays per seed gives score ~73. 200 replays → ~80+.
The replay distributions capture spatial correlations that global priors miss.
"""
import requests
import json
import numpy as np
import time
import os
import sys
from datetime import datetime, timezone

TOKEN = os.environ.get("ASTAR_TOKEN",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs")
BASE = "https://api.ainm.no/astar-island"
FLOOR = 0.01
NUM_CLASSES = 6
PRED_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "notes")


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def api_get(path):
    r = requests.get(f"{BASE}/{path}", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30)
    r.raise_for_status()
    return r.json()


def api_post(path, data):
    r = requests.post(f"{BASE}/{path}", headers={
        "Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"
    }, json=data, timeout=60)
    return r


def fetch_replay(round_id, seed_index, max_retries=3):
    """Fetch one replay with retries."""
    for attempt in range(max_retries):
        try:
            r = api_post("replay", {"round_id": round_id, "seed_index": seed_index})
            if r.status_code == 429:
                time.sleep(10)
                continue
            if r.status_code == 200:
                data = r.json()
                if "frames" in data:
                    return data
            time.sleep(2)
        except Exception as e:
            time.sleep(5)
    return None


def build_replay_priors(round_id, n_replays_per_seed=40, seeds=range(5)):
    """Build per-cell distributions from replays of a completed round.

    Returns: dict of seed_index -> (40, 40, 6) probability arrays
    """
    priors = {}

    for seed in seeds:
        counts = np.zeros((40, 40, NUM_CLASSES))
        n_ok = 0

        for i in range(n_replays_per_seed):
            data = fetch_replay(round_id, seed)
            if data is None:
                continue

            final_grid = data["frames"][-1]["grid"]
            for y in range(40):
                for x in range(40):
                    c = PRED_MAP.get(final_grid[y][x], 0)
                    counts[y, x, c] += 1
            n_ok += 1

            if n_ok % 10 == 0:
                log(f"  Seed {seed}: {n_ok}/{n_replays_per_seed} replays done")
            time.sleep(0.25)

        if n_ok > 0:
            dist = counts / n_ok
            dist = np.maximum(dist, FLOOR / 2)
            dist = dist / dist.sum(axis=2, keepdims=True)
            priors[seed] = dist
            log(f"  Seed {seed}: {n_ok} replays → prior built")
        else:
            priors[seed] = None

    return priors


def find_best_reference_round(active_round):
    """Find the most recent completed round with similar regime."""
    my_rounds = api_get("my-rounds")
    completed = [r for r in my_rounds if r["status"] == "completed" and r.get("round_score")]

    if not completed:
        return None

    # Sort by round number descending — prefer most recent
    completed.sort(key=lambda r: r["round_number"], reverse=True)

    # Just use the most recent completed round
    # (same hidden parameters may persist between adjacent rounds)
    best = completed[0]
    log(f"Reference round: R{best['round_number']} (score={best['round_score']:.1f})")
    return best


def detect_regime_from_initial_state(initial_states):
    """Detect regime from free initial state data."""
    total_settl = 0
    total_land = 0
    for state in initial_states:
        grid = np.array(state["grid"])
        total_land += (grid != 10).sum()
        total_settl += len(state.get("settlements", []))

    settl_frac = total_settl / max(total_land / len(initial_states), 1)

    if settl_frac > 0.03:
        regime = "hot"
    elif settl_frac > 0.015:
        regime = "medium"
    else:
        regime = "dead"

    return regime, settl_frac


def observe_and_submit(active_round, replay_priors=None):
    """Run observations on active round and submit predictions."""
    round_id = active_round["id"]
    rn = active_round["round_number"]

    # Get per-seed initial states
    round_detail = api_get(f"rounds/{round_id}")
    initial_states = round_detail.get("initial_states", [])

    regime, settl_frac = detect_regime_from_initial_state(initial_states)
    log(f"Regime: {regime} (settlement fraction: {settl_frac:.3f})")

    budget = api_get("budget")
    queries_left = budget["queries_max"] - budget["queries_used"]
    log(f"Budget: {queries_left} queries remaining")

    if queries_left == 0:
        log("No queries left, submitting with replay priors only")

    # Allocate queries: 10 per seed
    queries_per_seed = queries_left // 5

    for seed in range(5):
        ig = np.array(initial_states[seed]["grid"])
        settlements = initial_states[seed].get("settlements", [])

        # Start with replay priors if available
        if replay_priors and seed in replay_priors and replay_priors[seed] is not None:
            pred = replay_priors[seed].copy()
            log(f"  Seed {seed}: using replay priors as base")
        else:
            # Fallback: uniform-ish prior from terrain type
            pred = np.full((40, 40, NUM_CLASSES), FLOOR)
            for y in range(40):
                for x in range(40):
                    t = int(ig[y, x])
                    if t == 10:  # ocean
                        pred[y, x] = [0.95, 0.01, 0.01, 0.01, 0.01, 0.01]
                    elif t == 5:  # mountain
                        pred[y, x] = [0.01, 0.01, 0.01, 0.01, 0.01, 0.95]
                    elif t == 4:  # forest
                        pred[y, x] = [0.10, 0.15, 0.01, 0.02, 0.71, 0.01]
                    elif t == 1:  # settlement
                        pred[y, x] = [0.40, 0.35, 0.01, 0.03, 0.20, 0.01]
                    else:  # plains/empty
                        pred[y, x] = [0.65, 0.22, 0.02, 0.03, 0.07, 0.01]
            pred = pred / pred.sum(axis=2, keepdims=True)
            log(f"  Seed {seed}: using terrain-based priors (no replay)")

        # Run observations
        obs_counts = np.zeros((40, 40, NUM_CLASSES))
        obs_total = np.zeros((40, 40))

        if queries_per_seed > 0:
            # Place viewports: tiled coverage
            viewports = []
            for vy in range(0, 40, 15):
                for vx in range(0, 40, 15):
                    w = min(15, 40 - vx)
                    h = min(15, 40 - vy)
                    viewports.append((vx, vy, w, h))

            # Also add shifted viewports for better coverage
            for vy in range(7, 40, 15):
                for vx in range(7, 40, 15):
                    w = min(15, 40 - vx)
                    h = min(15, 40 - vy)
                    if w >= 5 and h >= 5:
                        viewports.append((vx, vy, w, h))

            n_queries = min(queries_per_seed, len(viewports))
            for qi in range(n_queries):
                vx, vy, vw, vh = viewports[qi % len(viewports)]
                try:
                    r = api_post("simulate", {
                        "round_id": round_id, "seed_index": seed,
                        "viewport_x": vx, "viewport_y": vy,
                        "viewport_w": vw, "viewport_h": vh
                    })
                    if r.status_code != 200:
                        continue
                    result = r.json()
                    vp = result["viewport"]
                    grid_obs = result["grid"]
                    for dy in range(len(grid_obs)):
                        for dx in range(len(grid_obs[0])):
                            gy = vp["y"] + dy
                            gx = vp["x"] + dx
                            if 0 <= gy < 40 and 0 <= gx < 40:
                                c = PRED_MAP.get(grid_obs[dy][dx], 0)
                                obs_counts[gy, gx, c] += 1
                                obs_total[gy, gx] += 1
                    time.sleep(0.25)
                except Exception as e:
                    log(f"  Query error: {e}")

        # Blend replay priors with observations
        # For observed cells: Bayesian update with replay prior as informative prior
        alpha = 2.0  # Dirichlet concentration
        for y in range(40):
            for x in range(40):
                n = obs_total[y, x]
                if n > 0:
                    # Posterior = (obs_counts + alpha * prior) / (n + alpha)
                    pred[y, x] = (obs_counts[y, x] + alpha * pred[y, x]) / (n + alpha)

        # Apply floor and normalize
        pred = np.maximum(pred, FLOOR)
        pred = pred / pred.sum(axis=2, keepdims=True)

        # Submit
        r = api_post("submit", {
            "round_id": round_id, "seed_index": seed,
            "prediction": pred.tolist()
        })
        status = r.json().get("status", "error") if r.status_code == 200 else f"HTTP {r.status_code}"
        n_obs = int((obs_total > 0).sum())
        log(f"  Seed {seed}: {status} (obs={n_obs} cells)")

    # Save observations
    obs_path = os.path.join(NOTES_DIR, f"astar_obs_r{rn}.json")
    obs_save = {}
    for seed in range(5):
        obs_save[f"seed_{seed}"] = {
            "counts": obs_counts.tolist(),
            "total_obs": obs_total.tolist(),
        }
    with open(obs_path, "w") as f:
        json.dump(obs_save, f)
    log(f"Observations saved to {obs_path}")


def main():
    log("=== Astar Island v7 — Replay-Powered Participation ===")

    # Find active round
    my_rounds = api_get("my-rounds")
    active = [r for r in my_rounds if r["status"] == "active"]

    if not active:
        log("No active round found!")
        return False

    active_round = active[0]
    rn = active_round["round_number"]
    weight = active_round.get("round_weight", 1)
    queries_used = active_round.get("queries_used", 0)
    seeds_submitted = active_round.get("seeds_submitted", 0)

    log(f"Active: R{rn} (weight={weight:.4f})")

    if seeds_submitted >= 5 and queries_used >= 50:
        log(f"Already fully submitted ({seeds_submitted}/5 seeds, {queries_used}/50 queries)")
        return True

    # Phase 1: Build replay priors from reference round
    ref_round = find_best_reference_round(active_round)
    replay_priors = None

    if ref_round:
        log(f"Building replay priors from R{ref_round['round_number']}...")
        replay_priors = build_replay_priors(
            ref_round["id"],
            n_replays_per_seed=40,  # 40 replays × 5 seeds = 200 total
            seeds=range(5)
        )

    # Phase 2: Observe and submit
    log("Phase 2: Observations + submission")
    observe_and_submit(active_round, replay_priors)

    log("=== Done! ===")
    return True


if __name__ == "__main__":
    main()
