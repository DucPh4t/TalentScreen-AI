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


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_score',[True,'3',3.0])
async def test_raw_score_types_fail_at_provider_to_service_boundary(bad_score,test_session_factory,experiment):
    inputs,selection,plan,context,output=experiment
    provider=BenchmarkMockProvider();original=provider.complete
    async def malformed(request):
        result=await original(request)
        payload=next(json.loads(m['content']) for m in request.messages if m['role']=='user' and m['content'].lstrip().startswith('{'))
        body=json.loads(result.content)
        body['criteria'][0].update(status='assessed',score=bad_score,evidence=[payload['source_spans'][0]],missing_information=[])
        result.content=json.dumps(body)
        return result
    provider.complete=malformed
    async with test_session_factory() as db:
        manifest=await run_experiment(db,inputs,selection,context,provider=provider,budget_plan=plan,output=output,embedding_mode='scripted')
        rows=read_records(output/'runs.jsonl')
        assert manifest.status=='partial'
        assert all(r.status=='failed' and r.diagnostics['counters']['schema_failures']==2 for r in rows)
        assert not (await db.scalars(select(CriterionAssessment).where(CriterionAssessment.run_id.in_([r.run_id for r in rows])))).all()


@pytest.mark.asyncio
@pytest.mark.parametrize('change_within_combination',[False,True])
async def test_alternating_served_models_stop_the_experiment(change_within_combination,test_session_factory,experiment,monkeypatch):
    inputs,_,_,context,output=experiment
    selection=select_runs(inputs,split=None,case_ids=('node-01','ai-01'),profiles=('full_text',),seed=1)
    monkeypatch.setattr(get_settings(),'DEEPSEEK_MODEL','deepseek-flash')
    plan=plan_budget(inputs,selection,{'full_text':benchmark_policy('full_text')},model='deepseek-flash',cap_usd=Decimal(5),bound=byte_bound())
    provider=BenchmarkMockProvider();original=provider.complete
    async def alternating(request):
        result=await original(request)
        result.reported_model='deepseek-flash' if len(provider.requests)==1 else 'deepseek-v4.1-flash'
        if change_within_combination and len(provider.requests)==1:result.content='{}'
        return result
    provider.complete=alternating
    async with test_session_factory() as db:
        manifest=await run_experiment(db,inputs,selection,context,provider=provider,budget_plan=plan,output=output,embedding_mode='real')
    rows=read_records(output/'runs.jsonl')
    assert manifest.status=='partial' and manifest.stop_code=='LLMModelChangedError'
    assert manifest.provenance['first_reported_model']=='deepseek-flash'
    assert manifest.provenance['model_comparability']=='invalid_model_change'
    assert len(provider.requests)==2
    assert rows[0 if change_within_combination else 1].status=='failed'
    events=[json.loads(s) for s in (output/'admissions.jsonl').read_text().splitlines()]
    assert any(e.get('event')=='model_identity_changed' for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize('all_oversize',[False,True])
async def test_context_diagnostics_survive_disposable_database(all_oversize,test_session_factory,experiment,monkeypatch):
    from app.services.evaluation.benchmark import seed
    from app.services.assessment import service
    from app.db.models import SanitizedVersion,SourceSpan
    from app.services.sanitizer import build_source_spans_from_canonical
    from sqlalchemy import delete
    import hashlib
    inputs,_,_,context,output=experiment
    profile='hybrid' if all_oversize else 'full_text'
    selection=select_runs(inputs,split=None,case_ids=('node-01',),profiles=(profile,),seed=1)
    plan=plan_budget(inputs,selection,{profile:benchmark_policy(profile)},model='mock',cap_usd=Decimal(5),bound=byte_bound())
    if all_oversize:monkeypatch.setattr(service,'MAX_ASSESSMENT_EVIDENCE_CHARS',1)
    else:
        original=seed.seed_cases
        async def long_fixture(db,*args,**kwargs):
            seeded=await original(db,*args,**kwargs)
            for item in seeded.values():
                version=await db.get(SanitizedVersion,item.sanitized_version_id)
                version.canonical_text=('Synthetic technical evidence ' * 45 + '\n') * 24
                version.sha256=hashlib.sha256(version.canonical_text.encode()).hexdigest()
                await db.execute(delete(SourceSpan).where(SourceSpan.sanitized_version_id==version.id))
                db.add_all(build_source_spans_from_canonical(version.id,version.canonical_text))
            await db.flush()
            return seeded
        monkeypatch.setattr(seed,'seed_cases',long_fixture)
    provider=BenchmarkMockProvider()
    async with test_session_factory() as db:
        await run_experiment(db,inputs,selection,context,provider=provider,budget_plan=plan,output=output,embedding_mode='scripted')
    row=read_records(output/'runs.jsonl')[0]
    ctx=row.diagnostics['context']
    assert ctx['initial_excluded_span_count']>0
    assert ctx['initial_delivered_characters']<=ctx['character_limit']
    assert ctx['original_span_count']==ctx['initial_delivered_span_count']+ctx['initial_excluded_span_count']
    assert ctx['original_characters']==ctx['initial_delivered_characters']+ctx['initial_excluded_characters']
    assert ctx['context_limit']==all_oversize
    if all_oversize:
        assert not provider.requests and row.error_code=='ASSESSMENT_CONTEXT_LIMIT'
        assert ctx['initial_delivered_span_count']==0
    else:
        assert len(provider.requests)==1 and ctx['initial_delivered_span_count']>0
