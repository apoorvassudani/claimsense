"""Search the policy wording (the RAG knowledge base) directly, e.g. from Swagger UI."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..services import policy_rag

router = APIRouter(prefix="/policy", tags=["policy"])


@router.get("/search")
def search_policy(q: str = Query(..., min_length=3, description="Plain-English question, e.g. 'claim reported late'"),
                  product: Literal["MOTOR", "HEALTH", "PROPERTY"] = "MOTOR", k: int = Query(3, ge=1, le=5)):
    try:
        hits, mode = policy_rag.search(q, product, k)
    except Exception as exc:
        raise HTTPException(502, f"policy search failed: {getattr(exc, 'category', type(exc).__name__)}")
    return {"query": q, "product": product, "mode": mode, "results": hits}


@router.get("/clauses")
def list_clauses():
    return [c.__dict__ for c in policy_rag.load_clauses()]
