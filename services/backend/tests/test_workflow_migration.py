"""Exercise legacy correspondence upgrade/backfill using the disposable test DB."""
import os
from pathlib import Path
import subprocess

from sqlalchemy import select, text

from app.db.models.email_draft import EmailDraft
from tests.test_decisions import setup_test_context, sample_docx_cv
from tests.test_workflow_repairs import client_for


async def test_workflow_migration_round_trip_preserves_content_but_retires_legacy_approvals(test_session_factory, sample_docx_cv):
    assert os.environ.get("TALENTSCREEN_TEST_DB_ISOLATED") == "1"
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    async with client_for(ctx) as client:
        first = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")
        assert first.status_code == 200
        second = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate?template=rejection_polite")
        assert second.status_code == 200
        body = second.json()["body"]
    root = Path(__file__).resolve().parents[3]
    alembic = root / ".venv/bin/alembic"
    for command, revision in (("downgrade", "7a1e8c9d0b2f"), ("upgrade", "head")):
        subprocess.run([str(alembic), command, revision], cwd=root, env=os.environ.copy(), check=True, capture_output=True, text=True)
    async with test_session_factory() as session:
        drafts = list((await session.execute(select(EmailDraft).where(EmailDraft.application_id == ctx["app_id"])
            .order_by(EmailDraft.version_no))).scalars())
        assert len(drafts) == 2
        assert [draft.version_no for draft in drafts] == [1, 2]
        assert drafts[-1].body == body
        assert all(draft.status == "invalidated" and draft.approved_by is None and draft.source_snapshot_hash is None for draft in drafts)
        assert (await session.execute(text("SELECT version_num FROM alembic_version"))).scalar_one() == "b7e2a9c4d105"
