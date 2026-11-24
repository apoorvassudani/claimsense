"""PostgreSQL schema. Business data (policies, claims, documents) is kept separate from
AI execution data (ai_runs, trace_events), the fraud graph, human reviews and audit events."""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer,
                        Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


TS = DateTime(timezone=True)


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint("product_type IN ('MOTOR','HEALTH','PROPERTY')", name="ck_policy_product"),
        CheckConstraint("end_date > start_date", name="ck_policy_dates"),
    )
    policy_id: Mapped[int] = mapped_column(primary_key=True)
    policy_number: Mapped[str] = mapped_column(String(30), unique=True)
    holder_code: Mapped[str] = mapped_column(String(20))
    product_type: Mapped[str] = mapped_column(String(20))
    sum_insured: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Claimant(Base):
    __tablename__ = "claimants"
    claimant_id: Mapped[int] = mapped_column(primary_key=True)
    claimant_code: Mapped[str] = mapped_column(String(20), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))  # synthetic names only
    phone: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("claimed_amount > 0", name="ck_claim_amount"),
        CheckConstraint(
            "status IN ('SUBMITTED','VALIDATED','NEEDS_REVIEW','CLEARED','ESCALATED','INFO_REQUESTED')",
            name="ck_claim_status"),
    )
    claim_id: Mapped[int] = mapped_column(primary_key=True)
    claim_number: Mapped[str] = mapped_column(String(30), unique=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.policy_id"))
    claimant_id: Mapped[int] = mapped_column(ForeignKey("claimants.claimant_id"))
    claim_type: Mapped[str] = mapped_column(String(20))
    incident_date: Mapped[date] = mapped_column(Date)
    reported_date: Mapped[date] = mapped_column(Date)
    claimed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="SUBMITTED")
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    policy: Mapped[Policy] = relationship()
    claimant: Mapped[Claimant] = relationship()
    documents: Mapped[list["Document"]] = relationship(back_populates="claim", order_by="Document.document_id")
    findings: Mapped[list["Finding"]] = relationship(back_populates="claim", cascade="all, delete-orphan")

    @property
    def claimant_name(self) -> str:
        return self.claimant.full_name

    @property
    def claimant_code(self) -> str:
        return self.claimant.claimant_code

    @property
    def rule_codes(self) -> list[str]:
        return sorted({f.rule_code for f in self.findings})


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("doc_type IN ('CLAIM_FORM','INVOICE','POLICE_REPORT','MEDICAL_BILL','OTHER')",
                        name="ck_doc_type"),
    )
    document_id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.claim_id"))
    doc_type: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    text_content: Mapped[str] = mapped_column(Text)
    uploaded_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    claim: Mapped[Claim] = relationship(back_populates="documents")
    extractions: Mapped[list["Extraction"]] = relationship(back_populates="document")


class AIRun(Base):
    __tablename__ = "ai_runs"
    __table_args__ = (CheckConstraint("status IN ('RUNNING','SUCCESS','FAILED')", name="ck_run_status"),)
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.claim_id"))
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.document_id"), nullable=True)
    task: Mapped[str] = mapped_column(String(20))  # EXTRACTION (Day 32), SUMMARY (later)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    model_id: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Extraction(Base):
    __tablename__ = "extractions"
    extraction_id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.document_id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("ai_runs.run_id"))
    fields: Mapped[dict] = mapped_column(JSON)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    document: Mapped[Document] = relationship(back_populates="extractions")


class Finding(Base):
    __tablename__ = "validation_findings"
    __table_args__ = (CheckConstraint("severity IN ('LOW','MEDIUM','HIGH')", name="ck_finding_sev"),)
    finding_id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.claim_id"))
    rule_code: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(String(300))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    claim: Mapped[Claim] = relationship(back_populates="findings")


class TraceEvent(Base):
    __tablename__ = "trace_events"
    event_id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_runs.run_id"), nullable=True)
    span_name: Mapped[str] = mapped_column(String(60))
    started_at: Mapped[datetime] = mapped_column(TS)
    duration_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
    error_category: Mapped[str | None] = mapped_column(String(40), nullable=True)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("node_type", "node_key", name="uq_node"),)
    node_id: Mapped[int] = mapped_column(primary_key=True)
    node_type: Mapped[str] = mapped_column(String(20))  # CLAIM, CLAIMANT, POLICY, PHONE, ADDRESS, PROVIDER, VEHICLE
    node_key: Mapped[str] = mapped_column(String(200))  # normalized identifier
    label: Mapped[str] = mapped_column(String(200))


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (UniqueConstraint("src_node_id", "dst_node_id", "relation", name="uq_edge"),)
    edge_id: Mapped[int] = mapped_column(primary_key=True)
    src_node_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.node_id"))
    dst_node_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.node_id"))
    relation: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("decision IN ('CLEAR','ESCALATE','REQUEST_INFO')", name="ck_review"),)
    review_id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.claim_id"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ai_runs.run_id"), nullable=True)
    reviewer_code: Mapped[str] = mapped_column(String(20))
    decision: Mapped[str] = mapped_column(String(20))
    ai_helpful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    audit_id: Mapped[int] = mapped_column(primary_key=True)
    actor_code: Mapped[str] = mapped_column(String(20))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
