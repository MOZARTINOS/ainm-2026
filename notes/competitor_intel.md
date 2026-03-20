# Competitor Intelligence — NM i AI 2026

## Leaderboard (21:48 CET, March 19)

| # | Team | Detection | Tripletex | Astar | Total |
|---|------|-----------|-----------|-------|-------|
| 1 | Companion | 98.6 | 52.1 | 51.9 | 67.5 |
| 2 | Cybotrix | 97.4 | 52.8 | 48.8 | 66.3 |
| 3 | Dahl Optimal | 99.0 | 9.6 | 68.7 | 59.1 |
| 5 | CAL-culated risks | — | 69.6 | 92.9 | 54.2 |
| 12 | Slop Overflow | — | 100.0 | 8.3 | 36.1 |
| 15 | Guru Meditation | 100.0 | — | 1.1 | 33.7 |

## Key Insights

### Tripletex (from shankygupta1323)
- GPT-4.1-mini with function calling (GET/POST/PUT/DELETE)
- MAX 30 iterations, 270s timeout
- Account starts EMPTY — don't search, just CREATE
- Parallel tool calls for speed
- Hardcoded constants: VAT 25% id=3, NOK id=1, Norway id=162
- Bank account: "86010517941" (valid MOD11) — NEEDED for invoice!
- Employee needs department (GET /department first)
- Project manager needs entitlements grant

### NorgesGruppen (from ChrTwentyFive)
- YOLOv8l at imgsz=640 (we use YOLOv8s at 1280 — potentially better)
- No classification pipeline visible
- Training on Mac MPS

### Lessons from trymhaak (postmortem)
- `import sys` BANNED but not in docs!
- torch.load crashes in sandbox
- "Submissions are scarce resources — treat each like a rocket launch"
- Pipeline validation BEFORE submit
- Their score: 17.1 at #69 after 4.5 hours
- Used 20+ agents — concluded "fewer, better agents > many half-finished"
