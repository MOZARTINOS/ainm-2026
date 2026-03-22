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
    """Build per-terrain-type distributions from replays of a completed round.

    Returns: dict of terrain_type -> (6,) probability arrays
    This works for ANY seed because it matches by terrain type, not position.
    """
    # Get reference round's initial states for terrain mapping
    try:
        ref_detail = api_get(f"rounds/{round_id}")
        ref_states = ref_detail.get("initial_states", [])
    except:
        ref_states = []

    terrain_counts = {}  # terrain_type -> (6,) count array
    terrain_n = {}
    n_ok = 0

    for seed in seeds:
        ref_grid = np.array(ref_states[seed]["grid"]) if seed < len(ref_states) else None

        for i in range(n_replays_per_seed):
            data = fetch_replay(round_id, seed)
            if data is None:
                continue

            final_grid = data["frames"][-1]["grid"]
            if ref_grid is None:
                ref_grid = np.array(data["frames"][0]["grid"])

            for y in range(40):
                for x in range(40):
                    t = int(ref_grid[y, x])
                    c = PRED_MAP.get(final_grid[y][x], 0)
                    if t not in terrain_counts:
                        terrain_counts[t] = np.zeros(NUM_CLASSES)
                        terrain_n[t] = 0
                    terrain_counts[t][c] += 1
                    terrain_n[t] += 1
            n_ok += 1

            if n_ok % 20 == 0:
                log(f"  {n_ok}/{n_replays_per_seed * len(list(seeds))} replays done")
            time.sleep(0.25)

    # Normalize to probabilities
    priors = {}
    names = ["empty", "settl", "port", "ruin", "forest", "mount"]
    for t, counts in terrain_counts.items():
        if terrain_n[t] > 0:
            p = counts / terrain_n[t]
            p = np.maximum(p, FLOOR)
            p /= p.sum()
            priors[t] = p

    t_names = {10: "ocean", 11: "plains", 4: "forest", 1: "settl", 5: "mount"}
    for t in sorted(priors.keys()):
        tn = t_names.get(t, str(t))
        log(f"  {tn}: {' '.join(f'{names[i]}={priors[t][i]:.3f}' for i in range(NUM_CLASSES))}")

    log(f"  Built from {n_ok} replays total")
    return priors


def classify_round_regime(round_data):
    """Classify a round's regime from its initial grid settlement count."""
    ig = np.array(round_data.get("initial_grid", []))
    if ig.size == 0:
        return "unknown", 0
    land = (ig != 10).sum()
    settl = np.isin(ig, [1, 2]).sum()
    frac = settl / max(land, 1)
    if frac > 0.03:
        return "hot", frac
    elif frac > 0.015:
        return "medium", frac
    else:
        return "dead", frac


def find_best_reference_round(active_round, active_regime):
    """Find the most recent completed round with MATCHING regime."""
    my_rounds = api_get("my-rounds")
    completed = [r for r in my_rounds if r["status"] == "completed" and r.get("round_score")]

    if not completed:
        return None

    # Classify each completed round and find same-regime matches
    same_regime = []
    for r in completed:
        regime, frac = classify_round_regime(r)
        r["_regime"] = regime
        r["_frac"] = frac
        if regime == active_regime:
            same_regime.append(r)

    # Prefer same regime, most recent
    if same_regime:
        same_regime.sort(key=lambda r: r["round_number"], reverse=True)
        best = same_regime[0]
        log(f"Reference round: R{best['round_number']} (regime={best['_regime']}, frac={best['_frac']:.3f})")
        return best

    # Fallback: most recent completed regardless of regime
    completed.sort(key=lambda r: r["round_number"], reverse=True)
    best = completed[0]
    regime, frac = best.get("_regime", "?"), best.get("_frac", 0)
    log(f"WARNING: No same-regime round found! Using R{best['round_number']} (regime={regime})")
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


def load_nca_prediction(initial_grid):
    """Use trained NCA model to predict from initial grid."""
    try:
        import torch
        model_path = os.path.join(SCRIPT_DIR, "nca_model.pt")
        if not os.path.exists(model_path):
            return None

        from train_nca import SimpleNCA, grid_to_onehot
        model = SimpleNCA(hidden=64)
        model.load_state_dict(torch.load(model_path, weights_only=True))
        model.eval()

        x = grid_to_onehot(initial_grid)
        x_t = torch.from_numpy(x).unsqueeze(0)  # (1, 8, 40, 40)
        with torch.no_grad():
            pred = model(x_t)  # (1, 6, 40, 40)
        return pred.numpy()[0].transpose(1, 2, 0)  # (40, 40, 6)
    except Exception as e:
        log(f"  NCA failed: {e}")
        return None


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

        # Layer 1: NCA prediction (trained on all rounds)
        nca_pred = load_nca_prediction(initial_states[seed]["grid"])

        # Layer 2: Replay priors (per-terrain-type from same-regime reference round)
        has_replay = replay_priors and len(replay_priors) > 0

        # Build per-cell prediction from terrain-type replay priors
        if has_replay:
            replay_pred = np.zeros((40, 40, NUM_CLASSES))
            for y in range(40):
                for x in range(40):
                    t = int(ig[y, x])
                    if t in replay_priors:
                        replay_pred[y, x] = replay_priors[t]
                    else:
                        replay_pred[y, x] = 1.0 / NUM_CLASSES
            replay_pred = np.maximum(replay_pred, FLOOR)
            replay_pred /= replay_pred.sum(axis=2, keepdims=True)

        if has_replay and nca_pred is not None:
            # Blend NCA + replay: 50/50
            pred = 0.5 * replay_pred + 0.5 * nca_pred
            log(f"  Seed {seed}: NCA + replay blend")
        elif has_replay:
            pred = replay_pred.copy()
            log(f"  Seed {seed}: replay priors only")
        elif nca_pred is not None:
            pred = nca_pred.copy()
            log(f"  Seed {seed}: NCA prediction only")
        else:
            # Fallback: terrain-based priors
            pred = np.full((40, 40, NUM_CLASSES), FLOOR)
            for y in range(40):
                for x in range(40):
                    t = int(ig[y, x])
                    if t == 10:
                        pred[y, x] = [0.95, 0.01, 0.01, 0.01, 0.01, 0.01]
                    elif t == 5:
                        pred[y, x] = [0.01, 0.01, 0.01, 0.01, 0.01, 0.95]
                    elif t == 4:
                        pred[y, x] = [0.10, 0.15, 0.01, 0.02, 0.71, 0.01]
                    elif t == 1:
                        pred[y, x] = [0.40, 0.35, 0.01, 0.03, 0.20, 0.01]
                    else:
                        pred[y, x] = [0.65, 0.22, 0.02, 0.03, 0.07, 0.01]
            pred = pred / pred.sum(axis=2, keepdims=True)
            log(f"  Seed {seed}: terrain-based fallback")

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
        alpha = 1.0  # Dirichlet concentration — lower = trust observations more
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

    # Detect active round regime
    round_detail = api_get(f"rounds/{active_round['id']}")
    initial_states = round_detail.get("initial_states", [])
    active_regime, active_frac = detect_regime_from_initial_state(initial_states)
    log(f"Active round regime: {active_regime} (frac={active_frac:.3f})")

    # Phase 1: Build replay priors from SAME-REGIME reference round
    ref_round = find_best_reference_round(active_round, active_regime)
    replay_priors = None

    if ref_round:
        log(f"Building replay priors from R{ref_round['round_number']}...")
        replay_priors = build_replay_priors(
            ref_round["id"],
            n_replays_per_seed=30,  # 30 replays × 5 seeds = 150 total (by terrain type)
            seeds=range(5)
        )

    # Phase 2: Observe and submit
    log("Phase 2: Observations + submission")
    observe_and_submit(active_round, replay_priors)

    log("=== Done! ===")
    return True


if __name__ == "__main__":
    main()
