# Tripletex API Deep Research — NM i AI 2026 Competition

## Context
We are competing in NM i AI 2026 (Norwegian Championship in AI). The Tripletex challenge requires building an AI agent that receives accounting tasks via webhook and executes them against Tripletex REST API. We have 30 task types across 3 tiers (T1 ×1, T2 ×2, T3 ×3 multiplier). Current score: 13.6/198 teams.

Our agent uses Gemini 2.5 Flash for task classification + Tripletex API v2 for execution. We've solved most T1 tasks but are hitting walls on T2 and need to prepare for T3.

## Research Questions

### 1. Tripletex Custom Dimensions API
The competition requires creating custom dimensions ("Kostsenter", "Prosjekt", etc.) and linking them to voucher postings. We found these fields on voucher postings: `freeAccountingDimension1`, `freeAccountingDimension2`, `freeAccountingDimension3`.

**Questions:**
- What is the exact API endpoint for creating custom dimensions in Tripletex? (POST /dimension? POST /freeAccountingDimension?)
- How do you create dimension values (e.g. "IT", "Økonomi" under "Kostsenter")?
- How do you reference a dimension value in a voucher posting? Is it `freeAccountingDimension1: {id: N}` or something else?
- Is there a Tripletex OpenAPI spec or Swagger that documents these endpoints?
- What permissions/modules need to be enabled for custom dimensions?

### 2. Tripletex Voucher Postings — Complete Schema
We have voucher creation working but are missing some fields. Need the COMPLETE posting schema:
- What fields are required vs optional on each posting?
- How do `vatType`, `customer`, `supplier`, `employee`, `project`, `department` work on postings?
- What is the `closeGroup` field used for?
- How does `amortizationAccount` + `amortizationStartDate`/`amortizationEndDate` work?

### 3. Tripletex Scoring for Competition Tasks
For the NM i AI competition, each task has 4-8 scoring checks. We need to understand what exactly is checked:

**Task: create_employee (10 points)**
- Employee found (2 pts)
- Correct first name (1 pt)
- Correct last name (1 pt)
- Correct email (1 pt)
- Administrator role assigned (5 pts)

**What are the scoring checks for these T2 tasks?**
- register_payment — what 7 checks? (amount, date, payment type, customer name, org number, product description, invoice amount?)
- create_invoice — what 7 checks?
- credit_note — what checks?
- supplier_invoice (leverandørfaktura) — what checks?
- payroll_voucher — what checks?
- project_invoice (timesheet + invoice) — what 8 checks?
- custom_dimensions — what 6 checks?

### 4. Tripletex T3 Tasks — Bank Reconciliation
T3 tasks (×3 multiplier) open tomorrow. They likely include:
- Bank reconciliation from CSV file
- Ledger error correction
- Year-end closing procedures

**Questions:**
- How does Tripletex bank reconciliation API work? (POST /bank/statement? POST /bank/reconciliation?)
- Can you import bank statements via API? What format (CSV, CAMT.053, MT940)?
- How do you match bank transactions to vouchers/invoices?
- What endpoints handle year-end closing in Tripletex? (POST /ledger/close? PUT /year/close?)

### 5. Tripletex Efficiency — Minimum API Calls
The competition scores efficiency (fewer API calls + zero 4xx errors = bonus up to 2×).

**For each common task, what is the MINIMUM number of API calls?**
- create_employee: POST /employee + PUT /entitlement = 2 calls minimum?
- create_customer: POST /customer = 1 call?
- create_invoice: POST /customer + POST /order + POST /invoice = 3 calls?
- register_payment: same as invoice + PUT /:payment = 4 calls?
- create_voucher: GET /account + POST /voucher = 2 calls?

### 6. Tripletex API — Undocumented Features
Are there any undocumented or lesser-known Tripletex API features that could help:
- Batch endpoints (create multiple entities in one call)?
- Webhook subscriptions for events?
- Import endpoints for bulk data?
- Any "shortcut" endpoints that combine multiple steps?

### 7. Norwegian Accounting Standards (Norsk Standard Kontoplan)
For voucher creation, we need the standard Norwegian chart of accounts:
- What are the standard account ranges and their VAT codes?
- What VAT types (mva-koder) are locked to which account ranges?
- How does the employer's contribution (arbeidsgiveravgift) work in payroll vouchers?
- What accounts are used for year-end closing entries?

Please provide detailed, technical answers with specific API endpoints, JSON body examples, and any relevant Tripletex documentation links.
