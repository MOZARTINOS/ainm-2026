# NM i AI 2026 — Orchestrator Handoff
## Дата: 20 марта 2026, 09:00 CET (пятница, день 2 из 3)
## Дедлайн: 22 марта 2026, 15:00 CET (осталось ~54 часа)

---

## ТЕКУЩИЕ SCORES

| Задача | Score | Rank | Детали |
|--------|-------|------|--------|
| NorgesGruppen | 38.76% (0.3876) | ~80/104 | 1 submission scored, 4/6 remaining today |
| Tripletex | 24.4 normalized | — | 28/32 daily submissions used, resets midnight UTC |
| Astar Island | 41.68 (weighted 50.66) | #126/191 | Round 5 submitted, Round 6 pending |
| **Overall** | **39.5** | **#82/191** | Average of 3 normalized scores |

---

## WORKERS (активные)

### Worker 1 — Astar Island
- Статус: ACTIVE, Round 5 submitted, v4 predictor ready for Round 6
- Код: F:\Workfolder\NM i AI main\repo\tracks\ml\
- Ключевые файлы: participate_v3.py, participate_v4.py (per-seed initial states)
- JWT: YOUR_JWT_TOKEN_HERE
- Score trajectory: 15.67 → 34.04 → 41.68 → ? (Round 5 pending)
- Top teams: 113 weighted. Gap huge — need fundamental improvements.

### Worker 2 — Tripletex
- Статус: ON PAUSE (waiting for instructions)
- Webhook: https://n8n.visam.no/webhook/tripletex-solve
- Workflow: WK54ADS72hF36hg2 on n8n.visam.no
- n8n API key: YOUR_JWT_TOKEN_HERE
- Gemini API: GEMINI_API_KEY_REDACTED (gemini-2.5-flash)
- Sandbox: https://kkpqfuj-amager.tripletex.dev/v2
- Sandbox token: eyJ0b2tlbklkIjoyMTQ3NjUyNjY1LCJ0b2tlbiI6ImQ4MjhkZDgzLTgxYjMtNDc5Yi04Yzk0LTBmNWU3NzcyODdlYyJ9
- КРИТИЧНОЕ ПРАВИЛО: Country Norway = 161, NOT 162 (Nepal)! Проверять grep перед КАЖДЫМ деплоем.
- Текущий код: F:\Workfolder\NM i AI main\repo\notes\v5_code.js

### NorgesGruppen Worker — отдельное окно Claude Code
- Статус: ACTIVE, packaging YOLOv8m + registers DINOv2 + 7-angle embeddings
- Код: F:\Workfolder\NM i AI main\repo\tracks\cv\
- ZIP: F:\Workfolder\NM i AI main\norgesgruppen_final.zip (374.5 MB) — СТАРЫЙ, без YOLOv8m

### Open Claw — Telegram бот на Hetzner (REDACTED_IP)
- Статус: ACTIVE, monitoring
- SSH key: /home/node/.openclaw/workspace/gcp_key
- Задачи: Slack monitoring, leaderboard tracking, GCP health checks
- ПРАВИЛО: НЕ пинговать webhook! Мешает competition submissions.

---

## INFRASTRUCTURE

### GCP (project: ai-nm26osl-1861, user: devstar18611@gcplab.me)
- L4 VM: REDACTED_IP (us-central1-a, g2-standard-8) — testing
- A100 VM: REDACTED_IP (us-central1-a, a2-highgpu-1g) — training done
- GCS: gs://nmiai-train-data-2026/
- H100 quota = 0 (not available)

### Trained models on A100 (/root/cv/):
- YOLOv8m ONNX: /root/cv/runs/yolov8m_train/weights/best.onnx (49.7MB, mAP 99.3%)
- YOLOv8s ONNX: /root/cv/runs/train4/weights/best.onnx (44MB, mAP 99.0%)
- DINOv2 registers: dinov2_vitb14.safetensors (346MB)
- Reference embeddings: ref_embeddings.npy (1594, 768), ref_category_ids.npy

### Hetzner (REDACTED_IP)
- SSH: ssh -i ~/.ssh/hetzner_key root@REDACTED_IP
- Open Claw Docker container running
- GCP key: /root/.ssh/gcp_key and /root/.openclaw/workspace/gcp_key

### n8n (n8n.visam.no)
- Tripletex Agent v5 workflow: WK54ADS72hF36hg2
- Other workflows exist (Visam business) — don't touch

---

## GITHUB REPOS
- MOZARTINOS/ainm-2026 — submissions (PRIVATE, must be PUBLIC before Sunday 15:00)
- MOZARTINOS/nmiai-workspace — working files (PRIVATE, keep private)

---

## CRITICAL BUGS FIXED (don't revert!)
1. Country Norway = 161, NOT 162 (Nepal)
2. startDate removed from POST /employee body (set via employment PUT)
3. userType = "STANDARD" string
4. VAT outgoing: 3=25%, 31=15%, 32=12%, 5/6=0%
5. Bank account: GET /ledger/account?number=1920 → PUT with bankAccountNumber="86010517941"
6. Invoice: POST /invoice (not PUT /order/:invoice)
7. Order: no vatType in orderLines (API auto-assigns)
8. Payment: GET /invoice/paymentType (not /ledger/paymentTypeOut), id with "bank" description
9. Supplier handler: POST /supplier with isSupplier=true
10. invoiceEmail = email for both customer and supplier
11. Multi-entity: Gemini splits "create 3 departments" into 3 POST calls
12. Project manager: create employee + grant entitlements + assign to project
13. Invoice send: PUT /invoice/{id}/:send?sendType=EMAIL after creation

---

## CRITICAL RULES
- NorgesGruppen: NO .pt files in ZIP (instant ban!). ONNX + safetensors only.
- NorgesGruppen: 6 submissions/day, max 420MB, 300s timeout, 3 weight files max
- Tripletex: 32 submissions/day (but may not reset properly), timeout ~2 min real (not 5)
- Tripletex: Tier 2 opens "early Friday" (NOW!), Tier 3 Saturday morning
- Astar: 50 queries/round, 5 seeds, resubmit overwrites previous
- NEVER submit without explicit user approval
- NEVER deploy to n8n without grep check (162=0, 161=correct count)
- Read ALL documentation BEFORE implementing anything

---

## DOCUMENTATION
- MCP server: https://mcp-docs.ainm.no/mcp (19 docs, use curl with session)
- Web docs: https://app.ainm.no/docs (5 sections + Google Cloud + Rules)
- Rules: https://app.ainm.no/rules
- Tripletex API: https://kkpqfuj-amager.tripletex.dev/v2-docs/
- Local copy: F:\Workfolder\NM i AI main\repo\notes\all_docs_mcp.md (partial)

---

## WHAT NEEDS TO BE DONE

### Priority 1: NorgesGruppen (biggest score potential)
- YOLOv8m trained (mAP 99.3%), embeddings built with registers DINOv2
- NorgesGruppen Worker packaging new ZIP
- First submission scored 38.76% — need 80%+
- Key issues: overfitting (99% train vs 45% test), classification weak
- 4 submissions remaining today

### Priority 2: Tripletex
- 28/32 daily submissions used (resets midnight UTC?)
- Tier 2 opening NOW — new task types
- Invoice chain works but payment still gets 2/7 (amount=0 bug fixed, payment type fixed)
- Need: credit notes, bank reconciliation prep for Tier 3
- Efficiency optimization: zero 4xx errors = double score

### Priority 3: Astar Island
- Score 41.68, top teams 113. Huge gap.
- v4 predictor with per-seed initial states ready
- Need fundamental algorithm improvement (spatial smoothing, GP, better Bayesian updates)
- Rounds every ~3 hours

### Must do before Sunday 15:00:
- Make ainm-2026 repo PUBLIC
- Select best submissions for final evaluation
- Push all code

---

## LESSONS LEARNED (don't repeat!)
1. READ ALL DOCS FIRST before coding
2. Country 162=Nepal, 161=Norway — ALWAYS verify constants via API
3. Don't trust competitor code on GitHub (may be intentional disinformation)
4. Test on sandbox BEFORE competition submission
5. .pt files = instant ban on NorgesGruppen
6. Timeout is ~2 min real, not 5 min stated
7. Don't spam Tripletex submissions — 32/day is precious
8. MCP server unstable — use curl with manual session management
9. Workers can overwrite critical fixes — always grep check before deploy
