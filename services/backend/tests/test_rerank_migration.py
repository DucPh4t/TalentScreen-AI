from sqlalchemy import text

async def test_rerank_column_nullable_and_old_rows_untouched(test_session_factory):
    async with test_session_factory() as db:
        row=(await db.execute(text("SELECT data_type,is_nullable,column_default FROM information_schema.columns WHERE table_name='assessment_runs' AND column_name='rerank_output'"))).one_or_none()
        assert row==('jsonb','YES',None)
