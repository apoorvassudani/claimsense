"""Generation half of RAG: write a reviewer briefing grounded in the rule findings and retrieved clauses.

  Retrieve : policy_rag finds the top policy clauses for every rule that fired (Azure AI Search, hybrid)
  Augment  : findings + those clauses go into the prompt
  Generate : the model explains the findings in plain English and cites clause IDs like [GEN-2]
  Check    : every cited clause must be one that retrieval actually returned; otherwise the briefing is
             rejected (status FAILED, error "ungrounded_citation") and nothing is shown

The briefing never changes the risk score or the claim status. Those still come from the rules,
and the decision stays with the reviewer.
"""
import hashlib
import json
import re
from time import perf_counter

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AIRun, Claim, ReviewerSummary, TraceEvent
from ..observability import StageRecorder, log_event
from . import llm

PROMPT_VERSION = "summary-v1"
CITATION = re.compile(r"\[([A-Z]{3}-\d+)\]")

SYSTEM_PROMPT = """You write a short briefing for a human insurance claim reviewer.
You are given the rule findings for one synthetic claim and policy clauses retrieved from the policy wording.
Use ONLY this information. Do not decide whether the claim is fraudulent, do not recommend approving or
rejecting it, and do not mention or change any score.
Explain in plain English why each finding matters, and support it by citing the relevant policy clause as
[CLAUSE-ID], for example [GEN-2]. Cite only clause IDs from the list you are given. If none of the given
clauses supports a finding, say that no clause was found for it.
Return ONLY a JSON object with these keys:
summary (string, 3 to 6 sentences),
next_steps (list of 1 to 4 short actions the reviewer could take to verify the findings),
citations (list of the clause IDs you cited)."""


class UngroundedCitation(Exception):
    category = "ungrounded_citation"


class Briefing(BaseModel):
    summary: str = Field(min_length=20)
    next_steps: list[str] = []
    citations: list[str] = []


def findings_signature(findings: list[dict]) -> str:
    key = sorted((f["rule_code"], f["message"]) for f in findings)
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()


def build_prompt(claim: Claim, findings: list[dict], clauses_by_rule: dict[str, list[dict]]) -> str:
    lines = [f"Claim {claim.claim_number}, {claim.claim_type.lower()} policy, risk level {claim.risk_level}.", "",
             "Rule findings:"]
    for f in findings:
        ev = {k: v for k, v in f["evidence"].items() if k != "policy_clause"}
        lines.append(f"- {f['rule_code']} ({f['severity']}): {f['message']} Evidence: {json.dumps(ev, default=str)}")
    lines += ["", "Policy clauses retrieved for these findings:"]
    seen = set()
    for hits in clauses_by_rule.values():
        for c in hits:
            if c["clause_id"] not in seen:
                seen.add(c["clause_id"])
                lines.append(f"[{c['clause_id']}] {c['title']}: {c['text']}")
    return "\n".join(lines)


def check_citations(b: Briefing, allowed: set[str]) -> list[str]:
    """All clause IDs the model used anywhere must come from retrieval."""
    used = set(b.citations) | set(CITATION.findall(b.summary))
    for step in b.next_steps:
        used |= set(CITATION.findall(step))
    bad = sorted(used - allowed)
    if bad:
        raise UngroundedCitation(f"cited clauses not retrieved: {bad}")
    return sorted(used)


def _mock_briefing(findings: list[dict], clauses_by_rule: dict[str, list[dict]]) -> str:
    """Offline stand-in for the model: a template built from the same inputs (tests and demos without Azure)."""
    parts, cites = [], []
    for f in findings:
        top = (clauses_by_rule.get(f["rule_code"]) or [None])[0]
        ref = f" [{top['clause_id']}]" if top else ""
        if top:
            cites.append(top["clause_id"])
        parts.append(f"{f['message']}{ref}")
    text = "The rules raised these points for review. " + " ".join(parts)
    return json.dumps({"summary": text, "next_steps": ["Check each flagged document against the claim form."],
                       "citations": sorted(set(cites))})


def latest_summary(db: Session, claim_id: int) -> ReviewerSummary | None:
    return db.scalar(select(ReviewerSummary).where(ReviewerSummary.claim_id == claim_id)
                     .order_by(ReviewerSummary.summary_id.desc()).limit(1))


def summarize_claim(db: Session, claim: Claim, findings: list[dict], clauses_by_rule: dict[str, list[dict]],
                    trace_id: str) -> AIRun | None:
    """Write (or reuse) the briefing for a claim. Returns the AI run, or None if nothing needed doing."""
    if not findings:
        return None
    signature = findings_signature(findings)
    existing = latest_summary(db, claim.claim_id)
    if existing and existing.findings_signature == signature:
        prev = db.get(AIRun, existing.run_id)
        live_now = settings.llm_provider != "mock"
        if not (live_now and prev and prev.model_id.startswith("mock")):
            return None  # same findings: keep the briefing, don't pay for another call

    run = AIRun(claim_id=claim.claim_id, task="SUMMARY", trace_id=trace_id, model_id=settings.model_label,
                prompt_version=PROMPT_VERSION, status="RUNNING")
    db.add(run)
    db.flush()
    rec = StageRecorder(trace_id, run.run_id)
    t0 = perf_counter()
    allowed = {c["clause_id"] for hits in clauses_by_rule.values() for c in hits}
    try:
        with rec.stage("prompt.build"):
            prompt = build_prompt(claim, findings, clauses_by_rule)
        with rec.stage("ai.inference"):
            if settings.llm_provider == "mock":
                if settings.simulate_failure in ("timeout", "quota"):  # failure demos apply offline too
                    llm.complete_json(SYSTEM_PROMPT, prompt, prompt)
                result = llm.LLMResult(text=_mock_briefing(findings, clauses_by_rule), model=settings.model_label)
            else:
                result = llm.complete_json(SYSTEM_PROMPT, prompt, prompt)
        with rec.stage("output.validation"):
            try:
                briefing = Briefing.model_validate(json.loads(result.text))
            except (json.JSONDecodeError, ValidationError) as exc:
                raise llm.LLMMalformed("briefing was not valid JSON") from exc
        with rec.stage("citation.check"):
            cited = check_citations(briefing, allowed)
        with rec.stage("db.save_summary"):
            db.add(ReviewerSummary(
                claim_id=claim.claim_id, run_id=run.run_id, findings_signature=signature,
                summary=briefing.summary, next_steps=briefing.next_steps[:4], citations=cited,
                clauses=[{"rule_code": r, "clause_ids": [c["clause_id"] for c in hits]}
                         for r, hits in clauses_by_rule.items()]))
        run.status = "SUCCESS"
        run.input_tokens, run.output_tokens = result.input_tokens, result.output_tokens
    except Exception as exc:  # isolated: a failed briefing never affects findings or the score
        run.status = "FAILED"
        run.error_type = getattr(exc, "category", "internal_error")
    run.latency_ms = int((perf_counter() - t0) * 1000)
    for ev in rec.events:
        db.add(TraceEvent(**ev))
    db.commit()
    log_event("ai_run", trace_id=trace_id, run_id=run.run_id, claim_id=claim.claim_id, task="SUMMARY",
              model=run.model_id, status=run.status, latency_ms=run.latency_ms, error_category=run.error_type)
    return run
