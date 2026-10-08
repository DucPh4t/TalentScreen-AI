"""Add email_drafts table for AI correspondence drafts.

Revision ID: 7a1e8c9d0b2f
Revises: 43de8b507ac2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7a1e8c9d0b2f"
down_revision = "43de8b507ac2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("template_type", sa.String(50), nullable=False, server_default="interview_invitation"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["decisions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_email_drafts_application_id", "email_drafts", ["application_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_email_drafts_application_id", table_name="email_drafts")
    op.drop_table("email_drafts")
