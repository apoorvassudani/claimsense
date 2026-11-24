"""RAG over policy wording: find the policy clause that backs up each rule finding.

Retrieval only. The clause is shown to the reviewer as evidence; it never changes the risk score,
which still comes from the deterministic rules.

Azure mode : policy clauses are embedded with Azure OpenAI and searched in Azure AI Search with
             hybrid search (vector similarity + keyword match in one query).
Local mode : if Azure AI Search is not configured or fails, a simple keyword search over the same
             clauses is used, so the app and tests keep working offline.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx

from ..config import settings
from . import llm

POLICY_DIR = Path(__file__).resolve().parents[3] / "data" / "policy_wording"
EMBED_DIMENSIONS = 1536  # text-embedding-3-small
PRODUCT_BY_PREFIX = {"GEN": "ALL", "MTR": "MOTOR", "HLT": "HEALTH", "PRP": "PROPERTY"}

QUERY_VERSION = "queries-v2"

# What to ask the policy for each rule. v1 used short generic questions ("claim made very soon after the
# policy started") and the word "policy" pulled GEN-1 (period of insurance) to the top too often: hit@1 77.5%,
# hit@3 97.5% on Azure hybrid search. v2 describes the situation the way the policy wording does.
RULE_QUERIES = {
    "POLICY_PERIOD": "loss or damage occurred before the policy start date or after the policy end date",
    "EARLY_CLAIM": "claim arising within the first 30 days after inception; proof the damage or illness did not exist before cover began; waiting period",
    "LATE_REPORTING": "claim notified to the company more than 30 days after the date of loss; reason for the delay",
    "OVER_SUM_INSURED": "amount claimed exceeds the sum insured, the maximum the company will pay",
    "AMOUNT_MISMATCH": "amount in the claim form differs from the amount on the supporting bills or invoices",
    "MISSING_DOCUMENT": "documents required to support the claim, such as the claim form, invoice, hospital bill or police report",
    "NAME_MISMATCH": "name of the insured on a document does not match the policy schedule and claim form",
    "POLICY_NUMBER_MISMATCH": "policy number shown on a supporting document does not match the claim form; inconsistent information",
    "DATE_MISMATCH": "date of loss shown on a document does not match the date declared in the claim form",
    "DUPLICATE_DOCUMENT": "same document submitted for more than one claim; reused or forged documents",
    "DUPLICATE_INVOICE": "bill or invoice already presented in support of another claim",
    "SHARED_PHONE": "claims that share a phone number or contact details with other claimants; referral for investigation",
    "SHARED_VEHICLE": "same vehicle registration claimed by different persons; ownership verification",
    "PROVIDER_CLUSTER": "many claims at the same hospital, garage or contractor within a short period; investigation",
    "SCAN_UNCLEAR": "information on a document is inconsistent with the policy schedule and claim form and must be verified",
}

# Clauses a reviewer would accept for each rule, used only to measure retrieval accuracy.
# A set means more than one clause is a correct answer (e.g. HLT-3 is the health-specific date rule).
EXPECTED = {
    "POLICY_PERIOD": "GEN-1", "LATE_REPORTING": "GEN-2", "OVER_SUM_INSURED": "GEN-3",
    "AMOUNT_MISMATCH": "GEN-4", "NAME_MISMATCH": "GEN-5", "POLICY_NUMBER_MISMATCH": "GEN-5",
    "DATE_MISMATCH": {"MOTOR": "GEN-5", "HEALTH": {"GEN-5", "HLT-3"}, "PROPERTY": "GEN-5"},
    "DUPLICATE_DOCUMENT": "GEN-6", "DUPLICATE_INVOICE": "GEN-6",
    "SHARED_PHONE": "GEN-7", "PROVIDER_CLUSTER": "GEN-7", "SCAN_UNCLEAR": "GEN-5",
    "SHARED_VEHICLE": {"MOTOR": {"MTR-2", "GEN-7"}},
    "EARLY_CLAIM": {"MOTOR": "MTR-3", "HEALTH": "HLT-2", "PROPERTY": "PRP-2"},
    "MISSING_DOCUMENT": {"MOTOR": "MTR-1", "HEALTH": "HLT-1", "PROPERTY": "PRP-1"},
}


class SearchError(Exception):
    category = "search_error"


@dataclass
class Clause:
    id: str
    product: str
    title: str
    content: str
    source: str


def load_clauses() -> list[Clause]:
    """Split each policy file into one chunk per clause ("## ID | Title" headings)."""
    clauses = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            cid, _, title = head.partition("|")
            cid = cid.strip()
            clauses.append(Clause(id=cid, product=PRODUCT_BY_PREFIX[cid.split("-")[0]], title=title.strip(),
                                  content=" ".join(body.split()), source=path.name))
    return clauses


def expected_clauses(rule_code: str, product: str) -> set[str]:
    exp = EXPECTED.get(rule_code)
    if isinstance(exp, dict):
        exp = exp.get(product)
    if exp is None:
        return set()
    return set(exp) if isinstance(exp, set) else {exp}


# ---------------------------------------------------------------- Azure AI Search (REST)
def _search_url(path: str) -> str:
    return (f"{settings.azure_search_endpoint.rstrip('/')}/indexes{path}"
            f"?api-version={settings.azure_search_api_version}")


def _search_call(method: str, path: str, body: dict) -> dict:
    try:
        resp = httpx.request(method, _search_url(path), json=body, timeout=settings.llm_timeout_s,
                             headers={"api-key": settings.azure_search_api_key})
    except httpx.HTTPError as exc:
        raise SearchError(type(exc).__name__) from exc
    if resp.status_code >= 400:
        err = SearchError(f"http_{resp.status_code}: {resp.text[:200]}")
        err.category = f"search_http_{resp.status_code}"
        raise err
    return resp.json() if resp.content else {}


def create_index() -> None:
    """Create (or update) the index: keyword-searchable text plus a vector field for embeddings."""
    name = settings.azure_search_index
    _search_call("PUT", f"/{name}", {
        "name": name,
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
            {"name": "product", "type": "Edm.String", "filterable": True},
            {"name": "title", "type": "Edm.String", "searchable": True},
            {"name": "content", "type": "Edm.String", "searchable": True},
            {"name": "source", "type": "Edm.String"},
            {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": True,
             "retrievable": False, "dimensions": EMBED_DIMENSIONS, "vectorSearchProfile": "clause-profile"},
        ],
        "vectorSearch": {
            "algorithms": [{"name": "clause-hnsw", "kind": "hnsw"}],
            "profiles": [{"name": "clause-profile", "algorithm": "clause-hnsw"}],
        },
    })


def upload_clauses(clauses: list[Clause]) -> int:
    vectors = llm.embed([f"{c.title}. {c.content}" for c in clauses])
    docs = [{"@search.action": "mergeOrUpload", "id": c.id, "product": c.product, "title": c.title,
             "content": c.content, "source": c.source, "content_vector": v} for c, v in zip(clauses, vectors)]
    _search_call("POST", f"/{settings.azure_search_index}/docs/index", {"value": docs})
    return len(docs)


def _azure_search(query: str, product: str, k: int) -> list[dict]:
    vector = llm.embed([query])[0]
    body = {
        "search": query,  # keyword half of the hybrid query
        "vectorQueries": [{"kind": "vector", "vector": vector, "fields": "content_vector", "k": k * 2}],
        "filter": f"product eq 'ALL' or product eq '{product}'",
        "select": "id,product,title,content,source",
        "top": k,
    }
    hits = _search_call("POST", f"/{settings.azure_search_index}/docs/search", body).get("value", [])
    return [{"clause_id": h["id"], "title": h["title"], "text": h["content"], "source": h["source"],
             "score": round(h.get("@search.score", 0), 4)} for h in hits]


# ---------------------------------------------------------------- local fallback
_STOP = {"the", "a", "an", "of", "to", "for", "on", "in", "is", "or", "and", "by", "than", "more", "with", "same",
         "was", "were", "not", "does", "at", "time", "different", "very", "after", "long", "from"}


def _tokens(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOP and len(w) > 2}


def _local_search(query: str, product: str, k: int) -> list[dict]:
    q = _tokens(query)
    scored = []
    for c in load_clauses():
        if c.product not in ("ALL", product):
            continue
        overlap = len(q & _tokens(f"{c.title} {c.title} {c.content}"))
        if overlap:
            scored.append((overlap, c))
    scored.sort(key=lambda t: -t[0])
    return [{"clause_id": c.id, "title": c.title, "text": c.content, "source": c.source, "score": float(s)}
            for s, c in scored[:k]]


# ---------------------------------------------------------------- public API
def search(query: str, product: str, k: int = 3) -> tuple[list[dict], str]:
    """Return (clauses, mode). mode is 'azure_hybrid' or 'local_keyword'."""
    if settings.search_enabled:
        return _azure_search(query, product, k), "azure_hybrid"
    return _local_search(query, product, k), "local_keyword"


@lru_cache(maxsize=256)
def _clauses_for_rule_cached(rule_code: str, product: str, mode_key: str, k: int) -> tuple:
    hits, mode = search(RULE_QUERIES[rule_code], product, k=k)
    return tuple(hits), mode


def clauses_for_rule(rule_code: str, product: str, k: int = 3) -> tuple[list[dict], str]:
    """Top-k policy clauses for a rule finding. Cached: the same rule on the same product asks the same question."""
    if rule_code not in RULE_QUERIES:
        return [], "none"
    hits, mode = _clauses_for_rule_cached(rule_code, product, "azure" if settings.search_enabled else "local", k)
    return [dict(h) for h in hits], mode


def clear_cache() -> None:
    _clauses_for_rule_cached.cache_clear()
