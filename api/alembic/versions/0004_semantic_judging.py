"""Add cached semantic judgments and review metadata."""

from alembic import op
import sqlalchemy as sa

revision = "0004_semantic_judging"
down_revision = "0003_phase2_tables_and_issues"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("issues", sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("issues", sa.Column("conflicting_span_a", sa.Text(), nullable=True))
    op.add_column("issues", sa.Column("conflicting_span_b", sa.Text(), nullable=True))
    op.create_table(
        "semantic_verdict_cache",
        sa.Column("pair_hash", sa.String(64), primary_key=True),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("conflicting_span_a", sa.Text(), nullable=True),
        sa.Column("conflicting_span_b", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("semantic_verdict_cache")
    op.drop_column("issues", "conflicting_span_b")
    op.drop_column("issues", "conflicting_span_a")
    op.drop_column("issues", "needs_review")
