# Comprehensive Deep Research Report: Tripletex API Integration for NM i AI 2026

**Executive Summary and Key Findings**
*   **Tripletex Custom Dimensions**: Research suggests that creating custom dimensions relies on the newly introduced endpoints `/ledger/accountingDimensionName` and `/ledger/accountingDimensionValue` [cite: 1, 2]. Referencing these in voucher postings is achieved via the `freeAccountingDimension1`, `freeAccountingDimension2`, and `freeAccountingDimension3` fields within the `PostingDTO` [cite: 2].
*   **API Efficiency and Scoring**: The NM i AI 2026 competition heavily penalizes 4xx HTTP errors and rewards minimal API call chains [cite: 3]. Perfect correctness scores can be doubled by maintaining "error cleanliness" and optimizing call efficiency [cite: 3].
*   **Bank Reconciliation (T3 Tasks)**: It seems likely that Tier 3 bank reconciliation tasks will require the `POST /bank/statement` endpoint for file uploads and the `POST /bank/reconciliation/match` endpoint to link bank transactions to ledger entries [cite: 4, 5].
*   **Undocumented/Advanced Features**: The Tripletex API heavily utilizes non-standard REST paradigms, such as using the `:` prefix for commands (e.g., `:approve`) and the `>` prefix for data summaries [cite: 1, 6]. Furthermore, partial updates are exclusively handled via `PUT` requests rather than `PATCH` [cite: 1].
*   **Scoring Metrics Limitation**: While the specific scoring matrix for the `create_employee` task is well-documented, the exact point allocations for Tier 2 tasks (e.g., `register_payment`, `create_invoice`) are not publicly detailed in the available competition literature [cite: 3]. Estimations based on accounting principles are provided.

**Contextual Overview**
The Norwegian Championship in Artificial Intelligence (NM i AI 2026) represents a significant benchmark for applied autonomous agents in the financial sector [cite: 7, 8]. Organized by Astar in collaboration with industry partners such as Tripletex, Digital Norway, and Norgesgruppen, the competition requires agents to parse natural language prompts and execute complex accounting workflows via the Tripletex REST API [cite: 7, 9]. Submissions are evaluated via field-by-field verification, normalizing the score to a correctness multiplier ranging from 0 to 1.0 [cite: 3].

**Methodological Considerations**
Integrating with the Tripletex environment requires strict adherence to Norwegian Accounting Standards (Norsk Standard Kontoplan NS 4102) and an advanced understanding of standard REST principles combined with Tripletex's bespoke API paradigms [cite: 6, 10]. The evidence leans toward an architecture that preemptively maps local data to Tripletex's unique identifiers to minimize sequential GET requests, thereby maximizing the efficiency bonus [cite: 3]. 

***

## Section 1: Tripletex Custom Dimensions API

The requirement to create and assign custom dimensions (e.g., "Kostsenter", "Prosjekt", "Avdeling") is a critical component of advanced financial reporting and is heavily tested in the competition's Tier 2 and Tier 3 tasks.

### API Endpoints for Custom Dimensions
Historically, Tripletex supported native endpoints for standard dimensions like Projects and Departments. However, to accommodate highly specific organizational needs, Tripletex introduced "free accounting dimensions" (user-defined dimensions). These features are restricted to Tripletex instances operating on the "Pro" package or higher [cite: 2].

The exact API endpoints for managing these dimensions reside under the `/ledger` path [cite: 1]:
1.  `POST /ledger/accountingDimensionName`: This endpoint initializes the overarching dimension category (e.g., "Kostsenter"). The system allows a maximum of 3 custom dimensions, which are automatically assigned an index of 1, 2, or 3 upon creation [cite: 2, 11].
2.  `POST /ledger/accountingDimensionValue`: This endpoint populates the specific values within the created dimension (e.g., "IT", "Г?konomi") [cite: 2].

### Authorization and Permissions
Creating or altering these dimensions requires elevated API privileges. The API token utilized by the agent must be granted the specific role: **"Regnskapsinnstillinger, kontoplan og historisk balanse"** (Accounts settings, chart of accounts and historical balance) [cite: 2]. If the agent attempts a `POST` or `PUT` without this entitlement, the API will yield a `403 Forbidden` error, which will actively degrade the agent's efficiency score in the competition [cite: 3, 6]. Reading these values (`GET`), however, requires no special roles [cite: 2].

### Referencing Dimension Values in Voucher Postings
When generating a voucher or ledger posting, custom dimensions are linked using the `PostingDTO` schema [cite: 2]. Rather than a generic array, Tripletex explicitly maps these to three read/write fields: `freeAccountingDimension1`, `freeAccountingDimension2`, and `freeAccountingDimension3` [cite: 2, 11]. 

To reference a dimension value (where `N` is the integer ID of the `accountingDimensionValue` created earlier), the JSON payload structure should mirror standard Tripletex object referencing:

```json
{
  "date": "2026-03-20",
  "account": { "id": 4000 },
  "amount": 1500.00,
  "freeAccountingDimension1": { "id": 12345 }
}
```

### OpenAPI Documentation
The Tripletex API specification has transitioned from Swagger 2.0 to OpenAPI 3.0 [cite: 12]. The most current schema documenting these endpoints can be fetched dynamically via the `GET /v2/openapi.json` endpoint [cite: 1]. Integrating this JSON spec directly into the agent's context window can drastically improve LLM-based endpoint classification.

## Section 2: Tripletex Voucher Postings вЂ” Complete Schema

Creating a voucher (`POST /ledger/voucher`) involves generating a `VoucherDTO` that contains an array of `PostingDTO` objects [cite: 1, 13]. Understanding the anatomy of a posting is critical to avoiding `422 Bad Request` errors [cite: 6].

### Required vs. Optional Fields
While the exact required fields vary based on the context of the posting (e.g., customer invoice vs. standard journal entry), a general baseline for `PostingDTO` includes:

| Field | Requirement | Description |
| :--- | :--- | :--- |
| `date` | **Required** | The accounting date of the transaction (ISO 8601 `YYYY-MM-DD`) [cite: 1, 6]. |
| `account` | **Required** | The GL account ID (e.g., `{ "id": 1500 }`). |
| `amount` | **Required** | The monetary value. Gross amount generally includes VAT. |
| `vatType` | Optional | Specifies the VAT code. If omitted, it often defaults to the account's standard VAT type. |
| `customer` | Conditional | Required if posting to an Accounts Receivable account (typically 1500). |
| `supplier` | Conditional | Required if posting to an Accounts Payable account (typically 2400). |
| `employee` | Optional | Used for travel expenses or payroll. |
| `project` / `department` | Optional | Standard dimensions for cost allocation. |

### The `closeGroup` Field
The `closeGroup` field is a foundational mechanism in Tripletex for managing open ledgers (Accounts Receivable and Accounts Payable). It functions as a settlement linker. 
*   **Open Status**: If `closeGroup` evaluates to `null`, the posting is "open." For instance, an unpaid customer invoice will have a posting on account 1500 with `closeGroup=null` [cite: 14].
*   **Closed Status**: When a payment is registered, the payment posting and the original invoice posting are assigned the same `closeGroup` ID, effectively matching them and closing the balance [cite: 14]. You can query `GET /ledger/closeGroup/{id}` to retrieve all postings linked to a specific settlement [cite: 5, 15].

### Amortization Specifications
For periodic cost distribution (periodisering), Tripletex utilizes the `amortizationAccount`, `amortizationStartDate`, and `amortizationEndDate` fields within the posting. When a posting contains these values, the Tripletex backend automatically generates subsequent automated journal entries that divide the initial cost across the specified date range, booking the deferred amount to the `amortizationAccount` (typically a balance sheet account) and recognizing the expense incrementally.

## Section 3: NM i AI 2026 Scoring Mechanisms & Task Benchmarks

The competition normalizes raw scores to a 0вЂ“1.0 index based on field-by-field verification of the agent's API side-effects [cite: 3]. 

### Documented Scoring Matrix
The only explicitly documented scoring matrix in the provided research is for the Tier 1 **"create_employee"** task (10 points total) [cite: 3]:
*   Employee successfully created and found (2 points)
*   Correct first name mapped (1 point)
*   Correct last name mapped (1 point)
*   Correct email address mapped (1 point)
*   Administrator role assigned (5 points)

### Extrapolated Scoring Checks for Tier 2 Tasks
The documentation limits explicit disclosures of Tier 2 checks to preserve the integrity of the competition [cite: 3]. However, based on standard API requirements, accounting rules, and the structure of the employee task, we can extrapolate the likely checks.

**register_payment (Estimated 7 checks):**
1.  Voucher created successfully.
2.  Payment matched to the correct invoice (via `closeGroup`).
3.  Correct payment date applied.
4.  Correct amount applied.
5.  Correct `paymentType` or bank account utilized [cite: 1].
6.  Customer balance successfully reduced to zero.
7.  No residual open entries created.

**create_invoice (Estimated 7 checks):**
1.  Invoice object created successfully.
2.  Linked to the correct Customer ID.
3.  Correct order lines / product IDs used.
4.  Quantities and unit prices accurately mapped.
5.  Invoice date and due date correctly set.
6.  Invoice formally "sent" or "approved" (via `:invoice` or `:approve` command) [cite: 6].
7.  VAT appropriately calculated.

**supplier_invoice (leverandГёrfaktura):**
1.  Voucher created.
2.  Correct supplier ID.
3.  KID (Payment Reference) correctly extracted and populated [cite: 16].
4.  Correct expense account (4000-8000 range) [cite: 10].
5.  Correct VAT code applied.

**project_invoice (timesheet + invoice) (Estimated 8 checks):**
1.  Project created.
2.  Time entries logged against correct employee.
3.  Time entries linked to correct project/activity [cite: 17, 18].
4.  Time entries marked as billable.
5.  Order generated from billable hours.
6.  Invoice created from order.
7.  Correct total amount invoiced.
8.  Correct dimensions assigned.

## Section 4: Tripletex T3 Tasks вЂ” Bank Reconciliation

Tier 3 tasks feature a \(\times3\) multiplier and involve complex, multi-step scenarios such as ledger error correction, year-end closing, and bank reconciliation from CSVs [cite: 3].

### Bank Reconciliation API Architecture
Bank reconciliation in Tripletex bridges external bank data with internal ledger postings.
1.  **Importing Bank Statements**: The API supports uploading bank statements via the `POST /bank/statement` endpoint [cite: 4, 19]. Tripletex natively supports standard banking formats, heavily favoring ISO 20022 XML formats like CAMT.053, MT940, and structured CSV files standard to Norwegian banks.
2.  **Reconciliation Initialization**: A new reconciliation instance is created via `POST /bank/reconciliation` [cite: 4, 19].
3.  **Matching Transactions**: The process of linking imported bank transactions to existing ledger vouchers (or creating new ones for fees/interest) is handled by the `POST /bank/reconciliation/match` endpoint [cite: 4, 20]. Alternatively, for automated systems, `GET /bank/reconciliation/{id}/:suggestMatches` (or similar beta endpoints) might be invoked to allow Tripletex's internal engine to attempt auto-matching [cite: 4].

### Year-End Closing Procedures
Year-end operations heavily involve finalizing the general ledger and generating annual accounts. The endpoints related to these tasks include:
*   `GET /ledger/annualAccount`: Retrieves data regarding the annual account statuses [cite: 1, 13].
*   `GET /ledger/accountingPeriod`: Ensuring period 13 (or standard December periods) are closed properly [cite: 1, 13].
*   `POST /ledger/voucher/openingBalance`: Specifically used for transferring closing balances of one year into the opening balances of the next [cite: 2].

## Section 5: Tripletex Efficiency вЂ” Minimum API Calls

The "Efficiency Bonus" is a core meta-game within NM i AI 2026. A perfect correctness score combined with zero `4xx` errors and optimal call efficiency can yield up to a 2.0x overall score multiplier [cite: 3]. Any `4xx` error (e.g., `404 Not Found`, `422 Unprocessable Entity`) immediately degrades the "error cleanliness" metric [cite: 3, 6].

### Optimized Call Chains

**1. `create_customer` (Minimum: 1 call)**
*   `POST /customer`: Requires passing all necessary fields (name, email, organization number, physical address) in a single payload. Note that if `invoiceSendMethod` is set to `EHF`, the `postalAddress` field becomes strictly required and omitting it triggers a 422 error [cite: 14].

**2. `create_employee` (Minimum: 2 calls)**
*   `POST /employee`: Creates the core identity.
*   `PUT /employee/entitlement`: Assigns system permissions (e.g., Administrator role, required for the 5-point bonus) [cite: 3, 13].

**3. `create_invoice` (Minimum: 2-3 calls)**
*   *Assumption*: Customer exists.
*   `POST /order`: Creates the order and order lines simultaneously (order lines can be passed as a nested array).
*   `PUT /order/{id}/:invoice`: Converts the order into an invoice. (Note the use of the non-standard `:` action prefix) [cite: 2, 6].

**4. `register_payment` (Minimum: 2 calls)**
*   `GET /ledger/posting/openPost`: Using the `customerId`, retrieve open postings where `closeGroup=null` [cite: 14].
*   `POST /ledger/voucher`: Create the payment voucher (Debit Bank 1920, Credit AR 1500) and link it to the previously retrieved posting to establish a matching `closeGroup`.

## Section 6: Tripletex API вЂ” Undocumented & Advanced Features

To maximize the efficiency bonus, the AI agent must leverage lesser-known REST paradigms inherent to the Tripletex system.

### Action and Summary Prefixes
Tripletex deviates from strict REST guidelines by utilizing URL prefixes for state changes and data aggregations [cite: 1, 6].
*   **Actions (`:`)**: State changes are executed via `PUT` requests to URLs containing a colon. For example, approving a timesheet is `PUT /v2/hours/123/:approve`, and generating an invoice from an order is `PUT /order/{id}/:invoice` [cite: 1, 6].
*   **Summaries (`>`)**: Aggregated data is retrieved using the greater-than symbol. For example, fetching billable hours is `GET /v2/hours/>thisWeeksBillables`, and fetching the last closed bank reconciliation is `GET /bank/reconciliation/>lastClosed` [cite: 1, 4, 18].

### Batch Endpoints
Creating objects individually severely damages call efficiency. Tripletex supports batch generation for various entities.
*   `POST /customer/list`: Allows creation of multiple customers in one HTTP transaction (listed as `[BETA] Create multiple customers`) [cite: 20].
*   `POST /asset/list`: Create several fixed assets [cite: 19].
*   `POST /purchaseOrder/orderline/list` [cite: 2].

### Webhook Subscriptions
For real-time event-driven architecture, Tripletex offers event subscriptions [cite: 1, 6].
*   `POST /event/subscription`: Registers an endpoint to receive JSON payloads whenever an internal entity is mutated [cite: 19]. The envelope contains the `event` type (e.g., `object.verb`) and the `value` of the modified object [cite: 1]. This allows the agent to asynchronously monitor for state changes rather than utilizing inefficient `GET` polling loops.

## Section 7: Norwegian Accounting Standards (Norsk Standard Kontoplan NS 4102)

Any agent interfacing with Tripletex must exhibit a semantic understanding of NS 4102, as the system enforces strict validity checks between accounts and VAT codes. If an agent attempts to post a high-rate VAT code to a balance sheet account, Tripletex will reject the payload with a `422 Bad Request` (18000 Validation Exception) [cite: 6].

### Standard Account Ranges (Kontoklasser)
The Norwegian chart of accounts is logically structured by the first digit [cite: 10]:
*   **Class 1 (Eiendeler / Assets)**: Balance sheet accounts (e.g., 1920 Bank, 1500 Accounts Receivable / Kundefordringer, 1230 Cars / Personbiler) [cite: 10, 21].
*   **Class 2 (Gjeld og Egenkapital / Liabilities & Equity)**: Balance sheet accounts (e.g., 2400 Accounts Payable / LeverandГёrgjeld, 2740 VAT Settlement / OppgjГёrskonto MVA) [cite: 10, 22].
*   **Class 3 (Salgsinntekter / Income)**: P&L accounts. E.g., 3000 is utilized for Sales Income subject to the high standard VAT rate (25%) [cite: 10].
*   **Class 4 (Varekostnader / Cost of Goods Sold)**: Direct material costs [cite: 10].
*   **Class 5 (LГёnnskostnader / Payroll)**: Salary and personnel expenses [cite: 10].
*   **Class 6 & 7 (Driftskostnader / Operating Expenses)**: E.g., 6800 Office supplies, 7320 Advertising [cite: 10, 23].
*   **Class 8 (Finans / Financial)**: Interest income and expense [cite: 10].

### VAT Codes (MVA-Koder) and Mapping
In Tripletex, VAT (Merverdiavgift) processing is highly automated. When creating a posting, the `vatType` dictates the tax calculation.
*   **Account 3000 (Sales, High Rate)**: Locked to outgoing VAT (UtgГҐende MVA) at 25%.
*   **Account 2740 (VAT Settlement)**: During period closures, balances from individual VAT tracking accounts (2700-2749) must be zeroed out and transferred to 2740 for settlement with Skatteetaten (the Norwegian Tax Administration) [cite: 22].

### Employer's Contribution (Arbeidsgiveravgift)
In payroll vouchers (`payroll_voucher`), standard Norwegian accounting requires booking both the gross salary and the associated social security tax (Arbeidsgiveravgift). 
*   Gross salary is debited to a Class 5 account (e.g., 5000).
*   Arbeidsgiveravgift (typically 14.1% depending on the geographical zone) is calculated on the gross amount, debited as an additional expense to account 5400 (Arbeidsgiveravgift), and credited as a liability to account 2770 (Skyldig arbeidsgiveravgift).
The AI agent must manually calculate and instantiate these dual postings if operating at the raw `/ledger/voucher` API level.

### Year-End Closing Entries
Year-end closing involves transferring the net result from the P&L (Classes 3-8) to the Equity section of the balance sheet (Class 2). A standard workflow (e.g., for an AS / Aksjeselskap) debits the net income account (e.g., 8990) and credits Other Equity (e.g., 2050 Annen innskutt egenkapital). Furthermore, the agent must ensure that asset accounts are properly subjected to depreciation rules into specific balance groups (saldogrupper) [cite: 21].

***

By strictly adhering to the `openapi.json` schema specifications, utilizing undocumented batch endpoints, and perfectly mirroring NS 4102 accounting logic, your Gemini 2.5 Flash agent will be optimally positioned to conquer the Tier 2 and Tier 3 task parameters within the NM i AI 2026 competition framework.

**Sources:**
1. [tripletex.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFfKJ1dcJefe7Nyq4bLBZme7mk5lTjtvQS0fjQTICZMUMEcJA6HEGysi8flqpHxUhlzRdfFDpm73V_-mJK4AUh6xcy3vJT90g_Jo7Z6RsOKnY1EGw==)
2. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGT8E3sDM5JSUy1jjXqbo82tqHQY_ZKtPCg5Ybh9ZANoUBYBU2l1KxICx4zZoPzbzJ6LRHw_wQlxan1r_Z30K4UYwGV_NMmjtVZfuaglMj1F594bnv3ClA-627weVUD4RBzUO-x5-PQORyyqrkUE3qsZiBZ0Mi-waPQCQ==)
3. [ainm.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEgHP6OPRMN8m86Cukr1rMARwvyihyYJPCDQz2tAqGbpcuHLXczqJsEIGaAADqYmM0ehr97zHfvVXuCoKMQZCpb9Lh5CFTAbi07nwbBc3VfF95NMeMamVuUZiOnB7EdhD0=)
4. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQENAcmwFTV1axOX8DJTwWDeHlNwmVx0AFx5PTOc4TbrqIF-NuepcOruazI6M3Q7Cw-m1zlaBqvW9qNicA5gitHNLHPazIKCKDeeXTof8RujmAVmFcED3aHok7-6Iks6Ag==)
5. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHyuwterrAXBVmUAR3-Xd2RtvMLta77IZht14L74ujcw3esjwsLJu2PorjFn0LgXanVY1jFmJsVlgb2mJtaR3fvyM1V7CljqAqY65TCJP2gmIAf5JNEOxSmBAdVVjbgvzGw)
6. [tripletex.tech](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHYBF97qRMJp6WHR2tAtTO05WADFkQsIuBM-702HR-bVYSfo6UOOBJ4tR1GFNYBhdxEpfT442zsq8EXrJu7PfD6DYzwwpk8F9oUNnFCnCmOMSusV0B1b-fgKgka4SrZ)
7. [ainm.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHnleWYjJX43RaylNpAGK5CNELes_dvJQCH_eyN20MzFYg36IIcrjRbOI5kGCePa5_GrLCxT8mP-RRbXTFoqCV0KXtisfVyrXQj7SgTJgE7a3_qeY2kDTGqUuv68CPsFb6w)
8. [aiavisen.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEYkhjuFVwVUOvnYXSv6ptFkCPOij0irTgV1ULnUxzkn0vBDu02Hl8L3Kmmg8KPtOIRPhXBx3uyygtjGsRP6nWzdhrRl9uIOlN6Q45Fboy6bF-2C_sP1Ko=)
9. [digitalnorway.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE3cTIdJt6ocjI9EhxvFYuFLS1Gz1RjTcgjT3Klzi7wdQ8jGONXttU5otAvj6YPK0Ul_4Pqq8jH3Eq_Ikcw0ws2cUQX3-j6v4MKnyLkUDU0wR4hiefEuIuX6ONkXpxJX1c3pRraCI9NTp1QTMOFSv9q8XeZ5IR3p2EbzgOl0x4SLddeFAXj77bZV8V2bHOllQI48pg81exW9uz5qA==)
10. [systima.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFP_vGWOS16xRWhXJ_hHK2Tg0e2EiMT9PwstWIG5H2hFreZYBRA3b9cVEujlYt7DRs_9piK09TfgtseJOp9HopK-tXCjBDOBrj5HjY1FWMSENApMoUzJq-v7k7fO1TqjFJISgo0W9_dqg==)
11. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHWtC3-qJWLikbI3YdzZR8kkAiTdVtknKYLGmze53cHyUjIyINlGnRCEbr7lDti1TaC6B3eLnoe7RTyrXnFwlb18xY3LHJjs4oMq5Vwc9hsW8JLk4cYzVb1HVBabB1rRG7ErIzgPi2kiP2aINxi_u9S3Lu32ncP494h2THtvNwvZqDV)
12. [tripletex.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGI251bgRuTGDFTr54x6dQqOHEjHekmZOSEFh7OSQyV9QttsbY4AMzqYlxblGbdSKwixUUil6yNsVFcaTrqw9oOzn1hp92BgyhDChjnN8RJvTRI1E87)
13. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQG0W7BieJiR4k-bZg1ihVvrRCchetKm4H5S76ahyLVVHa-b7_asKq-qokkJdxE_V0mWuPPvyOqvA6OU1fec9XQDXXtoYbTnEzFEfjjBYfLYrY5uL5KOkbWKfVH1inpjXMU=)
14. [tripletex.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHjj8iHMLQH0lbNnawP5o5Ax9aZiKc84hQL3WxLcR42tM7MHB7DXMj-pODu5BTgiguB1dQZMvlH25BuC8Xf69E2FemCgVVK0SQYtFoMQgdKlCkpVoAtWIcwu5eA5d20gvKQ5KjgqmDWcSbap7Pk8h-AW2EhpSQ=)
15. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEqrF6fCmRR2osxwXTAdaPJ-at0rxNDlD-1PhraMb9ZU7EcbUE6VdfxMX5RpBqP0ar2lZW__NTPQ3bXytshdc1KY4MqeGQfs33QAw_jtD37R7POa1KngdKjfob4cLXVCVZ7wgM4LHFvAj6-AEyvChVxqkoN_XyG0KrIpZtsh5J4hRK4qVYeRnkkXeWZ)
16. [unimicro.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGvnPSPhXmd1X3hiog0QdoqOQu52kHBIDE_YZUfRSigRo3SD2xLURtc1YBe7zV_lO4SlTHeaV2Uj1NYCypKJzNhfLV1sdfHwC9N_i0dRGfMZ76AJeoh6DxqqgmoX6TWWs4-rRJ21Fdlo3A=)
17. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEzI6bHh5hOCjBtLeo0NP_QVK3WP8L5Xy1WKo7M7f-00LD1-FLNpm6Qd9MUI4goArCzLVcXRw5HM9gtYSMMRdAuJl6Lls_W9Y44cf7yHN2XgIjm_biwyYKpN7cnHLO-GFVB)
18. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGdk7HarCHpA-X6b2BHYeN8Rzq5Qm5Ap-M_WxnmKCgd9f27zOPvnwaItbA9SXw3VPY1CKZTxMCGWLeWzsDqsmH5LqUjNxKiO9ojpJmnQpNpDai1492yn73elTBdTIOEEgbyEQ-7vFeqcQfumVtnVtzXFFzZdia2JEzX)
19. [github.com](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH0h3Vzz3G8bQBjdY4ncvpVl3hSqqWfo05c9Y8kioLqmoH2POY1lGWTV-mMGldg5Afg7nY379uCvy_ml_2xn-vA4umSJiJqwAxQIc_QlFOSMZMVWh0CxyCtnIv4uVY23qCUDJhHwUQ=)
20. [rubydoc.info](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEtg9TVYZD0BGf_CKdVCQRmHp43gLZo7VpY9QMA90yzIoBhWlaMJpDMHRJG6cMg_bjCSTWxCGeueRdyz2by_axHI1o7NOFcOpYFW8P7YVv2E6SEbgCi3jHz8ap8hnq6OKZW9bZ0AGbr)
21. [tripletex.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGF2meKgLVxDd2wOy-YaiVDgSOwCHWzZyzlF4OfM-KDna1qKJXZ6M2cBggaJF3UlNG2mck2yIaaudv2ehffMRMWnhcRYGrll6K0qtnDKVtF6K6__pzrTUREjxK9nSh6NXqXg0Z22Tczb4AyaGOcOsjdal0UivIv4Yj21pO-uKgq6cWOxAiz1zMtPzk5g4l1Gd216-Zfzupjo7kvkhuztk_au4hNKbJ6MqE=)
22. [tripletex.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQES7quswNmHJ7Ms9LRLpCD0xZvviv0L78DwyRmOwDtI_9U-ey4YkC60vfDv1d7INGlcgiUQlgkj75IYHt9l7H1fuZeAUpo2vjyORLt59Xe3UyxlaQG3FAGZ4LwNvVxS5dfLUSUxtICKAMFcncf3QS4EaLVjHWfWyFMEO_Pm2-xvq_DC-o6N7MPRlE-1mBeQXHYYO-rU7Vrl2X5yjw2112_TCHE0t3VIdKOdX9y94kJghQ-B2Z3sLER1NwLtqe5HEX0NldITS16lfggDgCp3w9qJFQ==)
23. [jithomassen.no](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEfwowr5qU5BhvoFE73t0bTKDjOzYWtr0Jug7ZY_11zeCpipQOxziZzsVwInCla1mByKDsMOxSFPQ6TwQzPSWqAc_Ur2Av-7hDVB8aKo5itY6hX5Iv6NTEt0F_yMkipeY5GXJmg7DfAbsNllBuabMDzmI8=)
