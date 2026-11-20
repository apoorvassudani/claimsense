# ClaimSense frontend (Day 33)

React + Vite app, to be built on Day 33. Planned screens:

1. **Claims queue**: list with risk level/status filters (`GET /claims`)
2. **Claim detail**: documents, extracted fields, findings with evidence (`GET /claims/{id}`, `/extractions`)
3. **Upload & process**: upload documents, run verification, show trace ID (`POST /documents`, `/process`)
4. **Fraud graph explorer**: claim → shared identifiers → other claims (`GET /graph/claims/{id}`)
5. **Observability dashboard + trace explorer**: metrics, alerts, run list, stage timeline (`/observability/*`)

The frontend never calls the AI provider directly and never holds API keys.
