import pytest
from sqlalchemy import select
from decimal import Decimal
from app.config import get_settings
from app.db.models import AssessmentRun,RubricCriterion
from app.services.reranking.contracts import canonical
from app.services.reranking.selection import rank_and_select
from app.services.retrieval import build_hybrid_assessment_pack,RetrievedChunkScore
from tests.test_assessment_agent import agent_context
from tests.test_ai_benchmark_budget import fresh_period
from tests.test_rerank_journal import rerank_context,ChoiceProvider


@pytest.mark.asyncio
async def test_supplied_pool_shadow_is_identical_and_gate_pack_empty(test_session_factory,agent_context):
    from app.services.reranking.contracts import PairJudgment,OPTIONS
    async with test_session_factory() as db:
        run,p,pools=await rerank_context(db,agent_context);pair=pools['api_design'][0]
        import uuid
        match=RetrievedChunkScore(uuid.UUID(pair.chunk_id),pair.chunk_index,pair.text,list(pair.span_ids),1,1,pair.rrf_score)
        criteria=[{'id':'api_design','name':pair.criterion.label,'description':pair.criterion.description}]
        candidate_pool={'api_design':[match]}
        before=await build_hybrid_assessment_pack(db,run.sanitized_version_id,criteria,candidates_by_criterion=candidate_pool)
        j=PairJudgment(pair_id=pair.pair_id,choice='unrelated',confidence=1.0,probabilities={k:float(k=='unrelated') for k in OPTIONS},reported_model=p.accepted_models[0])
        shadow=rank_and_select((pair,),(j,),p.model_copy(update={'mode':'shadow'}),stage='initial')
        after=await build_hybrid_assessment_pack(db,run.sanitized_version_id,criteria,candidates_by_criterion=candidate_pool,
            rerank_result=shadow,rerank_pairs_by_criterion=pools)
        assert canonical(before)==canonical(after)
        gate=rank_and_select((pair,),(j,),p.model_copy(update={'mode':'gate_experiment'}),stage='initial')
        empty=await build_hybrid_assessment_pack(db,run.sanitized_version_id,criteria,candidates_by_criterion=candidate_pool,
            rerank_result=gate,rerank_pairs_by_criterion=pools)
        assert empty['source_span_ids']==[] and empty['criteria_retrieval_map']['api_design']==[]


@pytest.mark.asyncio
async def test_actual_service_calls_jev_before_primary(test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.services.assessment.service import execute_assessment_job
    from app.services.llm.call_policy import JevReservationPolicy
    from app.services.evaluation.benchmark.mock_provider import BenchmarkMockProvider,scripted_embeddings
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pools=await rerank_context(db,agent_context)
        from app.services.assessment.policy import benchmark_policy
        ep=benchmark_policy('hybrid',retrieval_version='v2')
        run.snapshot={**run.snapshot,'assessment_execution_policy':ep.to_snapshot(),'assessment_execution_policy_hash':ep.digest,
            'assessment_prompt_version':ep.assessment_prompt_version}
        await db.commit()
        financial=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),'2026-10-09',frozenset(p.accepted_models),p.endpoint)
        jev=ChoiceProvider()
        with scripted_embeddings(True):
            await execute_assessment_job(db,run.job_id,provider_override=BenchmarkMockProvider(),
                rerank_provider_override=jev,rerank_financial_policy=financial)
        assert run.status=='succeeded' and jev.calls>=1
        assert run.rerank_output['stages'][0]['stage']=='initial'
        assert run.execution_trace['model_round_trips']>=1
