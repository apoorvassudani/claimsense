"""RAG over policy wording. Runs offline: local keyword retrieval, plus a forced Azure failure."""
from app.services import policy_rag
from tests.test_api import make_claim, upload


def test_policy_files_split_into_clauses():
    ids = {c.id for c in policy_rag.load_clauses()}
    assert {"GEN-1", "GEN-7", "MTR-1", "HLT-2", "PRP-2"} <= ids


def test_every_rule_has_a_question():
    from app.services.rules import SEVERITY
    assert set(SEVERITY) == set(policy_rag.RULE_QUERIES)


def test_search_respects_product_filter():
    hits, mode = policy_rag.search("documents required for the claim", "HEALTH", k=5)
    assert mode == "local_keyword"
    assert all(not h["clause_id"].startswith(("MTR", "PRP")) for h in hits)


def test_findings_carry_policy_clause(client):
    policy_rag.clear_cache()
    cid = make_claim(client)
    upload(client, cid)
    body = client.post(f"/claims/{cid}/process").json()
    missing = next(f for f in body["findings"] if f["rule_code"] == "MISSING_DOCUMENT")
    assert missing["evidence"]["policy_clause"]["clause_id"].startswith(("MTR", "GEN"))
    trace = client.get(f"/observability/traces/{body['trace_id']}").json()
    assert "rag.retrieve" in {e["span_name"] for e in trace["events"]}


def test_retrieval_failure_never_blocks_scoring(client, monkeypatch):
    policy_rag.clear_cache()

    def boom(*a, **k):
        raise policy_rag.SearchError("search down")
    monkeypatch.setattr(policy_rag, "search", boom)
    cid = make_claim(client)
    upload(client, cid)
    body = client.post(f"/claims/{cid}/process").json()
    assert body["risk_level"] and body["findings"]
    assert all("policy_clause" not in f["evidence"] for f in body["findings"])
    policy_rag.clear_cache()


def test_policy_search_endpoint(client):
    r = client.get("/policy/search", params={"q": "claim reported late", "product": "MOTOR"})
    assert r.status_code == 200 and r.json()["results"]


# ---------------------------------------------------------------- generation half (reviewer briefing)
def test_briefing_is_written_and_grounded(client):
    policy_rag.clear_cache()
    cid = make_claim(client)
    upload(client, cid)
    client.post(f"/claims/{cid}/process")
    s = client.get(f"/claims/{cid}/summary").json()
    assert s["summary"] and s["citations"]
    retrieved = {i for c in s["clauses"] for i in c["clause_ids"]}
    assert set(s["citations"]) <= retrieved


def test_ungrounded_citation_is_rejected(client, monkeypatch):
    """A model that cites a clause retrieval never returned must not reach the reviewer."""
    import json
    from app.config import settings
    from app.services import llm
    policy_rag.clear_cache()
    cid = make_claim(client)
    upload(client, cid)
    client.post(f"/claims/{cid}/process", params={})  # extraction + first briefing (mock)
    real = llm.complete_json

    def fake(system, user, doc):
        if "briefing" in system:
            return llm.LLMResult(text=json.dumps({"summary": "Late claim, see [ZZZ-9] for the rule here.",
                                                  "next_steps": [], "citations": ["ZZZ-9"]}), model="fake")
        return real(system, user, doc)
    monkeypatch.setattr(llm, "complete_json", fake)
    monkeypatch.setattr(settings, "llm_provider", "azure")  # live provider: mock briefing gets replaced
    body = client.post(f"/claims/{cid}/process").json()
    run = next(r for r in body["runs"] if r["task"] == "SUMMARY")
    assert run["status"] == "FAILED" and run["error_type"] == "ungrounded_citation"
    assert "ZZZ-9" not in json.dumps(client.get(f"/claims/{cid}/summary").json())


def test_same_findings_reuse_the_briefing(client):
    policy_rag.clear_cache()
    cid = make_claim(client)
    upload(client, cid)
    client.post(f"/claims/{cid}/process")
    assert client.post(f"/claims/{cid}/process").json()["runs"] == []


# ---------------------------------------------------------------- held-out stress set
def test_stress_set_is_realistic_and_reproducible():
    from app.stress_test import generate_stress, messify
    data = generate_stress()
    flagged = sum(c["expected_flagged"] for c in data["claims"])
    assert 130 <= len(data["claims"]) <= 160
    assert 0.04 <= flagged / len(data["claims"]) <= 0.12           # realistic fraud rate
    doc = data["claims"][0]["docs"][0]["text"]
    a, b = messify(doc), messify(doc)
    assert a == b                                                    # identical files stay identical
    assert "SYNTHETIC TEST DOCUMENT" in a[0]
    dev_names = {n for n in ("Aarav", "Vivaan")}
    assert not any(n in doc for n in dev_names)                      # unseen people
