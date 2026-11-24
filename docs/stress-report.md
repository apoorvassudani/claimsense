# ClaimSense held-out stress test

Generated 2026-11-23 13:40 UTC in 1505s. Extraction: azure:gpt-4.1-mini. OCR: vision:gpt-4.1-mini.

This data was **never used to tune** prompts or retrieval queries: new seed, new people and provider names, messier document layouts, scans, and a realistic fraud rate. Development-set results for comparison: 100% extraction, 100% routing.

**Fresh test set (seed 8128).** The scan-misread handling was added after the first held-out run (seed 7310: 8 of 132 clean claims wrongly sent to review, review-queue precision 55.6%, no problems missed). This set was generated afterwards and never looked at before this run.

Seed: **8128**. Documents: **351**. Layout changes applied: noise lines 351, relabelled 284, typos 150, separators 102, leaders 98, lost line breaks 67, all caps 34, missing label 13.

## Extraction by how the document arrived

| Source | Documents | Field accuracy | OCR text match |
|---|---|---|---|
| text | 307 | 99.3% | - |
| scan-light | 21 | 100.0% | 99.8% |
| scan-medium | 11 | 99.1% | 99.6% |
| scan-heavy | 12 | 88.3% | 88.9% |

## Extraction by layout change (a document can have several)

| Change | Documents | Field accuracy |
|---|---|---|
| missing label | 13 | 98.5% |
| typos | 150 | 98.5% |
| relabelled | 284 | 98.7% |
| separators | 102 | 98.8% |
| noise lines | 351 | 98.9% |
| leaders | 98 | 99.0% |
| lost line breaks | 67 | 99.1% |
| all caps | 34 | 99.7% |

## Reviewer workload at a realistic fraud rate

- Claims: **140**; with a real problem that needs review: **10** (7.1%).
- Sent to review: **10** (7.1% of the queue).
- Of those, real problems: **10** (review-queue precision 100.0%); problems missed: **0**.

## OCR ladder (same 10 documents, three scan qualities)

| Scan quality | OCR text match | Field accuracy |
|---|---|---|
| light | 99.8% | 98.0% |
| medium | 99.6% | 94.0% |
| heavy | 97.2% | 85.0% |

Light: slight tilt and blur. Medium: more tilt, noise, specks, uneven lighting, 60% resolution, JPEG artefacts. Heavy: strong tilt and noise, dark shadow, many specks, 45% resolution, heavy compression.

## AI field extraction

Documents scored: **351** (failed/unread: 0, read by mock and skipped: 0).
Overall field accuracy: **98.9%**.

| Field | Accuracy | Invented values* |
|---|---|---|
| document_type | 100.0% | 0 |
| policy_number | 98.9% | 0 |
| claimant_name | 100.0% | 0 |
| incident_date | 100.0% | 0 |
| document_date | 92.3% | 25 |
| amount | 99.7% | 0 |
| invoice_number | 99.4% | 0 |
| provider_name | 100.0% | 0 |
| vehicle_registration | 98.9% | 0 |
| phone | 100.0% | 0 |

*a value returned for a field that is not in the document.

First extraction differences:

- HLD-2025-00001_3_police_report.txt: document_date expected None, got '2025-04-05'
- HLD-2025-00006_1_claim_form.jpg: policy_number expected 'NW/PRP/2024/000111', got 'MX/PRP/2024/000111'
- HLD-2025-00011_3_police_report.txt: document_date expected None, got '2025-05-17'
- HLD-2025-00017_3_police_report.txt: document_date expected None, got '2025-06-19'
- HLD-2025-00021_3_police_report.jpg: document_date expected None, got '2025-07-11'
- HLD-2025-00021_3_police_report.jpg: vehicle_registration expected 'MH 02 ZY 2749', got 'MH 02 TX 2749'
- HLD-2025-00022_3_police_report.txt: document_date expected None, got '2025-07-13'
- HLD-2025-00025_3_police_report.txt: document_date expected None, got '2025-07-21'
- HLD-2025-00033_2_invoice.jpg: document_date expected '2025-08-22', got '2025-09-22'
- HLD-2025-00033_2_invoice.jpg: vehicle_registration expected 'TG 07 ZW 4304', got 'TG 07 ZX 4304'
- HLD-2025-00034_3_police_report.txt: document_date expected None, got '2025-09-02'
- HLD-2025-00042_3_police_report.txt: document_date expected None, got '2025-10-09'
- HLD-2025-00043_2_invoice.jpg: document_date expected '2025-08-22', got '2025-02-22'
- HLD-2025-00043_2_invoice.jpg: vehicle_registration expected 'TG 07 ZW 4304', got 'TG 07 ZN 4304'
- HLD-2025-00047_3_police_report.txt: document_date expected None, got '2025-10-30'
- HLD-2025-00055_2_medical_bill.jpg: amount expected 107680.0, got '107688'
- HLD-2025-00055_2_medical_bill.jpg: invoice_number expected 'EVB-00037', got 'EMS-00037'
- HLD-2025-00057_3_police_report.txt: document_date expected None, got '2025-12-12'
- HLD-2025-00058_1_claim_form.jpg: policy_number expected 'NW/MTR/2025/000036', got 'NM/MTR/2025/000036'
- HLD-2025-00062_3_police_report.txt: document_date expected None, got '2025-12-27'
- HLD-2026-00068_3_police_report.jpg: document_date expected None, got '2026-01-19'
- HLD-2026-00068_3_police_report.jpg: vehicle_registration expected 'GJ 01 ZW 6913', got 'GJ 01 ZN 6933'
- HLD-2026-00072_3_police_report.txt: document_date expected None, got '2026-01-30'
- HLD-2026-00074_1_claim_form.jpg: policy_number expected 'NW/HLT/2025/000084', got 'NM/HLT/2025/000084'
- HLD-2026-00076_3_police_report.txt: document_date expected None, got '2026-02-09'

## Fraud rules (all claims)

| Rule | Correct | False alarms | Missed | Precision | Recall |
|---|---|---|---|---|---|
| AMOUNT_MISMATCH | 1 | 0 | 0 | 100.0% | 100.0% |
| DUPLICATE_DOCUMENT | 0 | 0 | 2 | n/a | 0.0% |
| DUPLICATE_INVOICE | 2 | 0 | 0 | 100.0% | 100.0% |
| EARLY_CLAIM | 1 | 0 | 0 | 100.0% | 100.0% |
| LATE_REPORTING | 1 | 0 | 0 | 100.0% | 100.0% |
| MISSING_DOCUMENT | 1 | 0 | 0 | 100.0% | 100.0% |
| NAME_MISMATCH | 2 | 0 | 0 | 100.0% | 100.0% |
| OVER_SUM_INSURED | 1 | 0 | 0 | 100.0% | 100.0% |
| POLICY_PERIOD | 1 | 0 | 0 | 100.0% | 100.0% |
| PROVIDER_CLUSTER | 3 | 0 | 0 | 100.0% | 100.0% |
| SHARED_PHONE | 2 | 0 | 0 | 100.0% | 100.0% |
| SHARED_VEHICLE | 0 | 0 | 2 | n/a | 0.0% |

## Review routing

- Claims that should go to review: **10**; routed correctly: **10** (100.0%); missed: **0**.
- Clean claims wrongly sent to review (false alarms): **0** of 130.

Claims whose rules differ from the answer key:

- HLD-2025-00033 [duplicate source: invoice later reused by another claim]: expected ['DUPLICATE_DOCUMENT', 'DUPLICATE_INVOICE', 'SHARED_VEHICLE'], got ['DUPLICATE_INVOICE']
- HLD-2025-00043 [reused invoice file from another claim]: expected ['DUPLICATE_DOCUMENT', 'DUPLICATE_INVOICE', 'NAME_MISMATCH', 'SHARED_VEHICLE'], got ['DUPLICATE_INVOICE', 'NAME_MISMATCH']

Advisory notes (SCAN_UNCLEAR: a scanned value is probably misread; shown to the reviewer, not counted as a rule hit and never routes a claim on its own): **3** claims (HLD-2025-00006, HLD-2025-00058, HLD-2026-00074).

## Reviewer briefings (RAG generation)

Flagged claims: **15**; with a briefing: **15**. Attempts: **15**, succeeded: **15** (100.0%).
- Grounding: every succeeded briefing passed the citation check (only clauses that retrieval returned). Rejected for ungrounded citations: **0**.
- Coverage: findings supported by a cited clause: **100.0%** (18/18).
- Correct clause cited (vs. retrieval answer key): **100.0%**.
- Median briefing latency: **2997 ms**.
