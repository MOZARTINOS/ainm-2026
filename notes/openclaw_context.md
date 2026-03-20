# Open Claw — Competition Intelligence Context

## Our Team Status
- Team: MOZARTINOS (solo)
- Competition: NM i AI 2026 (Norwegian AI Championship)
- 69 hours: March 19 18:00 → March 22 15:00 CET
- Prize pool: 1,000,000 NOK

## Our Solutions

### Task 1: NorgesGruppen (Object Detection)
- YOLOv8s single-class detector, mAP@0.5 = 99.0%
- DINOv2 ViT-B/14 for classification (kNN, 356 categories)
- SAHI tiling 1280px, Soft-NMS
- ONNX export, 376MB total weights
- Score: NOT YET SUBMITTED

### Task 2: Tripletex (AI Accounting Agent)
- n8n webhook + Gemini 2.5 Flash
- 13/13 task types pass on sandbox
- Plan-and-Act architecture
- Score: NOT YET SUBMITTED

### Task 3: Astar Island (Prediction)
- Dirichlet smoothing with empirical priors
- 50 queries per round, 5 seeds
- Round 2 score: 15.67 (had terrain mapping bug, now fixed)
- Round 3: submitted, waiting for score
- Score: ~45-60 expected after fix

## Known Leaderboard (21:48 CET March 19)
| # | Team | Detection | Tripletex | Astar | Total |
|---|------|-----------|-----------|-------|-------|
| 1 | Companion | 98.6 | 52.1 | 51.9 | 67.5 |
| 2 | Cybotrix | 97.4 | 52.8 | 48.8 | 66.3 |
| 3 | Dahl Optimal | 99.0 | 9.6 | 68.7 | 59.1 |
| 5 | CAL-culated | — | 69.6 | 92.9 | 54.2 |
| 12 | Slop Overflow | — | 100.0 | 8.3 | 36.1 |
| 15 | Guru Meditation | 100.0 | — | 1.1 | 33.7 |

## Known Competitor Repos (public)
- shankygupta1323/nmiai-tripletex-agent — GPT-4.1-mini, function calling, full API reference in prompts
- ChrTwentyFive/Norgesgruppen — YOLOv8l, imgsz=640, no classification
- trymhaak/nmiai-2026 — postmortem, strategy docs, Astar predictor v3
- olacola123/blane-co — team of 3 (Ola, Joakim, Mathea), per-person logs
- larsendbaas/NM-AI-2026 — Astar solver with features/model/planner
- sth1712/NMiAI — workspace
- Larsottojohnsen/ai-plattform — modular platform
- davidmyrann-sketch/nm-i-ai-2026
- Stig-Johnny/nm-i-ai-2026

## What To Search For

### GitHub Searches (every 10 min)
1. `gh search repos "NM i AI 2026" --sort updated --limit 20`
2. `gh search repos "ainm 2026" --sort updated --limit 10`
3. `gh search repos "norgesgruppen detection 2026" --limit 10`
4. `gh search repos "tripletex agent" --sort updated --limit 10`
5. `gh search repos "astar island prediction" --limit 10`
6. `gh search code "tripletex" --language python --sort indexed --limit 20`
7. `gh search code "astar-island" --language python --sort indexed --limit 20`

### What We're Looking For
- Better Astar Island prediction strategies (spatial smoothing, GP, settlement models)
- Tripletex task types we haven't covered
- NorgesGruppen classification tricks (better than DINOv2 kNN?)
- Any team sharing their scores or strategies
- Sandbox gotchas (blocked imports, pickle issues)
- New competitor repos appearing

### When You Find Something Interesting
Save to /home/node/.openclaw/workspace/intel_findings.md with:
- Timestamp
- What repo/source
- Key finding
- How it could help us

## GCP Training Monitor (SECONDARY PRIORITY)
- A100 VM: ssh -i /home/node/.openclaw/workspace/gcp_key root@34.10.132.71
- L4 VM: ssh -i /home/node/.openclaw/workspace/gcp_key root@34.9.220.246
- Training is COMPLETE (mAP 99.0%). Only check if asked.
