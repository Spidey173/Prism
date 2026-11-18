"""Initial document audit schema."""
from alembic import op
import sqlalchemy as sa
import os

from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("documents",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True), sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("health_score", sa.Float()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("audit_runs",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(24), server_default="queued", nullable=False), sa.Column("stage", sa.String(24), server_default="parsing", nullable=False),
        sa.Column("progress", sa.Integer(), server_default="0", nullable=False), sa.Column("stage_timings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=False), sa.Column("estimated_cost", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("error", sa.Text()), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_audit_runs_document_created", "audit_runs", ["document_id", "created_at"])
    op.create_table("pages", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False), sa.Column("width", sa.Float(), nullable=False), sa.Column("height", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), server_default="", nullable=False), sa.UniqueConstraint("document_id", "page_number"))
    op.create_table("chunks", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.Uuid(), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False), sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("bboxes", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("embedding", Vector(int(os.getenv("EMBEDDING_DIM", "384")))), sa.CheckConstraint("jsonb_typeof(bboxes) = 'array'", name="ck_chunks_bboxes_array"), sa.UniqueConstraint("page_id", "chunk_index"))
    op.create_index("ix_chunks_embedding_hnsw", "chunks", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})
    op.execute("CREATE TYPE scale AS ENUM ('units', 'thousands', 'millions', 'billions')")
    op.create_table("facts", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False), sa.Column("subject", sa.Text(), nullable=False), sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False), sa.Column("value_num", sa.Numeric(24, 8)), sa.Column("raw_value", sa.Text()),
        sa.Column("scale", sa.Enum("units", "thousands", "millions", "billions", name="scale", create_type=False), server_default="units", nullable=False),
        sa.Column("unit", sa.Text()), sa.Column("unit_normalized", sa.Text()), sa.Column("period", sa.Text()), sa.Column("page_number", sa.Integer(), nullable=False), sa.Column("quote", sa.Text(), nullable=False))
    op.create_table("issues", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audit_run_id", sa.Uuid(), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False), sa.Column("type", sa.String(64), nullable=False),
        sa.Column("detector", sa.String(64), nullable=False), sa.Column("fingerprint", sa.String(128), nullable=False), sa.Column("severity", sa.String(8), nullable=False),
        sa.Column("title", sa.String(512), nullable=False), sa.Column("explanation", sa.Text(), nullable=False), sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("audit_run_id", "fingerprint", name="uq_issues_run_fingerprint"))
    op.create_table("issue_evidence", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.Uuid(), sa.ForeignKey("pages.id", ondelete="CASCADE"), nullable=False), sa.Column("chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="SET NULL")),
        sa.Column("page_number", sa.Integer(), nullable=False), sa.Column("bboxes", postgresql.JSONB(), server_default="[]", nullable=False), sa.Column("quote", sa.Text(), nullable=False), sa.Column("evidence_order", sa.Integer(), server_default="0", nullable=False))
    op.create_table("issue_feedback", sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feedback", sa.String(24), nullable=False), sa.Column("note", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    for table in ("issue_feedback", "issue_evidence", "issues", "facts", "chunks", "pages", "audit_runs", "documents"):
        op.drop_table(table)
    op.execute("DROP TYPE IF EXISTS scale")
