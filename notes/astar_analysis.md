# Astar Island Analysis — Round 2

## Round 2 Result
- **Score: 15.67** (rank 129)
- Seed scores: [14.87, 15.88, 15.54, 16.01, 16.04]
- Weighted KL ~ 0.618

## ROOT CAUSE: _terrain_to_class BUG

`min(max(terrain, 0), 5)` mapped ocean (10) and plains (11) to class 5 (mountain).
This caused **74% of cells** (1183 out of 1600) to get predicted as 95% mountain.
Fixed: explicit handling of 10->0 and 11->0.

## Ground Truth Analysis (5 seeds x 1600 cells)

### Transition Distributions (init terrain -> ground truth class probs)
```
         [empty,  settl,  port,  ruin, forest, mount]
plains:  [0.612, 0.186, 0.014, 0.018, 0.154, 0.015]
forest:  [0.480, 0.193, 0.012, 0.019, 0.284, 0.014]
settlem: [0.513, 0.240, 0.006, 0.022, 0.201, 0.018]
mountain:[0.424, 0.153, 0.005, 0.016, 0.176, 0.227]
ocean:   [0.950, 0.014, 0.006, 0.005, 0.021, 0.005]
```

### Key Insights
1. **Mountains**: varies by seed! Seed 0 = 100% static (all 30 cells). Seeds 1-4 = highly dynamic (~23% mountain, rest spread). Average: 22.7% mountain.
2. **Ocean**: border cells, 95% static (empty/plains class).
3. **Plains**: most common terrain (1001 cells), ~61% stays empty.
4. **Forest**: 28.4% stays forest, 48% becomes empty, 19% settlement.
5. **Settlements**: 24% stay settlement, 51% become empty, 20% forest.

### KL Contribution by Terrain Type
| Terrain | Contribution | % of total |
|---------|-------------|------------|
| Plains | 0.414 | 67% |
| Forest | 0.170 | 27% |
| Settlement | 0.014 | 2% |
| Mountain | 0.014 | 2% |
| Ocean | 0.011 | 2% |

### What Top Teams Do Better
- Score ~85+ vs our 15.67
- Their weighted KL ~ 0.05 vs our 0.62
- They likely: (1) have correct terrain mapping, (2) use per-cell observations
  to refine beyond global priors, (3) may use spatial smoothing

## Simulated Scores
- With fixed priors only (no observations): **40.38** (2.6x our actual)
- With observations + correct priors: should be **60-80+** (needs testing)
- Our actual: 15.67 (broken by terrain mapping bug)

## Fixes Applied
1. `_terrain_to_class`: 10->0, 11->0 (was mapping both to 5=mountain)
2. Priors updated from ground truth distributions
3. Added `_blend_low_obs` for cells with 1-3 observations
4. Both `predictor.py` and `auto_participate.py` updated

## Settlement Metadata
Settlements have: population, food, wealth, defense, has_port, alive, owner_id.
Positions are (x, y) - settlements move around the map between seeds.
Average population: ~2.5-3.5.

---

# Round 3 Preparation & Key Findings

## Leaderboard (after Round 2)
- Top teams: 95-99 weighted score (~85-90 raw)
- Our position: 129th with 15.67 (bug-affected)
- 176 total teams, 94 with >1 round

## Critical Discovery: FLOOR matters more than expected
```
floor=0.01:   upper bound = 94.5 (weighted 104.2)
floor=0.005:  upper bound = 97.2 (weighted 107.2)
floor=0.001:  upper bound = 99.4 (weighted 109.6)
```
**API accepts values < 0.01!** Changed FLOOR from 0.01 to 0.001.

## Gaussian Smoothing: NOT the answer
Tested sigma 0.3-2.0 on global priors — score DECREASES with smoothing.
- sigma=0.0: avg 40.42
- sigma=1.5: avg 38.35

## Spatial Correlation Analysis
- Same-type neighbors: cosine similarity **0.993** (near identical!)
- Different-type neighbors: cosine similarity **0.297**
- Conclusion: spatial correlation = driven by initial terrain type, already captured by priors

## Cross-seed Correlation
- Same cell across seeds: cosine similarity **0.706**
- 52% of cells have >0.95 similarity across seeds
- Pooling 5 seeds: marginal improvement (14.9→22.7), not silver bullet

## Settlement Distance Effect
```
Dist 0:    P(settl)=0.240 | P(empty)=0.513
Dist 1-2:  P(settl)=0.197 | P(empty)=0.570
Dist 3-5:  P(settl)=0.188 | P(empty)=0.575
Dist 11+:  P(settl)=0.093 | P(empty)=0.722
```
Moderate signal: settlement probability drops 2.5x at distance 11+ vs 0.

## Round 3 Changes
1. FLOOR: 0.01 → 0.001
2. Smart viewport placement (maximize land coverage)
3. Greedy coverage with per-seed offsets
4. Settlement proximity boost in predictions
5. **BUG**: accidentally overwrote seed 0 with test priors (resubmitted with correct priors)

---

# Round 3 Results

## Score: 34.04 (rank 127, weighted 39.40)
- Seeds: [27.97, 36.50, 34.53, 34.93, 36.26]
- Seed 0 = 27.97 (accidentally overwritten with priors-only)
- Seeds 1-4 avg = 35.56 (with observations)

## CRITICAL: Transition distributions CHANGE between rounds!
```
                 Round 2          Round 3          Delta
plains→settl:    18.6%            0.3%            -18.3%!!
plains→empty:    61.2%           79.1%            +17.9%
forest→settl:    19.3%            0.3%            -19.0%!!
forest→forest:   28.4%           38.8%            +10.4%
settlement→settl: 24.0%           0.6%            -23.4%!!
```
Round 3 was a "low-settlement" world — almost no settlements at all.
Our R2 priors predicted ~20% settlement everywhere → massive KL loss.

## Score Impact
- R2 priors (wrong) on R3 data: avg 22.30
- R3 priors (correct) on R3 data: avg 39.06
- Our actual (R2 priors + observations): avg 34.04
- Observations partially compensated but couldn't fully fix wrong priors

## KL Breakdown (R2 priors on R3 data)
- forest class: 65.2% of KL (over-predicted empty, under-predicted forest)
- empty class: 43.3% of KL (under-predicted empty probability)
- settlement class: -7.5% (overprediction, but offset by log ratio)

## Key Lesson: Regime Detection
Each round has different dynamics. Using 1-2 early queries to detect the "regime":
- If many settlements appear → high-settlement round (use R2-like priors)
- If few/no settlements → low-settlement round (use R3-like priors)

## Round 4+ Plan
1. **Regime detection**: Use 2-3 initial queries to estimate settlement density
2. **Adaptive priors**: Interpolate between R2 and R3 priors based on regime
3. **FLOOR=0.001**: Already implemented
4. **Save observations**: For resubmission capability
5. **Target: 50+ raw score** (realistic with adaptive priors)
