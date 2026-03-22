# Astar Island Simulator — Version Log

## v1 — Basic SCA (simulator_v1.py)
**Date:** 2026-03-20
**Score on R6 GT:** 44.51 (200 Monte Carlo sims)
**Time:** 2323ms per sim (464s for 200)

**Architecture:**
- 5-phase simulation: Growth, Conflict, Trade, Winter, Environment
- Settlement class with population, food, wealth, defense, has_port, alive, owner_id
- Hardcoded parameters from manual replay analysis

**Key Problems:**
- Settlement expansion rate too low (plains→settl: 11.7% vs GT 23.9%)
- Forest reclamation too high (forest stays forest 87.4% vs GT 57.8%)
- Conflict phase too simple (random raids)
- No trade mechanics
- Too slow for production use (2.3s per sim)

**Comparison:**
- v1 simulator: 44.51
- Per-terrain replay priors (no sim): 76.03
- Per-terrain spatial priors (no sim): 77.45
- Actual R6 submission: 48.72

**Conclusion:** Simulator is WORSE than simple replay-based priors. Rules need significant improvement before simulator adds value.

---

## v2 — Deep Research Informed (planned)
**Date:** 2026-03-21
**Target:** 70+ on R6 GT
**Status:** Deep Research launched for SCA reverse-engineering techniques

**Planned improvements:**
- Data-driven transition rules extracted from frame-by-frame replay analysis
- Conditional transition probabilities (context-dependent: adj_forest, adj_settl, dist_settl)
- Parameter calibration via ABC or direct extraction from settlement metadata
- Numba JIT for speed (<50ms per sim)
- Validation against multiple rounds (R2-R11)

---

## Comparison: Simulator vs Alternative Approaches

| Approach | Best Score (tested) | Speed | Works on Active Rounds? |
|----------|--------------------|----|------------------------|
| simulator_v1 | 44.51 | 2.3s/sim | Yes (if calibrated) |
| Per-terrain GT priors | 76.03 | instant | No (needs completed ref round) |
| Spatial GT priors | 77.45 | instant | No (needs completed ref round) |
| Replay-based priors (200 replays) | ~70 | ~100s | No (only completed rounds) |
| NCA CNN | 58-66 | <1s | Yes |
| Observations only (50 queries) | 40-55 | ~60s | Yes |

**Key insight:** Simulator only makes sense if it can BEAT per-terrain GT priors (76+). Otherwise, just use GT priors from closest reference round. Simulator's advantage: works on active rounds with unknown parameters — IF parameter inference is fast and accurate.
