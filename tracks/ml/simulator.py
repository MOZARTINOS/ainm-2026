#!/usr/bin/env python3
"""
Data-driven Astar Island Simulator.

Instead of reverse-engineering exact game rules, we use empirical transition
matrices extracted from replay data. Each step:
1. For each cell, look up P(next_class | current_class, neighborhood_context)
2. Sample next state from that distribution

This is a Markov chain simulator calibrated from real data.
"""
import numpy as np
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
NOTES_DIR = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), "notes")

# Terrain codes
OCEAN = 10
PLAINS = 11
EMPTY = 0
SETTLEMENT = 1
PORT = 2
RUIN = 3
FOREST = 4
MOUNTAIN = 5

# Prediction class mapping
PRED_MAP = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 0, 11: 0}

# 8-connected neighbors
DELTAS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


class TransitionModel:
    """Data-driven transition model extracted from replays.

    Stores per-step, context-dependent transition probabilities.
    Context = (current_terrain, n_adjacent_settlements, n_adjacent_forests, is_coastal)
    """

    def __init__(self):
        # Base transition matrix: P(next | current), shape (7, 7)
        # Indices: 0=empty/plains, 1=settlement, 2=port, 3=ruin, 4=forest, 5=mountain, 6=ocean
        self.base_trans = None

        # Context-dependent adjustments
        self.expansion_prob_per_adj_settl = 0.0  # P(empty->settlement) boost per adjacent settlement
        self.expansion_base = 0.0  # base P(empty->settlement) with 0 adjacent settlements
        self.port_prob_coastal = 0.0  # P(settlement->port) if coastal
        self.collapse_rate = 0.0  # base P(settlement->ruin)

    @classmethod
    def from_replay_data(cls, replay_analysis_path):
        """Build model from analyzed replay data."""
        model = cls()

        with open(replay_analysis_path) as f:
            data = json.load(f)

        # Build aggregate transition matrix
        trans = np.array(data["step_transitions"])  # (50, 7, 7)
        agg = trans.sum(axis=0).astype(float)  # (7, 7)

        # Normalize rows
        row_sums = agg.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        model.base_trans = agg / row_sums

        # Extract expansion rate from contexts
        contexts = data.get("expansion_contexts", [])
        if contexts:
            adj_s = np.array([c[0] for c in contexts])
            # P(expansion) ~= n_new_settlements / n_eligible_empty_cells
            # But we approximate: 74.9% had adj_settl >= 1
            # This means expansion is STRONGLY driven by adjacency
            model.expansion_prob_per_adj_settl = 0.008  # per adjacent settlement
            model.expansion_base = 0.001  # spontaneous (rare)

        # Collapse rate from transition matrix
        model.collapse_rate = model.base_trans[1, 3]  # settlement -> ruin

        # Port formation: from settlement data
        model.port_prob_coastal = model.base_trans[1, 2]  # settlement -> port

        return model

    @classmethod
    def from_regime(cls, regime, replay_data_dir=None):
        """Load pre-computed model for a regime."""
        if replay_data_dir is None:
            replay_data_dir = NOTES_DIR

        # Try to find matching replay analysis file
        # For now, build from hardcoded empirical data
        model = cls()

        if regime == "hot":
            # From R6 analysis (20 replays)
            model.base_trans = np.array([
                # empty    settl    port     ruin     forest   mount    ocean
                [0.9863,  0.0122,  0.0000,  0.0016,  0.0000,  0.0000,  0.0000],  # empty
                [0.0000,  0.8992,  0.0041,  0.0967,  0.0000,  0.0000,  0.0000],  # settl
                [0.0000,  0.0000,  0.9447,  0.0553,  0.0000,  0.0000,  0.0000],  # port
                [0.3334,  0.5113,  0.0124,  0.0000,  0.1430,  0.0000,  0.0000],  # ruin
                [0.0000,  0.0129,  0.0000,  0.0017,  0.9854,  0.0000,  0.0000],  # forest
                [0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  1.0000,  0.0000],  # mount
                [0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  1.0000],  # ocean
            ])
            model.expansion_prob_per_adj_settl = 0.008
            model.expansion_base = 0.001
        elif regime == "medium":
            # Interpolated — will be updated from R4/R5 analysis
            model.base_trans = np.array([
                [0.9940,  0.0050,  0.0000,  0.0010,  0.0000,  0.0000,  0.0000],
                [0.0000,  0.9200,  0.0020,  0.0780,  0.0000,  0.0000,  0.0000],
                [0.0000,  0.0000,  0.9600,  0.0400,  0.0000,  0.0000,  0.0000],
                [0.4000,  0.4000,  0.0100,  0.0000,  0.1900,  0.0000,  0.0000],
                [0.0000,  0.0050,  0.0000,  0.0010,  0.9940,  0.0000,  0.0000],
                [0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  1.0000,  0.0000],
                [0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  1.0000],
            ])
            model.expansion_prob_per_adj_settl = 0.004
            model.expansion_base = 0.0005
        elif regime == "dead":
            model.base_trans = np.array([
                [0.9995,  0.0002,  0.0000,  0.0003,  0.0000,  0.0000,  0.0000],
                [0.0000,  0.9500,  0.0010,  0.0490,  0.0000,  0.0000,  0.0000],
                [0.0000,  0.0000,  0.9700,  0.0300,  0.0000,  0.0000,  0.0000],
                [0.5000,  0.2000,  0.0050,  0.0000,  0.2950,  0.0000,  0.0000],
                [0.0000,  0.0002,  0.0000,  0.0003,  0.9995,  0.0000,  0.0000],
                [0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  1.0000,  0.0000],
                [0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  0.0000,  1.0000],
            ])
            model.expansion_prob_per_adj_settl = 0.001
            model.expansion_base = 0.0001

        model.collapse_rate = model.base_trans[1, 3]
        model.port_prob_coastal = model.base_trans[1, 2]
        return model


class AstarSimulator:
    """Data-driven Norse civilization simulator.

    Uses empirical transition matrices from replay data.
    Runs on a 40x40 grid for 50 steps.
    """

    def __init__(self, model: TransitionModel, rng_seed=None):
        self.model = model
        self.rng = np.random.RandomState(rng_seed)
        self.grid = None
        self.H = 40
        self.W = 40

        # Precompute neighbor lookup
        self._neighbors = {}
        for y in range(self.H):
            for x in range(self.W):
                ns = []
                for dy, dx in DELTAS:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < self.H and 0 <= nx < self.W:
                        ns.append((ny, nx))
                self._neighbors[(y, x)] = ns

    def load_initial_state(self, grid, settlements=None):
        """Load initial state from API format.

        grid: 40x40 list of lists with terrain codes
        settlements: list of {x, y, has_port, alive} dicts (optional)
        """
        self.grid = np.array(grid, dtype=np.int8)

        # Convert settlements to grid codes if provided
        if settlements:
            for s in settlements:
                x, y = s["x"], s["y"]
                if s.get("alive", True):
                    if s.get("has_port", False):
                        self.grid[y, x] = PORT
                    else:
                        self.grid[y, x] = SETTLEMENT

    def _count_adjacent(self, y, x, terrain_type):
        """Count 8-connected neighbors of given type."""
        count = 0
        for ny, nx in self._neighbors[(y, x)]:
            if self.grid[ny, nx] == terrain_type:
                count += 1
            # Also count ports as settlements for adjacency
            if terrain_type == SETTLEMENT and self.grid[ny, nx] == PORT:
                count += 1
        return count

    def _is_coastal(self, y, x):
        """Check if cell has adjacent ocean."""
        for ny, nx in self._neighbors[(y, x)]:
            if self.grid[ny, nx] == OCEAN:
                return True
        return False

    def step(self):
        """Execute one simulation step using context-dependent transitions."""
        new_grid = self.grid.copy()
        trans = self.model.base_trans

        # Process each cell
        for y in range(self.H):
            for x in range(self.W):
                cell = self.grid[y, x]

                # Static cells never change
                if cell == OCEAN or cell == MOUNTAIN:
                    continue

                # Map to transition matrix index
                if cell == PLAINS or cell == EMPTY:
                    idx = 0
                elif cell == SETTLEMENT:
                    idx = 1
                elif cell == PORT:
                    idx = 2
                elif cell == RUIN:
                    idx = 3
                elif cell == FOREST:
                    idx = 4
                else:
                    continue

                # Get base transition probabilities
                probs = trans[idx].copy()

                # Context-dependent adjustments for empty/plains cells
                if idx == 0:  # empty/plains
                    adj_settl = self._count_adjacent(y, x, SETTLEMENT)
                    # More adjacent settlements = higher expansion probability
                    extra_expansion = adj_settl * self.model.expansion_prob_per_adj_settl
                    probs[1] = self.model.expansion_base + extra_expansion
                    probs[0] = 1.0 - probs[1] - probs[3]  # adjust empty to maintain sum

                    # Forests expand nearby (if adjacent to forests)
                    adj_forest = self._count_adjacent(y, x, FOREST)
                    if adj_forest > 0 and adj_settl == 0:
                        probs[4] = 0.001 * adj_forest
                        probs[0] -= probs[4]

                elif idx == 1:  # settlement
                    # Coastal settlements can become ports
                    if self._is_coastal(y, x):
                        probs[2] = self.model.port_prob_coastal * 2  # boost for coastal
                    else:
                        probs[2] = 0  # can't become port if not coastal

                    # Settlements with many neighbors are more stable
                    adj_settl = self._count_adjacent(y, x, SETTLEMENT)
                    if adj_settl >= 2:
                        # Reduce collapse rate for well-connected settlements
                        probs[3] *= 0.7

                    # Renormalize
                    probs[1] = 1.0 - probs[2] - probs[3]

                elif idx == 3:  # ruin
                    # Ruins near settlements get reclaimed faster
                    adj_settl = self._count_adjacent(y, x, SETTLEMENT)
                    if adj_settl >= 1:
                        probs[1] *= (1 + 0.3 * adj_settl)  # boost reclamation

                    # Ruins near forests become forest faster
                    adj_forest = self._count_adjacent(y, x, FOREST)
                    if adj_forest >= 2:
                        probs[4] *= 1.5

                    # Renormalize
                    total = probs[0] + probs[1] + probs[2] + probs[4]
                    if total > 0:
                        probs /= total

                elif idx == 4:  # forest
                    # Forest -> settlement only if adjacent to settlements
                    adj_settl = self._count_adjacent(y, x, SETTLEMENT)
                    if adj_settl == 0:
                        probs[1] = 0
                        probs[3] = 0
                        probs[4] = 1.0
                    else:
                        probs[1] = 0.005 * adj_settl
                        probs[4] = 1.0 - probs[1] - probs[3]

                # Ensure valid probabilities
                probs = np.maximum(probs, 0)
                total = probs.sum()
                if total > 0:
                    probs /= total
                else:
                    probs[idx] = 1.0

                # Sample next state
                next_idx = self.rng.choice(7, p=probs)

                # Map back to terrain code
                terrain_map = [PLAINS, SETTLEMENT, PORT, RUIN, FOREST, MOUNTAIN, OCEAN]
                new_grid[y, x] = terrain_map[next_idx]

        self.grid = new_grid

    def run(self, steps=50):
        """Run full simulation, return final grid."""
        for _ in range(steps):
            self.step()
        return self.grid.copy()

    def run_monte_carlo(self, initial_grid, settlements, n_sims=100, steps=50):
        """Run n_sims simulations, return per-cell class distribution.

        Returns: (40, 40, 6) array of class probabilities
        """
        counts = np.zeros((self.H, self.W, 6), dtype=np.int32)

        for i in range(n_sims):
            self.rng = np.random.RandomState(i * 12345 + 42)
            self.load_initial_state(initial_grid, settlements)
            final = self.run(steps)

            for y in range(self.H):
                for x in range(self.W):
                    c = PRED_MAP.get(int(final[y, x]), 0)
                    counts[y, x, c] += 1

        # Convert to probabilities
        dist = counts.astype(float) / n_sims
        return dist


def build_prediction(initial_grid, settlements, regime="hot", n_sims=200, floor=0.01):
    """Build prediction tensor using Monte Carlo simulation.

    Args:
        initial_grid: 40x40 list/array of terrain codes
        settlements: list of settlement dicts from initial_states
        regime: "hot", "medium", or "dead"
        n_sims: number of simulations to run
        floor: minimum probability

    Returns:
        (40, 40, 6) probability tensor ready for submission
    """
    model = TransitionModel.from_regime(regime)
    sim = AstarSimulator(model)

    dist = sim.run_monte_carlo(initial_grid, settlements, n_sims=n_sims)

    # Apply floor and normalize
    dist = np.maximum(dist, floor)
    dist = dist / dist.sum(axis=2, keepdims=True)

    return dist


if __name__ == "__main__":
    import time

    # Quick test: simulate R6 and compare to ground truth
    import requests

    TOKEN = "YOUR_JWT_TOKEN_HERE"
    BASE = "https://api.ainm.no/astar-island"
    R6_ID = "ae78003a-4efe-425a-881a-d16a39bca0ad"
    headers = {"Authorization": f"Bearer {TOKEN}"}

    # Get initial state for R6 seed 0
    r = requests.get(f"{BASE}/rounds/{R6_ID}", headers=headers)
    state = r.json()["initial_states"][0]

    # Get ground truth
    r = requests.get(f"{BASE}/analysis/{R6_ID}/0", headers=headers)
    gt = np.array(r.json()["ground_truth"])

    # Run simulator
    print("Running 200 Monte Carlo simulations...", flush=True)
    t0 = time.time()
    pred = build_prediction(state["grid"], state["settlements"], regime="hot", n_sims=200)
    elapsed = time.time() - t0
    print(f"Done in {elapsed:.1f}s ({elapsed/200*1000:.0f}ms per sim)")

    # Compute score
    FLOOR = 0.01
    pred = np.maximum(pred, FLOOR)
    pred = pred / pred.sum(axis=2, keepdims=True)

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
    wkl = wkl / te if te > 0 else 0
    score = 100 * np.exp(-3 * wkl)

    print(f"\nScore vs R6 ground truth: {score:.2f}")
    print(f"(Our actual R6 score was 48.72)")

    # Per-terrain analysis
    ig = np.array(state["grid"])
    for t_name, t_val in [("plains", 11), ("forest", 4), ("settlement", 1)]:
        mask = ig == t_val
        if mask.sum() > 0:
            gt_avg = gt[mask].mean(axis=0)
            pred_avg = pred[mask].mean(axis=0)
            names = ["empty", "settl", "port", "ruin", "forest", "mount"]
            print(f"\n{t_name}:")
            for i in range(6):
                diff = pred_avg[i] - gt_avg[i]
                marker = "!!!" if abs(diff) > 0.05 else ""
                print(f"  {names[i]}: GT={gt_avg[i]:.3f} Pred={pred_avg[i]:.3f} diff={diff:+.3f} {marker}")
