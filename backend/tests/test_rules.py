from datetime import date

from app.services.rules import ClaimContext, evaluate, names_match, score


def ctx(**kw):
    base = dict(claim_number="T1", claim_type="MOTOR", policy_number="NW/MTR/2025/000001",
                policy_start=date(2025, 1, 1), policy_end=date(2025, 12, 31), sum_insured=100000,
                claimant_name="Arjun Mehta", claimant_code="C001", incident_date=date(2025, 6, 1),
                reported_date=date(2025, 6, 3), claimed_amount=50000,
                doc_types={"CLAIM_FORM", "INVOICE", "POLICE_REPORT"},
                extractions=[{"document_type": "INVOICE", "amount": "50000", "policy_number": "NW/MTR/2025/000001",
                              "claimant_name": "A. Mehta", "incident_date": "2025-06-01"}])
    base.update(kw)
    return ClaimContext(**base)


def codes(c):
    return {h.rule_code for h in evaluate(c)}


def link(n, code, d):
    return {"claim_number": n, "claimant_code": code, "incident_date": d}


def test_clean_claim_has_no_findings():
    hits = evaluate(ctx())
    assert hits == [] and score(hits) == (0, "LOW")


def test_name_matching_handles_initials_and_case():
    assert names_match("A. Mehta", "Arjun Mehta")
    assert names_match("ARJUN MEHTA", "Arjun Mehta")
    assert not names_match("Meena Pillay", "Meera Pillai")
    assert not names_match("Rohan Mehta", "Arjun Mehta")


def test_policy_period_and_over_sum_insured():
    assert {"POLICY_PERIOD", "OVER_SUM_INSURED"} <= codes(ctx(incident_date=date(2026, 2, 1), claimed_amount=150000,
                                                               extractions=[]))


def test_amount_tolerance():
    assert "AMOUNT_MISMATCH" not in codes(ctx(claimed_amount=52500))   # 5% over: allowed
    assert "AMOUNT_MISMATCH" in codes(ctx(claimed_amount=72500))       # 45% over: flagged


def test_shared_phone_only_counts_other_claimants():
    assert "SHARED_PHONE" not in codes(ctx(links={"PHONE:x": [link("T2", "C001", date(2025, 3, 1))]}))
    assert "SHARED_PHONE" in codes(ctx(links={"PHONE:x": [link("T2", "C009", date(2025, 3, 1))]}))


def test_shared_address_alone_is_not_flagged():
    assert codes(ctx(links={"ADDRESS:x": [link("T2", "C009", date(2025, 3, 1))]})) == set()


def test_provider_cluster_needs_two_claims_within_window():
    busy_but_spread = [link("T2", "C2", date(2025, 2, 1)), link("T3", "C3", date(2025, 9, 1))]
    clustered = [link("T2", "C2", date(2025, 5, 20)), link("T3", "C3", date(2025, 6, 15))]
    assert "PROVIDER_CLUSTER" not in codes(ctx(links={"PROVIDER:g": busy_but_spread}))
    assert "PROVIDER_CLUSTER" in codes(ctx(links={"PROVIDER:g": clustered}))


def test_score_is_capped():
    c = ctx(incident_date=date(2026, 2, 1), claimed_amount=500000, duplicate_docs=["X"], duplicate_invoices=["X"])
    assert score(evaluate(c)) == (100, "HIGH")


# ---------------------------------------------------------------- scan misreads vs genuine mismatches
REGISTER = {"policies": {"nwmtr2025000058", "nwmtr2025000044", "polm001"},
            "people": ["Sneha Chopra", "Kabir Mehta", "Ravi Kumar"]}


def scan_ctx(**fields):
    c = ctx(policy_number="NW/MTR/2025/000058", claimant_name="Sneha Chopra",
            extractions=[{"document_type": "CLAIM_FORM", **fields}])
    c.known_policies, c.known_people = REGISTER["policies"], REGISTER["people"]
    return c


def test_scanned_policy_misread_is_advisory():
    hits = evaluate(scan_ctx(policy_number="NW/NTR/2025/000051", _scanned=True))
    assert {h.rule_code for h in hits} >= {"SCAN_UNCLEAR"} and "POLICY_NUMBER_MISMATCH" not in {h.rule_code for h in hits}
    assert next(h for h in hits if h.rule_code == "SCAN_UNCLEAR").severity == "LOW"


def test_scanned_value_matching_another_real_policy_stays_a_mismatch():
    assert "POLICY_NUMBER_MISMATCH" in codes(scan_ctx(policy_number="NW/MTR/2025/000044", _scanned=True))


def test_text_document_is_never_softened():
    assert "POLICY_NUMBER_MISMATCH" in codes(scan_ctx(policy_number="NW/NTR/2025/000051"))


def test_scanned_name_misread_vs_other_person():
    assert codes(scan_ctx(claimant_name="SAHEMA CHOPRA", _scanned=True)) & {"SCAN_UNCLEAR"}
    assert "NAME_MISMATCH" in codes(scan_ctx(claimant_name="Kabir Mehta", _scanned=True))    # another real person
    assert "NAME_MISMATCH" in codes(scan_ctx(claimant_name="Ira Bose", _scanned=True))       # different surname
    assert "NAME_MISMATCH" in codes(scan_ctx(claimant_name="SAHEMA CHOPRA"))                 # text: strict
