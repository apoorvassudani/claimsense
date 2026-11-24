from app.datagen import generate
from app.services.rules import SEVERITY


def test_dataset_is_deterministic_and_well_formed():
    a, b = generate(), generate()
    assert [c["claim_number"] for c in a["claims"]] == [c["claim_number"] for c in b["claims"]]
    assert a["claims"][10]["docs"][0]["text"] == b["claims"][10]["docs"][0]["text"]
    assert len(a["claims"]) >= 80
    planted = [c for c in a["claims"] if c["expected_rules"]]
    assert 0.2 <= len(planted) / len(a["claims"]) <= 0.4
    for c in a["claims"]:
        assert set(c["expected_rules"]) <= set(SEVERITY)
        for d in c["docs"]:
            assert "SYNTHETIC TEST DOCUMENT" in d["text"]
    assert all(p["phone"].startswith("+91 55") for p in a["claimants"])  # not a real mobile range
