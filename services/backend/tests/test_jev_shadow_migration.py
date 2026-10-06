"""Regression checks for the latest Alembic additions used by interview workflows."""
from __future__ import annotations

from sqlalchemy import text


async def test_current_migrations_include_jev_output_and_optional_interview_bank(test_session_factory) -> None:
    async with test_session_factory() as session:
        jev_column = (
            await session.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'assessment_runs' "
                    "AND column_name = 'secondary_model_output'"
                )
            )
        ).scalar_one_or_none()
        bank_nullable = (
            await session.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = 'interview_drafts' "
                    "AND column_name = 'question_bank_id'"
                )
            )
        ).scalar_one_or_none()
        scorecard_table = (
            await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = current_schema() AND table_name = 'interview_scorecards'"
                )
            )
        ).scalar_one_or_none()
        revision = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()

    assert jev_column == "jsonb"
    assert bank_nullable == "YES"
    assert scorecard_table == "interview_scorecards"
    assert revision == "a6b9031d8f42"
