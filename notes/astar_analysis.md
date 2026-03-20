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
