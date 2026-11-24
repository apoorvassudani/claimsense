import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LOG_FILE"] = "/tmp/claimsense-test.jsonl"
os.environ["DEMO_PASSWORD"] = "test-pass-123"
os.environ["AUTH_SECRET"] = "test-secret-for-signing-tokens-only"

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Claimant, Policy

POLICIES = [("POL-M-001", "C001", "MOTOR", 300000, date(2025, 6, 1), date(2026, 5, 31)),
            ("POL-H-001", "C002", "HEALTH", 500000, date(2025, 5, 1), date(2026, 4, 30))]
CLAIMANTS = [("C001", "Arjun Mehta", "+91 55000 00001", "House No. 12, Dwarka Sector 12, New Delhi - 110078"),
             ("C002", "Kavya Rao", "+91 55000 00002", "House No. 44, Koramangala, Bengaluru - 560034")]


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    for n, h, p, s, st, en in POLICIES:
        db.add(Policy(policy_number=n, holder_code=h, product_type=p, sum_insured=Decimal(s), start_date=st, end_date=en))
    for code, name, phone, addr in CLAIMANTS:
        db.add(Claimant(claimant_code=code, full_name=name, phone=phone, address=addr))
    db.commit()
    db.close()
    settings.simulate_failure = ""
    from app.services.auth import reset_lockouts
    reset_lockouts()
    with TestClient(app) as c:  # startup creates the demo accounts
        token = c.post("/auth/login", json={"username": "admin01", "password": "test-pass-123"}).json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"   # existing tests run as an admin
        yield c
    settings.simulate_failure = ""
