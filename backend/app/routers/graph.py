from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Claim
from ..services.graph import neighborhood, shared_identifiers

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/claims/{claim_id}")
def claim_graph(claim_id: int, db: Session = Depends(get_db)):
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(404, "claim not found")
    return {**neighborhood(db, claim.claim_number), "shared_identifiers": shared_identifiers(db, claim)}
