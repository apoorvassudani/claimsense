"""Sign-in, roles, audit identity and token safety."""
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from tests.test_api import make_claim, upload

PW = "test-pass-123"


def login(client, username, password=PW):
    return client.post("/auth/login", json={"username": username, "password": password})


def as_user(client, username):
    client.headers["Authorization"] = "Bearer " + login(client, username).json()["access_token"]


def test_api_needs_sign_in_but_health_is_public(client):
    del client.headers["Authorization"]
    assert client.get("/claims").status_code == 401
    assert client.get("/health").status_code == 200


def test_wrong_password_and_lockout(client):
    assert login(client, "reviewer01", "nope").status_code == 401
    for _ in range(4):
        login(client, "reviewer01", "nope")
    assert login(client, "reviewer01").status_code == 429      # locked even with the right password now


def test_passwords_are_hashed(client):
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.query(User).filter_by(username="admin01").one()
        assert PW not in u.password_hash and u.password_hash.startswith("pbkdf2_sha256$")


def test_intake_cannot_decide_or_see_monitoring(client):
    cid = make_claim(client)
    upload(client, cid)
    client.post(f"/claims/{cid}/process")
    as_user(client, "intake01")
    assert client.get(f"/claims/{cid}").status_code == 200       # can work the claim
    r = client.post(f"/claims/{cid}/reviews", json={"decision": "CLEAR"})
    assert r.status_code == 403
    assert client.get("/observability/metrics").status_code == 403
    assert client.get(f"/graph/claims/{cid}").status_code == 403


def test_decision_is_recorded_under_the_signed_in_reviewer(client):
    cid = make_claim(client)
    upload(client, cid)
    client.post(f"/claims/{cid}/process")
    as_user(client, "reviewer01")
    r = client.post(f"/claims/{cid}/reviews", json={"decision": "ESCALATE", "reviewer_code": "someone-else"})
    assert r.status_code == 201 and r.json()["reviewer_code"] == "reviewer01"   # body can't pick the identity
    assert client.get("/auth/me").json()["role"] == "REVIEWER"


def test_tampered_and_expired_tokens_are_rejected(client):
    now = datetime.now(timezone.utc)
    forged = jwt.encode({"sub": "admin01", "role": "ADMIN", "exp": now + timedelta(hours=1)}, "wrong-key",
                        algorithm="HS256")
    client.headers["Authorization"] = f"Bearer {forged}"
    assert client.get("/claims").status_code == 401
    expired = jwt.encode({"sub": "admin01", "role": "ADMIN", "exp": now - timedelta(minutes=1)},
                         settings.auth_secret, algorithm="HS256")
    client.headers["Authorization"] = f"Bearer {expired}"
    r = client.get("/claims")
    assert r.status_code == 401 and "expired" in r.json()["detail"]
