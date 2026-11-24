from app.config import settings

DOC = """DOCUMENT TYPE: INVOICE
Policy Number: POL-M-001
Claimant Name: Arjun Mehta
Incident Date: 2026-02-10
Invoice Number: INV-1
Provider: Test Garage
Total Amount: INR 40000.00
"""


def make_claim(client, number="CLM-T1", amount=40000):
    r = client.post("/claims", json={"claim_number": number, "policy_number": "POL-M-001", "claimant_code": "C001",
                                     "claim_type": "MOTOR", "incident_date": "2026-02-10",
                                     "reported_date": "2026-02-11", "claimed_amount": amount})
    assert r.status_code == 201, r.text
    return r.json()["claim_id"]


def upload(client, cid, text=DOC, name="inv.txt", doc_type="INVOICE"):
    return client.post(f"/claims/{cid}/documents", data={"doc_type": doc_type},
                       files={"file": (name, text.encode(), "text/plain")})


def test_validation_rejects_bad_claim(client):
    r = client.post("/claims", json={"claim_number": "X1", "policy_number": "POL-M-001", "claimant_code": "C001",
                                     "claim_type": "MOTOR", "incident_date": "2026-02-10",
                                     "reported_date": "2026-02-01", "claimed_amount": -5})
    assert r.status_code == 422


def test_upload_rejects_unsupported_type(client):
    cid = make_claim(client)
    assert upload(client, cid, name="photo.exe").status_code == 422


def test_end_to_end_process_with_single_trace(client):
    cid = make_claim(client)
    assert upload(client, cid).status_code == 201
    r = client.post(f"/claims/{cid}/process")
    assert r.status_code == 200
    body = r.json()
    assert body["trace_id"] == r.headers["X-Trace-Id"]          # same trace from HTTP to AI run
    assert body["runs"][0]["status"] == "SUCCESS"
    assert "MISSING_DOCUMENT" in {f["rule_code"] for f in body["findings"]}
    run = client.get(f"/observability/runs/{body['runs'][0]['run_id']}").json()
    stages = [e["span_name"] for e in run["events"]]
    assert stages == ["db.read_document", "ai.inference", "output.validation", "db.save_extraction"]
    trace = client.get(f"/observability/traces/{body['trace_id']}").json()
    assert {"graph.build", "rules.evaluate"} <= {e["span_name"] for e in trace["events"]}


def test_ai_timeout_is_isolated(client):
    cid = make_claim(client)
    upload(client, cid)
    settings.simulate_failure = "timeout"
    body = client.post(f"/claims/{cid}/process").json()
    settings.simulate_failure = ""
    assert body["runs"][0]["status"] == "FAILED" and body["runs"][0]["error_type"] == "timeout"
    assert client.get(f"/claims/{cid}").json()["claimed_amount"] == "40000.00"   # claim data intact
    assert body["findings"]                                   # rules still ran on what was available
    m = client.get("/observability/metrics").json()
    assert m["failed"] == 2 and m["error_rate"] == 1.0        # extraction + reviewer briefing both timed out
    # retry succeeds: one extraction, one briefing; a third run has nothing left to do
    body2 = client.post(f"/claims/{cid}/process").json()
    assert [(r["task"], r["status"]) for r in body2["runs"]] == [("EXTRACTION", "SUCCESS"), ("SUMMARY", "SUCCESS")]
    assert client.post(f"/claims/{cid}/process").json()["runs"] == []


def test_duplicate_document_across_claims(client):
    a, b = make_claim(client, "CLM-A"), make_claim(client, "CLM-B")
    upload(client, a); upload(client, b)
    client.post(f"/claims/{a}/process")
    codes = {f["rule_code"] for f in client.post(f"/claims/{b}/process").json()["findings"]}
    assert {"DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE"} <= codes
    g = client.get(f"/graph/claims/{b}").json()
    assert any(n["type"] == "PROVIDER" for n in g["nodes"])


def test_review_sets_status_and_links_run(client):
    cid = make_claim(client)
    upload(client, cid)
    assert client.post(f"/claims/{cid}/reviews", json={"decision": "CLEAR"}).status_code == 422  # not verified yet
    client.post(f"/claims/{cid}/process")
    r = client.post(f"/claims/{cid}/reviews", json={"decision": "ESCALATE", "ai_helpful": False,
                                                     "comment": "Garage looks suspicious"})
    assert r.status_code == 201 and r.json()["run_id"]
    assert client.get(f"/claims/{cid}").json()["status"] == "ESCALATED"
    assert client.get(f"/claims/{cid}/reviews").json()[0]["comment"] == "Garage looks suspicious"
    fb = client.get("/observability/metrics").json()["feedback"]
    assert fb == {"reviews": 1, "helpful": 0, "not_helpful": 1}
    assert client.post(f"/claims/{cid}/reviews", json={"decision": "APPROVE"}).status_code == 422


def test_lists_for_frontend(client):
    cid = make_claim(client)
    upload(client, cid)
    client.post(f"/claims/{cid}/process")
    assert {c["claimant_code"] for c in client.get("/claimants").json()} == {"C001", "C002"}
    row = client.get("/claims").json()[0]
    assert row["claimant_name"] == "Arjun Mehta"
    runs = client.get(f"/observability/runs?claim_id={cid}").json()
    assert runs and all(r["claim_id"] == cid for r in runs)
    doc_id = client.get(f"/claims/{cid}").json()["documents"][0]["document_id"]
    assert "Policy Number" in client.get(f"/documents/{doc_id}").json()["text"]
