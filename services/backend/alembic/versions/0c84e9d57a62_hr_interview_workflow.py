"""Private progress, interview rounds and auditable scorecard corrections."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision = '0c84e9d57a62'
down_revision = 'b8c2d41a9e06'
branch_labels = None
depends_on = None

def upgrade():
    common = lambda: [sa.Column('id', sa.UUID(), primary_key=True), sa.Column('application_id', sa.UUID(), sa.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False), sa.Column('row_version', sa.BigInteger(), nullable=False), sa.Column('source_hash', sa.String(64), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)]
    op.create_table('review_progress', *common(), sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False), sa.Column('reviewed_criterion_ids', pg.JSONB(), nullable=False), sa.UniqueConstraint('application_id', 'user_id', name='uq_review_progress_actor'))
    op.create_index('ix_review_progress_application_id', 'review_progress', ['application_id'])
    op.create_table('interview_rounds', *common(), sa.Column('round_no', sa.Integer(), nullable=False), sa.Column('preparation', pg.JSONB(), nullable=False), sa.Column('conclusions', pg.JSONB(), nullable=False), sa.UniqueConstraint('application_id', 'round_no', name='uq_interview_round_application'))
    op.create_index('ix_interview_rounds_application_id', 'interview_rounds', ['application_id'])
    op.add_column('interview_scorecards', sa.Column('amendment_history', pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))

def downgrade():
    op.drop_column('interview_scorecards', 'amendment_history')
    op.drop_table('interview_rounds')
    op.drop_table('review_progress')
