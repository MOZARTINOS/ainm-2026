You are researching techniques for reverse-engineering a stochastic cellular automaton (SCA) simulator from observed state sequences. This is for an AI competition where we need to build a high-fidelity clone of a black-box Norse civilization simulator.

## Our Situation

We have a 40x40 grid simulation that runs 50 time steps. Each step processes 5 phases (Growth, Conflict, Trade, Winter, Environment). We have UNLIMITED access to full step-by-step replay data: 51 frames per replay, each frame containing the complete 40x40 grid state and full settlement metadata (position, population, food, wealth, defense, alive, has_port, owner_id).

Our current local simulator scores only 44/100 against ground truth. We need 80+. The ground truth is computed by averaging hundreds of simulation runs.

## What We Know About the Simulation

**Grid**: 40x40, terrain types: ocean(static), plains, forest, mountain(static), settlement, port, ruin

**Settlement properties**: x, y, population, food, wealth, defense, tech_level, has_port, alive, owner_id

**5 Phases per year**:
1. **Growth**: settlements produce food from adjacent terrain (forests), expand to adjacent plains when prosperous
2. **Conflict**: raids between settlements, desperate ones raid more, longships extend range
3. **Trade**: ports exchange wealth/food if not at war, tech diffuses
4. **Winter**: all settlements lose food, collapse threshold → become ruins
5. **Environment**: ruins reclaimed by settlements or become forest

**Hidden parameters** that vary per round: growth_rate, winter_severity, raid_intensity, trade_effectiveness, forest_reclaim_rate

## Research Questions (in priority order)

1. **What are the best techniques for extracting transition rules from frame-by-frame state sequences of a stochastic cellular automaton?** I need methods that can identify conditional transition probabilities (e.g., P(cell becomes settlement | adjacent to 2 existing settlements AND has forest neighbor)) from thousands of observed state transitions.

2. **How to calibrate hidden parameters of a stochastic simulation from observed trajectories?** We have step-by-step settlement metadata (food, population changes between frames). What methods can extract parameters like winter_severity = f(observed_food_loss), growth_rate = f(observed_expansion_events)?

3. **What are proven approaches for building high-fidelity SCA simulators that match empirical distributions?** Not exact trajectory matching, but distribution matching — our 1000 simulations should produce the same per-cell class frequency distribution as the server's hundreds of runs. Methods: ABC (Approximate Bayesian Computation), likelihood-free inference, neural simulation, learned transition kernels.

4. **How to handle context-dependent transition rules?** The probability of a cell transitioning from plains to settlement depends on local context (adjacent settlements, nearby forests, distance to nearest settlement). What architectures/methods capture these spatial dependencies efficiently?

5. **What are techniques for learning multi-phase sequential dynamics?** Each year has 5 phases that interact. How to decompose observed year-to-year transitions into phase-specific rules? Can we use the settlement metadata changes (food delta, population delta) between frames to identify which phase produces which effects?

6. **How to validate a simulator clone against the original?** Beyond final-state distribution matching, what metrics and diagnostic tools reveal where our simulator diverges? Per-step trajectory comparison, settlement survival curves, spatial expansion patterns?

## Constraints
- Must be implementable in Python with NumPy in a few hours
- Must run 1000 simulations in under 60 seconds (40x40 grid, 50 steps)
- We have data from 10 completed rounds, each with 5 seeds
- We can run unlimited replays (each ~0.5s API call)

## What I Need
- Specific, implementable algorithms (not just theory)
- Python code patterns or pseudocode
- References to papers/libraries for SCA parameter inference
- Practical tips for making the simulator match the real one
- Common pitfalls in SCA reverse-engineering
