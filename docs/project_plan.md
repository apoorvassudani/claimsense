# ClaimSense: Project Plan

## Milestones

| Day | Goal | Delivered | Status |
|---|---|---|---|
| 31 | Define and design | Problem statement, users, MVP scope, architecture, stack, data model, synthetic dataset design | Done |
| 32 | Backend and AI | FastAPI + Pydantic, PostgreSQL schema, AI extraction with validation, 14 rules, fraud graph, tracing and JSON logs, failure simulation, seed data | Done |
| 33 | Frontend and integration | React screens (claims queue, new claim, claim detail, fraud graph, monitoring, trace view) wired to the API | Done |
| 34 | Azure, testing, deployment | Switch to Azure OpenAI; RAG with Azure AI Search; OCR (vision, Document Intelligence ready); sign-in and roles; evaluation, held-out stress test and fix; deployment to Azure | Deployment in progress |

### Evidence-driven iterations

| Change | Trigger (evidence) | Result |
|---|---|---|
| Extraction prompt v1 → v2 | Evaluation: hospital and claim-form dates returned empty (89% / 80%) | Both date fields 100%; also found 18 wrong labels in the answer key |
| Prompt v2 → v3 | Evaluation: police stations returned as "providers" (85.4%) | 100% extraction on 213 documents |
| Retrieval queries v1 → v2 | Retrieval report: hit@1 77.5% (generic wording pulled the wrong clause) | Right clause in top 3 for 97.5%; briefings cite the correct clause 100% |
| Reviewer briefing (RAG generation) | Retrieval alone is not full RAG | 29/29 grounded briefings, 0 rejected citations |
| Scan-misread handling | Stress test (seed 7310): OCR misreads on heavy scans sent 8 clean claims to review (queue precision 55.6%) | Fresh test (seed 8128): 0 false alarms, 100% precision, nothing missed |

## Team roles

Fill in names. Every member should be able to explain the end-to-end flow.

| Member | Role | Owns |
|---|---|---|
| _name_ | Architecture & integration | Architecture, pipeline, repository, integration between components |
| _name_ | Backend | FastAPI routes, schemas, database, rules engine, auth |
| _name_ | AI / LLM | Prompts, extraction, OCR, RAG (embeddings, AI Search, briefings), evaluation |
| _name_ | Frontend | React screens and user journeys per role |
| _name_ | DevOps & QA | Tests, CI, Docker, Azure deployment, stress test |

## Risks and mitigations

| Risk | Impact | Mitigation | Status |
|---|---|---|---|
| AI returns wrong or invented values | Wrong flags | Pydantic validation; "use null, never guess" prompt; evaluation against an answer key; AI never scores | Measured: 100% dev, 98.9% unseen |
| AI provider timeout, quota or outage | Claims stuck | Failure isolation, retries on next run, FAILED runs logged, alerts (3 of 10 failed, > 5 s) | Tested with simulated failures |
| Made-up policy citations | Misleading briefings | Citation check rejects any clause search did not return | 0 rejected in all runs |
| Results tuned to the test data | Overstated accuracy | Held-out stress test with new seed, messy layouts, scans and realistic fraud rate; final check on a never-seen seed | Done |
| OCR misreads on poor scans | False alarms / missed links | Register-checked SCAN_UNCLEAR advisory; Document Intelligence confidence scores (next) | False alarms fixed; missed links documented |
| Secrets leaked | Account misuse | Keys only in backend `.env` / cloud settings; git-ignored; nothing in browser or logs | In place |
| Unauthorised decisions | Untrustworthy audit trail | Sign-in, roles, identity from token, audit events | In place |
| Azure permissions or quota | Deployment blocked | Check permissions first; local demo as backup; record any blocker honestly | To verify at deployment |

## Dependencies

- Azure OpenAI deployments: `gpt-4.1-mini` (chat) and `text-embedding-3-small` (embeddings)
- Azure AI Search (Free tier) with the `policy-clauses` index
- Azure AI Document Intelligence (Free tier), optional; vision OCR works without it
- For deployment: Azure App Service, Azure Static Web Apps, Azure Database for PostgreSQL

## Known limitations and next steps

- Re-scanned copies of the same document are not caught by the exact file fingerprint (the invoice-number rule still
  catches reused invoices): add near-duplicate image detection.
- OCR misreads of identifiers can hide links between claims: add fuzzy, register-checked linking for scanned values.
- Use Document Intelligence per-word confidence to flag uncertain characters directly.
- Replace the synthetic policy wording with real (e.g. IRDAI standard) wording: PDF extraction, section chunking,
  aligning rule thresholds, rebuilding the retrieval answer key.
- Production sign-in through Microsoft Entra ID.
