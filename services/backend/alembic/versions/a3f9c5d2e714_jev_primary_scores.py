"""Persist Jev's fractional primary score separately from legacy scores."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a3f9c5d2e714"
down_revision = "b6d12f84a901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("criterion_assessments", sa.Column("jev_score", sa.Numeric(5, 4), nullable=True))
    op.add_column("criterion_assessments", sa.Column("jev_probabilities", postgresql.JSONB(), nullable=True))
    op.add_column("criterion_assessments", sa.Column("jev_confidence", sa.Numeric(5, 4), nullable=True))
    op.add_column("criterion_assessments", sa.Column("score_disposition", sa.String(length=32), nullable=True))


def downgrade():
    op.drop_column("criterion_assessments", "score_disposition")
    op.drop_column("criterion_assessments", "jev_confidence")
    op.drop_column("criterion_assessments", "jev_probabilities")
    op.drop_column("criterion_assessments", "jev_score")
