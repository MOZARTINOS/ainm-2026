#!/usr/bin/env python3
"""
Astar Island — Post-Round Analysis (Generic)
Usage: python analyze_round.py [round_number]  (default: latest completed)
"""
import requests
import json
import numpy as np
from collections import defaultdict
import sys
import os

TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlZGY2MzE5MS1kZGVkLTRmOGItYjRhNy00MmExNDNiNjU0MjkiLCJlbWFpbCI6Im1vemFydGluaWNoQGdtYWlsLmNvbSIsImlzX2FkbWluIjpmYWxzZSwiZXhwIjoxNzc0NTUxNzUzfQ.om9fw-Potv7b6ABCyfcwRWHJsfQN31b4iVkj0mPjfjs"
BASE = "https://api.ainm.no/astar-island"
NOTES_DIR = "F:/Workfolder/NM i AI main/repo/notes"
NUM_CLASSES = 6
CLASS_NAMES = ['empty/plains', 'settlement', 'port', 'ruin', 'forest', 'mountain']
INIT_NAMES = {10: 'ocean', 11: 'plains', 1: 'settlement', 2: 'port', 3: 'ruin', 4: 'forest', 5: 'mountain'}
FLOOR = 0.001

# Empirical priors from Round 2 ground truth
EMPIRICAL = {
    11: np.array([0.612, 0.186, 0.014, 0.018, 0.154, 0.015]),
    4:  np.array([0.480, 0.193, 0.012, 0.019, 0.284, 0.014]),
    1:  np.array([0.513, 0.240, 0.006, 0.022, 0.201, 0.018]),
    5:  np.array([0.424, 0.153, 0.005, 0.016, 0.176, 0.227]),
    10: np.array([0.950, 0.014, 0.006, 0.005, 0.021, 0.005]),
}

headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def api_get(path):
    r = requests.get(f"{BASE}/{path}", headers=headers)
    r.raise_for_status()
    return r.json()


def kl_div(p, q):
    return sum(p[i] * np.log(p[i] / max(q[i], 1e-10)) for i in range(len(p)) if p[i] > 0)


def entropy(p):
    return -sum(pi * np.log(pi) for pi in p if pi > 0)


def analyze_seed(round_id, seed_index, initial_grid):
    """Fetch analysis for one seed."""
    print(f"\n{'='*60}")
    print(f"SEED {seed_index}")
    print(f"{'='*60}")

    data = api_get(f"analysis/{round_id}/{seed_index}")

    ground_truth = data.get("ground_truth")
    our_prediction = data.get("prediction")
    score = data.get("score")
    weighted_kl = data.get("weighted_kl")

    print(f"  Score: {score}")
    print(f"  Weighted KL: {weighted_kl}")

    if not ground_truth or not our_prediction:
        print("  No ground truth / prediction data")
        return data

    gt = np.array(ground_truth)
    pred = np.array(our_prediction)
    init = np.array(initial_grid)
    height, width = gt.shape[0], gt.shape[1]

    # Per-cell KL and entropy
    kl_per_cell = np.zeros((height, width))
    entropy_per_cell = np.zeros((height, width))
    for y in range(height):
        for x in range(width):
            kl_per_cell[y, x] = kl_div(gt[y, x], pred[y, x])
            entropy_per_cell[y, x] = entropy(gt[y, x])

    dynamic_mask = entropy_per_cell > 0
    total_entropy = entropy_per_cell[dynamic_mask].sum()
    computed_wkl = (entropy_per_cell[dynamic_mask] * kl_per_cell[dynamic_mask]).sum() / total_entropy if total_entropy > 0 else 0
    computed_score = 100 * np.exp(-3 * computed_wkl)

    print(f"  Computed wKL: {computed_wkl:.6f}, score: {computed_score:.4f}")
    print(f"  Dynamic cells: {dynamic_mask.sum()}/{height*width}")

    # KL breakdown by terrain
    kl_by_terrain = defaultdict(list)
    ent_by_terrain = defaultdict(list)
    for y in range(height):
        for x in range(width):
            if not dynamic_mask[y, x]:
                continue
            t = int(init[y, x])
            kl_by_terrain[t].append(kl_per_cell[y, x])
            ent_by_terrain[t].append(entropy_per_cell[y, x])

    print(f"\n  KL by initial terrain:")
    print(f"  {'Terrain':>12} | {'Count':>5} | {'Mean KL':>8} | {'Max KL':>8} | {'Contribution':>12}")
    terrain_contributions = {}
    for t in sorted(kl_by_terrain.keys()):
        kls = np.array(kl_by_terrain[t])
        entrs = np.array(ent_by_terrain[t])
        contrib = (entrs * kls).sum() / total_entropy if total_entropy > 0 else 0
        terrain_contributions[t] = contrib
        name = INIT_NAMES.get(t, str(t))
        print(f"  {name:>12} | {len(kls):5d} | {kls.mean():8.4f} | {kls.max():8.4f} | {contrib:12.6f}")

    # Per-class KL contribution
    class_kl = np.zeros(NUM_CLASSES)
    for y in range(height):
        for x in range(width):
            if not dynamic_mask[y, x]:
                continue
            for c in range(NUM_CLASSES):
                if gt[y, x, c] > 1e-10:
                    class_kl[c] += entropy_per_cell[y, x] * gt[y, x, c] * np.log(gt[y, x, c] / max(pred[y, x, c], 1e-10))

    total_ckl = class_kl.sum()
    print(f"\n  Per-class KL contribution:")
    for c in range(NUM_CLASSES):
        pct = 100 * class_kl[c] / total_ckl if total_ckl > 0 else 0
        print(f"    {CLASS_NAMES[c]:>15}: {pct:.1f}%")

    # Top 10 worst cells
    print(f"\n  Top 10 worst cells:")
    flat_kl = kl_per_cell.copy()
    flat_kl[~dynamic_mask] = -1
    for i in range(10):
        idx = np.unravel_index(flat_kl.argmax(), flat_kl.shape)
        y, x = idx
        if flat_kl[y, x] <= 0:
            break
        init_t = INIT_NAMES.get(int(init[y, x]), '?')
        gt_dom = CLASS_NAMES[gt[y, x].argmax()]
        pred_dom = CLASS_NAMES[pred[y, x].argmax()]
        print(f"    ({y:2d},{x:2d}) KL={flat_kl[y,x]:.4f} init={init_t} "
              f"GT={gt_dom}({gt[y,x].max():.2f}) pred={pred_dom}({pred[y,x].max():.2f})")
        flat_kl[y, x] = -1

    # Check what score we'd get with better priors + FLOOR=0.001
    better_pred = np.zeros_like(gt)
    for y in range(height):
        for x in range(width):
            t = int(init[y, x])
            better_pred[y, x] = EMPIRICAL.get(t, np.ones(NUM_CLASSES) / NUM_CLASSES)
    better_pred = np.maximum(better_pred, FLOOR)
    better_pred /= better_pred.sum(axis=2, keepdims=True)

    better_wkl = 0
    for y in range(height):
        for x in range(width):
            if not dynamic_mask[y, x]:
                continue
            kl = kl_div(gt[y, x], better_pred[y, x])
            better_wkl += entropy_per_cell[y, x] * kl
    better_wkl /= total_entropy if total_entropy > 0 else 1
    better_score = 100 * np.exp(-3 * better_wkl)
    print(f"\n  Priors-only with FLOOR=0.001 would score: {better_score:.2f}")

    return {
        'seed': seed_index,
        'score': score,
        'weighted_kl': weighted_kl,
        'computed_score': float(computed_score),
        'better_priors_score': float(better_score),
        'terrain_contributions': {INIT_NAMES.get(k, str(k)): float(v) for k, v in terrain_contributions.items()},
        'ground_truth': ground_truth,
    }


def main():
    target_round = int(sys.argv[1]) if len(sys.argv) > 1 else None

    my_rounds = api_get("my-rounds")

    if target_round is None:
        completed = [r for r in my_rounds if r['status'] == 'completed' and r.get('seeds_submitted', 0) > 0]
        if not completed:
            print("No completed rounds with submissions")
            return
        round_data = max(completed, key=lambda r: r['round_number'])
        target_round = round_data['round_number']
    else:
        round_data = next((r for r in my_rounds if r['round_number'] == target_round), None)
        if not round_data:
            print(f"Round {target_round} not found!")
            return

    if round_data['status'] != 'completed':
        print(f"Round {target_round} is {round_data['status']}, not completed yet")
        return

    round_id = round_data['id']
    initial_grid = round_data.get('initial_grid')
    num_seeds = round_data.get('seeds_count', 5)

    print(f"=== Round {target_round} Analysis ===")
    print(f"Score: {round_data.get('round_score')}")
    print(f"Seeds: {round_data.get('seed_scores')}")
    print(f"Rank: {round_data.get('rank')}")
    print(f"Weight: {round_data.get('round_weight')}")

    all_results = []
    gt_data = {}
    for seed in range(num_seeds):
        result = analyze_seed(round_id, seed, initial_grid)
        if result:
            all_results.append(result)
            if 'ground_truth' in result:
                gt_data[f"seed_{seed}"] = result['ground_truth']

    # Save ground truth
    gt_path = os.path.join(NOTES_DIR, f"astar_ground_truth_r{target_round}.json")
    if gt_data:
        with open(gt_path, 'w') as f:
            json.dump(gt_data, f)
        print(f"\nGround truth saved to {gt_path}")

    # Aggregate
    if all_results:
        print(f"\n{'='*60}")
        print("AGGREGATE")
        print(f"{'='*60}")
        scores = [r['computed_score'] for r in all_results if 'computed_score' in r]
        better = [r['better_priors_score'] for r in all_results if 'better_priors_score' in r]
        print(f"Avg submitted score: {np.mean(scores):.2f} ({min(scores):.2f}-{max(scores):.2f})")
        if better:
            print(f"Avg priors+FLOOR=0.001: {np.mean(better):.2f}")

        agg = defaultdict(list)
        for r in all_results:
            if 'terrain_contributions' in r:
                for t, c in r['terrain_contributions'].items():
                    agg[t].append(c)
        print(f"\nAvg KL contribution by terrain:")
        for t in sorted(agg.keys()):
            print(f"  {t:>12}: {np.mean(agg[t]):.6f}")

    # Save analysis to notes
    analysis_path = os.path.join(NOTES_DIR, "astar_analysis.md")
    mode = 'a' if os.path.exists(analysis_path) else 'w'
    with open(analysis_path, mode) as f:
        if mode == 'a':
            f.write("\n\n---\n\n")
        f.write(f"# Round {target_round} Analysis\n\n")
        f.write(f"- Score: {round_data.get('round_score')}\n")
        f.write(f"- Seeds: {round_data.get('seed_scores')}\n")
        f.write(f"- Rank: {round_data.get('rank')}\n")
        f.write(f"- Weight: {round_data.get('round_weight')}\n\n")
        if scores:
            f.write(f"- Avg computed score: {np.mean(scores):.2f}\n")
        if better:
            f.write(f"- Potential with FLOOR=0.001: {np.mean(better):.2f}\n")
    print(f"\nAppended to {analysis_path}")


if __name__ == "__main__":
    main()
