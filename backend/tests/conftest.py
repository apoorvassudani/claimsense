import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LOG_FILE"] = "/tmp/claimsense-test.jsonl"

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.db import SessionLocal
    from app.seed import CLAIMANTS, POLICIES
    from app.models import Claimant, Policy
    from decimal import Decimal
    db = SessionLocal()
    for n, h, p, s, st, en in POLICIES:
        db.add(Policy(policy_number=n, holder_code=h, product_type=p, sum_insured=Decimal(s), start_date=st, end_date=en))
    for code, name, phone, addr in CLAIMANTS:
        db.add(Claimant(claimant_code=code, full_name=name, phone=phone, address=addr))
    db.commit(); db.close()
    settings.simulate_failure = ""
    with TestClient(app) as c:
        yield c
    settings.simulate_failure = ""
