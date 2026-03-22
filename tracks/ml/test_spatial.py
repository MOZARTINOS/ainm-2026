#!/usr/bin/env python3
"""Test spatial-aware replay priors vs flat per-terrain priors."""
import requests, json, numpy as np, time

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
FLOOR = 0.01
PRED_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}


def compute_spatial_features(ig):
    h, w = ig.shape
    settl_pos = list(zip(*np.where(np.isin(ig, [1, 2]))))
    features = {}
    for y in range(h):
        for x in range(w):
            adj_forest = adj_settl = adj_ocean = 0
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w:
                        t = int(ig[ny, nx])
                        if t == 4: adj_forest += 1
                        elif t in (1, 2): adj_settl += 1
                        elif t == 10: adj_ocean += 1
            dist_settl = min((abs(y-sy)+abs(x-sx) for sy, sx in settl_pos), default=99)
            features[(y, x)] = {
                "adj_forest": adj_forest,
                "adj_settl": adj_settl,
                "adj_ocean": adj_ocean,
                "dist_settl": dist_settl,
                "is_coastal": adj_ocean > 0,
            }
    return features


def get_bucket(t, f):
    if t in (11, 0):
        if f["adj_settl"] > 0: return "near_settl"
        elif f["dist_settl"] <= 3: return "close_settl"
        elif f["adj_forest"] >= 3: return "forested"
        else: return "open"
    elif t == 4:
        if f["adj_settl"] > 0: return "near_settl"
        elif f["dist_settl"] <= 3: return "close_settl"
        else: return "far"
    elif t == 1:
        if f["adj_forest"] >= 2: return "forest_adj"
        elif f["is_coastal"]: return "coastal"
        else: return "inland"
    elif t == 5: return "static"
    elif t == 10: return "static"
    return "default"


def build_spatial_priors(round_id, ref_states, n_per_seed=30):
    counts = {}
    ns = {}
    n_ok = 0
    for seed in range(5):
        ref_grid = np.array(ref_states[seed]["grid"])
        features = compute_spatial_features(ref_grid)
        for i in range(n_per_seed):
            try:
                r = requests.post(f"{BASE}/replay", headers=headers,
                                  json={"round_id": round_id, "seed_index": seed}, timeout=30)
                if r.status_code != 200:
                    time.sleep(5)
                    continue
                data = r.json()
                if "frames" not in data:
                    continue
                final = data["frames"][-1]["grid"]
                for y in range(40):
                    for x in range(40):
                        t = int(ref_grid[y, x])
                        c = PRED_MAP.get(final[y][x], 0)
                        bucket = get_bucket(t, features[(y, x)])
                        key = (t, bucket)
                        if key not in counts:
                            counts[key] = np.zeros(6)
                            ns[key] = 0
                        counts[key][c] += 1
                        ns[key] += 1
                n_ok += 1
                time.sleep(0.25)
            except:
                time.sleep(2)
        print(f"  Seed {seed}: {n_ok} total replays", flush=True)

    priors = {}
    for key, c in counts.items():
        if ns[key] > 0:
            p = c / ns[key]
            p = np.maximum(p, FLOOR)
            p /= p.sum()
            priors[key] = p
    return priors, n_ok


def compute_score(gt, pred):
    pred = np.maximum(pred, FLOOR)
    pred /= pred.sum(axis=2, keepdims=True)
    te = wkl = 0
    for y in range(40):
        for x in range(40):
            p = gt[y, x]
            q = pred[y, x]
            h = -np.sum(p * np.log(p + 1e-10))
            if h > 0.001:
                kl = np.sum(p * np.log((p + 1e-10) / (q + 1e-10)))
                wkl += h * kl
                te += h
    return 100 * np.exp(-3 * wkl / te) if te > 0 else 0


# === MAIN ===
r = requests.get(f"{BASE}/my-rounds", headers=headers)
rounds = {rd["round_number"]: rd for rd in r.json() if rd["status"] == "completed"}
R4_ID = rounds[4]["id"]
R9_ID = rounds[9]["id"]

# Build spatial priors from R4 (medium regime)
print("Building SPATIAL priors from R4 (150 replays)...", flush=True)
r4_detail = requests.get(f"{BASE}/rounds/{R4_ID}", headers=headers).json()
r4_states = r4_detail.get("initial_states", [])
spatial_priors, n_replays = build_spatial_priors(R4_ID, r4_states, n_per_seed=30)

# Also build flat per-terrain priors from same replays for comparison
flat_counts = {}
flat_ns = {}
for (t, bucket), p in spatial_priors.items():
    if t not in flat_counts:
        flat_counts[t] = np.zeros(6)
        flat_ns[t] = 0
    flat_counts[t] += p
    flat_ns[t] += 1
flat_priors = {}
for t in flat_counts:
    flat_priors[t] = flat_counts[t] / flat_ns[t]
    flat_priors[t] = np.maximum(flat_priors[t], FLOOR)
    flat_priors[t] /= flat_priors[t].sum()

# Print spatial priors
names = ["empty", "settl", "port", "ruin", "forest", "mount"]
print(f"\nSpatial priors ({len(spatial_priors)} buckets, {n_replays} replays):")
for key in sorted(spatial_priors.keys()):
    t, bucket = key
    tn = {10: "ocean", 11: "plains", 4: "forest", 1: "settl", 5: "mount"}.get(t, str(t))
    p = spatial_priors[key]
    print(f"  {tn:>6}/{bucket:<12}: {' '.join(f'{names[i]}={p[i]:.3f}' for i in range(6))}")

# Test on R9 GT
print(f"\nTesting on R9 GT...", flush=True)
r9_detail = requests.get(f"{BASE}/rounds/{R9_ID}", headers=headers).json()
r9_states = r9_detail.get("initial_states", [])

for seed in range(5):
    resp = requests.get(f"{BASE}/analysis/{R9_ID}/{seed}", headers=headers)
    data = resp.json()
    gt = np.array(data["ground_truth"])
    ig = np.array(r9_states[seed]["grid"])
    features = compute_spatial_features(ig)

    # Spatial
    pred_s = np.zeros((40, 40, 6))
    for y in range(40):
        for x in range(40):
            t = int(ig[y, x])
            bucket = get_bucket(t, features[(y, x)])
            key = (t, bucket)
            if key in spatial_priors:
                pred_s[y, x] = spatial_priors[key]
            elif t in flat_priors:
                pred_s[y, x] = flat_priors[t]
            else:
                pred_s[y, x] = 1.0 / 6
    s_s = compute_score(gt, pred_s)

    # Flat
    pred_f = np.zeros((40, 40, 6))
    for y in range(40):
        for x in range(40):
            t = int(ig[y, x])
            pred_f[y, x] = flat_priors.get(t, np.ones(6) / 6)
    s_f = compute_score(gt, pred_f)

    print(f"  Seed {seed}: spatial={s_s:.2f}  flat={s_f:.2f}  diff={s_s - s_f:+.2f}")

print(f"\n(Actual R9 was 66.61)")
