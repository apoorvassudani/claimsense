"""Held-out stress test: data the prompts and queries were never tuned on.

Usage:
  python -m app.stress_test              full run with live Azure (about 25 minutes), seed 7310
  python -m app.stress_test --seed 8128  a fresh, never-seen set: use after fixing anything found with 7310
  python -m app.stress_test --offline    plumbing check only: mock extractor, no OCR, no API calls

What is different from the development set (data/ground_truth.json):
  - new claims from a different random seed, with new people and new hospital/garage/contractor names
  - realistic fraud rate: about 1 in 10 claims has a planted problem (development set: about 1 in 3)
  - messy documents: other label wording and abbreviations, typos in labels, boilerplate noise,
    lost line breaks, all-caps, different separators, occasionally a missing label
  - about 15% of documents arrive as scans (light / medium / heavy degradation) and go through OCR
  - an OCR ladder: the same 10 documents scanned at all three levels

It runs in its own SQLite database (data/stress/stress.db), so the main PostgreSQL data is untouched.
Report: docs/stress-report.md
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STRESS_DIR = ROOT / "data" / "stress"
STRESS_DIR.mkdir(parents=True, exist_ok=True)
# Must be set before anything imports the database settings.
os.environ["DATABASE_URL"] = f"sqlite:///{(STRESS_DIR / 'stress.db').as_posix()}"

import difflib  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import textwrap  # noqa: E402
import time  # noqa: E402
from collections import defaultdict  # noqa: E402
from contextlib import contextmanager  # noqa: E402
from datetime import date, datetime, timedelta, timezone  # noqa: E402

from sqlalchemy import select  # noqa: E402

from . import datagen  # noqa: E402
from . import evaluate  # noqa: E402
from .config import settings  # noqa: E402
from .models import Claim, Document, Extraction  # noqa: E402
from .seed import load_database  # noqa: E402
from .services import llm, ocr  # noqa: E402
from .services.extraction import SYSTEM_PROMPT, parse_fields  # noqa: E402
from .services.pipeline import process_claim  # noqa: E402

STRESS_SEED = 7310
DOC_DIR = STRESS_DIR / "documents"
SCAN_DIR = STRESS_DIR / "scans"
TRUTH_FILE = STRESS_DIR / "ground_truth.json"
REPORT = ROOT / "docs" / "stress-report.md"
SCAN_SHARE = 15  # percent of documents delivered as scans
LEVELS = ["light", "medium", "heavy"]

# New names, so nothing the prompts were tuned on reappears.
NEW_FIRST = ["Ishaan", "Kabir", "Arjun", "Dev", "Yash", "Tanmay", "Harsh", "Pranav", "Rajat", "Omkar", "Sameer",
             "Gaurav", "Kunal", "Abhay", "Rehan", "Meera", "Tara", "Ananya", "Kavya", "Riya", "Sneha", "Pooja",
             "Nandini", "Ira", "Shreya", "Divya", "Aditi", "Lavanya", "Bhavna", "Farah"]
NEW_LAST = ["Bhatt", "Chopra", "Desai", "Bhatia", "Malhotra", "Pillai", "Menon", "Saxena", "Kapoor", "Thakur",
            "Pandey", "Mishra", "Bose", "Ghosh", "Dutta", "Hegde", "Shetty", "Kamath", "Naidu", "Rathore",
            "Chauhan", "Sinha", "Agarwal", "Bajaj", "Khanna"]
NEW_GARAGE = ["Falcon", "Meridian", "Granite", "Sapphire", "Tamarind", "Monsoon", "Saffron", "Peacock", "Banyan",
              "Horizon", "Quartz", "Lantern", "Comet", "Marigold"]
NEW_HOSPITAL = ["Riverside", "Greenfield", "Starlight", "Harmony", "Bluebell", "Crescent", "Evergreen", "Orchid",
                "Pinecrest", "Silverline", "Maplewood", "Dawnview"]
NEW_CONTRACTOR = ["Keystone", "Mortar & Beam", "Plumbline", "Ridgeway", "Cornerstone"]
RING_GARAGE = "Vantage Auto Point"


@contextmanager
def new_names():
    """Swap the generator's name lists for unseen ones, then restore them."""
    keep = {k: getattr(datagen, k) for k in ("FIRST", "LAST", "GARAGE_WORDS", "HOSPITAL_WORDS", "CONTRACTOR_WORDS")}
    datagen.FIRST, datagen.LAST = NEW_FIRST, NEW_LAST
    datagen.GARAGE_WORDS, datagen.HOSPITAL_WORDS, datagen.CONTRACTOR_WORDS = NEW_GARAGE, NEW_HOSPITAL, NEW_CONTRACTOR
    try:
        yield
    finally:
        for k, v in keep.items():
            setattr(datagen, k, v)


class StressGenerator(datagen.Generator):
    def plant(self, make, **kw):
        """Add a scenario claim; if this seed overbooked the chosen provider, try another random draw."""
        for _ in range(20):
            try:
                return make(**kw)
            except RuntimeError:
                continue
        raise RuntimeError(f"could not place scenario {kw.get('scenario')!r}")

    def build(self):
        r = self.r
        for make, n in ((self.motor, 62), (self.health, 40), (self.property, 24)):
            for _ in range(n):
                try:
                    make()
                except RuntimeError:  # this seed overbooked a provider's calendar: skip one legit claim
                    pass
        # innocent oddities (should NOT be flagged)
        self.plant(self.motor, scenario="innocent: claim 4% above invoice", claim_factor=1.04)
        self.plant(self.property, scenario="innocent: claim 6% above invoice", claim_factor=1.06)
        self.plant(self.health, scenario="innocent: reported 18 days after discharge", report_delay=18)
        self.plant(self.motor, scenario="innocent: reported 25 days after incident", report_delay=25)
        # planted problems
        self.plant(self.motor, scenario="incident two days before policy start", expected={"POLICY_PERIOD"}, start_offset=-2)
        self.plant(self.property, scenario="claim exceeds sum insured", expected={"OVER_SUM_INSURED"}, heavy=True, si_factor=0.7)
        self.plant(self.health, scenario="inflated claim vs hospital bill", expected={"AMOUNT_MISMATCH"}, claim_factor=1.4)
        self.plant(self.motor, scenario="early claim", expected={"EARLY_CLAIM"}, start_offset=15)
        src = self.plant(self.motor, scenario="duplicate source: invoice later reused by another claim",
                         expected={"DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE", "SHARED_VEHICLE"}, inv_variant=2)
        src_last = src["claimant"]["full_name"].split()[1]
        copier = self.person(src["provider_loc"], last=r.choice([n for n in NEW_LAST if n != src_last]))
        self.plant(self.motor, scenario="reused invoice file from another claim",
                   expected={"DUPLICATE_DOCUMENT", "DUPLICATE_INVOICE", "NAME_MISMATCH", "SHARED_VEHICLE"},
                   copy_invoice_from=src, claimant=copier, garage=src["provider"],
                   incident=self.free_date(src["provider"], gap=31))
        loc = datagen.LOCALITIES[3]
        phone = self.phone()
        base = self.free_date(None, date(2025, 11, 1), date(2026, 4, 30))
        for i in range(3):
            cl = self.person(loc, phone=phone if i < 2 else None)
            self.plant(self.motor, scenario="garage ring: claims clustered at one garage",
                       expected={"PROVIDER_CLUSTER", "SHARED_PHONE"} if i < 2 else {"PROVIDER_CLUSTER"},
                       claimant=cl, garage=RING_GARAGE, incident=base + timedelta(days=i * 7 + r.randint(0, 3)),
                       description="Hit by an unidentified vehicle while parked")
        self.plant(self.health, scenario="hospital bill in another person's name", expected={"NAME_MISMATCH"}, patient="OTHER")
        self.plant(self.motor, scenario="reported 40 days after incident", expected={"LATE_REPORTING"}, report_delay=40)
        self.plant(self.property, scenario="contractor invoice not submitted", expected={"MISSING_DOCUMENT"}, invoice=False)
        return self


def generate_stress(seed: int = STRESS_SEED) -> dict:
    """Same structure as datagen.generate(), with the held-out generator and HLD- claim numbers."""
    from .services.rules import SEVERITY
    with new_names():
        g = StressGenerator(seed).build()
    claims = sorted(g.claims, key=lambda c: c["incident_date"])
    out = []
    for i, c in enumerate(claims, 1):
        number = f"HLD-{c['incident_date'].year}-{i:05d}"
        score = min(100, sum(datagen.WEIGHTS[SEVERITY[x]] for x in c["expected_rules"]))
        out.append({
            "claim_number": number, "claim_type": c["claim_type"], "claimant_code": c["claimant"]["claimant_code"],
            "policy_number": c["policy"]["policy_number"], "incident_date": c["incident_date"],
            "reported_date": c["reported_date"], "claimed_amount": c["claimed_amount"],
            "description": c["description"], "scenario": c["scenario"], "expected_rules": c["expected_rules"],
            "expected_flagged": score >= 20,
            "docs": [{"doc_type": d["doc_type"], "text": d["text"], "fields": d["fields"]} for d in c["docs"]]})
    claimants = [{k: p[k] for k in ("claimant_code", "full_name", "phone", "address")} for p in g.claimants]
    return {"claimants": claimants, "policies": g.policies, "claims": out}


# ---------------------------------------------------------------- messy layouts
LABELS = [
    (r"\b(Invoice No|Bill No|Receipt No)\b\.?", ["Inv #", "Bill#", "Ref. No", "Invoice Ref", "Voucher No"]),
    (r"\b(Policy No\.|Policy number|Insurance Policy)", ["Pol. No", "Policy #", "Ins. Policy Ref", "PolicyNo"]),
    (r"\bName of Insured\b", ["Insured", "Name", "Policyholder"]),
    (r"\bFull name\b", ["Name", "Insured name"]),
    (r"\bPatient Name\b", ["Pt. Name", "Patient", "Name of Pt"]),
    (r"\b(Customer|Client)(?=:)", ["Billed to", "Cust.", "Party"]),
    (r"\bDate of Admission\b", ["DOA", "Admit Dt", "Adm. Date"]),
    (r"\bAdmitted on\b", ["Admission", "Admit Dt"]),
    (r"\bDate of Discharge\b", ["DOD", "Disch. Dt", "Discharged on"]),
    (r"\b(Contact Number|Mobile)\b", ["Ph", "Mob.", "Tel", "Cell"]),
    (r"\bVehicle Reg\. No\.", ["Regn No", "Veh. No", "Reg #"]),
    (r"\bVehicle involved\b", ["Veh. No", "Vehicle"]),
    (r"\b(NET AMOUNT|GRAND TOTAL|NET PAYABLE)\b", ["AMT PAYABLE", "TOTAL (INR)", "NET AMT", "TOTAL BILL"]),
    (r"\bAmount Claimed\b", ["Claim Amt", "Amt claimed", "Loss amount"]),
    (r"\bEstimated loss\b", ["Claim Amt", "Est. loss"]),
    (r"\bDate of Intimation\b", ["Intimated on", "Dt. of Intim.", "Reported on"]),
    (r"\bDate of Loss\b", ["DOL", "Loss Dt", "Date of accident"]),
    (r"\bIncident on\b", ["Loss Dt", "Accident on"]),
    (r"\bDate & time of accident\b", ["Accident Dt/Time", "When"]),
    (r"\bDate:", ["Dt:", "Dated:", "Date -"]),
    (r"\bReport No\b", ["Ref No", "Rpt No"]),
    (r"\bReported by\b", ["Complainant", "Informant"]),
]
NOISE = ["Page 1 of 1", "*** This is a computer generated document ***", "E. & O.E.", "Thank you for your business!",
         "[ STAMP: RECEIVED ]", "Authorised Signatory: ____________", "HSN/SAC: 998714",
         "Subject to local jurisdiction only", "Original for recipient", "Please retain this copy for your records"]
FOOTER = "SYNTHETIC TEST DOCUMENT - NOT A REAL RECORD"


def _typo(word: str, r: random.Random) -> str:
    if len(word) < 4:
        return word
    i = r.randint(1, len(word) - 3)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def messify(text: str) -> tuple[str, list[str]]:
    """Rewrite a document in an unseen, messier style. Deterministic per document, so a reused
    (byte-identical) file stays byte-identical and duplicate detection still applies."""
    r = random.Random(hashlib.sha256(text.encode()).hexdigest())
    body = text.replace(FOOTER, "").rstrip()
    applied = []
    if r.random() < 0.10:
        new, n = re.subn(r"(Invoice No|Bill No|Receipt No)\.?:?\s*", "", body, count=1)
        if n:
            body = new
            applied.append("missing label")
    changed = False
    for pattern, options in LABELS:
        pick = r.choice(options)
        body, n = re.subn(pattern, pick, body)
        changed |= bool(n)
    if changed:
        applied.append("relabelled")
    lines = body.splitlines()
    typos = 0
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)([A-Za-z][A-Za-z .#/&()-]{2,30}?)(\s*(?::|\.{3,})\s)", line)  # real labels only
        if m and r.random() < 0.15:
            words = m.group(2).split(" ")
            j = max(range(len(words)), key=lambda k: len(words[k]))
            words[j] = _typo(words[j], r)
            lines[i] = m.group(1) + " ".join(words) + line[m.end(2):]
            typos += 1
    if typos:
        applied.append("typos")
    for _ in range(r.randint(1, 3)):
        lines.insert(r.randint(0, len(lines)), r.choice(NOISE))
    applied.append("noise lines")
    body = "\n".join(lines)
    if r.random() < 0.3:
        sep = r.choice([":- ", " = ", " - ", "\t"])
        body = re.sub(r"(?<=[A-Za-z.#)])\s*: (?=\S)", sep, body)
        applied.append("separators")
    if r.random() < 0.3:
        body = re.sub(r" ?\.{4,} ?", r.choice([" ", " -- ", ": "]), body)
        applied.append("leaders")
    if r.random() < 0.10:
        body = body.upper()
        applied.append("all caps")
    if r.random() < 0.20:
        body = " ".join(line.strip() for line in body.splitlines() if line.strip())
        applied.append("lost line breaks")
    return body + f"\n\n{FOOTER}\n", applied


# ---------------------------------------------------------------- scans
def _font(size: int = 20):
    from PIL import ImageFont
    for name in ("DejaVuSansMono.ttf", "consola.ttf", "cour.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_scan(text: str, level: str, seed: str) -> bytes:
    """Render text as a degraded scan (JPEG). Heavier levels add tilt, noise, blur, uneven lighting,
    speckles and low resolution. Still readable to a person at every level (that is the fair test)."""
    from PIL import Image, ImageDraw, ImageFilter
    rot, noise, blur, scale, quality, shadow, specks = {
        "light": (1.0, 0.08, 0.5, 1.0, 85, 0, 0),
        "medium": (2.5, 0.20, 0.9, 0.6, 45, 40, 150),
        "heavy": (4.5, 0.30, 1.2, 0.45, 25, 80, 600)}[level]
    r = random.Random(seed + level)
    lines = []
    for line in text.replace("₹", "Rs.").splitlines():
        lines += textwrap.wrap(line, 90) or [""]
    w = 40 + 12 * max(len(line) for line in lines)
    h = 60 + 30 * len(lines)
    img = Image.new("L", (w, h), 246)
    draw = ImageDraw.Draw(img)
    font = _font()
    for i, line in enumerate(lines):
        draw.text((30, 30 + i * 30), line, fill=r.randint(25, 80), font=font)
    for _ in range(specks):  # dust and toner specks
        x, y = r.randrange(w), r.randrange(h)
        draw.point((x, y), fill=r.randint(60, 160))
    angle = r.choice([-1, 1]) * r.uniform(rot * 0.6, rot)
    img = img.rotate(angle, expand=True, fillcolor=230)
    if shadow:  # uneven lighting, like a phone photo of a page
        grad = Image.linear_gradient("L").rotate(r.choice([0, 90, 180, 270])).resize(img.size)
        img = Image.composite(img, Image.new("L", img.size, 255 - shadow), grad.point(lambda v: 255 - v // 2))
    img = Image.blend(img, Image.effect_noise(img.size, 60), noise).filter(ImageFilter.GaussianBlur(blur))
    if scale < 1:
        small = img.resize((int(img.width * scale), int(img.height * scale)))
        img = small.resize(img.size)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def scan_level(text: str) -> str | None:
    h = int(hashlib.sha256(("scan" + text).encode()).hexdigest(), 16)
    return LEVELS[(h // 100) % 3] if h % 100 < SCAN_SHARE else None


# ---------------------------------------------------------------- build files
def _json_default(o):
    return o.isoformat() if isinstance(o, date) else str(o)


def build(offline: bool, seed: int = STRESS_SEED) -> tuple[dict, dict]:
    """Generate claims, messify documents, render scans, OCR them (live), write files and answer key."""
    data = generate_stress(seed)
    for d in (DOC_DIR, SCAN_DIR):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.iterdir():
            old.unlink()
    truth = {"seed": seed, "note": "Held-out stress set. Never used for tuning prompts or queries.",
             "claims": []}
    meta = {}  # filename -> {source, transforms, ocr_ms}
    for c in data["claims"]:
        docs = []
        for i, d in enumerate(c["docs"], 1):
            text, applied = messify(d["text"])
            level = None if offline else scan_level(text)
            stem = f"{c['claim_number']}_{i}_{d['doc_type'].lower()}"
            if level:
                image = render_scan(text, level, hashlib.sha256(text.encode()).hexdigest())
                d["filename"] = stem + ".jpg"
                (SCAN_DIR / d["filename"]).write_bytes(image)
                d["sha256"] = hashlib.sha256(image).hexdigest()
                d["scan"] = (image, level)
            else:
                d["filename"] = stem + ".txt"
                d["sha256"] = hashlib.sha256(text.encode()).hexdigest()
            d["text"] = text
            (DOC_DIR / (stem + ".txt")).write_text(text, encoding="utf-8", newline="\n")
            meta[d["filename"]] = {"source": f"scan-{level}" if level else "text", "transforms": applied}
            docs.append({"filename": d["filename"], "doc_type": d["doc_type"], "sha256": d["sha256"],
                         "fields": d["fields"], "source": meta[d["filename"]]["source"], "transforms": applied})
        truth["claims"].append({k: c[k] for k in ("claim_number", "claim_type", "scenario", "expected_rules",
                                                  "expected_flagged")} | {"documents": docs})
    TRUTH_FILE.write_text(json.dumps(truth, indent=2, default=_json_default), encoding="utf-8")
    return data, meta


def ocr_scans(data: dict, meta: dict) -> None:
    """Replace each scanned document's text with what OCR reads from its image (as an upload would)."""
    scans = [d for c in data["claims"] for d in c["docs"] if "scan" in d]
    print(f"OCR on {len(scans)} scanned documents with {ocr.engine_label()} ...")
    done = {}
    for n, d in enumerate(scans, 1):
        image, level = d["scan"]
        key = d["sha256"]
        if key not in done:  # a reused file is the same image: read it once
            t0 = time.perf_counter()
            try:
                done[key] = (ocr.read(image, "image/jpeg").text, int((time.perf_counter() - t0) * 1000))
            except Exception as exc:
                print(f"  OCR failed on {d['filename']}: {getattr(exc, 'category', exc)}")
                done[key] = ("", None)
        d["ocr_text"], meta[d["filename"]]["ocr_ms"] = done[key]
        meta[d["filename"]]["ocr_match"] = difflib.SequenceMatcher(
            None, _norm(d["text"]), _norm(d["ocr_text"])).ratio() if d["ocr_text"] else 0.0
        d["text"] = d["ocr_text"] or "[OCR failed]"
        if n % 10 == 0:
            print(f"  {n}/{len(scans)}")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("₹", "Rs.")).strip().lower()


# ---------------------------------------------------------------- OCR ladder
def ocr_ladder(data: dict) -> list[str]:
    """Same 10 documents at light / medium / heavy: where does OCR start to break?"""
    pool = [d for c in data["claims"] for d in c["docs"] if "scan" not in d]
    r = random.Random(STRESS_SEED)
    by_type = defaultdict(list)
    for d in pool:
        by_type[d["doc_type"]].append(d)
    picked = []
    while len(picked) < 10:
        for t in ("INVOICE", "MEDICAL_BILL", "CLAIM_FORM", "POLICE_REPORT"):
            if by_type[t] and len(picked) < 10:
                picked.append(by_type[t].pop(r.randrange(len(by_type[t]))))
    print(f"OCR ladder: {len(picked)} documents x {len(LEVELS)} levels ...")
    match, fields_ok, fields_n = defaultdict(list), defaultdict(int), defaultdict(int)
    for d in picked:
        for level in LEVELS:
            image = render_scan(d["text"], level, "ladder" + d["filename"])
            try:
                text = ocr.read(image, "image/jpeg").text
                raw = llm.complete_json(SYSTEM_PROMPT,
                                        f"Declared document type: {d['doc_type']}\n---\n{text[:6000]}\n---", text)
                got = parse_fields(raw.text).model_dump()
            except Exception:
                text, got = "", {}
            match[level].append(difflib.SequenceMatcher(None, _norm(d["text"]), _norm(text)).ratio())
            for f in evaluate.FIELDS:
                fields_n[level] += 1
                fields_ok[level] += evaluate.same(f, d["fields"].get(f), got.get(f))
    out = ["## OCR ladder (same 10 documents, three scan qualities)", "",
           "| Scan quality | OCR text match | Field accuracy |", "|---|---|---|"]
    for level in LEVELS:
        avg = sum(match[level]) / len(match[level])
        out.append(f"| {level} | {avg:.1%} | {evaluate.pct(fields_ok[level], fields_n[level])} |")
    return out + ["", "Light: slight tilt and blur. Medium: more tilt, noise, specks, uneven lighting, 60% resolution, "
                      "JPEG artefacts. Heavy: strong tilt and noise, dark shadow, many specks, 45% resolution, heavy "
                      "compression.", ""]


# ---------------------------------------------------------------- per-document breakdown
def breakdown(db, truth: dict, meta: dict) -> list[str]:
    by_source, by_transform = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    docs_by_source = defaultdict(int)
    for tc in truth["claims"]:
        claim = db.scalar(select(Claim).where(Claim.claim_number == tc["claim_number"]))
        for td in tc["documents"]:
            doc = db.scalar(select(Document).where(Document.claim_id == claim.claim_id,
                                                   Document.filename == td["filename"]))
            ext = db.scalar(select(Extraction).where(Extraction.document_id == doc.document_id, Extraction.is_valid)
                            .order_by(Extraction.extraction_id.desc()).limit(1))
            fields = ext.fields if ext else {}
            ok = sum(evaluate.same(f, td["fields"].get(f), fields.get(f)) for f in evaluate.FIELDS)
            src = meta[td["filename"]]["source"]
            docs_by_source[src] += 1
            by_source[src][0] += ok
            by_source[src][1] += len(evaluate.FIELDS)
            for t in meta[td["filename"]]["transforms"]:
                by_transform[t][0] += ok
                by_transform[t][1] += len(evaluate.FIELDS)
    order = ["text"] + [f"scan-{lv}" for lv in LEVELS]
    out = ["## Extraction by how the document arrived", "",
           "| Source | Documents | Field accuracy | OCR text match |", "|---|---|---|---|"]
    for src in order:
        if docs_by_source[src]:
            ms = [m["ocr_match"] for m in meta.values() if m["source"] == src and "ocr_match" in m]
            om = f"{sum(ms) / len(ms):.1%}" if ms else "-"
            out.append(f"| {src} | {docs_by_source[src]} | {evaluate.pct(*by_source[src])} | {om} |")
    out += ["", "## Extraction by layout change (a document can have several)", "",
            "| Change | Documents | Field accuracy |", "|---|---|---|"]
    for t, (ok, n) in sorted(by_transform.items(), key=lambda kv: kv[1][0] / max(kv[1][1], 1)):
        out.append(f"| {t} | {n // len(evaluate.FIELDS)} | {evaluate.pct(ok, n)} |")
    return out + [""]


def workload(db, truth: dict) -> list[str]:
    exp = {c["claim_number"]: c["expected_flagged"] for c in truth["claims"]}
    flagged = {c.claim_number for c in db.scalars(select(Claim)) if c.status == "NEEDS_REVIEW"}
    tp = sum(1 for n in flagged if exp.get(n))
    should = sum(exp.values())
    return ["## Reviewer workload at a realistic fraud rate", "",
            f"- Claims: **{len(exp)}**; with a real problem that needs review: **{should}** "
            f"({100 * should / len(exp):.1f}%).",
            f"- Sent to review: **{len(flagged)}** ({100 * len(flagged) / len(exp):.1f}% of the queue).",
            f"- Of those, real problems: **{tp}** (review-queue precision {evaluate.pct(tp, len(flagged))}); "
            f"problems missed: **{should - tp}**.", ""]


# ---------------------------------------------------------------- main
def main(argv: list[str]) -> None:
    offline = "--offline" in argv
    seed = int(argv[argv.index("--seed") + 1]) if "--seed" in argv else STRESS_SEED
    if offline:
        settings.llm_provider = "mock"
    elif settings.llm_provider == "mock" or ocr.engine() is None:
        sys.exit("The stress test needs live Azure (LLM_PROVIDER=azure). Use --offline for a plumbing check.")
    t_start = time.perf_counter()
    print(f"Generating held-out data (seed {seed}) ...")
    data, meta = build(offline, seed)
    truth = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))
    n_docs = sum(len(c["docs"]) for c in data["claims"])
    print(f"  {len(data['claims'])} claims, {n_docs} documents, "
          f"{sum(1 for m in meta.values() if m['source'] != 'text')} scans")
    if not offline:
        ocr_scans(data, meta)
    db, claims = load_database(data)
    for c in data["claims"]:
        for d in c["docs"]:
            if "scan" in d:
                doc = db.scalar(select(Document).where(Document.filename == d["filename"]))
                doc.ocr_engine = ocr.engine_label()
    db.commit()
    print(f"Processing {len(claims)} claims with {settings.model_label} ...")
    for i, c in enumerate(claims, 1):
        process_claim(db, c, summarize=False)
        if i % 10 == 0:
            print(f"  read {i}/{len(claims)}  ({time.perf_counter() - t_start:.0f}s)")
    for c in claims:  # second pass: cross-claim rules see everything, then briefings
        process_claim(db, c)
    ladder = [] if offline else ocr_ladder(data)
    parts = breakdown(db, truth, meta) + workload(db, truth)
    db.close()
    ev = evaluate.main([] if not offline else ["--include-mock"], truth_file=TRUTH_FILE,
                       report=STRESS_DIR / "evaluation.md", title="Stress evaluation")
    ev_body = ev[ev.index("## AI field extraction"):] if "## AI field extraction" in ev else ev
    transforms = defaultdict(int)
    for m in meta.values():
        for t in m["transforms"]:
            transforms[t] += 1
    previous = ([] if seed == STRESS_SEED else [
        f"**Fresh test set (seed {seed}).** The scan-misread handling was added after the first held-out run "
        f"(seed {STRESS_SEED}: 8 of 132 clean claims wrongly sent to review, review-queue precision 55.6%, "
        "no problems missed). This set was generated afterwards and never looked at before this run.", ""])
    head = ["# ClaimSense held-out stress test", "",
            f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} in {time.perf_counter() - t_start:.0f}s. "
            f"Extraction: {settings.model_label}. OCR: {ocr.engine_label() if not offline else 'none (offline)'}.", "",
            "This data was **never used to tune** prompts or retrieval queries: new seed, new people and provider "
            "names, messier document layouts, scans, and a realistic fraud rate. Development-set results for "
            "comparison: 100% extraction, 100% routing.", "",
            *previous,
            f"Seed: **{seed}**. Documents: **{n_docs}**. Layout changes applied: "
            + ", ".join(f"{k} {v}" for k, v in sorted(transforms.items(), key=lambda kv: -kv[1])) + ".", ""]
    report = head + parts + ladder + ev_body
    REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(head[2:3] + parts))
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    main(sys.argv[1:])
