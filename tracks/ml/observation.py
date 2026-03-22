"""
Astar Island Observation Strategy
NM i AI 2026

Budget: 50 queries across 5 seeds
Strategy: Uniform coverage with different regions per seed
Map: 40×40, viewport max 15×15

Phase A (40 queries): 5 seeds × 8 viewports = systematic coverage
Phase B (10 queries): targeted high-entropy cells
"""

GRID_SIZE = 40
MAX_VIEWPORT = 15


def generate_viewports_for_seed(seed_index: int) -> list:
    """
    Generate 8 viewports for one seed that cover most of the map.
    Different seeds get slightly different viewport positions
    to maximize spatial diversity.

    Returns list of (x, y, w, h) tuples.
    """
    # Base 3×3 grid covers 40×40 with 15×15 viewports
    # 3 × 15 = 45 > 40, so slight overlap
    # Offset each seed to cover different transition zones
    offset_x = (seed_index * 3) % 5
    offset_y = (seed_index * 2) % 5

    viewports = []

    # 3×3 grid = 9 viewports, but we want 8 (budget constraint)
    positions = [
        (0, 0), (13, 0), (25, 0),      # top row
        (0, 13), (13, 13), (25, 13),    # middle row
        (0, 25), (25, 25),              # bottom corners (skip center)
    ]

    for bx, by in positions:
        x = min(max(bx + offset_x, 0), GRID_SIZE - MAX_VIEWPORT)
        y = min(max(by + offset_y, 0), GRID_SIZE - MAX_VIEWPORT)
        viewports.append((x, y, MAX_VIEWPORT, MAX_VIEWPORT))

    return viewports


def generate_phase_a_queries(num_seeds: int = 5) -> list:
    """
    Phase A: Systematic coverage.
    5 seeds × 8 viewports = 40 queries.

    Returns list of (seed_index, x, y, w, h).
    """
    queries = []
    for seed in range(num_seeds):
        for x, y, w, h in generate_viewports_for_seed(seed):
            queries.append((seed, x, y, w, h))
    return queries


def generate_phase_b_queries(predictor, remaining_budget: int = 10,
                              num_seeds: int = 5) -> list:
    """
    Phase B: Target high-entropy cells.
    Find cells with most uncertainty and observe them.

    Returns list of (seed_index, x, y, w, h).
    """
    import numpy as np

    predictions = predictor.predict()
    total_obs = predictor.total_obs

    # Calculate entropy per cell
    entropy = np.zeros((GRID_SIZE, GRID_SIZE))
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE):
            p = predictions[y, x]
            # Shannon entropy
            h = -np.sum(p * np.log(p + 1e-10))
            # Weight by inverse observation count (prefer less-observed)
            obs_weight = 1.0 / (1.0 + total_obs[y, x])
            entropy[y, x] = h * obs_weight

    queries = []
    queries_per_seed = remaining_budget // num_seeds

    for seed in range(num_seeds):
        for _ in range(queries_per_seed):
            # Find highest entropy 15×15 region
            best_score = -1
            best_x, best_y = 0, 0

            for vy in range(0, GRID_SIZE - MAX_VIEWPORT + 1, 5):
                for vx in range(0, GRID_SIZE - MAX_VIEWPORT + 1, 5):
                    region_entropy = entropy[
                        vy:vy + MAX_VIEWPORT,
                        vx:vx + MAX_VIEWPORT
                    ].sum()
                    if region_entropy > best_score:
                        best_score = region_entropy
                        best_x, best_y = vx, vy

            queries.append((seed, best_x, best_y, MAX_VIEWPORT, MAX_VIEWPORT))
            # Reduce entropy for selected region to avoid repetition
            entropy[best_y:best_y + MAX_VIEWPORT,
                    best_x:best_x + MAX_VIEWPORT] *= 0.1

    # Fill remaining budget with highest entropy regions across all seeds
    remaining = remaining_budget - len(queries)
    for i in range(remaining):
        seed = i % num_seeds
        queries.append((seed, 10, 10, MAX_VIEWPORT, MAX_VIEWPORT))

    return queries[:remaining_budget]
