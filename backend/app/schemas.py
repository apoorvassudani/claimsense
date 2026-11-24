from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PolicyOut(ORM):
    policy_id: int
    policy_number: str
    holder_code: str
    product_type: str
    sum_insured: Decimal
    start_date: date
    end_date: date


class ClaimCreate(BaseModel):
    claim_number: str = Field(min_length=3, max_length=30)
    policy_number: str
    claimant_code: str
    claim_type: Literal["MOTOR", "HEALTH", "PROPERTY"]
    incident_date: date
    reported_date: date
    claimed_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    description: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def dates_ok(self):
        if self.reported_date < self.incident_date:
            raise ValueError("reported_date cannot be before incident_date")
        return self


class DocumentOut(ORM):
    document_id: int
    doc_type: str
    filename: str
    sha256: str
    ocr_engine: str | None = None
    uploaded_at: datetime


class FindingOut(ORM):
    rule_code: str
    severity: str
    message: str
    evidence: dict


class ClaimantOut(ORM):
    claimant_code: str
    full_name: str


class ClaimOut(ORM):
    claim_id: int
    claim_number: str
    claimant_code: str
    claimant_name: str
    claim_type: str
    incident_date: date
    reported_date: date
    claimed_amount: Decimal
    status: str
    risk_score: int | None
    risk_level: str | None
    rule_codes: list[str] = []
    policy: PolicyOut


class ClaimDetail(ClaimOut):
    description: str
    documents: list[DocumentOut]
    findings: list[FindingOut]


class RunOut(ORM):
    run_id: str
    claim_id: int
    document_id: int | None
    task: str
    trace_id: str
    model_id: str
    prompt_version: str
    status: str
    latency_ms: int | None
    error_type: str | None
    input_tokens: int | None
    output_tokens: int | None
    created_at: datetime


class TraceEventOut(ORM):
    span_name: str
    run_id: str | None
    started_at: datetime
    duration_ms: int
    status: str
    error_category: str | None


class ReviewCreate(BaseModel):
    decision: Literal["CLEAR", "ESCALATE", "REQUEST_INFO"]
    ai_helpful: bool | None = None
    comment: str = Field(default="", max_length=2000)


class ReviewOut(ORM):
    review_id: int
    claim_id: int
    run_id: str | None
    reviewer_code: str
    decision: str
    ai_helpful: bool | None
    comment: str
    reviewed_at: datetime
