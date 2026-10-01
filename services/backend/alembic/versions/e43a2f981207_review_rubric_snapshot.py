"""Keep labels immutable per rubric and record whether shadow enforcement was enabled."""
from alembic import op
import sqlalchemy as sa

revision = "e43a2f981207"
down_revision = "9ac6410bf15d"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("independent_reviews", sa.Column("blind_enforced", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_constraint("uq_independent_review_snapshot_reviewer", "independent_reviews", type_="unique")
    op.create_unique_constraint("uq_independent_review_snapshot_reviewer", "independent_reviews",
                               ["application_id", "reviewer_id", "application_generation", "rubric_version_id"])


def downgrade():
    # Restoring the old uniqueness may fail when multiple rubric labels exist.
    # Do not silently delete those human records; roll forward or restore a backup.
    op.drop_constraint("uq_independent_review_snapshot_reviewer", "independent_reviews", type_="unique")
    op.create_unique_constraint("uq_independent_review_snapshot_reviewer", "independent_reviews",
                               ["application_id", "reviewer_id", "application_generation"])
    op.drop_column("independent_reviews", "blind_enforced")
