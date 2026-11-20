"""End-to-end verification: extract (AI) -> build graph -> deterministic rules -> risk score.
One trace ID covers the whole request."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Claim, Document, Extraction, Finding, TraceEvent
from ..observability import StageRecorder, current_trace_id, log_event, tracer
from .extraction import extract_document
from .graph import build_claim_graph, shared_identifiers
from .rules import ClaimContext, evaluate, score


def _latest_valid(db: Session, document_id: int) -> Extraction | None:
    return db.scalar(select(Extraction).where(Extraction.document_id == document_id, Extraction.is_valid)
                     .order_by(Extraction.extraction_id.desc()).limit(1))


def _valid_extractions(db: Session, claim: Claim) -> list[Extraction]:
    return [e for d in claim.documents if (e := _latest_valid(db, d.document_id))]


def process_claim(db: Session, claim: Claim) -> dict:
    with tracer.start_as_current_span("claim.process") as span:
        span.set_attribute("claimsense.claim_id", claim.claim_id)
        trace_id = current_trace_id()
        runs = []
        for doc in claim.documents:
            if _latest_valid(db, doc.document_id) is None:
                runs.append(extract_document(db, claim, doc, trace_id))
        db.refresh(claim)

        rec = StageRecorder(trace_id)
        with rec.stage("graph.build"):
            exts = _valid_extractions(db, claim)
            build_claim_graph(db, claim, exts)
        with rec.stage("rules.evaluate"):
            fields = [e.fields for e in exts]
            hashes = [d.sha256 for d in claim.documents]
            dup_docs = db.scalars(select(Claim.claim_number).join(Document)
                                  .where(Document.sha256.in_(hashes), Claim.claim_id != claim.claim_id)).all()
            dup_inv = set()
            for f in fields:
                if f.get("invoice_number"):
                    for other in db.scalars(select(Extraction).join(Document)
                                            .where(Document.claim_id != claim.claim_id, Extraction.is_valid)):
                        of = other.fields
                        if (of.get("invoice_number") == f["invoice_number"]
                                and (of.get("provider_name") or "").lower() == (f.get("provider_name") or "").lower()):
                            dup_inv.add(other.document.claim.claim_number)
            ctx = ClaimContext(
                claim_number=claim.claim_number, claim_type=claim.claim_type,
                policy_number=claim.policy.policy_number, policy_start=claim.policy.start_date,
                policy_end=claim.policy.end_date, sum_insured=float(claim.policy.sum_insured),
                claimant_name=claim.claimant.full_name, incident_date=claim.incident_date,
                reported_date=claim.reported_date, claimed_amount=float(claim.claimed_amount),
                doc_types={d.doc_type for d in claim.documents}, extractions=fields,
                duplicate_docs=sorted(set(dup_docs)), duplicate_invoices=sorted(dup_inv),
                shared_ids=shared_identifiers(db, claim))
            hits = evaluate(ctx)
        with rec.stage("db.save_findings"):
            claim.findings.clear()
            for h in hits:
                claim.findings.append(Finding(rule_code=h.rule_code, severity=h.severity,
                                              message=h.message, evidence=h.evidence))
            claim.risk_score, claim.risk_level = score(hits)
            claim.status = "VALIDATED" if claim.risk_level == "LOW" else "NEEDS_REVIEW"
        for ev in rec.events:
            db.add(TraceEvent(**ev))
        db.commit()
        log_event("claim_processed", trace_id=trace_id, claim_id=claim.claim_id, risk_score=claim.risk_score,
                  risk_level=claim.risk_level, findings=len(hits), failed_runs=sum(r.status == "FAILED" for r in runs))
        return {
            "claim_id": claim.claim_id, "trace_id": trace_id, "risk_score": claim.risk_score,
            "risk_level": claim.risk_level, "status": claim.status,
            "runs": [{"run_id": r.run_id, "document_id": r.document_id, "status": r.status,
                      "error_type": r.error_type, "latency_ms": r.latency_ms} for r in runs],
            "findings": [{"rule_code": h.rule_code, "severity": h.severity, "message": h.message,
                          "evidence": h.evidence} for h in hits],
            "missing_extractions": len(claim.documents) - len(exts),
        }
