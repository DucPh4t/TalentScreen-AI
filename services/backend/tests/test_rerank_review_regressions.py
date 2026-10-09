from datetime import date
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select
from app.config import get_settings
from app.db.models import RubricCriterion,RetrievalChunk,SourceSpan
from app.services.reranking.service import criterion_from_row,rerank_candidates
from app.services.reranking.prompt import pairs_from_candidates
from app.services.reranking.selection import rank_and_select
from app.services.retrieval import RetrievedChunkScore
from app.services.llm.call_policy import JevReservationPolicy
from tests.test_rerank_journal import rerank_context,ChoiceProvider
from tests.test_rerank_kernel import pair,policy
from tests.test_assessment_agent import agent_context
from tests.test_ai_benchmark_budget import fresh_period


async def expanded_pool(db,context,criterion_count,chunk_count):
    run,p,_=await rerank_context(db,context)
    rows=list((await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all())
    for i in range(criterion_count-len(rows)):
        row=RubricCriterion(rubric_version_id=run.rubric_version_id,criterion_id=f'additional_{i}',label_vi='API',description_vi='HTTP implementation',weight=1,anchors={'0':'None','1':'Basic','2':'Good','3':'Strong','4':'Expert'})
        db.add(row);rows.append(row)
    from app.services.embedding import embedding_config_id
    span=await db.get(SourceSpan,context['span_id']);matches=[]
    for i in range(1,chunk_count+1):
        chunk=RetrievalChunk(id=uuid.uuid4(),sanitized_version_id=run.sanitized_version_id,chunk_index=i,
            text=span.text,span_ids=[span.span_id],embedding_config_id=embedding_config_id('v2'))
        db.add(chunk)
        matches.append(RetrievedChunkScore(chunk.id,i,span.text,[span.span_id],i,None,1/(60+i)))
    await db.commit()
    pools=pairs_from_candidates([criterion_from_row(c) for c in rows],{c.criterion_id:matches for c in rows},
        sanitized_version_id=run.sanitized_version_id,rubric_version_id=run.rubric_version_id)
    return run,p,pools


@pytest.mark.asyncio
@pytest.mark.parametrize('criteria,chunks',[(12,31),(12,60)])
async def test_valid_dense_lexical_union_reaches_bounded_planner(test_session_factory,agent_context,fresh_period,monkeypatch,criteria,chunks):
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pools=await expanded_pool(db,agent_context,criteria,chunks)
        f=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        provider=ChoiceProvider()
        result=await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pools,provider_override=provider,financial_policy=f)
        assert result.status=='ok' and provider.calls<=9
        assert len(result.judgments)<=8*criteria
        assert set(result.unscored_pair_ids)|{j.pair_id for j in result.judgments}=={p.pair_id for ps in pools.values() for p in ps}
        assert len(str(run.rerank_output).encode())<=262144


@pytest.mark.asyncio
async def test_completed_stage_restart_does_not_score_another_tail(test_session_factory,agent_context,fresh_period,monkeypatch):
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pools=await expanded_pool(db,agent_context,2,16)
        f=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        provider=ChoiceProvider()
        before=await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pools,provider_override=provider,financial_policy=f)
        first_calls=provider.calls
        await db.refresh(run)
        after=await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pools,provider_override=provider,financial_policy=f)
        assert provider.calls==first_calls
        assert before.selected_pair_ids_by_criterion==after.selected_pair_ids_by_criterion
        assert len(after.judgments)==len(before.judgments)==16


@pytest.mark.parametrize('stage',['initial','tool_1','tool_2'])
def test_unscored_result_matches_stage_specific_baseline(stage):
    ps=tuple(pair(i,section='work' if i<30 else 'projects') for i in range(31))
    r=rank_and_select(ps,(),policy(),stage=stage)
    assert r.selected_pair_ids_by_criterion['c']==('c-0','c-1','c-2','c-3')
    assert len(r.ordered_pair_ids_by_criterion['c'])==31
    assert len(r.unscored_pair_ids)==31
    # Tools have a simple top-four baseline, rather than section diversity.
    if stage!='initial':
        different=tuple(pair(i,section='work' if i<4 else 'projects') for i in range(8))
        assert rank_and_select(different,(),policy(),stage=stage).selected_pair_ids_by_criterion['c']==('c-0','c-1','c-2','c-3')


def test_offline_policy_fixture_remains_valid_at_future_clock(monkeypatch):
    import tests.test_rerank_kernel as kernel
    import app.services.llm.call_policy as calls
    class FutureDate(date):
        @classmethod
        def today(cls):return cls(2026,11,9)
    monkeypatch.setattr(calls,'date',FutureDate)
    monkeypatch.setattr(kernel,'date',FutureDate,raising=False)
    p=kernel.policy()
    JevReservationPolicy(uuid.uuid4(),Decimal('1'),65536,Decimal('.042'),p.rate_verified_at,frozenset(p.accepted_models),p.endpoint)
    with pytest.raises(ValueError):
        JevReservationPolicy(uuid.uuid4(),Decimal('1'),65536,Decimal('.042'),'2026-10-09',frozenset(p.accepted_models),p.endpoint)
