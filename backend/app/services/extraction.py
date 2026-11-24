"""AI step: turn raw document text into validated structured fields.
The model ONLY extracts; it never scores fraud or decides a claim."""
import json
from datetime import date
from decimal import Decimal
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AIRun, Claim, Document, Extraction, TraceEvent
from ..observability import StageRecorder, log_event
from . import llm

PROMPT_VERSION = "extract-v3"
MAX_CHARS = 6000

# v2: defines what each date means per document type. v1 left this open, so the model returned null for
# hospital admission/discharge dates and claim-form intimation dates (see docs/evaluation-report.md).
# v3: provider_name is the billing business only, name without address. v2 returned police stations as
# providers on police reports, which would also have linked unrelated claims in the fraud graph.
SYSTEM_PROMPT = """You extract fields from synthetic insurance claim documents.
Return ONLY a JSON object with exactly these keys:
document_type (one of CLAIM_FORM, INVOICE, POLICE_REPORT, MEDICAL_BILL, OTHER),
policy_number, claimant_name, incident_date (YYYY-MM-DD), document_date (YYYY-MM-DD),
amount (number, total amount on the document), invoice_number, provider_name,
vehicle_registration, phone, confidence_notes (list of short strings).

Field meanings:
- incident_date: the day the loss happened. Accident, theft or damage date for motor and property;
  for health, the date of admission (or "admitted on" date).
- document_date: the day the document itself was issued or filed. Bill or invoice date; on a hospital
  bill or discharge summary, the date of discharge; on a claim form, the date of intimation; on a police
  entry, the date it is "dated". If the only date shown is when the accident happened, use null.
- claimant_name: the insured person, patient or complainant, exactly as written.
- invoice_number: the bill, invoice or receipt number.
- provider_name: the business name of the hospital, garage or contractor that is charging for treatment or
  repairs, without its address or city. Police stations and the insurance company are never providers, so
  provider_name is null on police reports and claim forms.

Use null for anything not clearly present. Copy values as written; never guess or calculate them.
Do not judge whether the claim is fraudulent."""


class EmptyDocument(Exception):
    category = "empty_input"


class ExtractedFields(BaseModel):
    document_type: Literal["CLAIM_FORM", "INVOICE", "POLICE_REPORT", "MEDICAL_BILL", "OTHER"]
    policy_number: str | None = None
    claimant_name: str | None = None
    incident_date: date | None = None
    document_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    invoice_number: str | None = None
    provider_name: str | None = None
    vehicle_registration: str | None = None
    phone: str | None = None
    confidence_notes: list[str] = []

    @field_validator("*", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return None if isinstance(v, str) and v.strip().lower() in {"", "null", "n/a", "none"} else v


def parse_fields(raw: str) -> ExtractedFields:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise llm.LLMMalformed("model returned non-JSON") from exc
    if not isinstance(data, dict):
        raise llm.LLMMalformed("model returned non-object JSON")
    fields = ExtractedFields.model_validate(data)
    if not any([fields.policy_number, fields.claimant_name, fields.amount, fields.incident_date]):
        raise llm.LLMMalformed("no usable fields extracted")
    return fields


def _category(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "schema_validation"
    if isinstance(exc, SQLAlchemyError):
        return "sql_error"
    return getattr(exc, "category", "internal_error")


def extract_document(db: Session, claim: Claim, doc: Document, trace_id: str) -> AIRun:
    run = AIRun(claim_id=claim.claim_id, document_id=doc.document_id, task="EXTRACTION",
                trace_id=trace_id, model_id=settings.model_label, prompt_version=PROMPT_VERSION,
                status="RUNNING")
    db.add(run)
    db.flush()
    rec = StageRecorder(trace_id, run.run_id)
    t0 = perf_counter()
    try:
        with rec.stage("db.read_document"):
            text = (doc.text_content or "")[:MAX_CHARS]
            if not text.strip():
                raise EmptyDocument("document has no text")
        with rec.stage("ai.inference"):
            user_prompt = f"Declared document type: {doc.doc_type}\n---\n{text}\n---"
            result = llm.complete_json(SYSTEM_PROMPT, user_prompt, text)
        with rec.stage("output.validation"):
            fields = parse_fields(result.text)
        with rec.stage("db.save_extraction"):
            db.add(Extraction(document_id=doc.document_id, run_id=run.run_id,
                              fields=fields.model_dump(mode="json"), is_valid=True))
        run.status = "SUCCESS"
        run.input_tokens, run.output_tokens = result.input_tokens, result.output_tokens
    except Exception as exc:  # failure isolation: record it, never touch claim data
        run.status = "FAILED"
        run.error_type = _category(exc)
    run.latency_ms = int((perf_counter() - t0) * 1000)
    for ev in rec.events:
        db.add(TraceEvent(**ev))
    db.commit()
    log_event("ai_run", trace_id=trace_id, run_id=run.run_id, claim_id=claim.claim_id,
              model=run.model_id, status=run.status, latency_ms=run.latency_ms, error_category=run.error_type)
    return run
