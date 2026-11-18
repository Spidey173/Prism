"""Add table-aware chunks and audit fact metadata."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_phase2_tables_and_issues"
down_revision = "0002_sentence_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("chunk_type", sa.String(16), server_default="sentence", nullable=False))
    op.add_column("chunks", sa.Column("table_cells", postgresql.JSONB(), server_default="[]", nullable=False))
    op.add_column("chunks", sa.Column("table_bbox", postgresql.JSONB(), nullable=True))
    op.add_column("chunks", sa.Column("header_row", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_chunks_chunk_type", "chunks", "chunk_type IN ('sentence', 'table')")

    op.add_column("facts", sa.Column("audit_run_id", sa.Uuid(), sa.ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=True))
    op.add_column("facts", sa.Column("value_low", sa.Numeric(24, 8), nullable=True))
    op.add_column("facts", sa.Column("value_high", sa.Numeric(24, 8), nullable=True))
    op.add_column("facts", sa.Column("table_row", sa.Integer(), nullable=True))
    op.add_column("facts", sa.Column("table_col", sa.Integer(), nullable=True))
    op.add_column("issues", sa.Column("status", sa.String(24), server_default="open", nullable=False))
    op.create_check_constraint("ck_issues_status", "issues", "status IN ('open', 'confirmed', 'false_positive')")


def downgrade() -> None:
    op.drop_constraint("ck_issues_status", "issues", type_="check")
    op.drop_column("issues", "status")
    op.drop_column("facts", "table_col")
    op.drop_column("facts", "table_row")
    op.drop_column("facts", "value_high")
    op.drop_column("facts", "value_low")
    op.drop_column("facts", "audit_run_id")
    op.drop_constraint("ck_chunks_chunk_type", "chunks", type_="check")
    op.drop_column("chunks", "header_row")
    op.drop_column("chunks", "table_bbox")
    op.drop_column("chunks", "table_cells")
    op.drop_column("chunks", "chunk_type")
