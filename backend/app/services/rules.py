"""Deterministic validation & fraud-flag rules. Scores come from these rules, never from the LLM."""
from dataclasses import dataclass, field
from datetime import date

WEIGHTS = {"HIGH": 40, "MEDIUM": 20, "LOW": 5}
REQUIRED_DOCS = {"MOTOR": {"CLAIM_FORM", "INVOICE", "POLICE_REPORT"},
                 "HEALTH": {"CLAIM_FORM", "MEDICAL_BILL"},
                 "PROPERTY": {"CLAIM_FORM", "INVOICE"}}


@dataclass
class ClaimContext:
    claim_number: str
    claim_type: str
    policy_number: str
    policy_start: date
    policy_end: date
    sum_insured: float
    claimant_name: str
    incident_date: date
    reported_date: date
    claimed_amount: float
    doc_types: set[str]
    extractions: list[dict]                      # validated ExtractedFields dicts
    duplicate_docs: list[str] = field(default_factory=list)      # other claims with same file hash
    duplicate_invoices: list[str] = field(default_factory=list)  # other claims with same invoice+provider
    shared_ids: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class RuleHit:
    rule_code: str
    severity: str
    message: str
    evidence: dict


def _n(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def evaluate(ctx: ClaimContext) -> list[RuleHit]:
    hits: list[RuleHit] = []
    add = lambda code, sev, msg, ev=None: hits.append(RuleHit(code, sev, msg, ev or {}))

    if not (ctx.policy_start <= ctx.incident_date <= ctx.policy_end):
        add("POLICY_PERIOD", "HIGH", "Incident date is outside the policy period.",
            {"incident": str(ctx.incident_date), "start": str(ctx.policy_start), "end": str(ctx.policy_end)})
    elif (ctx.incident_date - ctx.policy_start).days <= 30:
        add("EARLY_CLAIM", "MEDIUM", "Incident within 30 days of policy start.",
            {"days_after_start": (ctx.incident_date - ctx.policy_start).days})
    if (ctx.reported_date - ctx.incident_date).days > 30:
        add("LATE_REPORTING", "LOW", "Claim reported more than 30 days after incident.",
            {"days": (ctx.reported_date - ctx.incident_date).days})
    if ctx.claimed_amount > ctx.sum_insured:
        add("OVER_SUM_INSURED", "HIGH", "Claimed amount exceeds sum insured.",
            {"claimed": ctx.claimed_amount, "sum_insured": ctx.sum_insured})

    missing = REQUIRED_DOCS.get(ctx.claim_type, set()) - ctx.doc_types
    if missing:
        add("MISSING_DOCUMENT", "LOW", "Required documents missing.", {"missing": sorted(missing)})

    bill_total = sum(float(e["amount"]) for e in ctx.extractions
                     if e.get("document_type") in ("INVOICE", "MEDICAL_BILL") and e.get("amount") is not None)
    if bill_total and abs(bill_total - ctx.claimed_amount) / ctx.claimed_amount > 0.10:
        add("AMOUNT_MISMATCH", "MEDIUM", "Invoice/bill total differs from claimed amount by more than 10%.",
            {"bill_total": round(bill_total, 2), "claimed": ctx.claimed_amount})

    for e in ctx.extractions:
        dt = e.get("document_type")
        if e.get("policy_number") and _n(e["policy_number"]) != _n(ctx.policy_number):
            add("POLICY_NUMBER_MISMATCH", "HIGH", f"{dt} shows a different policy number.",
                {"document": e["policy_number"], "claim": ctx.policy_number})
        if e.get("claimant_name") and _n(e["claimant_name"]) != _n(ctx.claimant_name):
            add("NAME_MISMATCH", "MEDIUM", f"{dt} shows a different claimant name.",
                {"document": e["claimant_name"], "claim": ctx.claimant_name})
        if e.get("incident_date") and e["incident_date"] != str(ctx.incident_date):
            add("DATE_MISMATCH", "MEDIUM", f"{dt} shows a different incident date.",
                {"document": e["incident_date"], "claim": str(ctx.incident_date)})

    if ctx.duplicate_docs:
        add("DUPLICATE_DOCUMENT", "HIGH", "Identical document file already submitted on another claim.",
            {"other_claims": ctx.duplicate_docs})
    if ctx.duplicate_invoices:
        add("DUPLICATE_INVOICE", "HIGH", "Same invoice number and provider used on another claim.",
            {"other_claims": ctx.duplicate_invoices})
    for ident, others in ctx.shared_ids.items():
        if len(others) >= 2:
            add("SHARED_IDENTIFIER", "MEDIUM", "Identifier shared with 2+ other claims (possible ring).",
                {"identifier": ident, "other_claims": others})
    return hits


def score(hits: list[RuleHit]) -> tuple[int, str]:
    s = min(100, sum(WEIGHTS[h.severity] for h in hits))
    return s, "LOW" if s < 20 else "MEDIUM" if s < 40 else "HIGH"
