"""Store a secondary model's candidate-scoped shadow output with its run."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c2f1a90d34b7"
down_revision = "b419ad53ef82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_runs",
        sa.Column("secondary_model_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("assessment_runs", "secondary_model_output")
