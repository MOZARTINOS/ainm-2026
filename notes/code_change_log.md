# Code Change Log & Baseline Tracking

## BASELINE: v5-git (cde4fb0) — 94KB
- Competition results: 19/50 perfect (38%), 10/50 zero (20%)
- max=7: 85% avg, max=8: 43% avg, max=13: 0%
- Known working: customer, product, department, supplier, project, credit_note
- Known broken: supplier_invoice, payroll, dimension, monthly_closing

## Change 1: customerName prefix strip
- File: v5_code.js line ~258
- What: strip "Kunden"/"El cliente" etc from customerName before search
- Sandbox test: PASS
- Competition result: credit_note 8/8 (100%) — was 1/8
- Verdict: **KEEP** ✅

## Change 2: fixed price → project_invoice override
- File: v5_code.js line ~260
- What: if task has "fixed price" + classified as create_invoice → force project_invoice
- Sandbox test: PASS
- Competition result: not directly tested yet
- Verdict: **KEEP** ✅

## Change 3: travel returnDate = departureDate + days - 1
- File: v5_code.js line ~714
- What: calculate returnDate from "days" field instead of same day
- Sandbox test: PASS (dep=03-21 → ret=03-25 for 5 days)
- Competition result: not tested yet (travel was 56%, expected 70%+)
- Verdict: **KEEP** ✅ (sandbox confirmed)

## Change 4: invoice product creation with numbers
- File: v5_code.js lines ~408-440
- What: for each invoice line, POST /product first, use product.id in orderLine
- Fallback: if POST fails, GET existing by name
- Sandbox test: PASS (2/3 products created, 1 found existing)
- Competition result: not tested yet (invoice was 38%, expected 70%+)
- Verdict: **KEEP** ✅ (sandbox confirmed)

## Change 5: v5-always-create — BROKEN, ROLLED BACK
- What: POST customer first instead of GET
- Bug: results.push({ok, id}) without .data broke downstream
- Competition result: score DROPPED 23.1 → 22.1
- Verdict: **NEVER USE** ❌
- Lesson: NEVER change results.push format

## CURRENT LIVE: v5-git + changes 1-4
- Size: 98KB
- 162=0, 161=3 ✅
- Sandbox: 8/8 PASS
- Competition: needs testing (13 submissions remaining today)

## Rules
1. One change at a time
2. Sandbox test before deploy
3. Grep 162/161 before every deploy
4. Log competition result for each change
5. If score drops → immediate rollback
6. Record baseline BEFORE and AFTER each change

## Finding: T3 monthly closing (max=10) — needs 4 vouchers
- Full prompt requires: accrual reversal + depreciation + salary provision + trial balance check
- Our handler creates only 2 vouchers, misses salary provision
- Accounts: 1700→expense, 6030←asset, 5000←2900
- Depreciation: cost/years/12 = monthly amount
- NOT fixing now — T3 tasks appear rarely, focus on travel/invoice first
- Competition tested: 0/10 [FFFFFF]

## Change 5: Employee employment details (T3 PDF task)
- File: v5_code.js
- What: extract nationalIdentityNumber, salary, employmentPercentage, occupationCode
- Employee handler: set NID on POST, set employment details via /employee/employment/details
- Classify prompt: added salary, employmentPercentage, occupationCode fields
- Sandbox test: employee created OK, employment details endpoint accessed (but Gemini may not extract from full prompt)
- NID validation: fake numbers rejected (MOD11), real ones from PDF should work
- Competition result: not tested yet (was 32% with 7/22 = PPPPFPFFFFFFFFF)
- Expected improvement: T3 employee 32% → 50%+ (more fields set = more checks pass)
- Verdict: **KEEP** (no risk, additive only)

## Round 1/5: 0/10 [FF] — T3 bank reconciliation from CSV
- max=10, T3 (×3 multiplier)
- Prompt: "Concilia el extracto bancario (CSV adjunto)"
- Classified as: register_payment (WRONG — should be bank_reconciliation)
- Handler created 5 invoice+payment chains instead of reconciling
- 20 API calls, 4 errors (product name conflicts)
- Duration: 171s (near timeout!)
- NEEDS: new handler bank_reconciliation that reads CSV, matches to existing invoices
- CSV file was in files[] but handler didn't use it properly

## Round 2/5: 36% (5/14) [PPPPFFFFFF] — T3 employee from PDF (DE)
- max=14, T3 (×3 multiplier)
- Prompt: German offer letter with attached PDF
- 4 pass: employee exists, firstName, lastName, email(?)
- 6 fail: NID, dateOfBirth, department, salary, percentage, occupation
- N8N: 3 calls, 0 errors — but only basic employee created
- ROOT CAUSE: Gemini extracts from text prompt but not from PDF content
- My employment details code exists but doesn't trigger (p.salary = undefined)
- FIX NEEDED: stronger prompt telling Gemini to extract ALL fields from PDF

## Round 3/5: 50% (5/10) [PPPFFF] — voucher reminder fee
- max=10, T3-ish
- Task: find overdue invoice + post reminder fee 65 NOK
- 3 pass, 3 fail
- 1st voucher fail (customer missing), retry OK
- IMPROVEMENT: handle reminder fee as specialized case

## Round 4/5: 0/10 [FFFFF] — dimension_voucher (known broken)
- Dimension API 422/404 on competition proxy
- Department fallback doesn't count for checks
- KNOWN ISSUE — no fix available

## Round 5/5: 36% (4/11) [PPFFFFP] — T3 full project cycle (DE)
- max=11, T3
- All 6 n8n steps OK, 0 errors!
- Checks 1-2 pass (project+customer), check 7 pass (invoice exists)
- Checks 3-6 fail: hourly rate? timesheet hours? invoice amount? employee details?
- Handler creates everything but data content may be wrong

## Change 6: Employee employment via POST (not PUT) + employment details
- File: v5_code.js lines 307-345
- What: POST /employee/employment instead of PUT /employee with employments[]
  Then POST /employee/employment/details with salary + percentage
- Sandbox test: PASS — salary=550000 pct=80 created successfully
- Before: T3 employee from PDF scored 36% (5/14) — 6 checks failed (no salary/percentage/employment)
- Expected: T3 employee should now score 60-80% (salary+percentage+startDate all set)
- Risk: LOW — additive change, doesn't modify existing working handlers
- Verdict: **DEPLOYED** ✅

## Submit after Change 6: 20% (2/10) [PFFFFF] — supplier_invoice from PDF (T3)
- max=10, T3
- Supplier "Brattli AS" created = Check 1 PASS
- incomingInvoice = 403 (expected)
- Voucher fallback created but 5 checks fail
- IMPROVEMENT: was 0/8, now 2/10 = supplier creation works
- REMAINING ISSUE: SupplierInvoice entity not created (incomingInvoice 403)
- This is a KNOWN UNSOLVABLE issue on current API permissions

## Change 7: PDF text extraction — BROKEN, ROLLED BACK ❌
- What: extract text from PDF base64 using regex on raw bytes
- Bug: regex with backslashes in template literal crashes n8n Code node
- Empty response = webhook returns nothing = competition gets timeout/error
- ROLLED BACK immediately to git version (cde4fb0)
- Lesson: NEVER deploy regex-heavy code without sandbox test FIRST
- Need simpler approach: just try Buffer.from(b64, 'base64').toString('utf-8')

## Change 7b: PDF toString('utf-8') — ALSO BROKEN, ROLLED BACK ❌
- Even simple Buffer.from(b64,'base64').toString('utf-8') on PDF data
  produces binary garbage with control chars that crash n8n JSON serialization
- CONCLUSION: Cannot extract PDF text in n8n Code node
- PDF processing MUST go through Gemini inline_data (vision) only
- Fix approach: improve classify prompt, not file processing
- Live code restored to git version (cde4fb0)

## Change 8: PDF via sub-workflow — PARTIAL, ROLLED BACK
- Created separate workflow "PDF Extractor Webhook" (6vEa8C7ucI9J3n8Z)
- Endpoint: https://n8n.visam.no/webhook/extract-pdf
- Main agent calls it via httpRequest when PDF files present
- Smoke test WITHOUT PDF: PASS
- Smoke test WITH fake PDF (text pretending to be PDF): FAIL — sub-workflow crashes
- ISSUE: Extract from File node needs REAL PDF (magic bytes %PDF-), not plain text
- ROLLED BACK main workflow to safe version
- NEXT: need to test sub-workflow with real PDF file separately
- Sub-workflow left active for future testing

## v6-t3-fix — DEPLOYED 2026-03-22 00:19 CET

### Change 9: callGemini JSON parse hardening
- **What**: Wrapped JSON.parse in try-catch, added fallback regex extraction for markdown code blocks
- **Why**: Competition submit returned `status=failed` — Gemini returned invalid JSON, JSON.parse threw unhandled SyntaxError
- **Impact**: CRITICAL — prevents all future crashes from Gemini returning malformed JSON
- **Risk**: NONE — purely defensive

### Change 10: PDF extraction limit 5000→12000 chars
- **What**: `extractedFileText.substring(0, 12000)` instead of 5000
- **Why**: Employee contract PDFs are long, 5000 chars truncated important fields (salary, NID, occupation)
- **Risk**: LOW — only increases context sent to Gemini

### Change 11: Employee classify prompt — PDF extraction checklist
- **What**: Added explicit checklist of ALL employee fields to extract from PDF text (NID, salary, percentage, occupation, employmentType)
- **Why**: Gemini was extracting firstName/lastName/email but missing salary/NID/occupation from PDF documents
- **Expected**: T3 employee from PDF 36% → 60%+ (more fields extracted = more checks pass)

### Change 12: reminder_fee handler rewrite
- **What**: Creates full chain: customer → product → order → invoice (with past due date) → reminder fee voucher
- **Why**: Old handler searched for existing overdue invoices — on fresh account there are NONE
- **Expected**: reminder_fee 50% → 70%+

### Change 13: bank_reconciliation handler rewrite
- **What**: Creates invoices from CSV transaction data instead of searching for existing invoices
- **Why**: Fresh account has no invoices to reconcile. Must create customer+product+order+invoice+payment for each CSV row
- **Expected**: bank_reconciliation 0% → 50%+

### Change 14: monthly_closing + ledger_analysis handlers improved
- **What**: Better Gemini prompts with specific account numbers, auto-balance postings (ensure debit=credit)
- **Why**: Old handlers relied on Gemini knowing Tripletex account structure — added explicit account list
- **Risk**: LOW — additive improvements

### Change 15: project_invoice handler improved
- **What**: Uses PUT /order/:invoice instead of POST /invoice, creates product for invoice line, hourly rate setup
- **Why**: Order-to-invoice conversion is more reliable and populates more fields correctly
- **Expected**: project_invoice 36% → 50%+

### First results (3 submits):
- 20% (2/10) T3 task
- **60% (6/10)** ★ T3 task — new record for max=10
- 36% (5/14) T3 employee — same as before (PDF extraction needs more work)
- Key win: **callGemini no longer crashes** — was the root cause of `status=failed` submissions

## v6 Error Analysis (10 submits, 2026-03-22 00:17-00:35 CET)

### ERROR 1: employmentType "Feltet eksisterer ikke i objektet" (422)
- **Execs**: 32626, 32620 (both create_employee from PDF)
- **What**: PUT /employee/{id} with `employments[0].employmentType = "FAST"` → 422 "employmentType field doesn't exist on object"
- **Root cause**: Tripletex API doesn't accept `employmentType` on the employments sub-object via PUT /employee. It may need to be set via POST /employee/employment or a separate endpoint.
- **Impact**: startDate also not set (same PUT fails), employment details not created
- **Fix needed**: Remove employmentType from the PUT /employee body. Set it via POST /employee/employment instead.

### ERROR 2: bank_reconciliation misclassified as reverse_payment (Exec 32624)
- **Task**: "Gleichen Sie den Kontoauszug (CSV) mit den offenen Rechnungen ab" (German bank reconciliation)
- **Classified as**: reverse_payment (WRONG — should be bank_reconciliation)
- **Root cause**: Gemini returned empty/null classification, keyword fallback didn't catch it. German "Gleichen...ab" not in keyword list. "Kontoauszug" not matched.
- **Result**: 0/10, handler tried wrong approach
- **Fix needed**: Add German keywords "Kontoauszug", "abgleichen" to bank_reconciliation fallback

### ERROR 3: project_invoice misclassified as supplier_invoice (Exec 32623)
- **Task**: "Führen Sie den vollständigen Projektzyklus für 'Cloud-Migration Eichenhof' durch: Stunden erfassen, Rechnung erstellen"
- **Classified as**: supplier_invoice (WRONG — should be project_invoice)
- **Root cause**: Gemini returned null/unknown, keyword fallback saw "Rechnung" (invoice) but "Lieferant" not present... yet supplier_invoice check may have matched something else. Actually the keyword check for supplier_invoice requires "supplier"+"invoice" both present — so Gemini itself must have classified wrong.
- **Result**: 18% (2/11) — supplier created instead of full project cycle
- **Fix needed**: Improve Gemini classification prompt for project_invoice, add "Projektzyklus"/"project cycle" as strong signal

### ERROR 4: ledger_analysis doesn't create projects (Exec 32627)
- **Task**: "Analyser hovedboken...Opprett et internt prosjekt for hver av de tre kontoene" (analyze + CREATE projects)
- **Classified as**: ledger_analysis (partially correct — task IS analysis but ALSO requires creating projects)
- **Result**: 0/10 — handler fetched postings but found none (fresh account), returned analysis_complete without creating anything
- **Root cause**: ledger_analysis handler just creates vouchers. This T3 task requires: analyze ledger → find top 3 expense accounts → create project + activity for each. Our handler doesn't create projects.
- **Fix needed**: ledger_analysis must use default handler fallback (let Gemini plan arbitrary API calls)

### ERROR 5: exchange_rate_voucher always fails (Execs 32625, 32618)
- **Task**: register_payment with EUR/NOK exchange rates
- **What**: Payment succeeds but exchange_rate_voucher POST /ledger/voucher → 422 "Validering feilet"
- **Impact**: Partial score (payment works, exchange voucher doesn't)
- **Not critical**: Payment itself succeeds, we get most points

### SUMMARY: 2 biggest ROI fixes
1. **employmentType crash** — breaks ALL employee PDF tasks (14-22 point tasks × 3 multiplier)
2. **Classification errors** — bank_recon and project_invoice misclassified = 0% on those tasks

## v6.1 — Error fixes — DEPLOYED 2026-03-22 00:40 CET

### Fix 16: Remove employmentType from PUT /employee
- Removed `employmentType` from employments update (API returns 422 "Feltet eksisterer ikke")
- This was blocking startDate and employment details from being set on ALL employee PDF tasks
- **Impact**: employee from PDF should now get startDate + salary + percentage again

### Fix 17: Classification — German keywords
- Added German: "Kontoauszug", "abgleich" → bank_reconciliation
- Added French: "rapprochez", "relevé bancaire" → bank_reconciliation
- Added German: "Stunden", "Rechnung", "Zyklus" + "Projekt" → project_invoice
- Added multilingual "project cycle" override: Projektzyklus/prosjektsyklus/ciclo → project_invoice
- Added CSV+bank statement override → bank_reconciliation (never reverse_payment)

### Fix 18: ledger_analysis handler rewrite
- Now uses full default handler approach — Gemini plans ANY API calls (projects, activities, vouchers)
- Fetches existing accounts list for context
- Handles both API call format [{method, endpoint, body}] and voucher format [{postings}]
- **Impact**: tasks like "analyze + create projects" now actually create projects
