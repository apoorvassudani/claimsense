# ClaimSense evaluation report

Generated 2026-11-22 17:15 UTC. Models scored: openai_compat:openai/gpt-oss-20b.

## AI field extraction

Documents scored: **40** (failed/unread: 0, read by mock and skipped: 173).
Overall field accuracy: **96.8%**.

| Field | Accuracy | Invented values* |
|---|---|---|
| document_type | 100.0% | 0 |
| policy_number | 100.0% | 0 |
| claimant_name | 100.0% | 0 |
| incident_date | 95.0% | 0 |
| document_date | 75.0% | 8 |
| amount | 97.5% | 0 |
| invoice_number | 100.0% | 0 |
| provider_name | 100.0% | 0 |
| vehicle_registration | 100.0% | 0 |
| phone | 100.0% | 0 |

*a value returned for a field that is not in the document.

First extraction differences:

- CLM-2025-00033_2_medical_bill.txt: incident_date expected '2025-12-10', got None
- CLM-2025-00033_2_medical_bill.txt: document_date expected '2025-12-14', got None
- CLM-2026-00038_3_police_report.txt: document_date expected None, got '2026-01-25'
- CLM-2026-00044_2_invoice.txt: amount expected 134284.0, got '133284.0'
- CLM-2026-00051_3_police_report.txt: document_date expected None, got '2026-03-26'
- CLM-2026-00053_3_police_report.txt: document_date expected None, got '2026-04-15'
- CLM-2026-00054_3_police_report.txt: document_date expected None, got '2026-04-23'
- CLM-2026-00058_2_medical_bill.txt: incident_date expected '2026-05-08', got None
- CLM-2026-00058_2_medical_bill.txt: document_date expected '2026-05-12', got None
- CLM-2026-00069_3_police_report.txt: document_date expected None, got '2026-06-15'
- CLM-2026-00070_3_police_report.txt: document_date expected None, got '2026-06-18'
- CLM-2026-00075_3_police_report.txt: document_date expected None, got '2026-06-29'
- CLM-2026-00083_3_police_report.txt: document_date expected None, got '2026-09-09'

## Fraud rules (15 claims read entirely by the live model)

| Rule | Correct | False alarms | Missed | Precision | Recall |
|---|---|---|---|---|---|
| AMOUNT_MISMATCH | 3 | 0 | 0 | 100.0% | 100.0% |
| DUPLICATE_DOCUMENT | 1 | 0 | 0 | 100.0% | 100.0% |
| DUPLICATE_INVOICE | 2 | 0 | 0 | 100.0% | 100.0% |
| EARLY_CLAIM | 1 | 0 | 0 | 100.0% | 100.0% |
| LATE_REPORTING | 1 | 0 | 0 | 100.0% | 100.0% |
| MISSING_DOCUMENT | 1 | 0 | 0 | 100.0% | 100.0% |
| PROVIDER_CLUSTER | 1 | 0 | 0 | 100.0% | 100.0% |
| SHARED_PHONE | 1 | 0 | 0 | 100.0% | 100.0% |
| SHARED_VEHICLE | 3 | 0 | 0 | 100.0% | 100.0% |

## Review routing

- Claims that should go to review: **8**; routed correctly: **8** (100.0%); missed: **0**.
- Clean claims wrongly sent to review (false alarms): **0** of 7.
