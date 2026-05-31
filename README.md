# NM i AI 2026 — Main Round

Solution code for the **main round** of NM i AI (the Norwegian AI Championship)
2026. Three independent tasks were tackled solo: a **NorgesGruppen VLM** task, a
**Tripletex** accounting-API automation task, and the **Astar Island**
probabilistic map-reconstruction game.

> The qualification round (a separate MAPF warehouse-coordination problem) is not
> in this repo — this is the main-round work only.

## Tasks

### `tracks/ml/` — Astar Island (probabilistic map reconstruction)
You get a limited query **budget** to peek at viewport observations of a hidden
grid, then must submit a full **probability distribution over 6 terrain classes
for every cell**. Submissions are scored by KL divergence against the true map:
`score = 100 · exp(−KL_weighted)`, with KL counted only over dynamic
(non-static) cells.

Approach — a **Bayesian observer** (`predictor.py`):
- **Dirichlet smoothing** over per-cell class counts; `α = 2.0` chosen by an
  offline score sweep (α=0.5→91.3, α=1.0→94.2, **α=2.0→96.7**, α=3.0→97.8 marginal).
- A **probability floor** (`PROB_FLOOR = 0.001`) on every class — a single 0.0
  produces infinite KL and tanks the score.
- A **two-phase observation policy** (`observation.py`): Phase A spends budget on
  systematic coverage, Phase B targets the highest-uncertainty cells.
- A central orchestrator (`main.py`) running the budget→observe→predict→submit
  loop with continuous polling and per-seed submission.

Iteration is visible in the versioned `participate_v*.py` files; `simulator.py`
is a local scorer used to tune α and the observation policy offline before
spending real query budget.

### `tracks/cv/` — NorgesGruppen VLM
Vision task on NorgesGruppen retail imagery: a YOLO (Ultralytics) detector paired
with a DINOv2/ViT **embedding + reference-matching** pipeline for product/shelf
recognition. Training helpers (`scripts/`) target a single L4 GPU on GCP.

### `tracks/llm/` — Tripletex automation
LLM-routed handler for the Tripletex accounting task: classify an input, then
dispatch it to the matching structured-extraction route (employees, invoices,
projects, expenses, accounting entries).

## Layout
- `tracks/ml/` — Astar Island Bayesian predictor
- `tracks/cv/` — NorgesGruppen VLM detection + embedding pipeline
- `tracks/llm/` — Tripletex routing / extraction
- `scripts/` — GCP training helpers (set `GCP_PROJECT`; no project IDs baked in)
- `submissions/` — generated artifacts (gitignored)

## Running the Astar Island predictor
```bash
pip install -r requirements.txt
export ASTAR_TOKEN=...        # competition JWT — read from env, never hardcoded
python tracks/ml/main.py --token "$ASTAR_TOKEN" --poll
```

## Notes on this repo
- **No credentials are committed.** Competition token is read from `ASTAR_TOKEN`;
  GCP scripts read `GCP_PROJECT` from the environment.
- Live working notes, API dumps, and internal endpoints from the competition were
  removed before this repo was made public.

## License
MIT — see [LICENSE](LICENSE).
