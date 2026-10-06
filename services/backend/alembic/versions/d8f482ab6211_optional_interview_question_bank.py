"""Allow candidate-specific interview prompts without a shared question bank.

Revision ID: d8f482ab6211
Revises: c2f1a90d34b7
"""
from alembic import op
import sqlalchemy as sa


revision = "d8f482ab6211"
down_revision = "c2f1a90d34b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "interview_drafts",
        "question_bank_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    # A draft created without a question bank cannot be represented by the old
    # schema. PostgreSQL will reject downgrade while such rows still exist.
    op.alter_column(
        "interview_drafts",
        "question_bank_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
