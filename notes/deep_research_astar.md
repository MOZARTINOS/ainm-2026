# Deep Research: Astar Island Score Optimization

## Context
I'm participating in NM i AI 2026, a Norwegian AI competition. One of three tasks is "Astar Island" — a probabilistic prediction challenge on a Norse civilization simulator.

## How the game works
- A 40x40 grid map with terrain types: Ocean, Plains, Forest, Settlement, Port, Ruin, Mountain
- A stochastic 50-year civilization simulation runs on this map (settlements grow, fight, trade, collapse)
- Each round has 5 "seeds" (different random initial conditions on similar maps)
- I get 50 queries total (shared across 5 seeds) to observe 15x15 viewport windows of simulation outcomes
- Each query runs one stochastic simulation and shows me the result in the viewport
- I must predict the probability distribution over 6 terrain classes for each of the 1600 cells
- Ground truth is computed by organizers running HUNDREDS of simulations and averaging results
- Score formula: `score = 100 * exp(-3 * weighted_kl)` where weighted_kl is entropy-weighted KL divergence

## My current approach
- 50 queries = ~10 per seed, each 15x15 viewport = 225 cells observed per query
- With overlapping viewports I get ~1.5 observations per land cell per seed
- I use terrain-type-based priors (e.g., "plains cells become settlement 24% of the time in hot regimes")
- Bayesian update: `prediction = (counts + alpha * prior) / (n_obs + alpha)` with alpha=2.0
- I detect "regime" (dead/medium/hot settlement activity) from first few queries
- Floor = 0.01 on all probabilities to avoid infinite KL

## Key discovery: FREE replay endpoint
- `POST /replay` with round_id and seed_index returns full 51-frame simulation (steps 0-50)
- It's FREE (doesn't cost queries), gives different random sim_seed each time
- BUT only works on COMPLETED rounds, not active ones
- I can run hundreds of replays on past rounds to build precise priors

## My scores so far
- Round 2: 15.7 (terrible — used wrong per-seed grids)
- Round 3: 34.0
- Round 4: 41.7
- Round 5: 24.7 (regression from bad resubmit)
- Round 6: 48.7
- Round 7: pending (resubmitted with replay-calibrated priors)
- Top teams: 85-90 raw score (weighted 115-118)

## The wall I've hit
With ~1.5 observations per cell and Bayesian smoothing, my theoretical maximum is around 55-65 score. Top teams achieve 85-90. The gap is enormous.

## Research questions

1. **Optimal Bayesian inference for categorical distributions with very few observations**
   - Given n=1-2 observations from a Categorical distribution, and a prior, what's the optimal posterior for minimizing expected KL divergence against the true distribution?
   - Is Dirichlet-Multinomial the best approach? What alpha is optimal for KL loss (not squared error)?
   - Papers on "learning distributions from limited samples" with KL divergence loss

2. **Can replay data from past rounds help predict current rounds?**
   - Past rounds have different "hidden parameters" (growth rate, raid intensity, winter severity)
   - But terrain dynamics follow similar patterns
   - How to transfer learned transition probabilities across different parameter regimes?
   - Meta-learning or hierarchical Bayesian approaches for parameter transfer

3. **Optimal experimental design with limited budget**
   - 50 queries across 5 seeds, 40x40 map, 15x15 viewport
   - Where should I place viewports to minimize expected KL divergence?
   - Is uniform coverage optimal, or should I focus on high-entropy regions?
   - Literature on optimal sensor placement, Bayesian optimal experimental design

4. **Exploiting spatial correlation in cellular automaton simulations**
   - Neighboring cells of the same terrain type have cosine similarity ~0.99 in ground truth
   - Can I propagate information from observed cells to unobserved neighbors?
   - Gaussian processes, kriging, or spatial smoothing for probability distributions?
   - Constraint: smoothing across different terrain types hurts (similarity drops to 0.30)

5. **KL divergence minimization with floor constraints**
   - The scoring uses `KL(ground_truth || prediction)` with entropy weighting
   - Floor of 0.01 is recommended but API accepts lower values
   - What's the optimal floor given n observations?
   - Is there an analytical solution for the optimal prediction that minimizes expected KL?

6. **Simulation-based inference / likelihood-free inference**
   - The simulator is a black box with hidden parameters
   - I can observe viewport outputs and settlement metadata (population, food, wealth, defense)
   - Can I infer hidden parameters from limited observations using ABC, neural likelihood estimation, or other methods?
   - Then run many simulations with inferred parameters to approximate ground truth?

7. **Multi-seed strategy**
   - 5 seeds share 50 queries — how to allocate?
   - Seeds have different initial maps (~42% cells differ between seeds)
   - Is it better to concentrate queries on fewer seeds (more obs per cell) or spread evenly?
   - Each unsubmitted seed scores 0, so all 5 must be submitted

8. **What are top teams likely doing differently?**
   - They score 85-90 with the same 50 queries
   - Possible: better priors, better Bayesian updates, spatial models, transfer learning from replays
   - Possible: they found a way to extract more information per query (settlement metadata analysis?)
   - The simulate response includes settlement stats: population, food, wealth, defense, owner_id, has_port, alive
   - Can settlement metadata predict terrain outcomes beyond what the grid shows?
