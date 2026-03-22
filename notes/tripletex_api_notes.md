# Tripletex API Testing Notes

**Date**: 2026-03-19
**Sandbox URL**: https://kkpqfuj-amager.tripletex.dev
**Production test env**: https://api-test.tripletex.tech

## Authentication

### Token Flow
1. You need a `consumerToken` and `employeeToken` (provisioned by competition/Tripletex)
2. Create session token: `PUT /v2/token/session/:create?consumerToken=X&employeeToken=Y&expirationDate=YYYY-MM-DD`
3. Use session token for all API calls: `Authorization: Basic <base64(0:sessionToken)>`
4. Username is always `0` (or companyId for proxy access)

### Competition Flow
- The competition sends `session_token` and `base_url` in the webhook payload
- We do NOT need to create session tokens ourselves
- Auth header: `Basic ` + base64(`0:` + session_token)

### Key Finding: Cannot Create Test Tokens
- The sandbox at `kkpqfuj-amager.tripletex.dev` requires real consumerToken/employeeToken
- Tokens `0`, `test`, etc. all fail with "Nokkelen er ugyldig" (invalid key)
- The `api-test.tripletex.tech` environment requires Visma Connect OAuth login
- Test tokens must come from the competition platform when tasks are sent

## Working Endpoints (verified via OpenAPI spec)

### GET Endpoints
| Endpoint | Description | Key Params |
|----------|-------------|------------|
| `GET /v2/employee?from=0&count=5` | List employees | firstName, lastName, email filters |
| `GET /v2/customer?from=0&count=5` | List customers | name, isCustomer filters |
| `GET /v2/ledger/vatType?from=0&count=20` | List VAT types | |
| `GET /v2/product?from=0&count=5` | List products | name filter |
| `GET /v2/department?from=0&count=5` | List departments | name filter |
| `GET /v2/project?from=0&count=5` | List projects | name filter |
| `GET /v2/order?from=0&count=5` | List orders | orderDateFrom, orderDateTo |
| `GET /v2/invoice?from=0&count=5` | List invoices | invoiceNumber filter |
| `GET /v2/token/session/>whoAmI` | Current user info | |

### POST Endpoints (Create)
| Endpoint | Description | Min Body |
|----------|-------------|----------|
| `POST /v2/employee` | Create employee | `{"firstName":"X","lastName":"Y"}` |
| `POST /v2/customer` | Create customer | `{"name":"X","isCustomer":true}` |
| `POST /v2/product` | Create product | `{"name":"X"}` |
| `POST /v2/order` | Create order | `{"customer":{"id":N},"orderDate":"YYYY-MM-DD","deliveryDate":"YYYY-MM-DD","orderLines":[...]}` |
| `POST /v2/invoice` | Create invoice | `{"invoiceDate":"YYYY-MM-DD","invoiceDueDate":"YYYY-MM-DD","orders":[{"id":N}]}` |
| `POST /v2/department` | Create department | `{"name":"X"}` |
| `POST /v2/project` | Create project | `{"name":"X","isInternal":true}` |

### PUT Endpoints (Update/Special)
| Endpoint | Description |
|----------|-------------|
| `PUT /v2/employee/{id}` | Update employee (full object) |
| `PUT /v2/customer/{id}` | Update customer |
| `PUT /v2/order/{id}/:invoice` | Convert order to invoice |
| `PUT /v2/invoice/{id}/:createCreditNote` | Create credit note |
| `PUT /v2/invoice/{id}/:payment` | Register payment on invoice |
| `PUT /v2/invoice/{id}/:send` | Send invoice |

### DELETE Endpoints
| Endpoint | Description |
|----------|-------------|
| `DELETE /v2/employee/{id}` | Delete employee |
| `DELETE /v2/customer/{id}` | Delete customer |
| `DELETE /v2/order/{id}` | Delete order |

## Entity Schemas (Key Fields)

### Employee
- `firstName` (string) - first name
- `lastName` (string) - last name
- `email` (string)
- `dateOfBirth` (string, YYYY-MM-DD)
- `phoneNumberMobile` (string)
- `department` (object, `{id: N}`)
- `employments` (array) - employment records with startDate, employmentDetails
- `userType` (string) - STANDARD, etc.
- No fields are marked as required in the schema, but firstName+lastName are practically required

### Customer
- `name` (string) - company/person name [practically required]
- `isCustomer` (boolean) - set to true [important!]
- `email` (string)
- `phoneNumber` (string)
- `organizationNumber` (string)
- `postalAddress` (Address object) - `{addressLine1, postalCode, city, country: {id: 162}}`
- `isSupplier` (boolean)
- `isPrivateIndividual` (boolean)
- `invoiceSendMethod` (string) - EMAIL, etc.

### Product
- `name` (string) [practically required]
- `number` (string) - product number
- `priceExcludingVatCurrency` (number) - price excl VAT
- `priceIncludingVatCurrency` (number) - price incl VAT
- `vatType` (object, `{id: N}`) - VAT type reference
- `isStockItem` (boolean)

### Order
- `customer` (object, `{id: N}`) [required for creation]
- `orderDate` (string, YYYY-MM-DD)
- `deliveryDate` (string, YYYY-MM-DD)
- `orderLines` (array) - line items with product, description, count, unitCostCurrency, vatType
- `isPrioritizeAmountsIncludingVat` (boolean)

### Invoice
- `invoiceDate` (string, YYYY-MM-DD)
- `invoiceDueDate` (string, YYYY-MM-DD)
- `orders` (array of `{id: N}`) - link to orders
- `orderLines` (array) - can include lines directly
- `customer` (object, `{id: N}`)
- Two creation methods:
  1. `POST /v2/invoice` with order references
  2. `PUT /v2/order/{id}/:invoice` to convert order to invoice

### Department
- `name` (string) [practically required]
- `departmentNumber` (string)

### Project
- `name` (string) [practically required]
- `number` (string) - auto-generated if NULL
- `isInternal` (boolean)
- `customer` (object, `{id: N}`) - for external projects
- `startDate` / `endDate` (string, YYYY-MM-DD)
- `projectManager` (object, `{id: N}`)

## Important Gotchas

### 1. Invoice Creation is Two-Step
The standard flow is: Order -> Invoice. You create an Order with orderLines first, then convert it to an Invoice using `PUT /v2/order/{id}/:invoice`. Alternatively, `POST /v2/invoice` can reference existing orders.

### 2. VAT Type IDs
- VAT types must be fetched from `/v2/ledger/vatType` - IDs vary by environment
- Common: 25% MVA (standard), 15% MVA (food), 0% (exempt)
- Products require a vatType reference

### 3. Country IDs
- Norway = `{id: 162}` in addresses
- Addresses use `postalAddress` for mailing, `physicalAddress` for location

### 4. Error Format
```json
{
  "status": 422,
  "code": 15000,
  "message": "Validation failed",
  "validationMessages": [
    {"field": "fieldName", "message": "Description of error"}
  ]
}
```
- 401: Invalid/missing auth token
- 422: Validation error (check validationMessages for details)
- 404: Entity not found

### 5. Pagination
- All list endpoints use `?from=0&count=N` for pagination
- Response includes `fullResultSize`, `from`, `count`, `versionDigest`
- Data is in `values` array: `response.data.values`

### 6. Fields Filter
- Use `?fields=id,name,email` to reduce response size
- Nested: `?fields=*,orderLines(*)`

### 7. Update Requires Full Object
- PUT endpoints expect the full entity object, not just changed fields
- Best practice: GET the entity first, modify fields, then PUT it back

### 8. URL Path Format
- All endpoints are under `/v2/`
- Special actions use colon prefix: `/:create`, `/:invoice`, `/:createCreditNote`
- The whoAmI endpoint uses `>` prefix: `/>whoAmI`

## Our Webhook (n8n)

**URL**: `https://n8n.visam.no/webhook/tripletex-solve`
**Method**: POST
**Expected payload**:
```json
{
  "task": "Opprett en ansatt med navn Ola Nordmann og epost ola@test.no",
  "base_url": "https://kkpqfuj-amager.tripletex.dev",
  "session_token": "REAL_SESSION_TOKEN_HERE",
  "attached_files": []
}
```
**Response**: `{"status": "completed"}`

### Supported Task Types
1. `create_employee` - Create employee
2. `create_customer` - Create customer
3. `create_product` - Create product
4. `create_invoice` - Create invoice (Order -> Invoice flow)
5. `register_payment` - Register payment on invoice
6. `create_travel_expense` - Create travel expense
7. `update_employee` - Update employee fields
8. `delete_employee` - Delete employee
9. `credit_note` - Create credit note
10. `create_department` - Create department
11. `create_project` - Create project
12. `unknown` - Falls back to Gemini for API call planning

### Workflow Architecture
1. Receive webhook POST
2. Gemini 2.0 Flash classifies task type and extracts parameters
3. Switch on task_type, execute appropriate API calls
4. If first attempt fails, Gemini retries with error context
5. Always returns `{"status": "completed"}` regardless of success/failure

### Known Issues
- Cannot test with real API calls without valid session token
- The workflow always returns "completed" even on failure (competition expects this)
- Invoice creation uses a non-standard path: creates Order first, then uses undocumented endpoint format
- The correct invoice-from-order endpoint is `PUT /v2/order/{id}/:invoice` (not `/v2/invoice/{orderId}/:createInvoice`)
