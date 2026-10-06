"""Add versioned human interview scorecards separate from AI CV ratings.

Revision ID: a6b9031d8f42
Revises: d8f482ab6211
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a6b9031d8f42"
down_revision = "d8f482ab6211"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_scorecards",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("interviewer_id", sa.UUID(), nullable=False),
        sa.Column("rubric_version_id", sa.UUID(), nullable=False),
        sa.Column("interview_draft_id", sa.UUID(), nullable=True),
        sa.Column("round_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("criteria_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("row_version", sa.BigInteger(), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["rubric_version_id"], ["rubric_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["interview_draft_id"], ["interview_drafts.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "application_id", "interviewer_id", "round_no", "rubric_version_id",
            name="uq_interview_scorecard_reviewer_round_rubric",
        ),
    )
    op.create_index("ix_interview_scorecards_application_id", "interview_scorecards", ["application_id"])
    op.create_index("ix_interview_scorecards_interviewer_id", "interview_scorecards", ["interviewer_id"])
    op.create_index(
        "ix_interview_scorecards_application", "interview_scorecards", ["application_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_interview_scorecards_application", table_name="interview_scorecards")
    op.drop_index("ix_interview_scorecards_interviewer_id", table_name="interview_scorecards")
    op.drop_index("ix_interview_scorecards_application_id", table_name="interview_scorecards")
    op.drop_table("interview_scorecards")
