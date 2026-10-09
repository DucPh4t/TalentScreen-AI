"""Persist validated post-score explanation artifacts for Jev-primary runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b7e2a9c4d105"
down_revision = "a3f9c5d2e714"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_runs",
        sa.Column("jev_explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assessment_runs", "jev_explanation")
