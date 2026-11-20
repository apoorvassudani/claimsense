"""Seed synthetic data (all names, numbers and documents are fictional).
Usage:  python -m app.seed            # reset tables, insert data, process with the mock extractor
        python -m app.seed --live     # process with the provider configured in .env
"""
import hashlib
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import settings
from .db import Base, SessionLocal, engine
from .models import Claim, Claimant, Document, Policy
from .services.pipeline import process_claim

DOC_DIR = Path(__file__).resolve().parents[2] / "data" / "sample_documents"

POLICIES = [  # number, holder, product, sum insured, start, end
    ("POL-M-001", "H001", "MOTOR", 300000, date(2025, 6, 1), date(2026, 5, 31)),
    ("POL-M-002", "H002", "MOTOR", 250000, date(2025, 9, 1), date(2026, 8, 31)),
    ("POL-M-003", "H003", "MOTOR", 150000, date(2025, 11, 1), date(2026, 10, 31)),
    ("POL-M-004", "H004", "MOTOR", 400000, date(2025, 4, 1), date(2026, 3, 31)),
    ("POL-M-005", "H005", "MOTOR", 200000, date(2025, 7, 1), date(2026, 6, 30)),
    ("POL-M-006", "H006", "MOTOR", 200000, date(2025, 7, 15), date(2026, 7, 14)),
    ("POL-M-007", "H007", "MOTOR", 200000, date(2025, 8, 1), date(2026, 7, 31)),
    ("POL-H-001", "H008", "HEALTH", 500000, date(2025, 5, 1), date(2026, 4, 30)),
    ("POL-H-002", "H009", "HEALTH", 300000, date(2025, 10, 1), date(2026, 9, 30)),
    ("POL-H-003", "H010", "HEALTH", 300000, date(2026, 1, 1), date(2026, 12, 31)),
    ("POL-P-001", "H011", "PROPERTY", 1000000, date(2025, 3, 1), date(2026, 2, 28)),
]
RING_PHONE = "+91 90000 11122"
CLAIMANTS = [  # code, name, phone, address
    ("C001", "Arjun Mehta", "+91 90000 00001", "12 Lake View Road, Sector 5, Testpur"),
    ("C002", "Priya Nair", "+91 90000 00002", "44 Hill Street, Demonagar"),
    ("C003", "Rahul Verma", "+91 90000 00003", "7 Station Lane, Samplegarh"),
    ("C004", "Sneha Iyer", "+91 90000 00004", "19 Park Avenue, Testpur"),
    ("C005", "Vikram Singh", RING_PHONE, "88 Market Road, Fakeabad"),
    ("C006", "Anil Kumar", RING_PHONE, "88 Market Road, Fakeabad"),
    ("C007", "Ramesh Gupta", RING_PHONE, "3 Canal Colony, Fakeabad"),
    ("C008", "Kavya Rao", "+91 90000 00008", "21 Temple Street, Mockpuram"),
    ("C009", "Deepak Joshi", "+91 90000 00009", "5 River Side, Demonagar"),
    ("C010", "Meera Pillai", "+91 90000 00010", "60 Garden Road, Samplegarh"),
    ("C011", "Farhan Ali", "+91 90000 00011", "9 Old Fort Road, Testpur"),
]


def doc(doc_type, policy, name, incident, amount=None, invoice=None, provider=None, vehicle=None, docdate=None):
    lines = [f"DOCUMENT TYPE: {doc_type}", "SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD",
             f"Policy Number: {policy}", f"Claimant Name: {name}", f"Incident Date: {incident}"]
    if docdate: lines.append(f"Document Date: {docdate}")
    if invoice: lines.append(f"Invoice Number: {invoice}")
    if provider: lines.append(f"Provider: {provider}")
    if vehicle: lines.append(f"Vehicle Registration: {vehicle}")
    if amount is not None: lines.append(f"Total Amount: INR {amount:.2f}")
    return "\n".join(lines) + "\n"


def motor_docs(pol, name, inc, amt, inv, garage, veh, inv_amt=None):
    return [("CLAIM_FORM", doc("CLAIM_FORM", pol, name, inc, amt, vehicle=veh)),
            ("INVOICE", doc("INVOICE", pol, name, inc, inv_amt or amt, inv, garage, veh, docdate=inc)),
            ("POLICE_REPORT", doc("POLICE_REPORT", pol, name, inc, vehicle=veh))]


INV_1001 = doc("INVOICE", "POL-M-001", "Arjun Mehta", "2026-02-10", 48500, "INV-5521", "Sharma Auto Works",
               "UP14AB1234", docdate="2026-02-10")

CLAIMS = [  # number, policy, claimant, type, incident, reported, amount, desc, docs, scenario
    ("CLM-1001", "POL-M-001", "C001", "MOTOR", "2026-02-10", "2026-02-12", 48500, "Rear bumper damage",
     [("CLAIM_FORM", doc("CLAIM_FORM", "POL-M-001", "Arjun Mehta", "2026-02-10", 48500, vehicle="UP14AB1234")),
      ("INVOICE", INV_1001),
      ("POLICE_REPORT", doc("POLICE_REPORT", "POL-M-001", "Arjun Mehta", "2026-02-10", vehicle="UP14AB1234"))],
     "clean"),
    ("CLM-1002", "POL-H-001", "C008", "HEALTH", "2026-01-20", "2026-01-25", 82000, "Appendix surgery",
     [("CLAIM_FORM", doc("CLAIM_FORM", "POL-H-001", "Kavya Rao", "2026-01-20", 82000)),
      ("MEDICAL_BILL", doc("MEDICAL_BILL", "POL-H-001", "Kavya Rao", "2026-01-20", 82000, "BILL-9001",
                           "City Care Hospital", docdate="2026-01-23"))], "clean"),
    ("CLM-1003", "POL-M-003", "C003", "MOTOR", "2025-10-20", "2025-11-05", 60000, "Side collision",
     motor_docs("POL-M-003", "Rahul Verma", "2025-10-20", 60000, "INV-7710", "Highway Garage", "DL3CAF0001"),
     "incident before policy start"),
    ("CLM-1004", "POL-M-002", "C002", "MOTOR", "2026-03-02", "2026-03-04", 310000, "Total loss claim",
     motor_docs("POL-M-002", "Priya Nair", "2026-03-02", 310000, "INV-3302", "Metro Motors", "KA01MN4455"),
     "claimed amount exceeds sum insured"),
    ("CLM-1005", "POL-M-004", "C004", "MOTOR", "2026-01-15", "2026-01-16", 95000, "Front-end damage",
     motor_docs("POL-M-004", "Sneha Iyer", "2026-01-15", 95000, "INV-4410", "Precision Autos", "MH12XY7788",
                inv_amt=61000), "invoice total much lower than claimed"),
    ("CLM-1006", "POL-M-001", "C009", "MOTOR", "2026-02-18", "2026-02-20", 48500, "Bumper repair",
     [("CLAIM_FORM", doc("CLAIM_FORM", "POL-M-001", "Deepak Joshi", "2026-02-18", 48500, vehicle="UP14AB1234")),
      ("INVOICE", INV_1001),  # identical file reused from CLM-1001
      ("POLICE_REPORT", doc("POLICE_REPORT", "POL-M-001", "Deepak Joshi", "2026-02-18", vehicle="UP14AB1234"))],
     "duplicate invoice/document from CLM-1001"),
    ("CLM-1007", "POL-M-005", "C005", "MOTOR", "2026-03-10", "2026-03-11", 72000, "Hit by unknown vehicle",
     motor_docs("POL-M-005", "Vikram Singh", "2026-03-10", 72000, "QF-101", "QuickFix Motors", "HR26AA1111"),
     "ring member"),
    ("CLM-1008", "POL-M-006", "C006", "MOTOR", "2026-03-14", "2026-03-15", 69000, "Hit by unknown vehicle",
     motor_docs("POL-M-006", "Anil Kumar", "2026-03-14", 69000, "QF-117", "QuickFix Motors", "HR26BB2222"),
     "ring member"),
    ("CLM-1009", "POL-M-007", "C007", "MOTOR", "2026-03-19", "2026-03-20", 74500, "Hit by unknown vehicle",
     motor_docs("POL-M-007", "Ramesh Gupta", "2026-03-19", 74500, "QF-123", "QuickFix Motors", "HR26CC3333"),
     "ring member"),
    ("CLM-1010", "POL-H-002", "C010", "HEALTH", "2026-02-05", "2026-02-08", 45000, "Fracture treatment",
     [("CLAIM_FORM", doc("CLAIM_FORM", "POL-H-002", "Meera Pillai", "2026-02-05", 45000)),
      ("MEDICAL_BILL", doc("MEDICAL_BILL", "POL-H-002", "Meena Pillay", "2026-02-05", 45000, "BILL-3120",
                           "Sunrise Clinic", docdate="2026-02-07"))], "name mismatch on bill"),
    ("CLM-1011", "POL-H-003", "C011", "HEALTH", "2026-01-12", "2026-03-01", 120000, "Hospitalisation",
     [("CLAIM_FORM", doc("CLAIM_FORM", "POL-H-003", "Farhan Ali", "2026-01-12", 120000)),
      ("MEDICAL_BILL", doc("MEDICAL_BILL", "POL-H-003", "Farhan Ali", "2026-01-12", 120000, "BILL-7781",
                           "Lifeline Hospital", docdate="2026-01-18"))], "early claim + late reporting"),
    ("CLM-1012", "POL-P-001", "C001", "PROPERTY", "2025-12-01", "2025-12-03", 150000, "Water damage",
     [("CLAIM_FORM", doc("CLAIM_FORM", "POL-P-001", "Arjun Mehta", "2025-12-01", 150000))],
     "missing invoice"),
]


def main(live: bool = False):
    if not live:
        settings.llm_provider = "mock"
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    pols = {}
    for n, h, p, s, st, en in POLICIES:
        pols[n] = Policy(policy_number=n, holder_code=h, product_type=p, sum_insured=Decimal(s),
                         start_date=st, end_date=en)
        db.add(pols[n])
    cls = {}
    for code, name, phone, addr in CLAIMANTS:
        cls[code] = Claimant(claimant_code=code, full_name=name, phone=phone, address=addr)
        db.add(cls[code])
    db.flush()
    claims = []
    for num, pol, cl, typ, inc, rep, amt, desc, docs, scenario in CLAIMS:
        c = Claim(claim_number=num, policy_id=pols[pol].policy_id, claimant_id=cls[cl].claimant_id, claim_type=typ,
                  incident_date=date.fromisoformat(inc), reported_date=date.fromisoformat(rep),
                  claimed_amount=Decimal(amt), description=f"{desc} [seed scenario: {scenario}]")
        db.add(c)
        db.flush()
        for i, (dtype, text) in enumerate(docs, 1):
            fname = f"{num}_{i}_{dtype.lower()}.txt"
            (DOC_DIR / fname).write_text(text)
            db.add(Document(claim_id=c.claim_id, doc_type=dtype, filename=fname,
                            sha256=hashlib.sha256(text.encode()).hexdigest(), text_content=text))
        claims.append(c)
    db.commit()

    # Failure telemetry for dashboards: first attempt on two claims fails, then succeeds on retry.
    for c, mode in ((claims[1], "timeout"), (claims[9], "malformed")):
        settings.simulate_failure = mode
        process_claim(db, c)
    settings.simulate_failure = ""
    for c in claims:
        process_claim(db, c)
    for c in claims:  # second rules pass so duplicates/rings see every claim
        process_claim(db, c)
    for c in claims:
        db.refresh(c)
        print(f"{c.claim_number:9} {c.risk_level:6} score={c.risk_score:3}  "
              f"{', '.join(sorted({f.rule_code for f in c.findings})) or '-'}")
    db.close()


if __name__ == "__main__":
    main(live="--live" in sys.argv)
