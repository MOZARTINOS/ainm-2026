# Training Data Summary

Generated: 2026-03-22 14:21:42

## Overview
- **Total records**: 1536
- **Sources**: cloud: 59, self-hosted: 1477
- **Success rate**: 1159/1536 (75.5%)
- **With files**: 37, Without files: 1499

## API Call Stats
- **Total API calls**: 3125
- **Successful**: 2450 (78.4%)
- **Errors**: 675 (21.6%)
- **Avg calls/execution**: 2.0

## Task Type Distribution

| Task Type | Count | Success | Fail | Rate |
|-----------|-------|---------|------|------|
| unknown | 248 | 5 | 243 | 2% |
| create_employee | 170 | 139 | 31 | 82% |
| create_invoice | 138 | 119 | 19 | 86% |
| create_customer | 128 | 124 | 4 | 97% |
| register_payment | 101 | 90 | 11 | 89% |
| create_product | 100 | 85 | 15 | 85% |
| create_department | 73 | 68 | 5 | 93% |
| create_project | 66 | 58 | 8 | 88% |
| create_travel_expense | 56 | 53 | 3 | 95% |
| supplier_invoice | 55 | 55 | 0 | 100% |
| create_voucher | 54 | 41 | 13 | 76% |
| credit_note | 52 | 47 | 5 | 90% |
| payroll_voucher | 52 | 50 | 2 | 96% |
| project_invoice | 51 | 49 | 2 | 96% |
| create_supplier | 42 | 41 | 1 | 98% |
| update_employee | 39 | 32 | 7 | 82% |
| dimension_voucher | 33 | 31 | 2 | 94% |
| reverse_payment | 28 | 25 | 3 | 89% |
| delete_employee | 21 | 18 | 3 | 86% |
| delete_travel_expense | 14 | 14 | 0 | 100% |
| update_customer | 12 | 12 | 0 | 100% |
| ledger_analysis | 3 | 3 | 0 | 100% |

## File Format

Each line in `training_data.jsonl` is a JSON object:
```json
{
  "exec_id": "32644",
  "source": "self-hosted",
  "timestamp": "2026-03-22T12:56:43.150Z",
  "task": "Uno de sus clientes tiene una factura vencida. Encuentre la factura vencida y registre un cargo por recordatorio de 40 NOK. Debito cuentas por cobrar (1500), credito ingresos por recordatorio (3400). También cree una factura por la tarifa de recordatorio al cliente y envíela. Además, registre un pago parcial de 5000 NOK en la factura vencida.",
  "task_type": "",
  "params": {},
  "n_files": 0,
  "file_names": [],
  "success": false,
  "n_api_calls": 4,
  "n_ok": 0,
  "n_errors": 4,
  "exec_status": "success"
}
```
