import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (CheckConstraint, DateTime, Enum, Float, ForeignKey, Index, Integer, Numeric,
                        String, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.db.base import Base


class Scale(str, enum.Enum):
    UNITS = "units"
    THOUSANDS = "thousands"
    MILLIONS = "millions"
    BILLIONS = "billions"


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    health_score: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    pages: Mapped[list["Page"]] = relationship(cascade="all, delete-orphan")
    audit_runs: Mapped[list["AuditRun"]] = relationship(cascade="all, delete-orphan")


class AuditRun(Base):
    __tablename__ = "audit_runs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="queued")
    stage: Mapped[str] = mapped_column(String(24), nullable=False, server_default="parsing")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    stage_timings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_audit_runs_document_created", "document_id", "created_at"),)


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)


class TextChunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    sentence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    chunk_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="sentence")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bboxes: Mapped[list[list[float]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    table_cells: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    table_bbox: Mapped[list[float] | None] = mapped_column(JSONB)
    header_row: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(get_settings().embedding_dim))
    __table_args__ = (
        CheckConstraint("jsonb_typeof(bboxes) = 'array'", name="ck_chunks_bboxes_array"),
        CheckConstraint("chunk_type IN ('sentence', 'table')", name="ck_chunks_chunk_type"),
        UniqueConstraint("page_id", "chunk_index"),
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )


class Fact(Base):
    __tablename__ = "facts"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    audit_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("audit_runs.id", ondelete="CASCADE"))
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    value_low: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    value_high: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    raw_value: Mapped[str | None] = mapped_column(Text)
    scale: Mapped[Scale] = mapped_column(
        Enum(Scale, name="scale", values_callable=lambda items: [item.value for item in items]),
        nullable=False,
        server_default="units",
    )
    unit: Mapped[str | None] = mapped_column(Text)
    unit_normalized: Mapped[str | None] = mapped_column(Text)
    period: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    table_row: Mapped[int | None] = mapped_column(Integer)
    table_col: Mapped[int | None] = mapped_column(Integer)


class Issue(Base):
    __tablename__ = "issues"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    audit_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    detector: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="open")
    needs_review: Mapped[bool] = mapped_column(default=False, nullable=False, server_default="false")
    conflicting_span_a: Mapped[str | None] = mapped_column(Text)
    conflicting_span_b: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("audit_run_id", "fingerprint", name="uq_issues_run_fingerprint"),)


class IssueEvidence(Base):
    __tablename__ = "issue_evidence"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bboxes: Mapped[list[list[float]]] = mapped_column(JSONB, nullable=False, server_default="[]")
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class IssueFeedback(Base):
    __tablename__ = "issue_feedback"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    feedback: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SemanticVerdictCache(Base):
    __tablename__ = "semantic_verdict_cache"
    pair_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    conflicting_span_a: Mapped[str | None] = mapped_column(Text)
    conflicting_span_b: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
