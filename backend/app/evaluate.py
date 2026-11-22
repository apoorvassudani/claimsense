"""Compare ClaimSense output in the database with the answer key (data/ground_truth.json).

Usage:
  python -m app.evaluate                 report on the current database (after `python -m app.seed ...`)
  python -m app.evaluate --include-mock  also score documents read by the offline mock (pipeline check only)

Writes docs/evaluation-report.md and prints a summary.
"""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from .db import SessionLocal
from .models import AIRun, Claim, Document, Extraction

ROOT = Path(__file__).resolve().parents[2]
TRUTH_FILE = ROOT / "data" / "ground_truth.json"
REPORT = ROOT / "docs" / "evaluation-report.md"
FIELDS = ["document_type", "policy_number", "claimant_name", "incident_date", "document_date", "amount",
          "invoice_number", "provider_name", "vehicle_registration", "phone"]


def _code(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def same(field: str, truth, pred) -> bool:
    if truth in (None, "") and pred in (None, "", []):
        return True
    if truth in (None, "") or pred in (None, ""):
        return False
    if field == "amount":
        try:
            return abs(float(truth) - float(pred)) <= 1.0
        except (TypeError, ValueError):
            return False
    if field in ("incident_date", "document_date"):
        return str(pred)[:10] == str(truth)
    if field == "phone":
        return re.sub(r"\D", "", str(pred))[-10:] == re.sub(r"\D", "", str(truth))[-10:]
    return _code(truth) == _code(pred)


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "n/a"


def main(argv: list[str]):
    include_mock = "--include-mock" in argv
    if not TRUTH_FILE.exists():
        sys.exit("No answer key found. Run `python -m app.seed` first.")
    truth = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))
    db = SessionLocal()
    claims = {c.claim_number: c for c in db.scalars(select(Claim))}
    if not claims:
        sys.exit("Database is empty. Run `python -m app.seed` first.")

    # ---------- extraction accuracy
    field_ok, field_n = defaultdict(int), defaultdict(int)
    invented = defaultdict(int)
    docs_scored = docs_failed = docs_mock = 0
    live_claims = set()
    models = set()
    errors: list[str] = []
    for tc in truth["claims"]:
        claim = claims.get(tc["claim_number"])
        if not claim:
            continue
        all_live = True
        for td in tc["documents"]:
            doc = db.scalar(select(Document).where(Document.claim_id == claim.claim_id,
                                                   Document.filename == td["filename"]))
            ext = doc and db.scalar(select(Extraction).where(Extraction.document_id == doc.document_id,
                                                             Extraction.is_valid)
                                    .order_by(Extraction.extraction_id.desc()).limit(1))
            if not ext:
                docs_failed += 1
                all_live = False
                continue
            model = db.get(AIRun, ext.run_id).model_id
            if model.startswith("mock") and not include_mock:
                docs_mock += 1
                all_live = False
                continue
            models.add(model)
            docs_scored += 1
            for f in FIELDS:
                t, p = td["fields"].get(f), ext.fields.get(f)
                field_n[f] += 1
                if same(f, t, p):
                    field_ok[f] += 1
                else:
                    if t in (None, ""):
                        invented[f] += 1
                    if len(errors) < 25:
                        errors.append(f"{td['filename']}: {f} expected {t!r}, got {p!r}")
        if all_live:
            live_claims.add(tc["claim_number"])

    # ---------- rule and routing accuracy
    def rule_metrics(subset):
        tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
        route = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        wrong = []
        for tc in truth["claims"]:
            if tc["claim_number"] not in subset:
                continue
            claim = claims[tc["claim_number"]]
            got, exp = {f.rule_code for f in claim.findings}, set(tc["expected_rules"])
            for r in got & exp:
                tp[r] += 1
            for r in got - exp:
                fp[r] += 1
            for r in exp - got:
                fn[r] += 1
            flagged = claim.status == "NEEDS_REVIEW"
            key = ("t" if flagged == tc["expected_flagged"] else "f") + ("p" if flagged else "n")
            route[key] += 1
            if got != exp:
                wrong.append(f"{tc['claim_number']} [{tc['scenario']}]: expected {sorted(exp)}, got {sorted(got)}")
        return tp, fp, fn, route, wrong

    scope = set(claims) if (include_mock or not live_claims) else live_claims
    scope_label = ("all claims" if scope == set(claims) else f"{len(scope)} claims read entirely by the live model")
    tp, fp, fn, route, wrong = rule_metrics(scope)
    rules = sorted(set(tp) | set(fp) | set(fn))

    # ---------- report
    out = [f"# ClaimSense evaluation report", "",
           f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. Models scored: {', '.join(sorted(models)) or 'none'}.",
           ""]
    out += ["## AI field extraction", ""]
    if docs_scored:
        total_ok, total_n = sum(field_ok.values()), sum(field_n.values())
        out += [f"Documents scored: **{docs_scored}** (failed/unread: {docs_failed}, read by mock and skipped: {docs_mock}).",
                f"Overall field accuracy: **{pct(total_ok, total_n)}**.", "",
                "| Field | Accuracy | Invented values* |", "|---|---|---|"]
        out += [f"| {f} | {pct(field_ok[f], field_n[f])} | {invented[f]} |" for f in FIELDS]
        out += ["", "*a value returned for a field that is not in the document.", ""]
        if errors:
            out += ["First extraction differences:", ""] + [f"- {e}" for e in errors] + [""]
    else:
        out += ["No documents were read by a live model, so extraction accuracy cannot be measured. Run "
                "`python -m app.seed --live --limit 15` (or without --limit) and evaluate again.", ""]
    out += [f"## Fraud rules ({scope_label})", ""]
    if include_mock or not live_claims:
        out += ["> Rule results here use mock (answer-key) extraction, so they check the rules engine itself, "
                "not the AI.", ""]
    out += ["| Rule | Correct | False alarms | Missed | Precision | Recall |", "|---|---|---|---|---|---|"]
    for r in rules:
        out.append(f"| {r} | {tp[r]} | {fp[r]} | {fn[r]} | {pct(tp[r], tp[r] + fp[r])} | {pct(tp[r], tp[r] + fn[r])} |")
    should = route["tp"] + route["fn"]
    out += ["", "## Review routing", "",
            f"- Claims that should go to review: **{should}**; routed correctly: **{route['tp']}** "
            f"({pct(route['tp'], should)}); missed: **{route['fn']}**.",
            f"- Clean claims wrongly sent to review (false alarms): **{route['fp']}** of "
            f"{route['fp'] + route['tn']}.", ""]
    if wrong:
        out += ["Claims whose rules differ from the answer key:", ""] + [f"- {w}" for w in wrong] + [""]
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    print(f"\nSaved to {REPORT}")
    db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
