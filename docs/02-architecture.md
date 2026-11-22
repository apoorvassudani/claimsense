# Architecture

```mermaid
flowchart LR
    UI["React UI<br/>claims · graph · observability"] -->|REST + X-Trace-Id| API
    subgraph API["FastAPI"]
        R[Routers + Pydantic] --> P[Pipeline]
        P --> X[Extraction service]
        P --> G[Graph service]
        P --> RU[Rules engine]
        O[OpenTelemetry + JSON logs]
    end
    X -->|synthetic text only| LLM["OpenAI gpt-oss-20b<br/>via Groq"]
    API --> DB[("PostgreSQL<br/>claims · documents · extractions<br/>findings · graph · ai_runs · trace_events")]
```

## Verification sequence (one trace ID throughout)

```mermaid
sequenceDiagram
    participant UI as React
    participant API as FastAPI
    participant DB as PostgreSQL
    participant LLM as Hosted LLM
    UI->>API: POST /claims/{id}/process
    Note over API: span HTTP POST, trace_id created
    loop each un-extracted document
        API->>DB: db.read_document
        API->>LLM: ai.inference (doc text, prompt v1)
        LLM-->>API: JSON fields
        API->>API: output.validation (Pydantic)
        API->>DB: db.save_extraction + ai_run + trace_events
    end
    API->>DB: graph.build (nodes/edges)
    API->>API: rules.evaluate (14 deterministic rules)
    API->>DB: db.save_findings, risk score
    API-->>UI: findings, risk, run IDs, trace_id (+ X-Trace-Id header)
```

If the LLM times out, hits quota or returns junk, the run is stored as FAILED with an error category, and the
rules still run on whatever was extracted. Claim records are never modified by the AI step.
