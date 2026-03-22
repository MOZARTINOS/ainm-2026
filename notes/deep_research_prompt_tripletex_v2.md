# Deep Research: Maximizing Tripletex Accounting Automation Score

## Research Objective

I'm competing in NM i AI 2026 (Norwegian AI Championship). The Tripletex challenge requires building an AI agent that receives accounting task prompts in 7 languages and executes the correct Tripletex REST API calls. Current score: 23.1/180 possible. I need to understand exactly what the scoring system checks and how to maximize each task's score.

## Current Architecture

- Webhook receives `{prompt, files[], tripletex_credentials}`
- Gemini 2.5 Flash classifies task type and extracts parameters
- JavaScript code executes Tripletex v2 REST API calls
- Returns `{status: "completed"}`
- Each task starts on a FRESH empty Tripletex account

## Specific Questions to Research

### 1. Tripletex SupplierInvoice — How to Create Properly

Our supplier_invoice handler creates a voucher with supplier reference in postings, but scores 0/8. Research:

- How are SupplierInvoice entities actually created in Tripletex v2 API?
- Is there a POST endpoint for SupplierInvoice, or is it auto-created from vouchers?
- What is the relationship between `/ledger/voucher` and `/supplierInvoice`?
- What fields on voucher postings trigger SupplierInvoice creation (invoiceNumber? supplier? specific accounts?)
- How do Norwegian accounting firms register incoming supplier invoices ("leverandørfaktura") in Tripletex?
- What is the correct account structure: 2400 (leverandørgjeld), expense account, 2710 (inngående mva)?

### 2. Tripletex Payroll / Salary (Lønn)

Our payroll_voucher scores 0/8. Research:

- How should salary/payroll be registered in Tripletex v2 API?
- Is there a dedicated payroll/salary module or API endpoint beyond manual vouchers?
- What accounts are used: 5000 (lønn), 5400 (arbeidsgiveravgift), 2770 (skyldig arbeidsgiveravgift)?
- Must the employee be created BEFORE the payroll voucher?
- What fields on voucher postings are required for payroll (employee reference, specific accounts)?
- How does arbeidsgiveravgift (employer's social security contribution, 14.1%) factor in?

### 3. Tripletex Travel Expense Scoring

Our travel expense scores 4.5/8 despite all API calls succeeding. Research:

- What specific fields does Tripletex check on travel expenses?
- POST /travelExpense — what are the critical fields beyond employee, title, travelDetails?
- POST /travelExpense/cost — what fields determine scoring (costCategory, paymentType, amountCurrencyIncVat)?
- POST /travelExpense/perDiemCompensation — what fields matter (overnightAccommodation, location, count)?
- Are costCategory IDs environment-specific or standardized?
- Should the employee be created with specific entitlements for travel expense access?

### 4. Tripletex Invoice Multi-Line with Products

Our multi-line invoice (3 products, different VAT rates) scores 3/8. Research:

- When creating products with POST /product, what fields are critical for scoring (name, number, priceExcludingVatCurrency, vatType)?
- In orderLines, should products be referenced by {id} or created inline?
- How do different VAT rates (25%, 15%, 0%) map to vatType IDs?
- Is the product `number` field (e.g., "8944") critical for scoring?
- Does the order need `deliveryDate` different from `orderDate`?

### 5. Tripletex Project Invoice with Hourly Rates

Our project_invoice scores 0/8 despite creating project + activity + timesheet + order + invoice. Research:

- What is the correct flow: customer → employee → project → activity → projectActivity → timesheetEntry → order → invoice?
- Must the project have `projectManager` set to the employee doing the work?
- How should hourly rates be configured on the project (PUT /project/hourlyRates)?
- Should the invoice reference the project, or just the order?
- What fields on timesheetEntry are critical (hours, chargeableHours, date)?

### 6. Efficiency Optimization

Score formula: correctness × tier_multiplier × (1 + efficiency_bonus). Research:

- What is the exact formula for efficiency bonus?
- How are API call counts measured (GET + POST + PUT = all count)?
- Do 4xx errors (422 validation) count against efficiency even if retried successfully?
- What is the minimum API call count for each task type?
- Do cache warming calls (GET /department at start) count against efficiency?

### 7. Tripletex Custom Dimensions

Our dimension_voucher scores 0/13. Research:

- What is the API for creating custom accounting dimensions ("fri regnskapsdimensjon")?
- Is this the `freeAccountingDimension` concept from posting schema?
- Are there endpoints like POST /dimension or POST /freeAccountingDimension?
- How do dimension values get linked to voucher postings?
- Is this feature available on all Tripletex environments or requires specific module activation?

### 8. General Tripletex Best Practices

- What is the recommended order of entity creation for a fresh account?
- Should bank account (1920) be set up before creating invoices?
- How does `isCustomer` vs `isSupplier` flag affect entity visibility?
- What is the relationship between `department` and `employee`?
- Are there batch creation endpoints (POST /customer/list) that are more efficient?

## Expected Output Format

For each question, provide:
1. **Direct answer** with API endpoint details
2. **Required fields** with correct data types
3. **Code example** (JSON body for POST/PUT)
4. **Common pitfalls** from Tripletex documentation or community
5. **Links to official documentation** where applicable
