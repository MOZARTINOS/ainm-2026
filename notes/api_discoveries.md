# Tripletex API Discoveries from OpenAPI Spec

## CRITICAL: Alternative endpoints we're NOT using

### 1. POST /incomingInvoice — SUPPLIER INVOICE ALTERNATIVE
- Creates incoming invoice directly (not via voucher!)
- `POST /incomingInvoice`
- `POST /incomingInvoice/{voucherId}/addPayment`
- May be what competition checks instead of voucher
- **MUST TEST ON SANDBOX**

### 2. /salary — 38 endpoints for payroll
- Dedicated salary API instead of manual voucher
- `/salary/transaction` — salary transactions
- `/salary/payslip` — payslips
- `/salary/settings` — salary settings
- May produce proper payroll entities that competition checks

### 3. /bank/reconciliation — T3 bank reconciliation
- `GET/POST /bank/reconciliation`
- `GET/POST /bank/reconciliation/match`
- `PUT /bank/reconciliation/match/:suggest`
- For T3 tasks (bank statement reconciliation)

### 4. /ledger/accountingPeriod — period management
- For year-end closing tasks (T3)

### 5. /yearEnd — year-end closing
- 18 endpoints for year-end procedures
- T3 task type

### 6. Employee employment details
- `GET/POST /employee/employment` — employment records
- `GET/POST /employee/employment/details` — detailed employment info
- `GET /employee/employment/employmentType` — types
- May fix startDate issues

### 7. /employee/entitlement endpoints we know
- `PUT /:grantEntitlementsByTemplate` — what we use
- `GET /employee/entitlement` — list entitlements
- `POST/DELETE /employee/entitlement` — manage individual

### 8. /order/:invoiceMultipleOrders — batch invoice
- `PUT /order/:invoiceMultipleOrders` — invoice multiple orders at once

### 9. /purchaseOrder — purchase orders (supplier side)
- 27 endpoints for purchase orders
- Alternative to voucher for supplier invoices?

## Full category stats
- 546 total endpoints across 56 categories
- We actively use ~15 categories
- ~40 categories unused

## POST /incomingInvoice — 403 on sandbox
- Schema: invoiceHeader{vendorId, invoiceNumber, invoiceDate, dueDate, invoiceAmount} + orderLines[{accountId, amountInclVat, vatTypeId, externalId, row}]
- Sandbox returns 403 (no permission) — may work on competition proxy
- TOO RISKY to deploy without sandbox test
- Voucher approach remains our only option for supplier_invoice


## CRITICAL FINDING: Why supplier_invoice = 0/8
- `GET /supplierInvoice` on sandbox = 0 entities
- Our voucher approach does NOT create SupplierInvoice entity
- Competition likely checks `GET /supplierInvoice` → finds nothing → 0 checks pass
- Only way to create SupplierInvoice: `POST /incomingInvoice`
- Schema: invoiceHeader{vendorId, invoiceNumber, invoiceDate, dueDate, invoiceAmount} + orderLines[{accountId, amountInclVat, vatTypeId, externalId, row}]
- Sandbox returns 403 but competition proxy MAY allow it
- STRATEGY: Try incomingInvoice first, fallback to voucher if fail
- This is THE key fix for supplier_invoice 0/8 → potentially 8/8

## Diagnostic endpoints available
- `GET /ledger/posting` — all recorded transactions
- `GET /supplierInvoice` — check if entity exists
- `GET /voucherStatus` — voucher status
- `GET /ledger/posting/openPost` — unmatched postings
- These can be used to VERIFY what we created after each operation

## Module Enabling — Research Results
- `GET /company/modules` — shows 15 ON, 20 OFF on sandbox
- `PUT /company/modules` — 405 Method Not Allowed on sandbox
- `POST /company/salesmodules` — accepts SalesModule enum names only
  Valid: MAMUT, BASIS, SMART, KOMPLETT, VVS, ELECTRO, WAGE, SMART_WAGE etc.
  NOT valid: DEPARTMENT_ACCOUNTING, PRODUCT_ACCOUNTING etc.
- `moduleDepartmentAccounting` = internal toggle, not a sales module
- CANNOT enable internal modules via API on sandbox
- Competition proxy MAY allow PUT /company/modules
- If task says "enable department accounting" → try PUT /company/modules
