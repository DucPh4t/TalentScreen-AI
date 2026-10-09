from sqlalchemy import text

async def test_rerank_column_nullable_and_old_rows_untouched(test_session_factory):
    async with test_session_factory() as db:
        row=(await db.execute(text("SELECT data_type,is_nullable,column_default FROM information_schema.columns WHERE table_name='assessment_runs' AND column_name='rerank_output'"))).one_or_none()
        assert row==('jsonb','YES',None)

async def test_populated_roundtrip_preserves_legacy_row(test_session_factory,agent_context):
    import os,subprocess
    from pathlib import Path
    assert os.environ.get('TALENTSCREEN_TEST_DB_ISOLATED')=='1'
    root=Path(__file__).resolve().parents[3]
    async with test_session_factory() as db:
        await db.execute(text("UPDATE assessment_runs SET rerank_output='{}'::jsonb WHERE id=:id"),{'id':agent_context['run_id']});await db.commit()
    for action,revision in [('downgrade','0c84e9d57a62'),('upgrade','head')]:
        subprocess.run([str(root/'.venv/bin/alembic'),action,revision],cwd=root,check=True,capture_output=True)
    async with test_session_factory() as db:
        row=(await db.execute(text('SELECT application_id,rerank_output FROM assessment_runs WHERE id=:id'),{'id':agent_context['run_id']})).one()
        assert row.application_id==agent_context['app_id'] and row.rerank_output is None

from tests.test_assessment_agent import agent_context
