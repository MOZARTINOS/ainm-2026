#!/usr/bin/env python3
"""
Round 2 recon: Use remaining 9 queries to understand terrain dynamics.
Analyze how simulation state differs from initial grid.
DO NOT resubmit — our 41-query submission is better than 9-query one.
"""
import requests
import time
import json
import numpy as np
from collections import defaultdict

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
ROUND_ID = "76909e29-f664-4b2f-b16b-61b7507277e9"
TERRAIN_MAP = {10: 0, 11: 0, 0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
INIT_NAMES = {10: 'ocean', 11: 'plains', 1: 'settlement', 2: 'port', 3: 'ruin', 4: 'forest', 5: 'mountain'}
SIM_NAMES = {0: 'empty/plains', 1: 'settlement', 2: 'port', 3: 'ruin', 4: 'forest', 5: 'mountain'}
WIDTH, HEIGHT = 40, 40

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

INITIAL_GRID = [[10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10],[10,11,11,4,4,11,4,11,4,4,4,11,11,11,4,11,11,11,11,11,11,11,11,11,11,11,11,11,4,11,11,11,11,4,10,11,11,11,11,10],[10,4,11,11,11,4,4,11,4,11,11,4,4,11,11,11,4,4,11,4,11,11,11,11,11,4,4,4,11,11,11,4,11,11,11,10,4,11,11,10],[10,11,4,5,11,11,11,4,11,11,11,11,11,11,11,11,11,1,11,11,11,11,4,11,11,11,1,11,11,4,4,4,11,11,4,4,10,11,11,10],[10,4,11,4,11,11,11,11,4,4,11,4,4,11,11,11,4,11,11,4,4,4,11,11,11,11,11,11,11,11,11,11,11,11,11,11,4,10,10,10],[10,4,1,5,11,11,11,4,11,1,11,11,4,11,4,11,11,11,4,4,11,11,11,11,4,11,11,11,11,4,11,4,4,4,11,11,11,11,10,10],[10,11,11,5,11,4,11,11,11,11,11,11,4,11,11,1,11,11,11,11,4,11,11,11,11,11,4,11,4,11,11,4,11,11,11,11,4,11,11,10],[10,11,11,11,5,11,4,11,11,11,11,4,4,11,11,11,11,11,4,11,11,11,11,11,4,11,11,1,4,4,11,11,11,11,11,11,4,4,11,10],[10,10,11,11,1,4,11,11,11,11,11,11,11,11,4,4,11,4,11,4,11,4,11,11,11,11,11,11,11,1,4,11,11,11,11,11,4,11,11,10],[10,10,11,11,4,5,4,5,11,11,4,11,11,11,11,4,4,11,11,4,4,11,4,11,11,11,11,11,4,11,11,4,11,11,11,11,11,4,11,10],[10,10,10,4,11,4,11,5,5,11,11,11,11,11,11,4,11,11,1,4,11,11,4,4,4,11,11,11,1,11,11,11,11,11,11,11,4,11,4,10],[10,10,10,11,11,11,4,5,5,11,11,11,4,11,11,4,11,11,4,4,4,11,11,11,4,11,4,11,11,4,11,11,4,11,11,11,11,11,4,10],[10,11,10,10,11,11,5,11,11,11,11,11,4,11,11,11,4,11,11,11,11,11,11,11,4,11,4,11,11,11,11,11,11,11,11,1,11,11,11,10],[10,4,11,11,11,11,5,4,11,11,4,11,4,11,4,11,11,11,11,4,11,11,11,11,11,11,11,4,4,11,11,4,11,11,4,11,11,11,11,10],[10,11,11,11,4,11,5,4,11,11,11,11,11,11,11,1,11,4,11,11,11,4,11,4,4,11,11,11,4,4,4,4,11,11,11,11,11,11,4,10],[10,11,11,11,11,11,11,4,11,11,11,11,11,4,11,4,11,11,11,11,11,4,11,11,11,11,11,4,4,4,11,1,4,11,11,11,11,11,11,10],[10,4,11,4,11,11,4,4,4,11,11,11,4,11,11,11,11,11,11,11,11,11,4,1,4,4,11,1,4,11,4,11,4,11,4,11,11,1,11,10],[10,11,11,4,11,11,11,4,4,11,11,11,11,11,11,11,11,11,11,11,11,4,11,11,11,11,11,11,4,11,11,11,4,4,11,1,11,11,11,10],[10,11,4,11,11,11,11,4,4,11,4,11,4,1,11,11,11,11,11,11,11,11,11,11,11,11,11,11,4,11,11,11,11,11,11,11,11,11,11,10],[10,11,11,11,4,11,11,11,4,4,11,11,4,11,11,11,11,11,4,11,5,4,4,4,11,11,11,4,11,4,11,11,11,4,11,4,11,11,11,10],[10,11,1,11,11,11,11,11,11,4,4,11,11,11,11,11,11,4,11,4,11,11,11,4,4,11,11,11,4,11,11,11,11,11,4,11,11,11,4,10],[10,11,4,4,11,11,11,11,4,4,11,11,11,11,11,4,11,4,11,11,5,11,11,4,11,11,11,11,4,11,11,11,4,11,4,4,11,11,11,10],[10,11,11,4,11,11,11,4,11,11,1,11,11,11,11,11,4,11,11,11,11,5,4,11,11,4,11,4,11,11,1,4,11,11,11,4,11,11,4,10],[10,11,11,11,11,11,11,11,11,11,11,11,11,11,11,4,11,11,11,4,4,11,4,11,11,11,4,11,11,4,11,4,11,11,11,4,11,4,11,10],[10,11,11,11,4,4,4,11,11,11,11,4,4,4,11,11,4,11,11,11,11,5,5,11,11,1,11,11,4,4,11,11,4,11,4,11,10,10,10,10],[10,11,11,11,4,11,4,4,11,4,11,11,11,4,11,11,11,4,11,11,11,11,11,11,11,11,11,4,4,1,11,11,11,4,4,11,11,11,11,10],[10,11,11,11,4,11,4,11,11,11,11,11,11,4,11,11,11,11,11,11,11,11,4,11,5,11,11,4,11,11,11,11,11,11,11,11,11,11,11,10],[10,11,11,4,4,11,4,11,11,11,11,11,11,11,4,4,11,11,4,11,11,11,11,11,11,1,5,5,5,11,5,11,4,11,11,11,1,11,11,10],[10,4,11,11,11,11,11,11,11,11,11,11,11,4,4,4,4,11,11,11,11,11,11,4,11,11,4,11,11,4,5,4,4,11,11,11,11,4,11,10],[10,11,11,11,1,11,4,11,11,11,11,4,4,11,11,1,4,4,11,4,11,11,11,4,4,11,1,5,11,11,4,11,11,11,11,1,11,11,11,10],[10,11,11,11,4,11,11,11,4,11,11,4,4,11,11,11,4,4,11,11,11,11,11,11,11,11,11,5,11,11,4,5,11,11,11,11,11,4,11,10],[10,11,4,4,4,11,11,11,11,11,11,11,11,11,11,11,11,4,4,4,4,11,4,4,11,11,11,5,5,4,11,11,11,1,11,11,4,11,11,10],[10,11,4,4,11,11,11,11,11,11,11,11,11,11,4,11,11,4,4,4,4,4,11,11,11,11,11,4,5,4,11,11,4,4,4,11,11,11,11,10],[10,11,4,11,11,4,11,4,11,11,4,11,11,11,11,11,11,11,4,11,4,4,11,4,11,11,11,11,4,11,11,11,11,11,11,11,11,11,11,10],[10,11,11,11,4,11,11,11,4,11,11,11,1,11,11,11,11,11,4,4,11,11,11,11,11,11,11,11,11,4,11,11,4,11,11,11,11,11,4,10],[10,11,4,11,11,11,11,11,4,11,11,11,11,11,4,11,4,11,11,11,4,11,4,11,11,11,4,11,11,11,11,11,11,4,11,11,4,1,11,10],[10,10,11,11,11,4,4,11,4,11,11,11,11,11,11,11,11,11,11,11,11,11,4,11,4,1,4,11,4,11,11,11,11,4,11,11,4,11,4,10],[10,10,4,11,4,4,11,11,11,11,11,11,11,4,11,11,4,4,11,11,11,11,11,11,11,4,11,4,4,11,4,11,11,11,11,11,11,4,11,10],[10,10,10,11,11,4,11,11,11,11,11,11,11,4,10,10,10,10,10,11,11,11,11,11,11,11,11,4,11,4,11,4,11,11,11,11,11,11,4,10],[10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10,10]]

initial = np.array(INITIAL_GRID)

def log(msg):
    print(f"[*] {msg}", flush=True)

def simulate(seed, x, y, w=15, h=15):
    r = requests.post(f"{BASE}/simulate", headers=headers, json={
        "round_id": ROUND_ID, "seed_index": seed,
        "viewport_x": x, "viewport_y": y, "viewport_w": w, "viewport_h": h
    })
    r.raise_for_status()
    return r.json()

# 9 targeted queries — focus on settlement-rich areas across different seeds
targeted_queries = [
    (0, 0, 0, 15, 15),    # top-left (has settlements at 5,2 and 5,9)
    (1, 0, 0, 15, 15),    # same area, different seed
    (2, 10, 10, 15, 15),  # center (settlements at 14,15, 16,23)
    (3, 10, 10, 15, 15),  # same center, different seed
    (4, 20, 20, 15, 15),  # bottom-right (mountains + settlements)
    (0, 25, 0, 15, 15),   # top-right
    (1, 25, 25, 15, 15),  # bottom-right seed1
    (2, 0, 25, 15, 15),   # bottom-left
    (3, 25, 0, 15, 15),   # top-right seed3
]

# Track changes from initial state
transitions = defaultdict(int)  # (initial_type, sim_type) -> count
same_count = 0
diff_count = 0
all_results = []

log("Executing 9 recon queries...")
for i, (seed, x, y, w, h) in enumerate(targeted_queries):
    try:
        result = simulate(seed, x, y, w, h)
        grid = result.get("grid", [])
        settlements = result.get("settlements", [])
        vp = result.get("viewport", {})
        vx, vy = vp.get("x", x), vp.get("y", y)

        changes_in_viewport = []
        for dy in range(len(grid)):
            for dx in range(len(grid[dy])):
                cy, cx = vy + dy, vx + dx
                if 0 <= cy < HEIGHT and 0 <= cx < WIDTH:
                    sim_class = TERRAIN_MAP.get(grid[dy][dx], 0)
                    init_terrain = initial[cy, cx]
                    init_class = TERRAIN_MAP.get(int(init_terrain), 0)

                    transitions[(int(init_terrain), sim_class)] += 1

                    if init_class != sim_class:
                        diff_count += 1
                        changes_in_viewport.append({
                            'pos': (cy, cx),
                            'init': INIT_NAMES.get(int(init_terrain), str(init_terrain)),
                            'sim': SIM_NAMES.get(sim_class, str(sim_class)),
                        })
                    else:
                        same_count += 1

        log(f"  Query {i+1}/9: seed={seed} vp=({vx},{vy}) - {len(changes_in_viewport)} changes")
        if changes_in_viewport:
            for c in changes_in_viewport[:5]:
                log(f"    ({c['pos'][0]},{c['pos'][1]}): {c['init']} -> {c['sim']}")
            if len(changes_in_viewport) > 5:
                log(f"    ... and {len(changes_in_viewport)-5} more")

        all_results.append({
            'seed': seed, 'vx': vx, 'vy': vy,
            'changes': len(changes_in_viewport),
            'settlements_meta': settlements,
            'grid': grid,
        })

        time.sleep(0.3)
    except Exception as e:
        log(f"  Query {i+1}/9: FAILED - {e}")

# Summary
log(f"\n{'='*60}")
log(f"RECON SUMMARY")
log(f"{'='*60}")
log(f"Total cells observed: {same_count + diff_count}")
log(f"Unchanged: {same_count} ({100*same_count/(same_count+diff_count+0.001):.1f}%)")
log(f"Changed: {diff_count} ({100*diff_count/(same_count+diff_count+0.001):.1f}%)")

log(f"\nTransition matrix (init -> sim):")
for (init_t, sim_c), count in sorted(transitions.items(), key=lambda x: -x[1]):
    init_name = INIT_NAMES.get(init_t, str(init_t))
    sim_name = SIM_NAMES.get(sim_c, str(sim_c))
    if init_t != 10:  # skip ocean
        pct = 100 * count / sum(v for (k, _), v in transitions.items() if k == init_t)
        log(f"  {init_name:>12} -> {sim_name:<15} {count:4d} ({pct:.1f}%)")

# Settlement metadata analysis
log(f"\nSettlement metadata from queries:")
for r in all_results:
    if r['settlements_meta']:
        log(f"  Seed {r['seed']}: {json.dumps(r['settlements_meta'][:3])}")

# Save results
output_path = "F:/Workfolder/NM i AI main/repo/notes/astar_recon_r2.json"
with open(output_path, 'w') as f:
    json.dump({
        'round_id': ROUND_ID,
        'transitions': {f"{k[0]}->{k[1]}": v for k, v in transitions.items()},
        'same_count': same_count,
        'diff_count': diff_count,
        'total_observed': same_count + diff_count,
    }, f, indent=2)
log(f"\nSaved recon data to {output_path}")

# Budget check
r = requests.get(f"{BASE}/budget", headers=headers)
log(f"Final budget: {r.json()}")
