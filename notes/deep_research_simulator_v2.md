# Reverse-Engineering Stochastic Cellular Automata for Complex Multi-Phase Simulators

**Key Points:**
*   **Rule Extraction:** Extracting transition rules from stochastic cellular automata (SCA) can be achieved reliably through empirical frequency counting and $l_1$-norm optimization [cite: 1], exploiting the vast amount of available frame-by-frame replay data.
*   **Parameter Calibration:** Research suggests that Approximate Bayesian Computation (ABC) is the most effective likelihood-free inference method for calibrating hidden stochastic parameters based on observed summary statistics [cite: 2, 3].
*   **Performance Constraints:** It is highly likely that meeting the constraint of 1000 simulations in under 60 seconds requires pure NumPy vectorization, specifically leveraging `numpy.lib.stride_tricks.as_strided` and `numpy.einsum` to perform batch 2D convolutions without Python-level loops [cite: 4, 5].
*   **Spatial Validation:** The evidence leans toward using a combination of the Lee-Sallee shape index [cite: 6, 7], Moran's I for spatial autocorrelation [cite: 8, 9], and the Wasserstein distance [cite: 10, 11] to rigorously validate spatial simulators against ground truth data.
*   **Multi-Phase Disentanglement:** Decomposing complex sequential dynamics requires mapping specific metadata deltas to their corresponding phenomenological phases (e.g., isolating winter severity through baseline food loss metrics).

The challenge of reverse-engineering a black-box stochastic cellular automaton (SCA) simulatorвЂ”particularly one governing a multi-phase, complex system such as a Norse civilization modelвЂ”lies at the intersection of inverse problem theory, likelihood-free inference, and high-performance computing. Because the underlying rules contain stochastic elements, deterministic mapping is impossible; instead, the goal is to construct a generative model whose probability distributions, spatial clustering, and temporal dynamics perfectly mirror the empirical distributions of the target system. This comprehensive report delineates the theoretical foundations and practical methodologies necessary to build, calibrate, and validate a high-fidelity Python/NumPy SCA clone capable of executing 1000 parallel simulations in under 60 seconds.

---

## 1. Extracting Transition Rules from State Sequences

The fundamental task in cloning an SCA is discovering the local transition rules that dictate the evolution of the 40x40 grid. A stochastic cellular automaton, unlike Conway's Game of Life, determines its next state probabilistically based on the configuration of its neighborhood [cite: 12, 13]. Given that you have access to frame-by-frame data (51 frames per 50-step simulation), you possess a fully observable Markov decision process where the global state at time $t+1$ depends only on the state at time $t$ and the hidden transition parameters [cite: 14].

### 1.1. Empirical Frequency Estimation (Tabular Extraction)
For categorical transitions (e.g., the probability of a "plains" cell becoming a "settlement"), the most robust and rapidly implementable approach in Python is Empirical Frequency Estimation. Since you have 10 rounds $\times$ 5 seeds $\times$ 50 steps $\times$ 1600 cells = 4,000,000 observed transitions, the law of large numbers allows you to approximate the conditional probabilities directly.

The probability of a cell transitioning to state $S_{t+1}$ given its neighborhood $N_t$ is:
\[ P(S_{t+1} | S_t, N_t) \approx \frac{\text{Count}(S_{t+1}, S_t, N_t)}{\text{Count}(S_t, N_t)} \]

To implement this efficiently in NumPy:
1. Define a neighborhood kernel (e.g., a $3 \times 3$ Moore neighborhood) [cite: 15, 16].
2. Use `scipy.signal.convolve2d` to calculate the number of adjacent settlements, forests, and ports for every cell in every historical frame [cite: 13, 16].
3. Flatten the historical states, the computed neighborhood contexts, and the target $t+1$ states into tabular arrays.
4. Use `numpy.unique(..., return_counts=True)` to count the frequencies of each $(S_t, N_t) \rightarrow S_{t+1}$ mapping.

This approach bypasses the need for complex machine learning models, strictly adheres to the "few hours to implement" constraint, and avoids the state-space explosion by only registering neighborhood configurations that actually occur in the data.

### 1.2. Neural Cellular Automata (NCA) Theory
While the time constraint favors NumPy tabular extraction, the academic state-of-the-art for this problem is the Neural Cellular Automaton (NCA) paradigm, introduced by Mordvintsev et al. [cite: 17, 18]. NCAs parameterize the transition rules using a Convolutional Neural Network (CNN) and learn the rules via backpropagation through time (BPTT) [cite: 18, 19]. By defining the cell state as a continuous vector and the updates as differentiable logic gates, systems can learn to "grow" and regenerate target spatial patterns [cite: 20, 21].

If you transition to a PyTorch implementation in the future, NCAs offer a generalized way to handle continuous metadata (wealth, population) alongside discrete terrain states, minimizing a masked Mean Squared Error (MSE) loss between the simulated step and the observed frame [cite: 22, 23]. However, for pure NumPy implementations, extracting parameterized linear or decision-tree logic from the tabular data remains the optimal path.

---

## 2. Calibrating Hidden Stochastic Parameters

Your simulation relies on hidden parameters (e.g., `growth_rate`, `winter_severity`, `raid_intensity`) that vary per round. Because the simulator is stochastic, calculating an exact mathematical likelihood for these parameters is intractable. This necessitates Likelihood-Free Inference, specifically Approximate Bayesian Computation (ABC) [cite: 2, 24, 25].

### 2.1. Approximate Bayesian Computation (ABC)
ABC algorithms are designed to infer parameter values by simulating data from a prior distribution and accepting parameters that produce summary statistics close to the observed data [cite: 3, 26]. It assumes the existence of model error and gives highly accurate results when sufficient summary statistics are chosen [cite: 27].

**The Standard Rejection ABC Algorithm:**
1. Sample a candidate parameter vector $\theta^*$ from a prior distribution $\pi(\theta)$.
2. Simulate a dataset $X^*$ from the generative model $M(\theta^*)$.
3. Compute a summary statistic $S(X^*)$ and compare it to the observed summary statistic $S(X_{obs})$ using a distance metric $\rho$.
4. Accept $\theta^*$ if $\rho(S(X^*), S(X_{obs})) < \epsilon$, where $\epsilon$ is a tolerance threshold [cite: 25, 26].

### 2.2. Selecting Summary Statistics for the Norse Simulator
To calibrate the parameters using ABC, you must map the macro-behaviors to summary statistics derived from your step-by-step metadata:

*   **`winter_severity`**: This strictly causes food loss. The summary statistic should be the average negative delta of food across all settlements during the transition from Trade to Winter. 
    \[ S_{winter} = \frac{1}{N_{settlements}} \sum \max(0, \text{Food}_t - \text{Food}_{t+1}) \]
*   **`growth_rate`**: This governs food production and spatial expansion. The summary statistic should be the number of new settlements formed per step, normalized by the number of existing highly-prosperous settlements adjacent to plains.
*   **`raid_intensity`**: This drives conflict. The summary statistic is the total reduction in global population and wealth not attributed to winter starvation.
*   **`forest_reclaim_rate`**: The frequency with which ruins transition to forest, normalized by the total number of ruins.

### 2.3. Utilizing pyABC or Custom SMC-ABC
For rapid implementation, the `pyABC` Python library provides a highly scalable framework for ABC utilizing Sequential Monte Carlo (SMC) [cite: 28, 29, 30]. ABC-SMC iteratively reduces the tolerance threshold $\epsilon$, adapting the prior based on previously accepted parameters, making it vastly more efficient than Rejection ABC [cite: 25, 28]. If external libraries cannot be installed for the competition, a basic Rejection ABC loop can be written in pure NumPy in under 50 lines of code, leveraging your fast batch simulator (detailed in Section 7) to generate $X^*$ rapidly.

---

## 3. Building High-Fidelity SCA Simulators (Distribution Matching)

To score 80+ against the ground truth, your local simulator must replicate the *distribution* of outcomes averaged across hundreds of server runs, rather than attempting to overfit to a specific trajectory. 

### 3.1. Ensemble Simulation and Ergodicity
Stochastic cellular automata are often analyzed within the framework of interacting particle systems and locally interacting Markov chains [cite: 12, 31]. The target distribution you are trying to match is the expected value of the grid over time. Because the server computes the ground truth by averaging hundreds of runs, you must execute an **ensemble simulation**. By running 1000 simultaneous simulations (a batch) and calculating the mean state of each cell, you approximate the true expected continuous distribution of the server's SCA.

### 3.2. Distribution Matching Strategies
Instead of matching categorical values (which are highly sensitive to the "butterfly effect" in chaotic CA systems), you match probabilities. If a cell on the server's ground truth has a 0.6 probability of being a forest and 0.4 of being a settlement, your batch of 1000 simulations should produce approximately 600 forests and 400 settlements in that exact cell. 

To tune your transition rules to hit these specific distributional targets, you treat the ensemble average as a continuous grid and compute the **Wasserstein Distance** (Earth Mover's Distance) between your ensemble average and the ground truth [cite: 10, 11]. The Wasserstein distance serves as an excellent loss function because it measures the minimal spatial "transport cost" to align your predicted distribution with the real one, providing smoother gradients for tuning rules than naive pixel-wise Mean Squared Error [cite: 11, 32].

---

## 4. Handling Context-Dependent Transition Rules

Spatial dependencies are the defining characteristic of Cellular Automata. The probability of settlement expansion relies on the spatial context: adjacent settlements, proximity to forests (for food generation), and coastal access (for ports/trade).

### 4.1. Spatial Feature Extraction via Convolutions
To capture these dependencies efficiently, you must use 2D convolution kernels. As noted in the development of differentiable cellular automata and image processing, convolutions act as a "stencil" that sums neighbor values [cite: 16]. 

For example, to detect if a plains cell is adjacent to exactly 2 settlements, you define a binary mask of settlement locations and convolve it with a Moore neighborhood kernel:
```python
import numpy as np
from scipy.signal import convolve2d

# Settlement mask (1 if settlement, 0 otherwise)
settlement_mask = (grid == SETTLEMENT_ID).astype(int)

# Moore neighborhood kernel (excluding center)
kernel = np.array([[cite: 2],
                   [cite: 2],
                   [cite: 2]])

# Count adjacent settlements
adjacent_settlements = convolve2d(settlement_mask, kernel, mode='same', boundary='wrap')
```
This method replaces slow `for` loops with optimized C-level spatial queries [cite: 4, 13]. You can create separate context arrays for `adjacent_forests`, `adjacent_ruins`, and `coastal_proximity` (by convolving the static ocean mask). 

### 4.2. Composite Context Matrices
Once the convolutions are applied, you stack these features into a multidimensional context tensor. Every cell on the 40x40 grid is now represented by its current state and a vector of contextual features. Transition probabilities are then applied through logical masks:

```python
# Boolean mask for cells eligible to become new settlements
eligible_expansion = (grid == PLAINS_ID) & (adjacent_settlements >= 2) & (adjacent_forests >= 1)

# Apply stochastic expansion based on calibrated growth_rate
random_matrix = np.random.rand(40, 40)
new_settlements = eligible_expansion & (random_matrix < growth_rate)
grid[new_settlements] = SETTLEMENT_ID
```
This vectorized, context-aware rule application ensures the model evaluates the entire 40x40 grid simultaneously [cite: 33].

---

## 5. Learning Multi-Phase Sequential Dynamics

The Norse simulator operates in 5 distinct phases (Growth, Conflict, Trade, Winter, Environment) per time step. Because you only observe the final frame of the year, you are faced with a "partially observable" temporal dynamic. You must decompose the observed year-to-year delta into phase-specific effects.

### 5.1. Phenomenological Disentanglement
The key to disentangling the 5 phases lies in identifying the mutually exclusive effects of each phase on the settlement metadata.
1.  **Environment**: This phase strictly alters terrain (ruins $\rightarrow$ forest). Terrain changes do not affect immediate settlement metadata (population/wealth). Thus, any ruin disappearing and becoming a forest can be isolated and modeled entirely independently.
2.  **Winter**: This phase strictly reduces food and triggers collapse (settlement $\rightarrow$ ruin) if food/population thresholds are breached. Winter severity can be isolated by looking at the baseline food loss across *all* settlements, regardless of trade networks.
3.  **Growth**: Increases food (based on forest proximity) and triggers expansion. By looking at cells that transitioned from plains to settlements, you can isolate the conditions of the Growth phase.
4.  **Trade**: Equalizes wealth and food among settlements with ports. You can identify Trade mechanics by isolating coastal settlements and observing the minimization of variance in their wealth/food compared to landlocked settlements.
5.  **Conflict**: Reduces population and wealth, redistributes wealth (looting). This is the stochastic remainder after Growth, Trade, and Winter effects are accounted for.

### 5.2. Delta Analysis
By computing the delta matrices ($\Delta \text{Food}$, $\Delta \text{Pop}$, $\Delta \text{Wealth}$) between frame $t$ and $t+1$, you can write a deterministic sequential pipeline that attempts to reconstruct the intermediate states. 

If you assume the pipeline is $S_{t+1} = E(W(T(C(G(S_t)))))$, you can calibrate the phases in reverse order of their strictness. Winter and Environment are highly predictable. Subtract their estimated effects from the delta matrices. The remaining deltas belong to Growth, Conflict, and Trade. By systematically peeling back these layers during your initial data analysis, you can reverse-engineer the exact mathematical operators applied during each phase.

---

## 6. Validating a Simulator Clone

Final-state distribution matching is insufficient to guarantee that the underlying dynamics of the clone match the original simulator. Relying strictly on endpoint analysis masks trajectory divergence. You must employ rigorous spatial and temporal validation metrics [cite: 8, 34].

### 6.1. Spatial Validation Metrics
*   **Lee-Sallee Shape Index**: This structural measurement assesses the spatial fit of the predicted urban/settlement footprint against the actual footprint [cite: 7, 8]. It is defined as the ratio of the intersection to the union of the simulated and actual spatial areas. A higher Lee-Sallee index indicates excellent spatial fidelity [cite: 7].
*   **Moran's I**: To ensure your clone mimics the spatial autocorrelation (clustering) of the Norse settlements, Moran's I is utilized [cite: 9, 10, 35]. It evaluates whether settlement patterns exhibit spatial clustering (positive I) or dispersion (negative I). If the true game generates highly clustered defensive settlements but your simulator generates dispersed settlements, Moran's I will immediately flag the divergence [cite: 9, 36].
*   **Wasserstein Distance**: Evaluates the disparity between probability density functions of the continuous metadata (e.g., population distributions across the grid) [cite: 10, 11]. It measures the spatial costs of prediction errors, making it superior to Mean Squared Error for geospatial applications [cite: 11, 32].

### 6.2. Temporal and Survival Metrics
Beyond spatial footprints, monitor the **Settlement Survival Curve** (Kaplan-Meier estimator of settlement lifespan before becoming a ruin). If your simulator's settlements collapse too early compared to the ground truth, your Winter threshold or Conflict intensity parameters are incorrectly calibrated. Additionally, tracking the global total of food and wealth over the 50 steps will reveal if your simulator suffers from unnatural value injection or leakage.

---

## 7. Meeting the Performance Constraints (1000 Sims < 60 Seconds)

A fundamental constraint is executing 1000 simulations of a 40x40 grid over 50 steps (2,000,000 total grid states) in under 60 seconds using Python and NumPy. Standard iteration over the grids will fail drastically due to Python's looping overhead and boxing/unboxing of number classes [cite: 33].

### 7.1. Batch Vectorization (The N-Dimensional Array)
You must discard the concept of "running a simulation 1000 times." Instead, you run **one simulation of a batch size of 1000**. Your grid representation must be a 3D NumPy array of shape `(1000, 40, 40)`, or a 4D array `(1000, Channels, 40, 40)` to hold both terrain and metadata simultaneously.

### 7.2. Extremely Fast Batch Convolutions
`scipy.signal.convolve2d` does not support batched 3D convolutions natively. Looping over 1000 grids to apply `convolve2d` will violate your time constraint [cite: 4]. 

To achieve sub-second processing for the entire batch, you must use **NumPy Stride Tricks** and `numpy.einsum` [cite: 4, 5]. By manipulating memory strides, you can create a 5D view of the 3D array consisting of all $3 \times 3$ neighborhoods, and then use Einstein summation to apply the rule kernel simultaneously across all 1000 simulations:

```python
import numpy as np

def batch_convolve_3x3(x, filter_kernel):
    # x shape: (Batch, 40, 40)
    # filter_kernel shape: (3, 3)
    
    # Pad the spatial dimensions for 'same' convolution / 'wrap' boundary
    x_padded = np.pad(x, ((0,0), (1,1), (1,1)), mode='wrap')
    
    # Extract shape and strides
    b, h, w = x_padded.shape
    shape = (b, h - 2, w - 2, 3, 3)
    strides = x_padded.strides + x_padded.strides[1:]
    
    # Create strided view (zero memory copy)
    windows = np.lib.stride_tricks.as_strided(x_padded, shape=shape, strides=strides)
    
    # Apply the kernel using einsum across the batch
    return np.einsum('ij,bklij->bkl', filter_kernel, windows)
```
This specific pattern is recognized as the fastest method for CPU-bound 2D batch convolution in Python without relying on external compiled C-extensions [cite: 4, 5, 37]. This capability guarantees that neighborhood awareness for the Growth and Conflict phases occurs in milliseconds.

### 7.3. Masked Array Operations
With batch convolutions providing the context, all transitions are handled via massive boolean arrays. 
```python
# random shape: (1000, 40, 40)
rands = np.random.rand(1000, 40, 40)

# Evaluate state changes for the entire batch simultaneously
grid_batch[survives_winter_mask] = SETTLEMENT_ID
grid_batch[collapses_mask] = RUIN_ID
```
By strictly keeping execution at the C-level backend of NumPy, 50 steps for 1000 grids will complete in a fraction of your 60-second limit, leaving ample computational headroom for overhead.

---

## 8. Practical Tips and Common Pitfalls

### Practical Tips
1. **Pre-compute Static Contexts:** The `ocean` and `mountain` terrain cells are static. Convolutions determining "coastal access" or "mountain defenses" should be computed exactly once during initialization and cached, rather than calculated per step.
2. **Seed Exploitation:** The ground truth averages *hundreds* of runs. To match this, ensure your 1000 batch simulations use highly diversified `np.random.seed` initializations to ensure proper uniform coverage of the stochastic space.
3. **Automated Unit Testing per Phase:** Build isolated tests for each phase. Create a mock grid, run *only* the Trade function, and assert that wealth has conserved mass and diffused correctly across port networks. 

### Common Pitfalls in SCA Reverse-Engineering
1. **The Fallacy of Exact Trajectory Matching:** A common pitfall in stochastic reverse-engineering is using Mean Squared Error (MSE) to compare single simulation runs against historical replays [cite: 10]. Because chaotic divergence occurs naturally in SCAs, matching exact states leads to catastrophic overfitting. Always match distributions (e.g., via ABC and Wasserstein distances) [cite: 11].
2. **Boundary Condition Neglect:** Cellular Automata are highly sensitive to boundary conditions [cite: 16]. Ensure you determine whether the Norse simulator uses a `wrap` (toroidal), `fill` (zero-padded edge), or `symm` (reflective) boundary. Incorrect boundaries will lead to cascading errors accumulating from the edges of the 40x40 map inwards over the 50 steps.
3. **Sequential Interference:** When processing the 5 phases, updating the master grid *in-place* during an iteration causes the "half-updated" state to interfere with subsequent cell calculations. Always calculate the `next_state` using data exclusively from the `current_state` (double buffering), unless the specific phase rules mandate asynchronous cascade effects.

By combining empirical tabular extraction for discrete logic, Approximate Bayesian Computation for hidden parameter inference, and stride-tricked batch convolutions for ultra-fast NumPy execution, you will possess a robust, high-fidelity SCA simulator capable of achieving excellent distribution matching scores in the competition.

**Sources:**
1. [researchgate.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFDAPZIfzza2zC8hnY4onxJ9OTI67oZhN9KyspOIKxGtV_3_bi-3BwqRHMr9bROOwL9jpQ74gZYb4sJWHtWdICPX3p5gzX9K5uvWmo5WklgxdDQY3mcqIGgiAOhatslBEleSR9yBH2o3Vf-xj0zb_ZdKkOmwDF0X27fJdh8FjrTXTkmpFBzfNRJDhOtfDVRLia8f3sDHU-qU-1AJhP5_g6um9BZt0I=)
2. [arxiv.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGCVX0aT58bX58tfJPZIhKrQHcCUeJM71NjaGYT1pN1raVXDNWcpeZyiLAQyciVQL4PaK8rMDXM0A4wA69d5JqtAbX4Wlt4_hUDttWGkIchYgLNzvZvYOo3xg==)
3. [reading.ac.uk](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE3avRu5GzzoPi7rxmJByzYo53838cvuE_L4h4P5sWfUpkLRYUEy5X6sDuX2RzK4yY3eDem0ca6wPt9tJknEixBMnqMlypwrYZtu8HzwFgo2Ndvt3NYu6XVnXRyvJmilMSXpnIOozUqQDRxSIuL93SsWNLemDRMbakf0TjdLplmq0e6)
4. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGb6IVpd6KyT6e5_Pg3VVdA-T_wwSoLuVCDm80niu7kjikt3zYCw5jHqIZiEgCCPiy_leScLwCaw_Hm3VymJlhAa1vT_NzeCuU-mITD1PhaG8QGcDe5SRJ0dla4i5ujyd8tuqjuINwgbDuX_EFrbwYZWgIptu36ZqBYk5e2GCvxb1cdhlPmdPs=)
5. [stackoverflow.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF0zXURIOo8RHj0O6SDltDGYaUYEcchfzywIejmq2LyxfCP8AOBd8Cz3QKLcFLchkrgpPwnSZzVwn1XFkYgcj2RXUv5qxcLnRSH4Dc5uQy8O8uEgHMNINx9O5h7K9kiEek49MfAL9pxsmaNYCMPLzG-7mqeXIwXzYTmqHfrn5Ya9seXnGLBybQm1Q4zAO2c)
6. [nih.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGrKo13oGz2SW_q7U7NxzGIxnmm3cSPite8utDjQvwBUl5iSLvOEr91Iog3KbA3i8JbnM31IkEFuqIVFsIaAWU6I066PuPcnZrMdKpFvufDZv32rUIFCFLrAO3YP7EP3rSzVdKQkjM3AQ==)
7. [mdpi.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHUlsBMY64rIXZHdTtRAbYOYqqqaDxgp0G7PMmelgsKrYVrycZvG3Xnrhl9UOzm0V_CNOk4gN14ZPrHX8UMt2jluE6KPLVJYYmwEAeJegy9--uTsB4EAoJWvqbI2g==)
8. [intechopen.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF9oUPnbEPEeLVQCPnf1FMNYpuQ_MwfZ2HgdUv5nr3EvJikxLVj3dRBgjDQ45Ns6_4YD9sXm2VlDISShduFOyhtTTFEVavVqmEWnGv_JaGg1-hicVRttnIdCPNqHzkecA==)
9. [copernicus.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH3j0TKBd-2nlFp_qO0pH2XAz7GWhvuiVf7fLpCRS0-sRnEyXEFUe5yVSvypCzijiJjl4Pb-XNWhaa4773bKCRy8V1s9-RPbn1ByGoLTHO1EKmtGkTvjcDcFiPnas2oPj-ifskPr62m3A==)
10. [nih.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH1bX1Gf28_fs_SSBlA0n0bGM5s1Y6rePKr1nnZcX8Pk19QH1ieXQglG70Hse4tyoVEIb-XN_9kY8Oa5MPLCGxwQhE5nbDRoe8ant1qhyWJj2sM-WFTbyB_bauK4CwhprN51mVBmN0P3Q==)
11. [arxiv.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEn5IbeLxL41_-LNW0zF38IsncerdxGa9picWTtx8M017sWpBuFZV3U_yfVQbpl_rbhzaKFFacwyZmrfcJ8LA_Qi5dA_BwnPhApVptHEg2vtGIY39K884P-kQ==)
12. [wikipedia.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHEYrI2KZUvPidv9GqSf20Ns0TSahUSTVbyNRIWn1mXUBC-EWVd93r8DFq0pQH9-OQlJSWHMXwzvJGWE4QGH9nB3A1w8M0na_BuQNKoTtL3RPidIBNP-wzVBf23G1wON5ArdtA7Q5C8WX7IINKpUwcqJw==)
13. [nicholasrui.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGfwexQRnOf1pbrzCcilsdGgC_8zGjWyRaIZgjZ2fc4Hs06_payiq26RmJuGLdWYxijfr92z1Co7ZNIZchq1gh1LTFE0tRFfO5pBY4S2toasC1yneoJ9XGKGs8tRuJu6dYwrf4vVtkqmRKmLd2DuI5sUKgEHMpAL6rF4QE=)
14. [peercommunityjournal.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGX6JJoAWrb0z8_zjRyOKNnoselSaFcnt5O6JDP4LTFhsuIGLwXBBm40lhB_cz6gS9ywgBVsipOl0TxhP5ettb9TVPtzj8z02m7l1lXa-pTW_S-SstZImoUMwl3awms5KG_-MtdQd2Cxv7HZ2c5_yToEr5O)
15. [cellpylib.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHyjK1hYV2mnET5d8B357i4fNGoFiWS9o3R39ymVJQ5EURnCq6amVPAAB4By28JdE4h8y9YsHmZgBGHO_ltXX6g4I45usaf1jVb7puI)
16. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFn1AOittHpkRkJWR_nKW4fvIQYdnKCUn6U-U2bizbtVG2iKL9HPuguTE5Eh-yL0niACqo_LzhCQM0CMbv2CKnDuZkFORa1yR4Yp2BgxosbTlJUOfD0q5nnRSntQA==)
17. [aman-bhargava.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEW_WZehzgoMVQJ6ghRy7_w1hXDQsLSqeYn34Q158PJrVOwd22zeOKqe13qIl2BFWJr-XQaXsXfrSAwnpqgp5RJrhtaLyPJaZI1avkNlawal4O1fa0vLaGXHdrPdyyeRtLb1I5xltJitf9MYGlw9m1JsvHDuIhNbrDUBzG-hQgN7to7tlLgiS8pHV-9cWQ=)
18. [distill.pub](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF2sAGkMGHoa1UtnJEiJm2H_GrpjQQofb863SUBgWQ-gv6zg0pOPFtvra1aa7ijTr-CXiQtFVGX-PA3-N9gsqeiTaoipHv2vNaWFfEH8CXgHpN9ChZPDw2x7pk=)
19. [plos.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGR9NgUsltqP9vDXlqAo_F5WbR1ueHcwpHOcNg6cTcqAIwnQr-vgr8eSZ6lDoYdbHrZFW-vC8gOo9JlEI5APzl8RrRICPsqRgljpYU_utb-jcTSV-m-YEDLvzCNk8S1EJgFSt-hJXNEjAEmIeaWgO81l8djtpH5qSs8PJBwJ7Cl2CCJOVQ=)
20. [github.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFCWxMKfK5BeDPvdBcpQnuFNmgHbK44R0cTrdsKK97R33ZsoB_s9YJAOSHXaf1n1-mZaVwkPp8pYB_jlUnZi4hyKGLBpMlHRi-3ifIQ6HBQnvdzKEZWqXMavYlrdCLPVHBnttL6U6pGecDnyjsYy8FWP-tDiyvm6tvuR1fJAQ==)
21. [quantamagazine.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEqWL6PadvWyLYL9Wrmle2OLYUYCjHj4Ul8_TBP_DQzrYqz3uARLd96zWPItBC8QsRXkuldxpNB-I7k_QkR6MNvVUloCtT9Za-HtBuHVIMtdsCr3NXI-6bDw16cbLgtTXhY14qxccS7OoMa4c3tjSD_8_okjrQ_XwpVvktayTxOIklr02b-x9omUAI8GQcI-ARMQyydugg=)
22. [arxiv.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEUX2nJKpH2irX7GEOsQ3jFOSXW9Q4-y-a8VAAJouvvmdj8ZxPeZfKvtfHUbC8OTDqbrwnhEncvUgATYgOrEgLbdWTIxSavTVq3fSA7Zaf61AlBEMBhrMVTLg==)
23. [github.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEhGhFRjJ-66Y7PMcYrArudFSfh9FG3e75qjCpXCUb6BKUywsnQOXjiVWJjoWiD71wK8pLkfu8vemid6DOGNxIdwCt8i_fkjipUJ5wro5uNcbvuVyh_FW5RM4LwfBzHyekXLB-MdtM36VL93A==)
24. [uliege.be](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF42vYBnYOR5JnuF0hbKBnmVsEmbKYEtEytZdF8t5X0NAOpSjap9HM48qo8WUZVR_kbYASFjkSS0_0COPHkfNp6FP1dOFi_qNjTMlyAEkq_IeAQcACVQTgiPazwTydY0ft5Oo7OZEPXHAI6hVsnxmk=)
25. [wikipedia.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFWobxchnvN2k3FRRrLG49hoKQHy1uzQAYz0MCdvhipY86hUl92ritsSJGq5OReL0V6Dddh7Hb4JTxXpeAp8iBQay-XBiNo9A35FOgGOhrikBeJDVx6uhnqtyQ1eGHqm87QIkNW-qTHeFWpGiwQ81F-XTf-yQ==)
26. [qut.edu.au](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEivQ1EWDLB8dYQe6UzbOEoSRT14R3I0WO9Sc4yOsSzwy5Wik5GJGFt-MhdViNCqeEjmgk8qKSlcKMe45ECV27I6_YSU3STQw4k0cVK3Jt-La6QCnxsxq2Kp7InN3twY6XfD9DHlYXticMbs41c_rYo-o4=)
27. [researchgate.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFlBEM_dAO4_Vi3MjbnchwdKi9ZKPpCeriCWxEvc5jqH-ixx_OzbT1HH7FTK4vzmLisgOCJF7V0wlLA_JjzS5QpO_rwVbJULiqCnFoPHwCCzBa4LPXMR1_vU4jthK3inUMiJLMgF3cYospsyrSgc8GpEPkzF8_IrTwgN9viuaUg2u3VTtQNrR3EJKvb0boxbPrS_lzrMo97lLDPu3tcDF71bAp5bGfcO4pHiX_HgOgZ_x2lKqhsAIZgfkarfC9KiQ87Qwhj6VU=)
28. [researchgate.net](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEi5dMUAMJGPD59i5sa9ZHic8QW1ykTwWK7yrj6t5Y30kI1CdcCh-etw5D0mjI3mOkObHOGAVi7AFU0nAslOOqds0OysRAvbE6ekt1f145uzPRE9xmYGcLmhqf_m97BrKWWVU0iOYAi1OSh_V12NaoP2RnWSYv2dxd53CU3a9Lvke8xBrpm54Djfe3HvVXIh0VA5XiRadRhLSFESm9ms-d4y2RDeb1nIq6uOJ6iC_id-A==)
29. [pypi.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGDSEz869fD_REopsNSmC81hmGGeFjfgi9WwVKa36zThSO74P_3gk0llLdaFS0eKNaTdD814k5rctZ6UGtAlWl7wkh_EjH-MlNYLd-6l4q50euU5SQw)
30. [readthedocs.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG9OjPXw8yv5ya0fwowvvFfgFtYEviQNIIqNU1HcOZzTbcUYP0GCsT3LiAlazGVXD-Xd_f3oVquLlYZBDML28Uzmwxi3KmgqhWPI5Y3RA2ZrboC7jSfFsGPqy-GffZHkWC_3xmN8tk=)
31. [github.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEEmBq-EQT_zX31Z714zac8NdIyDfhRLWr0I-iFNageCc3F2MOhzsj7Mv5mC3QkoQxvwYihQZsFDK7cGnGLdWE_E2p9bUEBGBFWtwHNgJ9rvLcFR0Sd1RVAVru8BmPbOHe694febw==)
32. [tandfonline.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGdTGpPh6aKm8CzAQ2x4T1o7Pxao6Bj3cMRH0Jglxdtp88ruVmsH7ZVyGiUNY4lZv6A8nCPCEeh7ncBr8GME815BYzpwpFb8mtV1ZaLT7rsMfUjKRTrZ_kORJp6RvG4-DBIkpHqTD_z2gzgIF3fm7PKBbA5z3SwCGk=)
33. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG_cgCI8VEW_w23E7YiHw_X_7Li2urW00txMfjVxwEh3Dc-neOeY86kvHniEKNeLHkeTYBkI8Zq6mS7Hq3EeaSouDcgmB4VpCIi0hHyJOcU75zKB7pTixAEePD3UN4g-md0LxO-9HHL0mp7hO-g0acpmO3CqDbMtQ7qeNBf4Zrblif8kALXygZ2r3MsUWz27EXM1NAUpqwp39vNkwlcGaCEB7VZ-qU=)
34. [tandfonline.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGF15Ql2EWOkFrBPsXACF2o8G74qrMiLhGVigAFNL71bpyN-E-HQyRxtZD1ib3AsrAMQ4kCpWOoH4sA7FRnAvErKt6cEw4PbQaEogDsv-EmUptO158kL2mZUjVeLuH-ICUYvNwBLbseIwZzNq2dh2K5AKmQ)
35. [nih.gov](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHRMoTy-BrDkhWc2_Kfr32p4KSEZ6leQ9ZiSXzmUjDVmSxCj_WIkezapAOQwye-FXfztFqkIqqUuMXbt8V7-YV2cMf1CBloM7qfaUw240S06NUixaaWcKhJHw4k4aC104-idmBNVecltA==)
36. [biorxiv.org](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEXrlvuPWpDOcjxxUOgsBha6l_A5BCG9lpeh41wkhjEtiarY-t3J_mLWHalol-ZU8hCfdzF2eAoJb61uCy2mNeaTwnj3TKV-HfiHuM4z1GZJpjkwmBgq_xX3Je8jT86meZdzdjdq_piEOIZWEv3Rq2U07HvuzLEi1kfAIM=)
37. [github.io](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF5sKniBeac-djJxAXxQjadya_ZEDrX-xkefZkXPmDp6RC_TOO812DSMDSMFbl3-jU-bZkZk-Tv0hJNWh0SH6-nGTAUaLN_yYHEqaNS70HWJyCtdwjAD_ysntNtfeZPYCZJeKvA8XoTgRD9ARD3LuoS30glq1eNBrOqnxR4_k1ZxNOTGPbr_eTz7IzAn5rxncjoNYjphqCyxQ_0OEOa)
