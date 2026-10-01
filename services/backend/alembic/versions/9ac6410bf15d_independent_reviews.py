"""Add snapshot-bound independent HR/IT labels for shadow evaluation.

Revision ID: 9ac6410bf15d
Revises: 43bc71851f0e
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "9ac6410bf15d"
down_revision = "43bc71851f0e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "independent_reviews",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("application_id", sa.UUID(), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("review_kind", sa.String(10), nullable=False),
        sa.Column("application_generation", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sanitized_version_id", sa.UUID(), sa.ForeignKey("sanitized_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rubric_version_id", sa.UUID(), sa.ForeignKey("rubric_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("criterion_scores", postgresql.JSONB(), nullable=False),
        sa.Column("criterion_statuses", postgresql.JSONB(), nullable=False),
        sa.Column("criterion_quotes", postgresql.JSONB(), nullable=False),
        sa.Column("criterion_notes", postgresql.JSONB(), nullable=False),
        sa.Column("recommendation", sa.String(30), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "reviewer_id", "application_generation", name="uq_independent_review_snapshot_reviewer"),
    )
    op.create_index("ix_independent_reviews_application_id", "independent_reviews", ["application_id"])
    op.create_index("ix_independent_reviews_reviewer", "independent_reviews", ["reviewer_id", "submitted_at"])


def downgrade() -> None:
    op.drop_index("ix_independent_reviews_reviewer", table_name="independent_reviews")
    op.drop_index("ix_independent_reviews_application_id", table_name="independent_reviews")
    op.drop_table("independent_reviews")
