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
    m = client.get("/observability/metrics").json()
    assert m["failed"] == 1 and m["error_rate"] == 1.0
    # retry succeeds and does not re-extract twice
    body2 = client.post(f"/claims/{cid}/process").json()
    assert [r["status"] for r in body2["runs"]] == ["SUCCESS"]
    assert client.post(f"/claims/{cid}/process").json()["runs"] == []


def test_duplicate_document_across_claims(client):
    a, b = make_claim(client, "CLM-A"), make_claim(client, "CLM-B")
    upload(client, a); upload(client, b)
    client.post(f"/claims/{a}/process")
    codes = {f["rule_code"] for f in client.post(f"/claims/{b}/process").json()["findings"]}
    assert {"DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE"} <= codes
    g = client.get(f"/graph/claims/{b}").json()
    assert any(n["type"] == "PROVIDER" for n in g["nodes"])
