"""Version correspondence approvals and store organization-scoped duplicate signals."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b8c2d41a9e06"
down_revision = "7a1e8c9d0b2f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("duplicate_fingerprints", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("email_drafts", sa.Column("version_no", sa.Integer(), nullable=True))
    op.execute("""WITH versions AS (
        SELECT id, row_number() OVER (PARTITION BY application_id ORDER BY created_at, id) AS n FROM email_drafts
    ) UPDATE email_drafts SET version_no = versions.n FROM versions WHERE email_drafts.id = versions.id""")
    op.alter_column("email_drafts", "version_no", nullable=False)
    op.create_unique_constraint("uq_email_draft_application_version", "email_drafts", ["application_id", "version_no"])
    op.add_column("email_drafts", sa.Column("source_snapshot_hash", sa.String(64), nullable=True))
    for column in ("created_by", "approved_by"):
        op.add_column("email_drafts", sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_email_drafts_{column}", "email_drafts", "users", [column], ["id"], ondelete="SET NULL")
    op.add_column("email_drafts", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    # Old drafts cannot be proven to match a decision or audited approval.
    op.execute("UPDATE email_drafts SET status = 'invalidated'")


def downgrade():
    for column in ("created_by", "approved_by"):
        op.drop_constraint(f"fk_email_drafts_{column}", "email_drafts", type_="foreignkey")
    op.drop_constraint("uq_email_draft_application_version", "email_drafts", type_="unique")
    for column in ("version_no", "source_snapshot_hash", "created_by", "approved_by", "approved_at"):
        op.drop_column("email_drafts", column)
    op.drop_column("documents", "duplicate_fingerprints")
