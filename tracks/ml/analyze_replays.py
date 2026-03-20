#!/usr/bin/env python3
"""Analyze replay frame-by-frame data to reverse-engineer simulator mechanics."""
import requests, json, numpy as np, time, sys

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

RAW_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 0}
NAMES = ["empty", "settl", "port", "ruin", "forest", "mount", "ocean"]


def fetch_replay(round_id, seed):
    """Fetch one replay with retry."""
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/replay", headers=headers,
                              json={"round_id": round_id, "seed_index": seed}, timeout=60)
            if r.status_code == 429:
                time.sleep(15)
                continue
            r.raise_for_status()
            data = r.json()
            if "frames" not in data:
                time.sleep(5)
                continue
            return data
        except Exception as e:
            print(f"  Retry {attempt+1}: {e}", flush=True)
            time.sleep(5)
    return None


def analyze_round(round_id, n_replays=20):
    """Analyze replays for a round."""
    # Step transitions: count how terrain changes step by step
    step_trans = np.zeros((50, 7, 7), dtype=int)

    # Settlement dynamics
    births = np.zeros(50)
    deaths = np.zeros(50)
    alive_count = np.zeros(51)
    settl_count = np.zeros(51)  # settlement cells on grid

    # Settlement metadata deltas
    food_by_step = [[] for _ in range(50)]
    pop_by_step = [[] for _ in range(50)]

    # Neighborhood context: when a new settlement appears, what was around it?
    expansion_contexts = []  # list of (adjacent_settlements, adjacent_forests, step)
    collapse_foods = []  # food of settlements that died

    n_ok = 0
    for rep in range(n_replays):
        data = fetch_replay(round_id, rep % 5)
        if data is None:
            print(f"  Replay {rep+1} FAILED, skipping", flush=True)
            continue

        frames = data["frames"]
        n_ok += 1

        for t in range(51):
            f = frames[t]
            grid = f["grid"]
            n_settl = sum(1 for row in grid for c in row if c in (1, 2))
            n_alive = sum(1 for s in f["settlements"] if s.get("alive", True))
            settl_count[t] += n_settl
            alive_count[t] += n_alive

        for t in range(50):
            g0 = frames[t]["grid"]
            g1 = frames[t + 1]["grid"]
            s0 = {(s["x"], s["y"]): s for s in frames[t]["settlements"]}
            s1 = {(s["x"], s["y"]): s for s in frames[t + 1]["settlements"]}

            # Grid transitions
            for y in range(40):
                for x in range(40):
                    c0 = RAW_MAP.get(g0[y][x], 0)
                    c1 = RAW_MAP.get(g1[y][x], 0)
                    step_trans[t, c0, c1] += 1

            # Births & deaths
            new_positions = set(s1.keys()) - set(s0.keys())
            dead_positions = set(s0.keys()) - set(s1.keys())
            births[t] += len(new_positions)
            deaths[t] += len(dead_positions)

            # What collapsed? Record food
            for pos in dead_positions:
                s = s0[pos]
                if s.get("alive", True):
                    collapse_foods.append(s.get("food", 0))

            # What expanded? Record neighborhood
            for pos in new_positions:
                x, y = pos
                adj_settl = 0
                adj_forest = 0
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < 40 and 0 <= nx < 40:
                            if g0[ny][nx] in (1, 2):
                                adj_settl += 1
                            if g0[ny][nx] == 4:
                                adj_forest += 1
                expansion_contexts.append((adj_settl, adj_forest, t))

            # Food/pop deltas
            for pos in set(s0.keys()) & set(s1.keys()):
                if s0[pos].get("alive") and s1[pos].get("alive"):
                    food_by_step[t].append(s1[pos].get("food", 0) - s0[pos].get("food", 0))
                    pop_by_step[t].append(s1[pos].get("population", 0) - s0[pos].get("population", 0))

        print(f"  Replay {rep+1}/{n_replays} OK (seed {rep%5})", flush=True)
        time.sleep(0.5)

    if n_ok == 0:
        print("No replays succeeded!")
        return

    # Normalize
    births /= n_ok
    deaths /= n_ok
    alive_count /= n_ok
    settl_count /= n_ok

    # === REPORT ===
    print(f"\n{'='*60}")
    print(f"ANALYSIS: {n_ok} replays")
    print(f"{'='*60}")

    # 1. Settlement growth curve
    print("\n--- SETTLEMENT GROWTH CURVE ---")
    print(f"{'Step':>4} {'Alive':>6} {'Cells':>6} {'Births':>7} {'Deaths':>7} {'AvgFood':>8} {'AvgPop':>7}")
    for t in range(0, 51, 2):
        fd = np.mean(food_by_step[min(t, 49)]) if t < 50 and food_by_step[t] else 0
        pd = np.mean(pop_by_step[min(t, 49)]) if t < 50 and pop_by_step[t] else 0
        b = births[t] if t < 50 else 0
        d = deaths[t] if t < 50 else 0
        print(f"{t:>4} {alive_count[t]:>6.1f} {settl_count[t]:>6.1f} {b:>7.2f} {d:>7.2f} {fd:>8.3f} {pd:>7.3f}")

    # 2. Transition matrix (aggregate over all steps)
    agg_trans = step_trans.sum(axis=0)
    print("\n--- AGGREGATE TRANSITION MATRIX (all 50 steps) ---")
    print(f"{'From->To':>8}", end="")
    for n in NAMES:
        print(f"{n:>8}", end="")
    print()
    for i, n in enumerate(NAMES):
        row = agg_trans[i]
        total = row.sum()
        print(f"{n:>8}", end="")
        for j in range(7):
            if total > 0:
                print(f"{row[j]/total:>8.4f}", end="")
            else:
                print(f"{'---':>8}", end="")
        print(f"  (n={total})")

    # 3. Per-step transition rates for key transitions
    print("\n--- KEY TRANSITIONS BY STEP ---")
    print(f"{'Step':>4} {'e->s':>7} {'e->f':>7} {'s->r':>7} {'r->e':>7} {'r->f':>7} {'r->s':>7} {'f->s':>7}")
    for t in range(0, 50, 5):
        row = step_trans[t]
        def rate(fr, to):
            total = row[fr].sum()
            return row[fr, to] / total if total > 0 else 0
        print(f"{t:>4} {rate(0,1):>7.4f} {rate(0,4):>7.4f} {rate(1,3):>7.4f} "
              f"{rate(3,0):>7.4f} {rate(3,4):>7.4f} {rate(3,1):>7.4f} {rate(4,1):>7.4f}")

    # 4. Expansion context
    if expansion_contexts:
        adj_s = [c[0] for c in expansion_contexts]
        adj_f = [c[1] for c in expansion_contexts]
        print(f"\n--- EXPANSION CONTEXT (n={len(expansion_contexts)} new settlements) ---")
        print(f"Adjacent settlements: mean={np.mean(adj_s):.2f}, median={np.median(adj_s):.0f}")
        print(f"Adjacent forests: mean={np.mean(adj_f):.2f}, median={np.median(adj_f):.0f}")
        print(f"% with adj_settlement >= 1: {100*np.mean(np.array(adj_s)>=1):.1f}%")

    # 5. Collapse analysis
    if collapse_foods:
        print(f"\n--- COLLAPSE ANALYSIS (n={len(collapse_foods)} deaths) ---")
        print(f"Food at death: mean={np.mean(collapse_foods):.3f}, max={np.max(collapse_foods):.3f}")
        print(f"% with food < 0.1: {100*np.mean(np.array(collapse_foods)<0.1):.1f}%")
        print(f"% with food < 0.5: {100*np.mean(np.array(collapse_foods)<0.5):.1f}%")

    # 6. Save raw data for simulator building
    save_data = {
        "step_transitions": step_trans.tolist(),
        "births_per_step": births.tolist(),
        "deaths_per_step": deaths.tolist(),
        "alive_per_step": alive_count.tolist(),
        "settl_cells_per_step": settl_count.tolist(),
        "expansion_contexts": expansion_contexts,
        "collapse_foods": collapse_foods,
        "n_replays": n_ok,
    }
    outpath = f"F:/Workfolder/NM i AI main/repo/notes/replay_analysis_{round_id[:8]}.json"
    with open(outpath, "w") as f:
        json.dump(save_data, f)
    print(f"\nSaved to {outpath}")


# Get completed round IDs
r = requests.get(f"{BASE}/my-rounds", headers=headers)
rounds = {rd["round_number"]: rd["id"] for rd in r.json()
          if rd["status"] == "completed" and rd.get("round_score")}

print(f"Completed rounds: {sorted(rounds.keys())}")

# Analyze R6 (hot regime) — our most recent best data
print(f"\n=== Analyzing R6 (HOT regime) ===")
analyze_round(rounds[6], n_replays=20)
