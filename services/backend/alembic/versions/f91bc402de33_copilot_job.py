"""Add ledger-backed, bounded Copilot requests."""
from alembic import op
revision = "f91bc402de33"
down_revision = "e43a2f981207"
branch_labels = None
depends_on = None

def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'COPILOT_SELECT'")

def downgrade():
    # PostgreSQL cannot safely remove a populated enum value in place.
    # The additive value is intentionally retained; old applications ignore it.
    pass
