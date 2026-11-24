from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from sqlalchemy.orm import selectinload

from ..models import AIRun, AuditEvent, Claim, Claimant, Document, Policy, Review
from ..schemas import (ClaimantOut, ClaimCreate, ClaimDetail, ClaimOut, DocumentOut, PolicyOut, ReviewCreate,
                       ReviewOut)
from ..services.ingestion import IngestionError, extract_text
from ..services.pipeline import process_claim

router = APIRouter(tags=["claims"])
DOC_TYPES = {"CLAIM_FORM", "INVOICE", "POLICE_REPORT", "MEDICAL_BILL", "OTHER"}
DECISION_STATUS = {"CLEAR": "CLEARED", "ESCALATE": "ESCALATED", "REQUEST_INFO": "INFO_REQUESTED"}


def _audit(db: Session, entity: str, entity_id, action: str, actor: str = "analyst-01"):
    db.add(AuditEvent(actor_code=actor, entity_type=entity, entity_id=str(entity_id), action=action))


def _get_claim(db: Session, claim_id: int) -> Claim:
    claim = db.get(Claim, claim_id)
    if not claim:
        raise HTTPException(404, "claim not found")
    return claim


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(db: Session = Depends(get_db)):
    return db.scalars(select(Policy).order_by(Policy.policy_id)).all()


@router.get("/claimants", response_model=list[ClaimantOut])
def list_claimants(db: Session = Depends(get_db)):
    return db.scalars(select(Claimant).order_by(Claimant.full_name)).all()


@router.get("/claims", response_model=list[ClaimOut])
def list_claims(status: str | None = None, risk_level: str | None = None, db: Session = Depends(get_db)):
    q = (select(Claim).options(selectinload(Claim.claimant), selectinload(Claim.policy), selectinload(Claim.findings))
         .order_by(Claim.incident_date.desc(), Claim.claim_id.desc()))
    if status:
        q = q.where(Claim.status == status)
    if risk_level:
        q = q.where(Claim.risk_level == risk_level)
    return db.scalars(q).all()


@router.post("/claims", response_model=ClaimOut, status_code=201)
def create_claim(body: ClaimCreate, db: Session = Depends(get_db)):
    policy = db.scalar(select(Policy).where(Policy.policy_number == body.policy_number))
    claimant = db.scalar(select(Claimant).where(Claimant.claimant_code == body.claimant_code))
    if not policy or not claimant:
        raise HTTPException(422, "unknown policy_number or claimant_code")
    if policy.product_type != body.claim_type:
        raise HTTPException(422, f"claim_type must match policy product ({policy.product_type})")
    if db.scalar(select(Claim).where(Claim.claim_number == body.claim_number)):
        raise HTTPException(409, "claim_number already exists")
    claim = Claim(claim_number=body.claim_number, policy_id=policy.policy_id, claimant_id=claimant.claimant_id,
                  claim_type=body.claim_type, incident_date=body.incident_date, reported_date=body.reported_date,
                  claimed_amount=body.claimed_amount, description=body.description)
    db.add(claim)
    db.flush()
    _audit(db, "claim", claim.claim_id, "CREATE")
    db.commit()
    return claim


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
def get_claim(claim_id: int, db: Session = Depends(get_db)):
    c = _get_claim(db, claim_id)
    return ClaimDetail.model_validate({**ClaimOut.model_validate(c).model_dump(), "description": c.description,
                                       "documents": c.documents, "findings": c.findings})


@router.get("/documents/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if not d:
        raise HTTPException(404, "document not found")
    return {"document_id": d.document_id, "claim_id": d.claim_id, "doc_type": d.doc_type, "filename": d.filename,
            "text": d.text_content}


@router.post("/claims/{claim_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(claim_id: int, doc_type: str = Form(...), file: UploadFile = File(...),
                          db: Session = Depends(get_db)):
    claim = _get_claim(db, claim_id)
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {sorted(DOC_TYPES)}")
    data = await file.read()
    try:
        text, sha = extract_text(file.filename or "upload", data, settings.max_upload_bytes)
    except IngestionError as exc:
        raise HTTPException(422, str(exc))
    doc = Document(claim_id=claim.claim_id, doc_type=doc_type, filename=file.filename, sha256=sha, text_content=text)
    db.add(doc)
    db.flush()
    _audit(db, "document", doc.document_id, "UPLOAD")
    db.commit()
    return doc


@router.post("/claims/{claim_id}/process")
def process(claim_id: int, db: Session = Depends(get_db)):
    claim = _get_claim(db, claim_id)
    if not claim.documents:
        raise HTTPException(422, "upload at least one document first")
    result = process_claim(db, claim)
    _audit(db, "claim", claim_id, "PROCESS", actor="system")
    db.commit()
    return result


@router.get("/claims/{claim_id}/extractions")
def get_extractions(claim_id: int, db: Session = Depends(get_db)):
    claim = _get_claim(db, claim_id)
    return [{"document_id": d.document_id, "doc_type": d.doc_type,
             "extractions": [{"run_id": e.run_id, "fields": e.fields, "is_valid": e.is_valid} for e in d.extractions]}
            for d in claim.documents]


@router.get("/claims/{claim_id}/reviews", response_model=list[ReviewOut])
def list_reviews(claim_id: int, db: Session = Depends(get_db)):
    _get_claim(db, claim_id)
    return db.scalars(select(Review).where(Review.claim_id == claim_id).order_by(Review.reviewed_at.desc())).all()


@router.post("/claims/{claim_id}/reviews", response_model=ReviewOut, status_code=201)
def create_review(claim_id: int, body: ReviewCreate, db: Session = Depends(get_db)):
    """Human decision. The only way a claim leaves NEEDS_REVIEW; AI and rules never decide."""
    claim = _get_claim(db, claim_id)
    if claim.risk_level is None:
        raise HTTPException(422, "run verification before recording a decision")
    latest = db.scalar(select(AIRun).where(AIRun.claim_id == claim_id, AIRun.status == "SUCCESS")
                       .order_by(AIRun.created_at.desc()).limit(1))
    review = Review(claim_id=claim_id, run_id=latest.run_id if latest else None, reviewer_code=body.reviewer_code,
                    decision=body.decision, ai_helpful=body.ai_helpful, comment=body.comment.strip())
    db.add(review)
    claim.status = DECISION_STATUS[body.decision]
    db.flush()
    _audit(db, "claim", claim_id, f"REVIEW_{body.decision}", actor=body.reviewer_code)
    db.commit()
    return review
