# ClaimSense frontend

React 18 + Vite. Talks only to the ClaimSense FastAPI backend; it never calls the AI provider and holds no keys.

## Run it
Requires Node.js 18 or newer (`node --version`). With the backend running on port 8000:
```bash
cd frontend
npm install        # first time only
npm run dev        # http://localhost:5173
```
The API address defaults to `http://localhost:8000`. To change it, copy `.env.example` to `.env` and edit
`VITE_API_URL`.

## Screens
| Screen | What it does | API |
|---|---|---|
| Claims queue | All claims with risk, status and red flags; filter by risk, status, type; search; sort | `GET /claims` |
| Claim file | Findings with evidence, documents next to what the AI read, claim and policy facts, risk score, AI activity, reviewer decision and history | `GET /claims/{id}`, `/extractions`, `/documents/{id}`, `/reviews`, `POST /process`, `POST /reviews` |
| New claim | Three steps: claim details, upload documents, run verification | `GET /claimants`, `/policies`, `POST /claims`, `/documents`, `/process` |
| Fraud graph | Interactive graph of a claim, its identifiers and other claims that share them | `GET /graph/claims/{id}` |
| Monitoring | AI calls, error rate, p95 latency, alerts, feedback, latency chart, filterable call list | `GET /observability/metrics`, `/runs` |
| Trace | Stage-by-stage timeline of one AI call and of the whole request | `GET /observability/runs/{id}`, `/traces/{id}` |

## States
Every screen handles loading, empty data, validation errors and an unreachable backend. When the AI fails during
verification, the claim screen says how many documents couldn't be read and why, confirms the claim data is
unchanged, and links to the trace.

## Structure
```
src/
  api.js           fetch wrapper, error messages, useApi hook
  format.js        currency/date formatting and plain-English labels
  claimsIndex.jsx  shared claim list (claim number -> link)
  components/      badges, loading/empty/error states, stage timeline
  pages/           one file per screen
  styles.css       design tokens and layout
```
