"""Server-side private draft persistence for independent reviewers."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "b419ad53ef82"
down_revision = "f91bc402de33"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("independent_review_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sanitized_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sanitized_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rubric_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rubric_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("application_generation", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("application_id", "reviewer_id", name="uq_review_draft_actor"))

def downgrade():
    op.drop_table("independent_review_drafts")
