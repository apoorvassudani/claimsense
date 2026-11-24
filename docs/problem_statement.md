# ClaimSense: Problem Statement

## Users

| User | What they do in ClaimSense |
|---|---|
| **Claims intake staff** | Enter new claims, upload the customer's documents (text, PDF, scans or photos) and run verification. |
| **Claims reviewers** | Review flagged claims, read the AI briefing and evidence, and record the decision (clear, escalate or request more information). |
| **Operations / model reviewers (admin)** | Monitor AI quality and reliability: traces, error rates, latency, alerts and reviewer feedback. |

## Business problem

Insurance claims arrive with several supporting documents: a claim form, invoices or hospital bills, and police reports.
Today, staff check these by hand, comparing names, policy numbers, dates and amounts across documents and against the
policy, and trying to remember whether an invoice or phone number has appeared on another claim.

This causes three problems:

- **It is slow and inconsistent.** Each claim takes manual effort, and two reviewers may check different things.
- **Fraud slips through.** Reused invoices, inflated amounts, claims outside the policy period and organised rings
  (several claimants sharing a phone number or garage) are hard to spot one claim at a time.
- **Decisions are hard to explain.** When a claim is questioned, it is not always clear which policy rule applies or
  why it was flagged.

## Proposed solution

ClaimSense is an internal web application that verifies claim documents and flags possible fraud for human review.

1. **Read:** OCR turns scans and photos into text (Azure Document Intelligence, or GPT-4.1-mini vision), and Azure
   OpenAI GPT-4.1-mini extracts structured fields from every document, validated with Pydantic.
2. **Check:** 14 deterministic rules compare the claim, its documents, the policy and other claims (via a relationship
   graph) and produce an explainable risk score. Medium and high risk claims go to a reviewer.
3. **Explain (RAG):** For each red flag, Azure AI Search retrieves the matching policy clause using hybrid vector and
   keyword search, and GPT-4.1-mini writes a short reviewer briefing that cites those clauses. Any briefing citing a
   clause that search did not return is rejected.
4. **Decide:** A signed-in reviewer records the decision. Every action is audited under the reviewer's identity.
5. **Observe:** Every AI call is traced, timed and logged, with metrics, alerts and reviewer feedback on AI quality.

**Core principle: the AI reads and explains; plain code scores; a human decides.**

## Scope

### In scope

- Motor, health and property claims on synthetic data
- Document upload: text, PDF, and scans or photos via OCR
- AI field extraction with schema validation
- 14 fraud and validation rules, a cross-claim fraud graph, and risk scoring
- RAG reviewer briefings grounded in policy wording, with citation checks
- Human review workflow with feedback on AI accuracy
- Sign-in with three roles (intake, reviewer, admin) and an audit trail
- Observability: traces, structured logs, metrics, alerts and failure simulation
- Evaluation against an answer key, plus a held-out stress test

### Out of scope

- Automatic approval, rejection or payment of claims: humans always decide
- Real customer data or real insurer systems
- Live integration with policy administration or payment systems
- Legal or regulatory determinations
- Enterprise single sign-on (Microsoft Entra ID is the production path; the demo uses its own sign-in)
- Real policy wording (the knowledge base is synthetic, modelled on real policies)

## Success criteria

| Criterion | Target | Result |
|---|---|---|
| Field extraction accuracy (development set, 213 documents) | ≥ 95% | **100%** |
| Field extraction on unseen, messy documents (held-out stress test) | ≥ 95% | **98.9%** |
| Planted problems sent to review | 100% | **26 of 26** (development), **10 of 10** (unseen data) |
| Clean claims wrongly sent to review | Low | **0 of 58** (development), **0 of 130** (unseen data) |
| Right policy clause in top 3 search results (hit@3) | ≥ 90% | **97.5%** |
| Briefings citing only retrieved clauses | 100% | **100%** (0 rejected) |
| An AI failure never breaks a claim or corrupts data | Always | Proven by simulated timeout, quota and bad-response tests |
| Every AI call traceable by trace ID, model, duration and status | Always | Yes: trace view, logs and monitoring |
| Automated tests passing | All | **41 of 41** |

All results are on synthetic data. Real-world documents (handwriting, poor photos, unusual layouts) would need
further testing.
