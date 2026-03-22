# NM i AI 2026 — Full Documentation (from MCP)

## TRIPLETEX

### Request Format
```json
{
  "prompt": "Opprett en ansatt med navn Ola Nordmann...",
  "files": [
    {"filename": "faktura.pdf", "content_base64": "JVBERi0...", "mime_type": "application/pdf"}
  ],
  "tripletex_credentials": {
    "base_url": "https://tx-proxy.ainm.no/v2",
    "session_token": "abc123..."
  }
}
```

### Response
```json
{"status": "completed"}
```

### Auth: Basic Auth, username=0, password=session_token

### Scoring
- correctness = points_earned / max_points (0-1)
- score = correctness × tier_multiplier (1/2/3)
- If perfect correctness: efficiency bonus up to 2× tier score
- Max score per task: 6.0 (perfect Tier 3 + best efficiency)
- Best score per task retained forever
- 30 task types, 56 variants each (7 langs × 8 datasets)
- Efficiency benchmarks recalculated every 12 hours

### Rate Limits
| Limit | Verified | Unverified |
|-------|----------|------------|
| Concurrent submissions | 3 | 1 |
| Per task per day | 5 | 2 |

### Tier Schedule
- Tier 1: competition start
- Tier 2: early Friday
- Tier 3: early Saturday

### Create Employee Example (max 10 points)
| Check | Points |
|-------|--------|
| Employee found | 2 |
| Correct first name | 1 |
| Correct last name | 1 |
| Correct email | 1 |
| Administrator role assigned | 5 |

### API Endpoints
| Endpoint | Methods |
|----------|---------|
| /employee | GET, POST, PUT |
| /customer | GET, POST, PUT |
| /product | GET, POST |
| /invoice | GET, POST |
| /order | GET, POST |
| /travelExpense | GET, POST, PUT, DELETE |
| /project | GET, POST |
| /department | GET, POST |
| /ledger/account | GET |
| /ledger/posting | GET |
| /ledger/voucher | GET, POST, DELETE |

### Common Patterns
| Pattern | API Flow |
|---------|----------|
| Create single | POST /employee |
| Create with linking | GET /customer → POST /order → POST /invoice |
| Modify existing | GET /customer → PUT /customer/{id} |
| Delete/reverse | GET /travelExpense → DELETE /travelExpense/{id} |
| Multi-step | POST /customer → POST /invoice → POST /payment |

### Sandbox
- URL: https://kkpqfuj-amager.tripletex.dev
- Token expires: March 31, 2026
- Competition uses: https://tx-proxy.ainm.no/v2

---

## NORGESGRUPPEN

### Submission Format
```
submission.zip
├── run.py          # Required
├── model.onnx      # Optional
└── utils.py        # Optional
```

### Limits
| Limit | Value |
|-------|-------|
| Max zip (uncompressed) | 420 MB |
| Max files | 1000 |
| Max Python files | 10 |
| Max weight files | 3 |
| Max weight size | 420 MB |
| Submissions/day | 3 |
| In-flight | 2 |
| Infra freebies | 2/day |

### run.py Contract
```bash
python run.py --input /data/images --output /output/predictions.json
```

### Output Format
```json
[{"image_id": 42, "category_id": 0, "bbox": [x, y, w, h], "score": 0.923}]
```

### Scoring
Score = 0.7 × detection_mAP@0.5 + 0.3 × classification_mAP@0.5

### Sandbox
- Python 3.11, 4 vCPU, 8 GB RAM
- NVIDIA L4 (24 GB VRAM), CUDA 12.4
- Network: NONE (offline)
- Timeout: 300 seconds

### Pre-installed
PyTorch 2.6.0+cu124, torchvision 0.21.0+cu124, ultralytics 8.1.0, onnxruntime-gpu 1.20.0, opencv 4.9.0, albumentations 1.3.1, numpy 1.26.4, scipy 1.12.0, scikit-learn 1.4.0, timm 0.9.12, safetensors 0.4.2, ensemble-boxes 1.0.9, supervision 0.18.0, pycocotools 2.0.7

### Blocked imports
os, sys, subprocess, socket, ctypes, builtins, importlib, pickle, marshal, shelve, shutil, yaml, requests, urllib, http.client, multiprocessing, threading, signal, gc, code, codeop, pty
Also: eval(), exec(), compile(), __import__(), getattr() with dangerous names

### Allowed file types
.py, .json, .yaml, .yml, .cfg, .pt, .pth, .onnx, .safetensors, .npy

### Version Pinning
- ultralytics==8.1.0 (8.2+ breaks)
- timm==0.9.12 (1.0+ breaks)
- torch==2.6.0
- ONNX opset ≤ 20

---

## ASTAR ISLAND

### Scoring Formula
```
weighted_kl = Σ entropy(cell) × KL(ground_truth, prediction) / Σ entropy(cell)
score = max(0, min(100, 100 × exp(-3 × weighted_kl)))
```

### Ground Truth
Hundreds of simulations per seed → probability distribution per cell

### Classes
0: Ocean/Plains/Empty
1: Settlement
2: Port
3: Ruin
4: Forest
5: Mountain

### API
- GET /rounds — list rounds
- GET /rounds/{id} — round details + initial states
- GET /budget — queries remaining
- POST /simulate — observe viewport (costs 1 query)
- POST /submit — submit prediction
- GET /my-rounds — scores
- GET /analysis/{round_id}/{seed_index} — post-round comparison

### Constraints
- 50 queries per round, shared across 5 seeds
- Max viewport: 15×15
- Map: 40×40
- Prediction: [y][x][6 classes], sum to 1.0
- NEVER assign 0.0 (infinite KL!)
- Minimum floor: 0.01

### Round Structure
- Prediction window: ~2h45m
- 5 seeds per round
- round_score = average of 5 seed scores
- Leaderboard = best round ever (weighted)
- Hot streak = avg last 3 rounds
