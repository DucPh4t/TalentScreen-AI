"""Persist minimized evidence-agent execution metadata on assessment runs.

Revision ID: 6f2c91a4d8e0
Revises: a6b9031d8f42
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "6f2c91a4d8e0"
down_revision = "a6b9031d8f42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_runs",
        sa.Column(
            "execution_trace",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("assessment_runs", "execution_trace")
