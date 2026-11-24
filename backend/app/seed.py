"""Build the synthetic dataset, write documents + answer key + scans, load PostgreSQL and process claims.

Usage:
  python -m app.seed                     offline: mock extractor for every document (fast, no API calls)
  python -m app.seed --live              real model from .env for every document (slow on free tiers)
  python -m app.seed --live --limit 15   real model for 15 claims, mock for the rest (graph stays complete)
"""
import hashlib
import json
import random
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import settings
from .datagen import SEED, generate
from .db import Base, SessionLocal, engine
from .models import Claim, Claimant, Document, Policy
from .services import llm
from .services.auth import ensure_demo_users
from .services.pipeline import process_claim

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DOC_DIR = DATA_DIR / "sample_documents"
SCAN_DIR = DOC_DIR / "scans"
TRUTH_FILE = DATA_DIR / "ground_truth.json"


def _json_default(o):
    return o.isoformat() if isinstance(o, date) else str(o)


def write_files(data: dict) -> dict:
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    for old in DOC_DIR.glob("*.txt"):
        old.unlink()
    truth = {"seed": SEED, "note": "Synthetic data. Real Indian localities; all people, businesses, numbers "
                                   "and documents are fictional. expected_rules is the answer key.",
             "claims": []}
    for c in data["claims"]:
        docs = []
        for i, d in enumerate(c["docs"], 1):
            d["filename"] = f"{c['claim_number']}_{i}_{d['doc_type'].lower()}.txt"
            d["sha256"] = hashlib.sha256(d["text"].encode("utf-8")).hexdigest()
            (DOC_DIR / d["filename"]).write_text(d["text"], encoding="utf-8", newline="\n")
            docs.append({"filename": d["filename"], "doc_type": d["doc_type"], "sha256": d["sha256"],
                         "fields": d["fields"]})
        truth["claims"].append({k: c[k] for k in ("claim_number", "claim_type", "scenario", "expected_rules",
                                                  "expected_flagged")} | {"documents": docs})
    truth["scans"] = make_scans(data)
    TRUTH_FILE.write_text(json.dumps(truth, indent=2, default=_json_default), encoding="utf-8")
    llm.reset_truth_cache()
    return truth


def make_scans(data: dict, count: int = 8) -> list[dict]:
    """Render a few documents as scanned-looking PNGs (for Document Intelligence / OCR later)."""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError:
        print("Pillow not installed - skipping scans")
        return []
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCAN_DIR.glob("*.png"):
        old.unlink()
    font = None
    for name in ("DejaVuSansMono.ttf", "consola.ttf", "cour.ttf"):
        try:
            font = ImageFont.truetype(name, 20)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    rng = random.Random(SEED)
    wanted = ["INVOICE", "MEDICAL_BILL", "CLAIM_FORM", "POLICE_REPORT", "INVOICE", "MEDICAL_BILL", "CLAIM_FORM",
              "INVOICE"]
    flagged = [c for c in data["claims"] if c["expected_rules"]]
    pool = flagged + [c for c in data["claims"] if not c["expected_rules"]]
    picked, used = [], set()
    for t in wanted[:count]:
        for c in pool:
            d = next((d for d in c["docs"] if d["doc_type"] == t), None)
            if d and c["claim_number"] not in used:
                used.add(c["claim_number"])
                picked.append((c, d))
                break
    out = []
    for c, d in picked:
        lines = d["text"].replace("₹", "Rs.").splitlines()
        w = 40 + 12 * max(len(line) for line in lines)
        h = 60 + 30 * len(lines)
        img = Image.new("L", (w, h), 246)
        draw = ImageDraw.Draw(img)
        for i, line in enumerate(lines):
            draw.text((30, 30 + i * 30), line, fill=rng.randint(25, 60), font=font)
        img = img.rotate(rng.uniform(-1.6, 1.6), expand=True, fillcolor=236)
        noise = Image.effect_noise(img.size, 18)
        img = Image.blend(img, noise, 0.08).filter(ImageFilter.GaussianBlur(0.6))
        name = d["filename"].replace(".txt", ".png")
        img.save(SCAN_DIR / name)
        out.append({"scan_file": f"scans/{name}", "source_document": d["filename"]})
    return out


def load_database(data: dict):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    people = {}
    for p in data["claimants"]:
        people[p["claimant_code"]] = Claimant(claimant_code=p["claimant_code"], full_name=p["full_name"],
                                              phone=p["phone"], address=p["address"])
        db.add(people[p["claimant_code"]])
    pols = {}
    for p in data["policies"]:
        pols[p["policy_number"]] = Policy(policy_number=p["policy_number"], holder_code=p["holder_code"],
                                          product_type=p["product_type"], sum_insured=Decimal(str(p["sum_insured"])),
                                          start_date=p["start_date"], end_date=p["end_date"])
        db.add(pols[p["policy_number"]])
    db.flush()
    claims = []
    for c in data["claims"]:
        claim = Claim(claim_number=c["claim_number"], policy_id=pols[c["policy_number"]].policy_id,
                      claimant_id=people[c["claimant_code"]].claimant_id, claim_type=c["claim_type"],
                      incident_date=c["incident_date"], reported_date=c["reported_date"],
                      claimed_amount=Decimal(str(c["claimed_amount"])), description=c["description"])
        db.add(claim)
        db.flush()
        for d in c["docs"]:
            db.add(Document(claim_id=claim.claim_id, doc_type=d["doc_type"], filename=d["filename"],
                            sha256=d["sha256"], text_content=d["text"]))
        claims.append(claim)
    db.commit()
    ensure_demo_users(db)  # drop_all removed the accounts too
    return db, claims


def pick_live(data: dict, limit: int | None) -> set[str]:
    numbers = [c["claim_number"] for c in data["claims"]]
    if limit is None:
        return set(numbers)
    rng = random.Random(SEED)
    flagged = [c["claim_number"] for c in data["claims"] if c["expected_rules"]]
    clean = [n for n in numbers if n not in flagged]
    k = min(len(flagged), (limit + 1) // 2)
    return set(rng.sample(flagged, k) + rng.sample(clean, min(len(clean), limit - k)))


def main(argv: list[str]):
    live = "--live" in argv
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    configured = settings.llm_provider
    if live and configured == "mock":
        print("WARNING: --live given but LLM_PROVIDER=mock in .env; using the mock extractor.")
    data = generate()
    write_files(data)
    db, claims = load_database(data)
    live_set = pick_live(data, limit) if live else set()
    print(f"Dataset: {len(claims)} claims, {sum(len(c['docs']) for c in data['claims'])} documents, "
          f"{len(data['claimants'])} claimants, {len(data['policies'])} policies. "
          f"Live AI on {len(live_set)} claims.")

    def provider_for(claim):
        settings.llm_provider = configured if claim.claim_number in live_set else "mock"

    # Failure telemetry for dashboards: first attempt on one claim times out, then succeeds on retry.
    provider_for(claims[0])
    settings.simulate_failure = "timeout"
    process_claim(db, claims[0])
    settings.simulate_failure = ""
    for i, c in enumerate(claims, 1):
        provider_for(c)
        process_claim(db, c, summarize=False)
        if c.claim_number in live_set:
            print(f"  live {i}/{len(claims)} {c.claim_number}")
    # Second rules pass so duplicates/rings see every claim. Documents are already read, so the only AI call
    # left is the reviewer briefing (RAG), written once per flagged claim with its final findings.
    for c in claims:
        provider_for(c)
        process_claim(db, c)
    settings.llm_provider = configured

    truth = {c["claim_number"]: c for c in data["claims"]}
    levels = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    mismatches = []
    print("\nFlagged / planted scenarios:")
    for c in claims:
        db.refresh(c)
        levels[c.risk_level] += 1
        got = sorted({f.rule_code for f in c.findings})
        t = truth[c.claim_number]
        if got != t["expected_rules"]:
            mismatches.append((c.claim_number, t["expected_rules"], got))
        if got or t["expected_rules"]:
            print(f"  {c.claim_number}  {c.risk_level:6} {c.risk_score:3}  {', '.join(got) or '-':55} "
                  f"[{t['scenario']}]")
    print(f"\nRisk levels: {levels}")
    if live_set:
        print("Live AI was used: run `python -m app.evaluate` for accuracy against the answer key.")
    elif mismatches:
        print(f"Answer-key check: {len(mismatches)} claim(s) differ:")
        for n, exp, got in mismatches:
            print(f"  {n}: expected {exp}, got {got}")
    else:
        print(f"Answer-key check: all {len(claims)} claims match the expected rules.")
    db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
