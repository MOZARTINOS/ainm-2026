#!/usr/bin/env python3
"""
Astar Island v8 — GT-Prior Blended Participation.

Key improvements over v7:
1. Regime detection via REPLAY of previous round (not initial grid frac)
2. Blended GT priors from 2 closest reference rounds (weighted by distance)
3. Logarithmic pooling for observation blending (w_prior=0.85, w_obs=0.15)
4. Frontier score: settlement proximity affects expansion probability
5. Coast-aware: port probability boosted for coastal cells
6. Temperature scaling T=1.2 for better entropy matching
7. Settlement metadata from observations for regime refinement
8. Full grid coverage: 9 viewports × 5 seeds = 45 queries (< 50 budget)
9. NO NCA blend (NCA hurts: 48 vs replay 73)
"""
import requests
import json
import numpy as np
import time
import os
from datetime import datetime, timezone

TOKEN = os.environ.get("ASTAR_TOKEN",
    "YOUR_JWT_TOKEN_HERE")
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


def temperature_scale(probs, T=1.2):
    """Apply temperature scaling to soften/sharpen distribution."""
    lp = np.log(probs + 1e-10) / T
    e = np.exp(lp - lp.max())
    return e / e.sum()


def estimate_regime_from_replays(round_id, initial_states, n=10):
    """Estimate regime by running replays on a completed round."""
    fracs = []
    for i in range(n):
        try:
            r = api_post("replay", {"round_id": round_id, "seed_index": i % 5})
            if r.status_code == 200:
                d = r.json()
                if "frames" in d:
                    final = np.array(d["frames"][-1]["grid"])
                    ig = np.array(initial_states[i % 5]["grid"])
                    land = ig != 10
                    sf = (final[land] == 1).sum() / land.sum()
                    fracs.append(sf)
            time.sleep(0.3)
        except:
            time.sleep(2)
    return np.mean(fracs) if fracs else 0.1


def get_gt_settlement_fractions():
    """Get GT settlement fractions for all completed rounds with analysis."""
    my_rounds = api_get("my-rounds")
    completed = [r for r in my_rounds if r["status"] == "completed" and r.get("round_score")]
    gt_fracs = {}
    for rd in completed:
        rn = rd["round_number"]
        rid = rd["id"]
        try:
            resp = requests.get(f"{BASE}/analysis/{rid}/0",
                                headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30)
            if resp.status_code == 200:
                gt = np.array(resp.json()["ground_truth"])
                ig = np.array(resp.json().get("initial_grid", []))
                land = ig != 10
                gt_fracs[rn] = gt[land, 1].mean()
        except:
            pass
    return gt_fracs


def build_blended_gt_priors(est_frac, gt_fracs, rounds_dict):
    """Build per-terrain priors blended from 2 closest reference rounds by GT settlement fraction."""
    sorted_refs = sorted(gt_fracs.items(), key=lambda x: abs(x[1] - est_frac))
    ref1_rn = sorted_refs[0][0]
    ref2_rn = sorted_refs[1][0] if len(sorted_refs) > 1 else ref1_rn

    log(f"Blend refs: R{ref1_rn} ({gt_fracs[ref1_rn]:.4f}) + R{ref2_rn} ({gt_fracs[ref2_rn]:.4f})")

    terrain_priors = {}
    for ref_rn in [ref1_rn, ref2_rn]:
        w = 1.0 / (abs(gt_fracs[ref_rn] - est_frac) + 0.01)
        rid = rounds_dict[ref_rn]["id"]
        for seed in range(5):
            try:
                resp = requests.get(f"{BASE}/analysis/{rid}/{seed}",
                                    headers={"Authorization": f"Bearer {TOKEN}"}, timeout=30)
                if resp.status_code != 200:
                    continue
                d = resp.json()
                gt = np.array(d["ground_truth"])
                ig = np.array(d.get("initial_grid", []))
                for t in [10, 11, 4, 1, 5, 2, 3, 0]:
                    mask = ig == t
                    if mask.sum() > 0:
                        if t not in terrain_priors:
                            terrain_priors[t] = {"sum": np.zeros(NUM_CLASSES), "n": 0}
                        terrain_priors[t]["sum"] += gt[mask].sum(axis=0) * w
                        terrain_priors[t]["n"] += mask.sum() * w
            except:
                pass

    result = {}
    names = ["empty", "settl", "port", "ruin", "forest", "mount"]
    for t in terrain_priors:
        p = terrain_priors[t]["sum"] / terrain_priors[t]["n"]
        p = np.maximum(p, FLOOR)
        p /= p.sum()
        result[t] = p

    for t in [11, 4, 1]:
        if t in result:
            tn = {11: "plains", 4: "forest", 1: "settl"}.get(t)
            log(f"  {tn}: {' '.join(f'{names[i]}={result[t][i]:.3f}' for i in range(NUM_CLASSES))}")

    return result


def compute_frontier_score(ig, settlements):
    """Compute frontier score: exp(-dist/3) for each cell based on settlement proximity."""
    H, W = ig.shape
    # Distance to nearest settlement
    settl_positions = [(s["y"], s["x"]) for s in settlements]
    if not settl_positions:
        # Use grid settlement cells
        settl_positions = list(zip(*np.where(np.isin(ig, [1, 2]))))

    dist_map = np.full((H, W), 99.0)
    for sy, sx in settl_positions:
        for y in range(H):
            for x in range(W):
                d = abs(y - sy) + abs(x - sx)
                dist_map[y, x] = min(dist_map[y, x], d)

    frontier = np.exp(-dist_map / 3.0)
    return frontier


def compute_coastal_mask(ig):
    """Compute which cells are coastal (adjacent to ocean)."""
    from scipy.signal import convolve2d
    ocean = (ig == 10).astype(np.float32)
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
    adj_ocean = convolve2d(ocean, kernel, mode="same", boundary="fill")
    return adj_ocean > 0


def build_prediction(ig, settlements, terrain_priors, frontier, coastal_mask, T=1.2):
    """Build prediction tensor with spatial awareness."""
    pred = np.zeros((40, 40, NUM_CLASSES))

    for y in range(40):
        for x in range(40):
            t = int(ig[y, x])
            p = terrain_priors.get(t, np.ones(NUM_CLASSES) / NUM_CLASSES).copy()

            # Frontier boost: cells near settlements get higher settlement probability
            # Conservative: only boost cells VERY close to settlements
            if t not in (10, 5):  # not ocean/mountain
                f_score = frontier[y, x]
                if f_score > 0.5:  # within ~2 cells of a settlement
                    boost = 0.015 * f_score
                    p[1] += boost  # settlement
                    p[0] -= boost * 0.6  # less empty
                    p[4] -= boost * 0.4  # less forest

            # Coast-aware: coastal cells get port boost
            if coastal_mask[y, x] and t not in (10, 5):
                p[2] += 0.005  # port boost (conservative)
                p[0] -= 0.005

            # Temperature scaling
            p = np.maximum(p, FLOOR)
            p /= p.sum()
            p = temperature_scale(p, T)
            pred[y, x] = p

    return pred


def observe_full_grid(round_id, seed, queries_per_seed=9):
    """Observe full grid with tiled 15x15 viewports. Returns counts + metadata."""
    obs_counts = np.zeros((40, 40, NUM_CLASSES))
    obs_total = np.zeros((40, 40))
    all_settlements = []

    # 9 viewports cover full 40x40: (0,0), (0,13), (0,25), (13,0), ...
    positions = [(0, 0), (0, 13), (0, 25),
                 (13, 0), (13, 13), (13, 25),
                 (25, 0), (25, 13), (25, 25)]

    for qi in range(min(queries_per_seed, len(positions))):
        vx, vy = positions[qi]
        vw = min(15, 40 - vx)
        vh = min(15, 40 - vy)
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

            # Collect settlement metadata
            for s in result.get("settlements", []):
                all_settlements.append(s)

            for dy in range(len(grid_obs)):
                for dx in range(len(grid_obs[0])):
                    gy = vp["y"] + dy
                    gx = vp["x"] + dx
                    if 0 <= gy < 40 and 0 <= gx < 40:
                        c = PRED_MAP.get(grid_obs[dy][dx], 0)
                        obs_counts[gy, gx, c] += 1
                        obs_total[gy, gx] += 1
            time.sleep(0.22)
        except Exception as e:
            log(f"  Query {qi} error: {e}")

    return obs_counts, obs_total, all_settlements


def log_pool_blend(prior, obs_dist, w_prior=0.85, w_obs=0.15):
    """Logarithmic pooling: pooled = prior^w1 * obs^w2, normalized."""
    pooled = prior ** w_prior * obs_dist ** w_obs
    s = pooled.sum()
    return pooled / s if s > 0 else prior


def analyze_settlement_metadata(all_settlements):
    """Extract regime signal from settlement metadata."""
    if not all_settlements:
        return {}
    pops = [s.get("population", 0) for s in all_settlements if s.get("alive", True)]
    foods = [s.get("food", 0) for s in all_settlements if s.get("alive", True)]
    wealths = [s.get("wealth", 0) for s in all_settlements if s.get("alive", True)]
    n_alive = sum(1 for s in all_settlements if s.get("alive", True))
    n_ports = sum(1 for s in all_settlements if s.get("has_port", False))
    return {
        "n_alive": n_alive,
        "n_ports": n_ports,
        "avg_pop": np.mean(pops) if pops else 0,
        "avg_food": np.mean(foods) if foods else 0,
        "avg_wealth": np.mean(wealths) if wealths else 0,
    }


def main():
    log("=== Astar Island v8 — GT-Prior Blended ===")

    # Find active round
    my_rounds = api_get("my-rounds")
    active = [r for r in my_rounds if r["status"] == "active"]
    if not active:
        log("No active round found!")
        return False

    active_round = active[0]
    rn = active_round["round_number"]
    weight = active_round.get("round_weight", 1)
    round_id = active_round["id"]
    log(f"Active: R{rn} (weight={weight:.4f})")

    if active_round.get("seeds_submitted", 0) >= 5 and active_round.get("queries_used", 0) >= 50:
        log(f"Already fully submitted")
        return True

    # Step 1: Estimate regime from most recent completed round's replays
    rounds_dict = {rd["round_number"]: rd for rd in my_rounds
                   if rd["status"] == "completed" and rd.get("round_score")}

    prev_rn = max(rounds_dict.keys()) if rounds_dict else None
    if prev_rn:
        prev_rd = rounds_dict[prev_rn]
        prev_detail = api_get(f"rounds/{prev_rd['id']}")
        prev_states = prev_detail.get("initial_states", [])
        log(f"Estimating regime from R{prev_rn} replays...")
        est_frac = estimate_regime_from_replays(prev_rd["id"], prev_states, n=10)
        log(f"R{prev_rn} replay settlement frac: {est_frac:.4f}")
    else:
        est_frac = 0.1

    # Step 2: Get GT settlement fractions and build blended priors
    log("Fetching GT settlement fractions...")
    gt_fracs = get_gt_settlement_fractions()
    for grn, gf in sorted(gt_fracs.items()):
        log(f"  R{grn}: {gf:.4f}")

    terrain_priors = build_blended_gt_priors(est_frac, gt_fracs, rounds_dict)

    # Step 3: Get per-seed initial states
    round_detail = api_get(f"rounds/{round_id}")
    initial_states = round_detail.get("initial_states", [])

    budget = api_get("budget")
    queries_left = budget["queries_max"] - budget["queries_used"]
    log(f"Budget: {queries_left} queries remaining")

    queries_per_seed = queries_left // 5  # should be 10 (50/5)

    # Step 4: For each seed — build prediction, observe, blend, submit
    all_obs = {}
    for seed in range(5):
        ig = np.array(initial_states[seed]["grid"])
        settlements = initial_states[seed].get("settlements", [])

        # Compute spatial features
        frontier = compute_frontier_score(ig, settlements)
        try:
            coastal_mask = compute_coastal_mask(ig)
        except ImportError:
            coastal_mask = np.zeros((40, 40), dtype=bool)

        # Build base prediction from blended GT priors + spatial features
        pred = build_prediction(ig, settlements, terrain_priors, frontier, coastal_mask, T=1.2)

        # Observe full grid (9 viewports = 9 queries per seed)
        if queries_per_seed >= 9:
            obs_counts, obs_total, obs_settlements = observe_full_grid(round_id, seed, queries_per_seed)

            # Analyze settlement metadata for regime signal
            meta = analyze_settlement_metadata(obs_settlements)
            if meta:
                log(f"  Seed {seed} meta: alive={meta['n_alive']} ports={meta['n_ports']} "
                    f"pop={meta['avg_pop']:.1f} food={meta['avg_food']:.2f}")

            # Blend with observations using LOGARITHMIC POOLING
            for y in range(40):
                for x in range(40):
                    n = obs_total[y, x]
                    if n > 0:
                        obs_dist = (obs_counts[y, x] + FLOOR) / (n + NUM_CLASSES * FLOOR)
                        pred[y, x] = log_pool_blend(pred[y, x], obs_dist, w_prior=0.85, w_obs=0.15)

            all_obs[f"seed_{seed}"] = {
                "counts": obs_counts.tolist(),
                "total_obs": obs_total.tolist(),
                "settlements": obs_settlements,
            }
        else:
            all_obs[f"seed_{seed}"] = {"counts": [], "total_obs": [], "settlements": []}

        # Apply floor and normalize
        pred = np.maximum(pred, FLOOR)
        pred = pred / pred.sum(axis=2, keepdims=True)

        # Submit
        r = api_post("submit", {
            "round_id": round_id, "seed_index": seed,
            "prediction": pred.tolist()
        })
        status = r.json().get("status", "error") if r.status_code == 200 else f"HTTP {r.status_code}"
        n_obs = int((obs_total > 0).sum()) if queries_per_seed >= 9 else 0
        log(f"  Seed {seed}: {status} (obs={n_obs} cells)")

    # Save observations
    obs_path = os.path.join(NOTES_DIR, f"astar_obs_r{rn}.json")
    with open(obs_path, "w") as f:
        json.dump(all_obs, f)
    log(f"Observations saved to {obs_path}")

    log("=== Done! ===")
    return True


if __name__ == "__main__":
    main()
