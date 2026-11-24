"""Build the policy-clause index in Azure AI Search, then measure retrieval accuracy.

Usage:
  python -m app.rag_index           create index, embed and upload clauses, then run the accuracy check
  python -m app.rag_index --check   only run the accuracy check (works offline with local keyword search)

The check asks the question for every rule and product, and counts how often the expected clause
comes back first (hit@1) or in the top 3 (hit@3). Results are saved to docs/retrieval-report.md.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import settings
from .services import policy_rag

REPORT = Path(__file__).resolve().parents[2] / "docs" / "retrieval-report.md"
PRODUCTS = ["MOTOR", "HEALTH", "PROPERTY"]


def build() -> None:
    if not settings.search_enabled:
        sys.exit("Azure AI Search is not configured. Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY "
                 "(plus the Azure OpenAI embedding settings) in backend/.env.")
    clauses = policy_rag.load_clauses()
    print(f"Creating index '{settings.azure_search_index}' ...")
    policy_rag.create_index()
    print(f"Embedding and uploading {len(clauses)} clauses with {settings.azure_openai_embedding_deployment} ...")
    print(f"Uploaded {policy_rag.upload_clauses(clauses)} clauses.")


def check() -> None:
    rows, hit1, hit3, total, mode = [], 0, 0, 0, "none"
    for rule, query in policy_rag.RULE_QUERIES.items():
        for product in PRODUCTS:
            expected = policy_rag.expected_clauses(rule, product)
            if not expected:
                continue
            hits, mode = policy_rag.search(query, product, k=3)
            got = [h["clause_id"] for h in hits]
            top_ok = bool(got) and got[0] in expected
            total += 1
            hit1 += top_ok
            hit3 += bool(expected & set(got))
            rows.append(f"| {rule} | {product} | {' or '.join(sorted(expected))} | {', '.join(got) or '-'} | "
                        f"{'yes' if top_ok else 'no'} |")
    pct = lambda n: f"{100 * n / total:.1f}%"
    summary = f"Retrieval mode: **{mode}** ({policy_rag.QUERY_VERSION}). Questions: **{total}**. Hit@1: **{pct(hit1)}**. Hit@3: **{pct(hit3)}**."
    REPORT.write_text("\n".join([
        "# ClaimSense retrieval report", "",
        f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.", "", summary, "",
        "Hit@1 = the expected policy clause was the top result. Hit@3 = it was in the top three.",
        "Previous run (queries-v1, Azure hybrid): hit@1 77.5%, hit@3 97.5%. Local keyword baseline: 77.5% / 95.0%.",
        "Note: queries-v2 was written after looking at the v1 misses, so its score is optimistic on this test set.", "",
        "| Rule | Product | Expected | Retrieved (top 3) | Top-1 correct |", "|---|---|---|---|---|", *rows, ""]),
        encoding="utf-8")
    print(summary)
    print(f"Saved to {REPORT}")


if __name__ == "__main__":
    if "--check" not in sys.argv:
        build()
    check()
