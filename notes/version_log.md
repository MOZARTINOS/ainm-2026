# Tripletex Version Log & Statistics

## CURRENT LIVE: v6-t3-fix (deployed 2026-03-22 00:19 CET)
- Size: 117KB
- Git base: cde4fb0 + all previous changes + T3 fixes
- 162=0, 161=3 ✅
- Changes from v5:
  1. **callGemini JSON parse hardened** — try-catch on JSON.parse, fallback to regex extraction
  2. **callGemini outer try-catch** — network errors return {} instead of crashing
  3. **PDF extraction limit** increased from 5000 to 12000 chars
  4. **Employee classify prompt** — detailed checklist for NID, salary, percentage, occupation, employmentType
  5. **Employee handler** — added employmentType field support
  6. **reminder_fee rewrite** — creates full invoice chain (customer→product→order→invoice) before posting fee
  7. **bank_reconciliation rewrite** — creates invoices from CSV data instead of searching (fresh account)
  8. **monthly_closing improved** — better Gemini prompt with account numbers, auto-balance postings
  9. **ledger_analysis rewrite** — creates vouchers from task description, handles empty account
  10. **project_invoice improved** — uses PUT /order/:invoice, creates products, hourly rate setup
- First 3 submits: 20% (2/10), **60% (6/10)** ★, 36% (5/14)
- T3 max=10 best went from 50% → **75%** ★★

### v6.1 — Error fixes (deployed 2026-03-22 00:40 CET)
- Fix: removed employmentType from PUT /employee (was causing 422 on ALL employee PDF tasks)
- Fix: German/French keywords for bank_reconciliation (Kontoauszug, abgleich, rapprochez)
- Fix: project_invoice override for "Projektzyklus"/"project cycle"
- Fix: bank statement + CSV = always bank_reconciliation (not reverse_payment)
- Fix: ledger_analysis now creates projects/activities (not just vouchers)

## Overall Statistics (50 submissions total)
- **100%**: 14 submissions (28%)
- **Partial (1-99%)**: 18 submissions (36%)
- **0%**: 18 submissions (36%)

## By Task Complexity (score_max)
| max_score | Count | Avg % | 100% | 0% | Likely Task Types |
|-----------|-------|-------|------|----|-------------------|
| 7.0 | 15 | 78% | 10 | 1 | customer, product, department, supplier, project |
| 8.0 | 30 | 37% | 4 | 12 | employee, invoice, payment, credit_note, travel, payroll |
| 13.0 | 5 | 0% | 0 | 5 | dimension_voucher |

## Key Insight
- **max=7 tasks**: we handle well (78% avg, 67% perfect)
- **max=8 tasks**: very weak (37% avg, 40% = zero)
- **max=13 tasks**: completely broken (0%)

## Version History

### v5-git (cde4fb0) — STABLE BASELINE
- Size: 94KB, 20 handlers
- Tested: 101/101 sandbox simulator
- Competition: 100% on simple, 75% on invoice, 0% on dimension/supplier_invoice
- **DO NOT MODIFY without sandbox test first**

### v5-always-create — BROKEN, DO NOT USE
- Bug: results.push({ok, id}) without .data breaks downstream
- Caused score DROP 23.1 → 22.1
- Lesson: NEVER change results.push format

### v5-dimension-fix — SANDBOX TESTED, NOT YET ON COMPETITION
- Correct endpoints: /ledger/accountingDimensionName {dimensionName}
- Values: /ledger/accountingDimensionValue {dimensionIndex, displayName}
- Voucher: freeAccountingDimension1: {id}
- MUST be applied carefully to avoid breaking other handlers

## Score Timeline
| Time | Score | Rank | Version | Action |
|------|-------|------|---------|--------|
| Day 1 19:00 | 16.8 | #86 | v4 baseline | First deployment |
| Day 1 20:00 | 20.5 | #74 | v5-git | All handlers deployed |
| Day 2 00:00 | 22.4 | #144 | v5-git | Farming (T2 multiplier active globally) |
| Day 2 01:30 | 23.1 | #143 | v5-git | Peak score |
| Day 2 02:30 | 23.1 | #145 | v5-broken | always-create deployed |
| Day 2 03:00 | 22.1 | #156 | v5-broken | Score DROPPED |
| Day 2 03:30 | 22.1 | #156 | v5-git | Rolled back |
| Day 2 03:45 | 22.1 | #156 | v5-git-patched | customerName prefix fix |

## Rules for Future Changes
1. **NEVER deploy without sandbox test**
2. **NEVER change results.push() format** — use spread operator: results.push({step: 'x', ...apiResult})
3. **Grep 162=0, 161=3 before EVERY deploy**
4. **Record version + score BEFORE and AFTER each deploy**
5. **If score drops → immediate rollback to last known good**
6. **One fix at a time** — don't bundle multiple changes
7. **Test the EXACT competition prompt** on sandbox before deploying fix

## Unsolved Problems (ordered by impact)
1. **dimension_voucher 0/13** — API may not work on competition proxy
2. **supplier_invoice 0-1/8** — voucher created but SupplierInvoice entity not recognized
3. **credit_note 1/8** — customer created with "Kunden" prefix (Gemini extraction bug)
4. **register_payment 2/7** — all calls succeed but checks fail
5. **payroll_voucher 0/8** — employee + voucher structure unclear
6. **fixed price → project_invoice** — misclassified as create_invoice
| Day 2 03:55 | 22.1+ | #156 | v5-git-patched | credit_note 8/8 (100%) norm=2.67 — customerName fix WORKS |

| 04:33 | ? | ? | v5-patched | 1 subs: 100%=0 good=0 bad=0 zero=1 |

| 04:45 | ? | ? | v5-git-patched+override | 12 subs: 100%=4 good=0 bad=4 zero=4 |

## Cycle results (15 subs, v5-git-patched+override, before incomingInvoice fix)
- 100%: 4 (create_supplier, create_product)
- Partial: 4 (travel 56%, invoice 38%, reverse 25%)
- Zero: 4 (supplier_invoice 0% — confirmed supplierInvoices=0)
- Pattern: simple tasks=100%, complex tasks=0-56%
- FIX DEPLOYED: POST /incomingInvoice with voucher fallback

| 05:03 | ? | ? | v5+incomingInv | 4 subs: 100%=3 good=0 bad=1 zero=0 |

### v5-travel-fix — DEPLOYED
- Fix: returnDate = departureDate + days - 1 (was: returnDate = departureDate)
- Fix: perDiem count uses p.days fallback
- Fix: classify prompt extracts "days" from multilingual prompts
- Sandbox test: dep=2026-03-21, ret=2026-03-25 for "5 dias" ✅
- Expected improvement: travel_expense 56% → 80%+

### Scripts fixed
- one_cycle.py: polling 200s, --no-submit, --dry-run, proper CSV, no duplicate submits
- rebuild_log.py: clean CSV from competition API

## Autonomous cycle results (31 subs, v5-git-patched+override)
- 100%: 14, 70%+: 3, partial: 6, 0%: 8

### v5-invoice-products — DEPLOYED
- Fix: create products for each invoice line with product numbers
- Fix: if POST /product fails → GET existing by name → use id in orderLine
- Sandbox test: 2/3 products created, 1 found existing, order+invoice OK
- Expected improvement: invoice multi-line 38% → 70%+

| 05:56 | ? | ? | v5-patched+override | 35 subs: 100%=23 good=3 bad=4 zero=5 |

| 06:32 | ? | ? | v5-patched+override | 39 subs: 100%=35 good=2 bad=0 zero=2 |

### Latest 0% analysis: T3 monthly closing (max=10)
- Prompt: "encerramento mensal de março 2026" (Portuguese)
- Type: create_voucher (should be specialized monthly_closing handler)
- Task: reversal of accruals + depreciation of fixed assets
- Error: "Det mangler posteringer for rad 1" on 2nd voucher
- This is T3 (×3 multiplier) — worth up to 6 points if perfect
- NOT fixing now — focus on travel/invoice first
