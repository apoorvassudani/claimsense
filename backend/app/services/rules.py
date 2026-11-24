"""Deterministic validation & fraud-flag rules. Scores come from these rules, never from the LLM."""
import difflib
import re
from dataclasses import dataclass, field
from datetime import date

WEIGHTS = {"HIGH": 40, "MEDIUM": 20, "LOW": 5}
SEVERITY = {
    "POLICY_PERIOD": "HIGH", "OVER_SUM_INSURED": "HIGH", "POLICY_NUMBER_MISMATCH": "HIGH",
    "DUPLICATE_DOCUMENT": "HIGH", "DUPLICATE_INVOICE": "HIGH", "SHARED_VEHICLE": "HIGH",
    "EARLY_CLAIM": "MEDIUM", "AMOUNT_MISMATCH": "MEDIUM", "NAME_MISMATCH": "MEDIUM", "DATE_MISMATCH": "MEDIUM",
    "SHARED_PHONE": "MEDIUM", "PROVIDER_CLUSTER": "MEDIUM",
    "LATE_REPORTING": "LOW", "MISSING_DOCUMENT": "LOW", "SCAN_UNCLEAR": "LOW",
}
# Advisory: shown to the reviewer, but on its own never sends a claim to review (LOW = 5 points).
ADVISORY = {"SCAN_UNCLEAR"}
NEAR_MATCH = 0.8  # similarity above which a scanned value is "one or two characters off"
REQUIRED_DOCS = {"MOTOR": {"CLAIM_FORM", "INVOICE", "POLICE_REPORT"},
                 "HEALTH": {"CLAIM_FORM", "MEDICAL_BILL"},
                 "PROPERTY": {"CLAIM_FORM", "INVOICE"}}
AMOUNT_TOLERANCE = 0.10
CLUSTER_WINDOW_DAYS = 30
_TITLES = {"mr", "mrs", "ms", "dr", "shri", "smt", "kumari", "km"}
DOC_NAMES = {"CLAIM_FORM": "The claim form", "INVOICE": "The invoice", "POLICE_REPORT": "The police report",
             "MEDICAL_BILL": "The hospital bill", "OTHER": "A document"}


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
    claimant_code: str = ""
    duplicate_docs: list[str] = field(default_factory=list)      # other claims with same file hash
    duplicate_invoices: list[str] = field(default_factory=list)  # other claims with same invoice+provider
    # "TYPE:label" -> [{"claim_number", "claimant_code", "incident_date"}] for other claims sharing that identifier
    links: dict[str, list[dict]] = field(default_factory=dict)
    # Registers used to tell a scan misread from a genuine mismatch (see _scan_misread_*).
    known_policies: set[str] = field(default_factory=set)   # normalised policy numbers on record
    known_people: list[str] = field(default_factory=list)   # claimant names on record


@dataclass
class RuleHit:
    rule_code: str
    severity: str
    message: str
    evidence: dict


def _name_tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", (s or "").lower()) if t not in _TITLES]


def names_match(a: str | None, b: str | None) -> bool:
    """'A. Mehta', 'ARJUN MEHTA' and 'Arjun Mehta' match; 'Meena Pillay' vs 'Meera Pillai' does not."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return True
    if ta[-1] != tb[-1]:
        return False
    if len(ta) == 1 or len(tb) == 1:
        return True
    fa, fb = ta[0], tb[0]
    return fa[0] == fb[0] and (len(fa) == 1 or len(fb) == 1 or fa == fb)


def _code(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _scan_misread_policy(e: dict, ctx: ClaimContext) -> bool:
    """A scanned policy number that is close to the claim's own but matches no policy on record is far more
    likely an OCR misread than fraud. One that matches another real policy stays a full mismatch.
    The other identity on the same document must agree too: if its name belongs to someone else, the document
    probably isn't this claimant's at all, so the policy mismatch keeps full strength (found in a manual test
    where OCR misread a policy number on a document that genuinely belonged to another person)."""
    read = _code(e.get("policy_number"))
    name = e.get("claimant_name")
    name_agrees = not name or names_match(name, ctx.claimant_name) or _scan_misread_name(e, ctx)
    return bool(e.get("_scanned") and ctx.known_policies and read not in ctx.known_policies
                and _similar(read, _code(ctx.policy_number)) >= NEAR_MATCH and name_agrees)


def _scan_misread_name(e: dict, ctx: ClaimContext) -> bool:
    """Same surname, garbled first name, and not a person on record: likely a misread. A different surname,
    or a name that matches another real claimant, stays a full mismatch."""
    if not e.get("_scanned"):
        return False
    read, claim = _name_tokens(e.get("claimant_name")), _name_tokens(ctx.claimant_name)
    if not read or not claim or _similar(read[-1], claim[-1]) < NEAR_MATCH:
        return False
    others = [p for p in ctx.known_people if not names_match(p, ctx.claimant_name)]
    return not any(names_match(e["claimant_name"], p) for p in others)


def evaluate(ctx: ClaimContext) -> list[RuleHit]:
    hits: list[RuleHit] = []

    def add(code, msg, ev=None):
        hits.append(RuleHit(code, SEVERITY[code], msg, ev or {}))

    if not (ctx.policy_start <= ctx.incident_date <= ctx.policy_end):
        add("POLICY_PERIOD", "Incident date is outside the policy period.",
            {"incident": str(ctx.incident_date), "start": str(ctx.policy_start), "end": str(ctx.policy_end)})
    elif (ctx.incident_date - ctx.policy_start).days <= 30:
        add("EARLY_CLAIM", "Incident within 30 days of policy start.",
            {"days_after_start": (ctx.incident_date - ctx.policy_start).days})
    if (ctx.reported_date - ctx.incident_date).days > 30:
        add("LATE_REPORTING", "Claim reported more than 30 days after incident.",
            {"days": (ctx.reported_date - ctx.incident_date).days})
    if ctx.claimed_amount > ctx.sum_insured:
        add("OVER_SUM_INSURED", "Claimed amount exceeds sum insured.",
            {"claimed": ctx.claimed_amount, "sum_insured": ctx.sum_insured})

    missing = REQUIRED_DOCS.get(ctx.claim_type, set()) - ctx.doc_types
    if missing:
        add("MISSING_DOCUMENT", "Required documents missing.", {"missing": sorted(missing)})

    bill_total = sum(float(e["amount"]) for e in ctx.extractions
                     if e.get("document_type") in ("INVOICE", "MEDICAL_BILL") and e.get("amount") is not None)
    if bill_total and abs(bill_total - ctx.claimed_amount) / ctx.claimed_amount > AMOUNT_TOLERANCE:
        add("AMOUNT_MISMATCH", "Invoice/bill total differs from claimed amount by more than 10%.",
            {"bill_total": round(bill_total, 2), "claimed": ctx.claimed_amount})

    seen = set()
    for e in ctx.extractions:
        dt = DOC_NAMES.get(e.get("document_type"), "A document")
        if e.get("policy_number") and _code(e["policy_number"]) != _code(ctx.policy_number):
            if _scan_misread_policy(e, ctx):
                if "SCAN_UNCLEAR:policy" not in seen:
                    seen.add("SCAN_UNCLEAR:policy")
                    add("SCAN_UNCLEAR", f"{dt} (scanned) seems to show policy number {e['policy_number']}, which "
                        "matches no policy on record and is one or two characters off. Probably a scan misread: "
                        "check the original.", {"field": "policy number", "document": e["policy_number"],
                                                "claim": ctx.policy_number})
            elif "POLICY_NUMBER_MISMATCH" not in seen:
                seen.add("POLICY_NUMBER_MISMATCH")
                add("POLICY_NUMBER_MISMATCH", f"{dt} shows a different policy number.",
                    {"document": e["policy_number"], "claim": ctx.policy_number})
        if e.get("claimant_name") and not names_match(e["claimant_name"], ctx.claimant_name):
            if _scan_misread_name(e, ctx):
                if "SCAN_UNCLEAR:name" not in seen:
                    seen.add("SCAN_UNCLEAR:name")
                    add("SCAN_UNCLEAR", f"{dt} (scanned) seems to show the name {e['claimant_name']}: same surname, "
                        "but the first name doesn't match anyone on record. Probably a scan misread: check the "
                        "original.", {"field": "name", "document": e["claimant_name"], "claim": ctx.claimant_name})
            elif "NAME_MISMATCH" not in seen:
                seen.add("NAME_MISMATCH")
                add("NAME_MISMATCH", f"{dt} shows a different person's name.",
                    {"document": e["claimant_name"], "claim": ctx.claimant_name})
        if e.get("incident_date") and str(e["incident_date"]) != str(ctx.incident_date) \
                and "DATE_MISMATCH" not in seen:
            seen.add("DATE_MISMATCH")
            add("DATE_MISMATCH", f"{dt} shows a different incident date.",
                {"document": str(e["incident_date"]), "claim": str(ctx.incident_date)})

    if ctx.duplicate_docs:
        add("DUPLICATE_DOCUMENT", "Identical document file already submitted on another claim.",
            {"other_claims": ctx.duplicate_docs})
    if ctx.duplicate_invoices:
        add("DUPLICATE_INVOICE", "Same invoice number and provider used on another claim.",
            {"other_claims": ctx.duplicate_invoices})

    def other_people(key_prefix):
        return {k: [o for o in v if o["claimant_code"] != ctx.claimant_code]
                for k, v in ctx.links.items() if k.startswith(key_prefix)}

    for ident, others in other_people("PHONE:").items():
        if others:
            add("SHARED_PHONE", "Contact phone also used by a different claimant.",
                {"identifier": ident, "other_claims": sorted(o["claim_number"] for o in others)})
            break
    for ident, others in other_people("VEHICLE:").items():
        if others:
            add("SHARED_VEHICLE", "Same vehicle appears on a claim by a different claimant.",
                {"identifier": ident, "other_claims": sorted(o["claim_number"] for o in others)})
            break
    for ident, others in ctx.links.items():
        if not ident.startswith("PROVIDER:"):
            continue
        near = [o for o in others if abs((o["incident_date"] - ctx.incident_date).days) <= CLUSTER_WINDOW_DAYS]
        if len(near) >= 2:
            add("PROVIDER_CLUSTER", f"Provider handled {len(near)} other claims within {CLUSTER_WINDOW_DAYS} days.",
                {"identifier": ident, "other_claims": sorted(o["claim_number"] for o in near)})
            break
    return hits


def score(hits: list[RuleHit]) -> tuple[int, str]:
    s = min(100, sum(WEIGHTS[h.severity] for h in hits))
    return s, "LOW" if s < 20 else "MEDIUM" if s < 40 else "HIGH"
