# Astar Island — Experiment Log & Baseline Tracker

## Current Best: R13 = 66.78 raw, 125.92 weighted, #185

---

## Round Results

| Round | Raw Score | Weighted | Rank | Regime (GT) | Method | Reference |
|-------|-----------|----------|------|-------------|--------|-----------|
| R1    | —         | —        | —    | —           | Not submitted | — |
| R2    | 15.67     | 17.27    | 129  | hot (20.1%) | Global priors, shared grid bug | — |
| R3    | 34.04     | 39.40    | 53   | dead (0.2%) | Global priors | — |
| R4    | 41.67     | 50.66    | 73   | medium (8.9%) | Per-round priors, regime detect v1 | — |
| R5    | 24.69     | 31.52    | 121  | medium (13.4%) | Bad resubmit overwrote good predictions | — |
| R6    | 48.72     | 65.30    | 116  | hot (24.1%) | Per-seed grids, regime detect, FLOOR=0.001 | — |
| R7    | 54.75     | 77.03    | 116  | hot (15.1%) | NCA + replay blend | R6 replays |
| R8    | 24.09     | 35.60    | 195  | dead (2.4%) | **WRONG REGIME** — hot priors on dead round | R7 replays (wrong!) |
| R9    | 66.61     | 103.33   | 139  | medium (11.6%) | NCA + per-terrain replay priors | R4 replays |
| R10   | 60.64     | 98.77    | 126  | dead (0.8%) | NCA + replay priors, NCA overestimated | R9 replays |
| R11   | 32.62     | 55.78    | 153  | hot (24.8%) | Spatial replay priors from R7 — R7 too cold (15.1% vs 24.8%) | R7 replays (WRONG: should have been R6) |
| R12   | 44.72     | 80.31    | 90   | medium (13.7%) | Blended GT priors R11+R6 + T=1.2 | R11+R6 GT |
| R13   | 66.78     | 125.92   | 136  | medium (9.4%) | auto_runner v7 (NCA+replay) | R12 replays |
| R14   | 52.78     | 104.49   | 159  | hot (28.1%) | auto_runner v7 | R13 replays |
| R15   | pending   | —        | —    | hot? (est 30.5%) | Blended GT priors R14+R11 + T=1.2 | R14+R11 GT |

---

## Method Versions

### v1 — Global Static Priors (R2-R3)
- Fixed probability per terrain type (plains, forest, settlement, mountain, ocean)
- Same prior for all rounds
- Shared initial_grid for all seeds (BUG: seeds have different grids)
- FLOOR=0.01
- **Score: 15-34**

### v2 — Per-Round Priors + Regime Detection (R4)
- Detect regime from first queries (settlement fraction)
- 3 sets of priors: dead/medium/hot (from R2-R3 GT)
- Still using shared grid (bug not fixed yet)
- **Score: 41.67**

### v3 — Per-Seed Grids + Improved Regime (R5-R6)
- Fixed per-seed grid bug: GET /rounds/{id} → initial_states
- Each seed uses its own terrain map (~42% cells differ)
- Empirical priors from all available GT
- FLOOR=0.001 tested (API accepts but no reliable improvement)
- **Score: 24-49** (R5 bad resubmit, R6 solid)

### v4 — Replay-Based Priors (R7)
- POST /replay discovered — FREE, unlimited, full 40x40 grid
- Run 50 replays on previous completed round
- Build per-terrain priors from replay final states
- Blend with query observations (Dirichlet alpha=2.0)
- **Score: 54.75**

### v5 — NCA + Replay Blend (R8-R10)
- SimpleNCA CNN trained on R2-R7 ground truth
- NCA gives per-cell prediction from initial terrain features
- Blend: 50% NCA + 50% replay priors from regime-matched round
- Dirichlet alpha=1.0 for observations
- **Problem: NCA overestimates settlements on dead rounds**
- **Score: 24 (wrong regime) to 66.61 (correct regime)**

### v6 — Per-Terrain Replay Priors (tested, not yet deployed)
- Aggregate replays by initial terrain type (not per-cell)
- Works across different seeds and rounds of same regime
- Tested on R9 GT: **76.03 average** (vs actual 66.61)
- **+10 score over v5 NCA approach**

### v7 — Spatial Replay Priors (current, R11+)
- Per-(terrain_type, spatial_context_bucket) priors
- Spatial buckets: near_settl, close_settl, forested, open, far, coastal, inland, forest_adj
- Key insight: plains near settlement → 11.2% settl (vs 5% far from settlement)
- Tested on R9 GT: **77.45 average** (vs flat 76.03, vs actual 66.61)
- **+1.4 over v6 flat priors, +11 over v5 NCA**
- Regime-matched reference rounds: dead=R10, medium=R4/R9, hot=R7

---

## Experiments & Findings

### Experiment 1: FLOOR sensitivity (R10 predictions)
| Floor | Score |
|-------|-------|
| 0.01  | 60.73 |
| 0.005 | 60.64 |
| 0.003 | 60.64 |
**Conclusion:** Floor doesn't matter when prediction values are already > 0.01. Only matters for priors-only (no observations).

### Experiment 2: Gaussian spatial smoothing (R2 GT)
| Sigma | Score |
|-------|-------|
| 0.0   | 40.42 |
| 0.5   | 40.04 |
| 1.0   | 38.85 |
| 1.5   | 38.35 |
**Conclusion:** Smoothing HURTS. Same-type neighbors cos=0.993, different-type cos=0.297. Terrain boundaries are sharp.

### Experiment 3: Cross-seed correlation
- Same cell, different seeds: cosine similarity = 0.706
- 52% cells have >0.95 similarity across seeds
- Pooling observations across seeds: marginal help (14.9→22.7) but hurts when seeds diverge

### Experiment 4: Local SCA simulator (R6 GT)
- Built 5-phase simulator (growth, conflict, trade, winter, environment)
- 200 Monte Carlo simulations
- **Score: 44.51** (worse than v5 approach)
- Settlement expansion rate too low; forest reclamation too high
- **Conclusion:** Simulator rules too approximate. Replay-based approach is superior.

### Experiment 5: NCA CNN model
- SimpleNCA: 3-layer CNN, input=12 features (terrain one-hot + adjacency counts + distance + coastal)
- Trained on R2-R7 GT (5 seeds each = 30 training grids)
- **Score on R9: ~58-66** depending on regime
- **Problem:** Overestimates settlements on dead rounds
- **Conclusion:** NCA adds value as supplement but not as primary predictor

### Experiment 6: Per-terrain replay priors (tested on R9)
| Approach | Score | vs Actual |
|----------|-------|-----------|
| Actual submission (v5 NCA+obs) | 66.61 | baseline |
| Per-terrain flat priors (150 R4 replays) | 76.03 | +9.4 |
| Per-terrain spatial priors (150 R4 replays) | 77.45 | +10.8 |
**Conclusion:** Replay-based priors >> NCA. Spatial context adds +1.4.

### Experiment 7: Regime mismatch (R8 catastrophe)
- R8 initial grid looked hot (frac=0.043 by initial_grid)
- Applied R7 hot replay priors
- R8 GT was actually dead (settl=2.4%)
- **Score: 24.09** (catastrophic)
- **Lesson:** NEVER rely on initial_grid for regime. Use GT-based classification for reference round selection. Verify with first queries.

### Experiment 8: Reference round closeness matters (R11 analysis)
| Reference Round | GT Settl % | Score on R11 (GT=24.8%) |
|-----------------|-----------|------------------------|
| R6 (closest)    | 24.1%     | **70.22** |
| R2              | 20.1%     | 66.24 |
| R7 (used)       | 15.1%     | 52.78 |
| Our actual      | —         | 32.62 |
**Conclusion:** Closest GT settlement % = best reference. R6 would have scored 70.22 vs our actual 32.62. The spatial replay approach (v7) was worse than even flat R7 priors — indicating a bug in spatial bucketing or observation blending.

### Experiment 9: GT-based priors vs replay-based priors
- GT priors = average GT distribution per terrain type from reference round (exact, from /analysis endpoint)
- Replay priors = average final-state distribution from 100+ replays (approximate, from /replay endpoint)
- GT priors consistently score 5-15 points higher because they're computed from hundreds of server-side runs
- **Conclusion:** Use GT priors when available (completed rounds), replays only for calibration

---

## Key KL Breakdown by Terrain (R9)

| Terrain | % of Entropy | avg wKL | Simulated Score | Main Error |
|---------|-------------|---------|----------------|------------|
| Plains  | 67%         | 0.1275  | 68.2           | Settlement overestimate |
| Forest  | 28%         | 0.1429  | 65.1           | Forest underestimate |
| Settlement | 5%       | 0.1960  | 55.5           | Settlement overestimate |

**Biggest opportunity:** Plains cells (67% of entropy). Reducing plains wKL from 0.128 to 0.06 would give score ~85.

---

## Regime Classification (by GT settlement fraction)

| Regime | GT Settl % | Rounds | Best Reference |
|--------|-----------|--------|----------------|
| Dead   | <5%       | R3(0.2%), R8(2.4%), R10(0.8%) | R10 |
| Medium | 5-15%     | R4(8.9%), R5(13.4%), R9(11.6%) | R9 |
| Hot    | >15%      | R2(20.1%), R6(24.1%), R7(15.1%), R11(24.8%) | R6 or R11 (pick closest to target) |

---

## Top Teams Comparison
| Time | Top Score | Our Score | Our Rank | Gap |
|------|-----------|-----------|----------|-----|
| R2   | ~98       | 17.27     | 129      | 81  |
| R6   | ~118      | 65.30     | 116      | 53  |
| R9   | ~140      | 103.33    | 178      | 37  |
| R11  | ~152      | 103.33    | 178      | 49  |

Gap narrowing from 81 to 37 (R9), widening again with later weights.

### Experiment 10: Observations HURT score (R9 simulated)
| Config | Score |
|--------|-------|
| Priors only | 77.64 |
| Priors + Dirichlet obs (n=1) | 48.98 |
| Priors + Log pooling obs | 73.78 |
| Priors + Log pool + T=1.2 | 76.94 |
**Conclusion:** Single observations are too noisy — they REDUCE score. Priors-only is better.

### Experiment 11: Temperature scaling (R9 priors-only)
| Temperature | Score |
|-------------|-------|
| T=0.8 | 63.40 |
| T=1.0 | 77.64 |
| T=1.1 | 80.46 |
| **T=1.2** | **80.68** |
| T=1.3 | 79.05 |
| T=1.5 | 72.71 |
**Conclusion:** T=1.2 optimal. Priors are slightly overconfident, T>1 softens them. **+3 points free.**

### Experiment 12: Per-CELL replay priors (R9 same-round, 86 replays)
| Approach | Score |
|----------|-------|
| Per-cell replay (86 replays, same round) | **88.08** |
| Per-terrain GT priors (same round) | 83.51 |
| Difference | **+4.57** |
**Conclusion:** Per-cell replays are MUCH better than per-terrain because each cell has unique spatial context. This is essentially approximating ground truth. 200+ replays would give 90+.

### Experiment 13: Simulator v2 (data-driven SCA)
- Empirical transition tables from 50 R6 replays
- Context-dependent: (terrain, adj_settl, adj_forest, is_coastal)
- 134 unique context buckets
- **Score on R6 GT: 48.22** (vs v1 44.51, vs replay priors 70.22)
- 1734ms/sim (too slow)
**Conclusion:** Still far below replay priors. SCA rules too simplified.

### Experiment 14: Autocorrelation of regimes
- Lag-1 autocorrelation: -0.237 (weak negative)
- Lag-2: -0.164
- Mean settlement fraction: 0.134, Std: 0.087
**Conclusion:** Regimes are slightly anti-correlated but essentially unpredictable. Must detect from replays of most recent completed round.

---

## Files & Versions
- `participate_v3.py` — regime detection + global priors
- `participate_v4.py` — per-seed grids
- `participate_v5.py` — replay priors (50 per round)
- `participate_v6.py` — replay-powered (100+ replays)
- `participate_v7.py` — NCA + replay blend + spatial (current in auto_runner)
- `auto_runner.py` — autonomous loop, calls participate_v7.py
- `train_nca.py` — NCA model training
- `simulator.py` — local SCA simulator (not production)
- `test_spatial.py` — spatial priors experiment

## Data
- `astar_ground_truth_r{2-8}.json` — GT per seed per round
- `astar_obs_r{4-11}.json` — saved observations
- `nca_model.pt` / `nca_regime_model.pt` — trained NCA weights
