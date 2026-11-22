# ClaimSense: AI-Powered Insurance Claim Document Verification & Fraud Flagging

> Educational capstone project. **All policies, people and documents are synthetic.** ClaimSense flags claims
> for human review; it does not approve, reject or pay claims.

ClaimSense ingests claim documents, uses a hosted LLM to **extract** structured fields, then applies
**deterministic** validation and fraud rules, including a cross-claim relationship graph. Reviewers get a risk
score with evidence. Every AI call is traced, timed and logged.

**Stack:** React · FastAPI + Pydantic · PostgreSQL · OpenAI gpt-oss-20b via Groq (Azure OpenAI planned) · OpenTelemetry

## Architecture
```mermaid
flowchart LR
    UI[React] --> API[FastAPI + OTel] --> DB[(PostgreSQL)]
    API --> LLM[Hosted LLM: extraction only]
```
Details: [docs/02-architecture.md](docs/02-architecture.md) · Design: [docs/01-day31-define-and-design.md](docs/01-day31-define-and-design.md) · Schema & rules: [docs/03-data-and-graph-schema.md](docs/03-data-and-graph-schema.md)

## Repository layout
```
backend/
  app/
    main.py              FastAPI app, trace middleware
    config.py            env-based settings (no secrets in code)
    models.py            SQLAlchemy schema
    schemas.py           Pydantic request/response models
    observability.py     OpenTelemetry, JSON logs, stage recorder
    services/            ingestion · llm · extraction · graph · rules · pipeline
    routers/             claims · observability · graph
    datagen.py           synthetic dataset generator (real places, fictional people)
    seed.py              writes documents, answer key and scans; loads and processes claims
    evaluate.py          accuracy report against the answer key
  tests/                 pytest (rules + API, runs on SQLite)
data/sample_documents/   213 generated synthetic documents (+ scans/ for OCR)
data/ground_truth.json   answer key: expected rules per claim, true field values per document
docs/                    design, architecture, schema
sql/demo_queries.sql     SQL demonstrations
frontend/                React app (Day 33)
```

## Quick start
```bash
docker compose up -d                       # PostgreSQL on :5432
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                    # set LLM_PROVIDER / LLM_API_KEY for a live model
python -m app.seed                         # 84 synthetic claims, processed offline (fast)
uvicorn app.main:app --reload              # http://localhost:8000/docs
pytest -q
```
Use the real model: set `LLM_PROVIDER=openai_compat`, `LLM_API_KEY`, `LLM_BASE_URL` and `LLM_MODEL` in
`backend/.env`, then:
```bash
python -m app.seed --live --limit 15       # real AI on 15 claims (free-tier friendly), offline for the rest
python -m app.seed --live                  # real AI on every document (slow on free tiers)
python -m app.evaluate                     # accuracy vs the answer key -> docs/evaluation-report.md
```

Demo failures: set `SIMULATE_FAILURE=timeout|quota|malformed|slow` and restart the API.

## API
| Method | Route | Purpose |
|---|---|---|
| GET | /health | status + active model |
| GET | /policies | list policies |
| GET / POST | /claims | list (filter `status`, `risk_level`) / create claim |
| GET | /claims/{id} | claim with documents and findings |
| POST | /claims/{id}/documents | upload .txt/.pdf/.md (`doc_type` form field) |
| POST | /claims/{id}/process | extract → graph → rules → risk score (returns `trace_id`) |
| GET | /claims/{id}/extractions | AI-extracted fields per document |
| GET | /graph/claims/{id} | 2-hop relationship graph + shared identifiers |
| GET | /observability/runs | AI runs (filter `status`, `model`, `hours`) |
| GET | /observability/metrics | totals, error rate, p95 latency, alerts |
| GET | /observability/runs/{run_id} | stage events for one AI run |
| GET | /observability/traces/{trace_id} | all stages for one request |

## Dataset
84 synthetic claims and 213 documents set in real Indian cities, with fictional people, businesses and numbers.
About a third carry planted red flags (rings, reused invoices, inflated amounts, policy-period violations), and a
few contain innocent oddities that must not be flagged. Details: [docs/03-data-and-graph-schema.md](docs/03-data-and-graph-schema.md).

## Safety & privacy
- API keys live only in `backend/.env`; the frontend never calls the model.
- Logs never contain document text, phone numbers, addresses or keys.
- The LLM only extracts fields. Risk scores come from rules, and decisions are made by humans.
- Phone numbers and addresses are masked in graph labels.

## Progress
| Day | Deliverable | Status |
|---|---|---|
| 31 | Define & design: problem, roles, MVP, stories, architecture, tech decisions, repo | ✅ |
| 32 | Backend & AI: schema, ingestion, extraction, validation, API foundation, 84-claim dataset + answer key | ✅ |
| 33 | Frontend & integration | ⏳ |
| 34 | Deployment & testing | ⏳ |
