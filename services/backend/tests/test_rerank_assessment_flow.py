from datetime import date
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
        financial=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        jev=ChoiceProvider()
        with scripted_embeddings(True):
            await execute_assessment_job(db,run.job_id,provider_override=BenchmarkMockProvider(),
                rerank_provider_override=jev,rerank_financial_policy=financial)
        assert run.status=='succeeded' and jev.calls>=1
        assert run.rerank_output['stages'][0]['stage']=='initial'
        assert run.execution_trace['model_round_trips']>=1

@pytest.mark.asyncio
async def test_actual_two_multi_criterion_tools_and_repair_share_call_caps(test_session_factory,owned_context,fresh_period,tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from app.services.llm.types import CompletionResult,ToolCall
    from app.services.llm.provider import BaseLLMProvider
    from app.services.evaluation.benchmark.dataset import load_inputs,select_runs
    from app.services.evaluation.benchmark.runner import run_experiment
    from app.services.evaluation.benchmark.preflight import plan_budget,context_bound
    from app.services.evaluation.benchmark.reranking import experiment_policy,plan_rerank_budget,ScriptedJevProvider
    from app.services.assessment.policy import benchmark_policy
    from app.db.models import LLMInvocation
    settings=get_settings();monkeypatch.setattr(settings,'DEEPSEEK_MODEL','mock');monkeypatch.setattr(settings,'DEV_EVAL_BUDGET_USD',1)
    class ToolsAndRepair(BaseLLMProvider):
        def __init__(self):self.calls=0
        async def complete(self,request):
            self.calls+=1
            body=next(json.loads(m['content']) for m in request.messages if m['role']=='user' and m['content'].lstrip().startswith('{'))
            if self.calls<=2:
                return CompletionResult(content=None,requested_model='mock',reported_model='mock',input_tokens=0,output_tokens=0,
                    tool_calls=[ToolCall(id=f'call_qa{self.calls}',name='retrieve_more_evidence',arguments={'criterion_ids':[c['criterion_id'] for c in (body['rubric'][:4] if self.calls==1 else body['rubric'][4:])],'query_hint':'triển khai kiểm thử API' if self.calls==1 else 'technical experience implementation'})])
            if self.calls==3:result={}
            else:result={'criteria':[{'criterion_id':c['criterion_id'],'status':'insufficient_evidence','score':None,'evidence':[],
                'rationale':'Synthetic tool/repair contract','missing_information':['Clarify individual responsibility']} for c in body['rubric']]}
            return CompletionResult(content=json.dumps(result),requested_model='mock',reported_model='mock',input_tokens=0,output_tokens=0)
    root=Path(__file__).resolve().parents[3];inputs=load_inputs(root/'fixtures/ai_benchmark/golden_100')
    sel=select_runs(inputs,split=None,case_ids=('backend-003',),profiles=('hybrid_agent',),seed=1)
    b=plan_budget(inputs,sel,{'hybrid_agent':benchmark_policy('hybrid_agent',retrieval_version='v2')},model='mock',cap_usd=Decimal('1'),bound=context_bound('mock'))
    p=experiment_policy('rerank','scripted',settings);rb=plan_rerank_budget(b,sel,policy=p,reranker_provider='scripted',cap_usd=Decimal('1'))
    async with test_session_factory() as db:
        from app.db.models import BudgetPeriod
        period=await db.get(BudgetPeriod,fresh_period);period.limit_usd=1;await db.commit()
        primary=ToolsAndRepair()
        report=await run_experiment(db,inputs,sel,owned_context,provider=primary,budget_plan=b,output=tmp_path/'calls',embedding_mode='scripted',retrieval_version='v2',rerank_policy=p,reranker_provider=ScriptedJevProvider(),rerank_budget_plan=rb)
        assert report.counts['accepted']==1,(report.stop_code,(tmp_path/'calls'/'runs.jsonl').read_text())
        import uuid
        record=json.loads((tmp_path/'calls'/'runs.jsonl').read_text().splitlines()[0])
        run=await db.get(AssessmentRun,uuid.UUID(record['run_id']))
        rows=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==run.job_id))).all()
        assert primary.calls==4 and run.execution_trace['tool_execution_count']==2 and run.execution_trace['repair_count']==1
        assert len(rows)<=13 and sum(r.logical_step.startswith('jev_rerank_') for r in rows)<=9
        assert {s['stage'] for s in run.rerank_output['stages']}=={'initial','tool_1','tool_2'}

from tests.test_ai_benchmark_isolation import owned_context


@pytest.mark.asyncio
async def test_initial_rerank_pool_uses_identical_baseline_anchor_query(test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.services.assessment.service import execute_assessment_job
    from app.services.llm.call_policy import JevReservationPolicy
    from app.services.evaluation.benchmark.mock_provider import BenchmarkMockProvider,scripted_embeddings
    from app.services.assessment.policy import benchmark_policy
    from app.services import retrieval
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    captured=[];seen_focus=[];original=retrieval.collect_hybrid_candidates
    from app.services.reranking import service as ranking_service
    original_pool=ranking_service.rerank_retrieval_pool
    async def capture_pool(**kwargs):
        seen_focus.append(kwargs["focus_ids"])
        return await original_pool(**kwargs)
    monkeypatch.setattr(ranking_service,"rerank_retrieval_pool",capture_pool)
    async def capture(*args,**kwargs):
        captured.append(kwargs['anchor_terms'])
        return await original(*args,**kwargs)
    monkeypatch.setattr(retrieval,'collect_hybrid_candidates',capture)
    async with test_session_factory() as db:
        run,p,_=await rerank_context(db,agent_context)
        criterion=await db.scalar(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))
        criterion.anchors={**criterion.anchors,'0':{'description':'No API implementation','qualifying_evidence':['explicit limitation'],
            'disqualifying_evidence':['unsupported framework claim']}}
        ep=benchmark_policy('hybrid',retrieval_version='v2')
        run.snapshot={**run.snapshot,'assessment_execution_policy':ep.to_snapshot(),'assessment_execution_policy_hash':ep.digest,
            'assessment_prompt_version':ep.assessment_prompt_version,'focus_criterion_ids':['python_backend','api_design']}
        await db.commit()
        financial=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        with scripted_embeddings(True):
            await execute_assessment_job(db,run.job_id,provider_override=BenchmarkMockProvider(),
                rerank_provider_override=ChoiceProvider(),rerank_financial_policy=financial)
        assert run.status=='succeeded'
        assert captured[0]==retrieval._flatten_text_values(criterion.anchors)

        assert seen_focus==[('api_design','python_backend')]


@pytest.mark.asyncio
async def test_shadow_supplied_full_pool_keeps_baseline_top30_scope(test_session_factory,agent_context):
    import uuid
    from app.services.reranking.contracts import RerankStageResult
    from app.services import retrieval
    async with test_session_factory() as db:
        run,p,pools=await rerank_context(db,agent_context);pair=pools['api_design'][0]
        pool=[RetrievedChunkScore(uuid.uuid4(),i,pair.text,list(pair.span_ids),i+1,None,1/(60+i)) for i in range(31)]
        # Distinct actual spans make a beyond-30 section eligible for diversity.
        from app.db.models import SourceSpan
        from app.services.sanitizer import build_source_spans_from_canonical
        late=build_source_spans_from_canonical(run.sanitized_version_id,'Late unrelated section')[0]
        late_id='late_scope_test';db.add(SourceSpan(span_id=late_id,full_hash=late.full_hash,sanitized_version_id=run.sanitized_version_id,
            start_cp=0,end_cp=len(late.text),text=late.text,section_label='late-section',language='en'))
        pool[-1].span_ids=[late_id]
        await db.flush()
        criteria=[{'id':'api_design','name':pair.criterion.label,'description':pair.criterion.description}]
        expected=await build_hybrid_assessment_pack(db,run.sanitized_version_id,criteria,pipeline_version='v2',candidates_by_criterion={'api_design':pool[:30]})
        result=RerankStageResult(stage='initial',mode='shadow',ordered_pair_ids_by_criterion={},selected_pair_ids_by_criterion={})
        actual=await build_hybrid_assessment_pack(db,run.sanitized_version_id,criteria,pipeline_version='v2',candidates_by_criterion={'api_design':pool},rerank_result=result)
        assert canonical(actual)==canonical(expected)
