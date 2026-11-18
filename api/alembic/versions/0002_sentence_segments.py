"""Link page-local chunk segments belonging to one sentence."""

from alembic import op
import sqlalchemy as sa

revision = "0002_sentence_segments"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("sentence_id", sa.Uuid(), nullable=True))
    op.add_column("chunks", sa.Column("segment_index", sa.Integer(), server_default="0", nullable=False))
    op.execute("UPDATE chunks SET sentence_id = id WHERE sentence_id IS NULL")
    op.alter_column("chunks", "sentence_id", nullable=False)
    op.create_index("ix_chunks_sentence_id", "chunks", ["sentence_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_sentence_id", table_name="chunks")
    op.drop_column("chunks", "segment_index")
    op.drop_column("chunks", "sentence_id")
