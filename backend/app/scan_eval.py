"""Evaluate OCR on the scanned documents: scan -> OCR text -> the same extraction prompt -> compare to the answer key.

Usage:  python -m app.scan_eval
Needs live Azure (vision OCR with gpt-4.1-mini, or Document Intelligence when configured).
Writes docs/scan-report.md. The clean-text version of the same documents scores 100%, so the gap shows
what scanning costs.
"""
import difflib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .evaluate import FIELDS, pct, same
from .services import llm, ocr
from .services.extraction import PROMPT_VERSION, SYSTEM_PROMPT, parse_fields

ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = ROOT / "data" / "sample_documents"
TRUTH = ROOT / "data" / "ground_truth.json"
REPORT = ROOT / "docs" / "scan-report.md"


def _norm(text: str) -> str:
    text = text.replace("₹", "Rs.")  # the scans print the rupee sign as "Rs."
    return re.sub(r"\s+", " ", text).strip().lower()


def main() -> None:
    if ocr.engine() is None or settings.llm_provider == "mock":
        sys.exit("Needs live Azure: LLM_PROVIDER=azure (vision OCR) or AZURE_DOCINTEL_* for Document Intelligence.")
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    docs = {d["filename"]: (d, c) for c in truth["claims"] for d in c["documents"]}
    scans = truth.get("scans", [])
    if not scans:
        sys.exit("No scans in the answer key. Run `python -m app.seed` first.")

    field_ok, field_n = defaultdict(int), defaultdict(int)
    rows, diffs, sims, failures = [], [], [], 0
    print(f"OCR engine: {ocr.engine_label()} | extraction: {settings.model_label} ({PROMPT_VERSION})")
    for s in scans:
        src, _claim = docs[s["source_document"]]
        image = (DOC_DIR / s["scan_file"]).read_bytes()
        try:
            o = ocr.read(image, "image/png")
            text = o.text[:6000]
            r = llm.complete_json(SYSTEM_PROMPT, f"Declared document type: {src['doc_type']}\n---\n{text}\n---", text)
            fields = parse_fields(r.text).model_dump()
        except Exception as exc:
            failures += 1
            rows.append(f"| {s['scan_file']} | failed ({getattr(exc, 'category', type(exc).__name__)}) | - | - |")
            print(f"  {s['scan_file']}: FAILED {exc}")
            continue
        source_text = (DOC_DIR / s["source_document"]).read_text(encoding="utf-8")
        sim = difflib.SequenceMatcher(None, _norm(source_text), _norm(o.text)).ratio()
        sims.append(sim)
        ok = 0
        for f in FIELDS:
            t, p = src["fields"].get(f), fields.get(f)
            field_n[f] += 1
            if same(f, t, p):
                field_ok[f] += 1
                ok += 1
            else:
                diffs.append(f"{s['scan_file']}: {f} expected {t!r}, got {p!r}")
        rows.append(f"| {s['scan_file']} | {sim:.1%} | {ok}/{len(FIELDS)} | {src['doc_type']} |")
        print(f"  {s['scan_file']}: text match {sim:.1%}, fields {ok}/{len(FIELDS)}")

    total_ok, total_n = sum(field_ok.values()), sum(field_n.values())
    out = ["# ClaimSense scan (OCR) report", "",
           f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}. OCR engine: **{ocr.engine_label()}**. "
           f"Extraction: {settings.model_label} ({PROMPT_VERSION}).", "",
           f"Scans: **{len(scans)}**, failed: **{failures}**. "
           f"Average OCR text match vs. the original: **{(sum(sims) / len(sims)):.1%}**." if sims else "No scans read.",
           f"Field accuracy on scans: **{pct(total_ok, total_n)}** (clean-text version of the same documents: 100%).", "",
           "Text match compares the OCR output with the original document text after collapsing whitespace "
           "(1.0 = identical). Field accuracy uses the same answer key and rules as the main evaluation.", "",
           "| Scan | Text match | Fields correct | Type |", "|---|---|---|---|", *rows, "",
           "| Field | Accuracy |", "|---|---|", *[f"| {f} | {pct(field_ok[f], field_n[f])} |" for f in FIELDS], ""]
    if diffs:
        out += ["Differences:", ""] + [f"- {d}" for d in diffs] + [""]
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[2:5]))
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    main()
