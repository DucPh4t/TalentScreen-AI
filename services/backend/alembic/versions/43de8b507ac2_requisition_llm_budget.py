"""Attribute LLM budget reservations to their requisition.

Revision ID: 43de8b507ac2
Revises: 6f2c91a4d8e0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "43de8b507ac2"
down_revision = "6f2c91a4d8e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "budget_reservations",
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_budget_reservations_requisition_id_requisitions",
        "budget_reservations",
        "requisitions",
        ["requisition_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_budget_reservations_requisition_status",
        "budget_reservations",
        ["requisition_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_budget_reservations_requisition_status", table_name="budget_reservations")
    op.drop_constraint(
        "fk_budget_reservations_requisition_id_requisitions",
        "budget_reservations",
        type_="foreignkey",
    )
    op.drop_column("budget_reservations", "requisition_id")
