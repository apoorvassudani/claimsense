# Day 31: Define & Design

## 1. Problem statement
Insurance claims arrive with several supporting documents (claim form, repair invoice, police report, medical bill).
Checking them by hand is slow, inconsistent and misses cross-claim patterns such as the same invoice used twice or
several "unrelated" claimants who share one phone number and one garage.

**ClaimSense** is a synthetic-data portal that (1) ingests claim documents, (2) uses a hosted LLM to extract
structured fields, (3) runs **deterministic** validation and fraud-flag rules, including a relationship graph across
claims, and (4) gives a human reviewer an explainable risk score with evidence. Every AI call is traced, timed,
logged and reviewable.

> ClaimSense **flags** claims for human review. It never approves, rejects or pays a claim, and it uses only
> fictional data.

## 2. User roles
| Role | Responsibilities |
|---|---|
| **Claims analyst** | Create claims, upload documents, run verification, read findings and extracted fields |
| **Fraud reviewer (SIU)** | Investigate HIGH/MEDIUM claims, explore the relationship graph, record decision (clear / escalate / request info) and rate AI output |
| **Ops / model reviewer** | Monitor AI runs, failures, p95 latency, alerts; drill into traces |

## 3. MVP scope
**In:** claim + document CRUD, text/PDF ingestion, LLM field extraction with Pydantic validation, 14 deterministic
rules, risk score, Postgres-backed relationship graph, trace/log/metrics endpoints, seed data, failure simulation,
React UI (Day 33).

**Out (post-MVP):** OCR for scanned images, ML fraud model, real policy-admin integration, payments, auth/SSO,
production monitoring stack.

## 4. User stories & acceptance criteria
| # | Story | Acceptance criteria |
|---|---|---|
| US1 | As an analyst I create a claim against an existing policy | Invalid amount/dates rejected with 422; claim type must match policy product; audit event written |
| US2 | As an analyst I upload claim documents | Only .txt/.pdf/.md ≤ 5 MB; SHA-256 stored; empty or unreadable files rejected |
| US3 | As an analyst I run verification | Each document gets an AI run with run ID + trace ID; extracted fields pass Pydantic schema or run is FAILED |
| US4 | As a reviewer I see why a claim is flagged | Each finding shows rule code, severity, message and evidence; score is computed by rules, not the LLM |
| US5 | As a reviewer I explore links between claims | Graph shows claim → phone/address/provider/vehicle → other claims; phone/address masked |
| US6 | As ops I see AI health | Metrics show total, failed, error rate, p95 latency; alert when ≥3 of last 10 fail or a call > 5 s |
| US7 | As ops I debug one request | Trace view lists stages (read → inference → validation → save → graph → rules) with timing and status |
| US8 | As ops I confirm failures are isolated | Simulated timeout gives FAILED run + log; claim data unchanged; retry works |
| US9 | As a reviewer I record a decision and AI feedback | Decision + helpful flag + comment saved against claim and run (Day 34+) |

## 5. Architecture
See [02-architecture.md](02-architecture.md).

## 6. Technology decisions
| Decision | Choice | Why |
|---|---|---|
| Frontend | React + Vite | Mandatory stack; fast dev server |
| Backend | FastAPI + Pydantic v2 + SQLAlchemy 2 | Mandatory; typed validation of inputs and LLM outputs |
| Database | PostgreSQL 16 | Mandatory; relational integrity + JSON columns for extracted fields |
| Graph | Node/edge tables **inside PostgreSQL** | Keeps the mandatory 3-layer stack; 2-hop queries are enough for MVP. Neo4j is a possible stretch goal |
| AI | Option A: OpenAI gpt-oss-20b hosted on Groq (free tier) via OpenAI-compatible API; Azure OpenAI planned; `mock` provider for offline tests | No local models; one client, swappable provider |
| AI role | Extraction only | Scores and decisions must be deterministic and auditable |
| Tracing | OpenTelemetry SDK, console exporter + `trace_events` table | Trace explorer works without paid tooling |
| Logging | JSON Lines, secrets/doc text blocked | Searchable, safe |
| Tests | pytest + SQLite in-memory | Runs in CI without Postgres |

## 7. Repository & README outline
See the root [README.md](../README.md).
