# ClaimSense retrieval report

Generated 2026-11-23 11:30 UTC.

Retrieval mode: **azure_hybrid** (queries-v2). Questions: **40**. Hit@1: **95.0%**. Hit@3: **100.0%**.

Hit@1 = the expected policy clause was the top result. Hit@3 = it was in the top three.
Previous run (queries-v1, Azure hybrid): hit@1 77.5%, hit@3 97.5%. Local keyword baseline: 77.5% / 95.0%.
Note: queries-v2 was written after looking at the v1 misses, so its score is optimistic on this test set.

| Rule | Product | Expected | Retrieved (top 3) | Top-1 correct |
|---|---|---|---|---|
| POLICY_PERIOD | MOTOR | GEN-1 | GEN-1, MTR-3, GEN-5 | yes |
| POLICY_PERIOD | HEALTH | GEN-1 | GEN-1, HLT-2, GEN-5 | yes |
| POLICY_PERIOD | PROPERTY | GEN-1 | GEN-1, PRP-2, GEN-6 | yes |
| EARLY_CLAIM | MOTOR | MTR-3 | GEN-1, MTR-3, GEN-2 | no |
| EARLY_CLAIM | HEALTH | HLT-2 | HLT-2, GEN-1, GEN-2 | yes |
| EARLY_CLAIM | PROPERTY | PRP-2 | PRP-2, GEN-1, GEN-2 | yes |
| LATE_REPORTING | MOTOR | GEN-2 | GEN-2, MTR-3, GEN-5 | yes |
| LATE_REPORTING | HEALTH | GEN-2 | GEN-2, GEN-5, HLT-2 | yes |
| LATE_REPORTING | PROPERTY | GEN-2 | GEN-2, PRP-2, GEN-6 | yes |
| OVER_SUM_INSURED | MOTOR | GEN-3 | GEN-3, GEN-4, GEN-2 | yes |
| OVER_SUM_INSURED | HEALTH | GEN-3 | GEN-3, GEN-4, GEN-6 | yes |
| OVER_SUM_INSURED | PROPERTY | GEN-3 | GEN-3, GEN-4, GEN-5 | yes |
| AMOUNT_MISMATCH | MOTOR | GEN-4 | GEN-4, GEN-6, GEN-3 | yes |
| AMOUNT_MISMATCH | HEALTH | GEN-4 | GEN-4, GEN-6, GEN-3 | yes |
| AMOUNT_MISMATCH | PROPERTY | GEN-4 | GEN-4, GEN-6, GEN-3 | yes |
| MISSING_DOCUMENT | MOTOR | MTR-1 | MTR-1, GEN-6, GEN-4 | yes |
| MISSING_DOCUMENT | HEALTH | HLT-1 | HLT-1, GEN-6, GEN-4 | yes |
| MISSING_DOCUMENT | PROPERTY | PRP-1 | PRP-1, GEN-6, GEN-4 | yes |
| NAME_MISMATCH | MOTOR | GEN-5 | GEN-5, GEN-3, GEN-1 | yes |
| NAME_MISMATCH | HEALTH | GEN-5 | GEN-5, GEN-3, GEN-1 | yes |
| NAME_MISMATCH | PROPERTY | GEN-5 | GEN-3, GEN-5, PRP-1 | no |
| POLICY_NUMBER_MISMATCH | MOTOR | GEN-5 | GEN-5, GEN-6, GEN-4 | yes |
| POLICY_NUMBER_MISMATCH | HEALTH | GEN-5 | GEN-5, GEN-6, HLT-1 | yes |
| POLICY_NUMBER_MISMATCH | PROPERTY | GEN-5 | GEN-5, PRP-1, GEN-6 | yes |
| DATE_MISMATCH | MOTOR | GEN-5 | GEN-5, GEN-2, GEN-6 | yes |
| DATE_MISMATCH | HEALTH | GEN-5 or HLT-3 | HLT-3, GEN-5, GEN-1 | yes |
| DATE_MISMATCH | PROPERTY | GEN-5 | GEN-5, GEN-2, PRP-1 | yes |
| DUPLICATE_DOCUMENT | MOTOR | GEN-6 | GEN-6, GEN-4, MTR-1 | yes |
| DUPLICATE_DOCUMENT | HEALTH | GEN-6 | GEN-6, HLT-1, GEN-4 | yes |
| DUPLICATE_DOCUMENT | PROPERTY | GEN-6 | GEN-6, PRP-1, GEN-4 | yes |
| DUPLICATE_INVOICE | MOTOR | GEN-6 | GEN-6, GEN-4, MTR-1 | yes |
| DUPLICATE_INVOICE | HEALTH | GEN-6 | GEN-6, HLT-1, GEN-4 | yes |
| DUPLICATE_INVOICE | PROPERTY | GEN-6 | GEN-6, PRP-1, GEN-4 | yes |
| SHARED_PHONE | MOTOR | GEN-7 | GEN-7, GEN-6, MTR-1 | yes |
| SHARED_PHONE | HEALTH | GEN-7 | GEN-7, GEN-6, HLT-1 | yes |
| SHARED_PHONE | PROPERTY | GEN-7 | GEN-7, GEN-6, PRP-1 | yes |
| SHARED_VEHICLE | MOTOR | GEN-7 or MTR-2 | MTR-2, GEN-7, MTR-1 | yes |
| PROVIDER_CLUSTER | MOTOR | GEN-7 | GEN-7, MTR-3, GEN-6 | yes |
| PROVIDER_CLUSTER | HEALTH | GEN-7 | GEN-7, GEN-6, HLT-1 | yes |
| PROVIDER_CLUSTER | PROPERTY | GEN-7 | GEN-7, GEN-6, PRP-1 | yes |
