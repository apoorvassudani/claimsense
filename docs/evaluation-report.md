# ClaimSense evaluation report

Generated 2026-11-23 11:41 UTC. Models scored: azure:gpt-4.1-mini.

## AI field extraction

Documents scored: **213** (failed/unread: 0, read by mock and skipped: 0).
Overall field accuracy: **100.0%**.

| Field | Accuracy | Invented values* |
|---|---|---|
| document_type | 100.0% | 0 |
| policy_number | 100.0% | 0 |
| claimant_name | 100.0% | 0 |
| incident_date | 100.0% | 0 |
| document_date | 100.0% | 0 |
| amount | 100.0% | 0 |
| invoice_number | 100.0% | 0 |
| provider_name | 100.0% | 0 |
| vehicle_registration | 100.0% | 0 |
| phone | 100.0% | 0 |

*a value returned for a field that is not in the document.

## Fraud rules (all claims)

| Rule | Correct | False alarms | Missed | Precision | Recall |
|---|---|---|---|---|---|
| AMOUNT_MISMATCH | 5 | 0 | 0 | 100.0% | 100.0% |
| DATE_MISMATCH | 1 | 0 | 0 | 100.0% | 100.0% |
| DUPLICATE_DOCUMENT | 2 | 0 | 0 | 100.0% | 100.0% |
| DUPLICATE_INVOICE | 4 | 0 | 0 | 100.0% | 100.0% |
| EARLY_CLAIM | 2 | 0 | 0 | 100.0% | 100.0% |
| LATE_REPORTING | 2 | 0 | 0 | 100.0% | 100.0% |
| MISSING_DOCUMENT | 3 | 0 | 0 | 100.0% | 100.0% |
| NAME_MISMATCH | 2 | 0 | 0 | 100.0% | 100.0% |
| OVER_SUM_INSURED | 2 | 0 | 0 | 100.0% | 100.0% |
| POLICY_NUMBER_MISMATCH | 1 | 0 | 0 | 100.0% | 100.0% |
| POLICY_PERIOD | 2 | 0 | 0 | 100.0% | 100.0% |
| PROVIDER_CLUSTER | 7 | 0 | 0 | 100.0% | 100.0% |
| SHARED_PHONE | 5 | 0 | 0 | 100.0% | 100.0% |
| SHARED_VEHICLE | 4 | 0 | 0 | 100.0% | 100.0% |

## Review routing

- Claims that should go to review: **26**; routed correctly: **26** (100.0%); missed: **0**.
- Clean claims wrongly sent to review (false alarms): **0** of 58.

## Reviewer briefings (RAG generation)

Flagged claims: **29**; with a briefing: **29**. Attempts: **29**, succeeded: **29** (100.0%).
- Grounding: every succeeded briefing passed the citation check (only clauses that retrieval returned). Rejected for ungrounded citations: **0**.
- Coverage: findings supported by a cited clause: **100.0%** (42/42).
- Correct clause cited (vs. retrieval answer key): **100.0%**.
- Median briefing latency: **2716 ms**.
