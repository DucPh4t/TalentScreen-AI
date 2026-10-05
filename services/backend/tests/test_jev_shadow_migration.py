"""Regression checks for the Alembic migration that stores Jev shadow output."""
from __future__ import annotations

from sqlalchemy import text


async def test_jev_shadow_migration_adds_jsonb_column_and_is_current_head(test_session_factory) -> None:
    async with test_session_factory() as session:
        column = (
            await session.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'assessment_runs' "
                    "AND column_name = 'secondary_model_output'"
                )
            )
        ).scalar_one_or_none()
        revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()

    assert column == "jsonb"
    assert revision == "c2f1a90d34b7"
