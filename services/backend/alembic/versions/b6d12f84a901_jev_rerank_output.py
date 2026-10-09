"""Add private nullable run-scoped evidence ranking provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='b6d12f84a901'
down_revision='0c84e9d57a62'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('assessment_runs',sa.Column('rerank_output',postgresql.JSONB(),nullable=True))

def downgrade():
    op.drop_column('assessment_runs','rerank_output')
