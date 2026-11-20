from datetime import date

from app.services.rules import ClaimContext, evaluate, score


def ctx(**kw):
    base = dict(claim_number="T1", claim_type="MOTOR", policy_number="POL-1", policy_start=date(2025, 1, 1),
                policy_end=date(2025, 12, 31), sum_insured=100000, claimant_name="Test User",
                incident_date=date(2025, 6, 1), reported_date=date(2025, 6, 3), claimed_amount=50000,
                doc_types={"CLAIM_FORM", "INVOICE", "POLICE_REPORT"},
                extractions=[{"document_type": "INVOICE", "amount": "50000", "policy_number": "POL-1",
                              "claimant_name": "Test User", "incident_date": "2025-06-01"}])
    base.update(kw)
    return ClaimContext(**base)


def codes(c):
    return {h.rule_code for h in evaluate(c)}


def test_clean_claim_has_no_findings():
    hits = evaluate(ctx())
    assert hits == [] and score(hits) == (0, "LOW")


def test_policy_period_and_over_sum_insured():
    assert {"POLICY_PERIOD", "OVER_SUM_INSURED"} <= codes(ctx(incident_date=date(2026, 2, 1), claimed_amount=150000,
                                                               extractions=[]))


def test_amount_and_name_mismatch():
    c = ctx(extractions=[{"document_type": "INVOICE", "amount": "30000", "claimant_name": "Other Person"}])
    assert {"AMOUNT_MISMATCH", "NAME_MISMATCH"} <= codes(c)


def test_ring_needs_two_other_claims():
    assert "SHARED_IDENTIFIER" not in codes(ctx(shared_ids={"PHONE:x": ["A"]}))
    assert "SHARED_IDENTIFIER" in codes(ctx(shared_ids={"PHONE:x": ["A", "B"]}))


def test_score_is_capped():
    c = ctx(incident_date=date(2026, 2, 1), claimed_amount=500000, duplicate_docs=["X"], duplicate_invoices=["X"])
    assert score(evaluate(c)) == (100, "HIGH")
