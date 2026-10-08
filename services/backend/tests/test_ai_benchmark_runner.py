from decimal import Decimal
import asyncio
import json
from pathlib import Path
import shutil
import pytest
from sqlalchemy import select, update
from app.config import get_settings
from app.db.models import Application, AssessmentRun, CriterionAssessment, LLMInvocation
from app.services.assessment.policy import benchmark_policy
from app.services.evaluation.benchmark.contracts import PROFILES
from app.services.evaluation.benchmark.dataset import load_inputs, select_runs
from app.services.evaluation.benchmark.preflight import plan_budget
from app.services.evaluation.benchmark.runner import run_experiment
from app.services.evaluation.benchmark.artifacts import read_records, append_record
from app.services.evaluation.benchmark.mock_provider import BenchmarkMockProvider
from tests.test_ai_benchmark_isolation import owned_context
from tests.test_ai_benchmark_budget import fresh_period, byte_bound

DATA=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/v1'

@pytest.fixture
async def experiment(test_session_factory,owned_context,fresh_period,monkeypatch,tmp_path):
    settings=get_settings()
    monkeypatch.setattr(settings,'DEEPSEEK_MODEL','mock')
    monkeypatch.setattr(settings,'JEV_MODE','off')
    inputs=load_inputs(DATA)
    selection=select_runs(inputs,split=None,case_ids=('node-01',),profiles=PROFILES,seed=20261008)
    plan=plan_budget(inputs,selection,{p:benchmark_policy(p) for p in PROFILES},model='mock',cap_usd=Decimal(5),bound=byte_bound())
    return inputs,selection,plan,owned_context,tmp_path/'result'

@pytest.mark.asyncio
async def test_runner_invokes_real_assessment_service_and_ledger(test_session_factory,experiment,monkeypatch):
    inputs,selection,plan,context,output=experiment
    from app.services.assessment import service
    original_graph=service.run_assessment_agent
    seen=[]
    async def checked_graph(**kwargs):
        assert 'GOLD_NOT_FOR_MODEL' not in json.dumps(kwargs['initial_pack'],default=str)
        assert 'GOLD_NOT_FOR_MODEL' not in json.dumps(kwargs['run'].snapshot)
        assert not any('gold' in name or 'reference' in name for name in kwargs)
        seen.append(kwargs['run'].id)
        return await original_graph(**kwargs)
    monkeypatch.setattr(service,'run_assessment_agent',checked_graph)
    provider=BenchmarkMockProvider()
    async with test_session_factory() as db:
        manifest=await run_experiment(db,inputs,selection,context,provider=provider,budget_plan=plan,output=output,embedding_mode='scripted')
        rows=read_records(output/'runs.jsonl')
        assert manifest.status=='complete' and len(rows)==4
        assert len({r.source_snapshot_hash for r in rows})==1
        for r in rows:
            run=await db.get(AssessmentRun,r.run_id)
            assert run.status=='succeeded' and r.status=='accepted'
            assert len((await db.scalars(select(CriterionAssessment).where(CriterionAssessment.run_id==r.run_id))).all())==5
            assert len((await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==r.job_id))).all())==1
    assert manifest.mode=='contract_only' and manifest.model_quality=='unmeasured'
    assert len(provider.requests)==4 and len(seen)==4
    assert 'GOLD_NOT_FOR_MODEL' not in json.dumps([r.messages for r in provider.requests])
    assert 'cv_text' not in (output/'manifest.json').read_text()
    assert 'Linh' not in (output/'admissions.jsonl').read_text()

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['snapshot','dataset','interrupt'])
async def test_stop_conditions_do_not_continue_or_persist_scores(failure,test_session_factory,experiment,tmp_path):
    inputs,selection,plan,context,output=experiment
    if failure=='dataset':
        copy=tmp_path/'dataset'
        shutil.copytree(DATA,copy)
        inputs=load_inputs(copy)
    provider=BenchmarkMockProvider()
    original=provider.complete
    async with test_session_factory() as db:
        async def sabotaged(request):
            result=await original(request)
            if failure=='snapshot':
                await db.execute(update(Application).where(Application.current_sanitized_version_id.is_not(None)).values(generation=Application.generation+1))
                await db.commit()
                from app.services.llm.types import ToolCall
                result.content=None
                result.tool_calls=[ToolCall(id='call_test',name='retrieve_more_evidence',arguments={'criterion_ids':['api_design'],'query_hint':'more'})]
            elif failure=='dataset':
                with (inputs.root/'cases.jsonl').open('a') as f:f.write('\n')
            else:raise asyncio.CancelledError()
            return result
        provider.complete=sabotaged
        manifest=await run_experiment(db,inputs,selection,context,provider=provider,budget_plan=plan,output=output,embedding_mode='scripted')
        rows=read_records(output/'runs.jsonl')
        assert manifest.status in {'partial','interrupted'} and len(rows)==4
        assert len(provider.requests)==1
        if failure in {'snapshot','interrupt'}:
            assert not (await db.scalars(select(CriterionAssessment).where(CriterionAssessment.run_id==rows[0].run_id))).all()
        with pytest.raises(ValueError,match='DUPLICATE'):
            append_record(output/'runs.jsonl',rows[0])
        with pytest.raises(ValueError,match='OUTPUT_EXISTS'):
            await run_experiment(db,inputs,selection,context,provider=provider,budget_plan=plan,output=output,embedding_mode='scripted')
    if failure=='interrupt':
        assert manifest.financial['unresolved_invocations']==1
        assert json.loads((output/'admissions.jsonl').read_text().splitlines()[0])['event']=='admitted'


def test_torn_journal_is_explicit(tmp_path):
    p=tmp_path/'runs.jsonl'
    p.write_text('{"case_id":')
    with pytest.raises(ValueError,match='INCOMPLETE'):
        read_records(p)
