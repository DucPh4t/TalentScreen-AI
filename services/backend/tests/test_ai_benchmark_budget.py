"""Conservative input bounds, one experiment cap and held ambiguous spend."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import uuid
import httpx
import pytest
from sqlalchemy import select,update
from app.config import get_settings
from app.db.models import BudgetPeriod,BudgetReservation,LLMInvocation
from app.domain.enums import BudgetScope
from app.services.assessment.policy import benchmark_policy
from app.services.evaluation.benchmark.contracts import InputBound,PROFILES
from app.services.evaluation.benchmark.dataset import load_inputs,select_runs
from app.services.evaluation.benchmark.preflight import plan_budget,validate_live_preflight
from app.services.llm.cost import RATE_CARD_VERSION,estimate_request_cost
from app.services.llm.exceptions import BudgetExceededError,LLMTimeoutError,LLMServerError,LLMUsageUnavailableError,LLMModelChangedError
from app.services.llm.ledger import get_or_create_active_budget_period,reserve_budget
from app.services.llm.orchestrator import execute_bounded_llm_call,PreconditionViolationError
from app.services.llm.provider import BaseLLMProvider,DeepSeekHTTPXProvider
from app.services.llm.types import CompletionRequest,CompletionResult,StrictReservationPolicy
from tests.test_llm_adapter import setup_llm_test_context
from tests.test_assessment_agent import agent_context

DATA=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/v1'

def byte_bound():
    return InputBound(strategy='verified_utf8',max_input_tokens=69632,max_serialized_bytes=65536,
        framing_allowance=4096,tokenizer_artifact_sha256='c90dfa01249db1be4245780a052ede752e1361c612ac6d08e2bdada7d599476b',
        proof_reference='docs/evaluation/deepseek-token-bound.json',rate_card_version=RATE_CARD_VERSION)

def test_plan_includes_unicode_tool_history_and_repairs():
    inputs=load_inputs(DATA)
    selection=select_runs(inputs,split=None,case_ids=('node-01','ai-01','android-01'),profiles=PROFILES,seed=20261008)
    plan=plan_budget(inputs,selection,{p:benchmark_policy(p) for p in PROFILES},model='deepseek-flash',cap_usd=Decimal('5'),bound=byte_bound())
    assert plan.admitted and len(plan.combinations)==12
    assert all(c.max_calls==4 and c.max_output_tokens==4096 for c in plan.combinations)
    assert plan.total_upper_usd==estimate_request_cost(69632,4096)*4*12
    policy=StrictReservationPolicy(budget_period_id=uuid.uuid4(),cap_usd=Decimal('5'),bound=byte_bound(),requested_model='deepseek-flash')
    request=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt='',messages=[
        {'role':'system','content':'Vietnamese résumé'}, {'role':'user','content':'é'*33000}],strict_reservation_policy=policy)
    with pytest.raises(PreconditionViolationError,match='BYTE_LIMIT'):
        policy.input_reservation_tokens(request)
    request.messages[1]['content']='é'*100
    assert policy.input_reservation_tokens(request)==69632


def test_over_budget_plan_makes_no_provider_calls():
    inputs=load_inputs(DATA)
    selection=select_runs(inputs,split='all',case_ids=(),profiles=PROFILES,seed=1)
    plan=plan_budget(inputs,selection,{p:benchmark_policy(p) for p in PROFILES},model='deepseek-flash',cap_usd=Decimal('5'),bound=byte_bound())
    assert not plan.admitted and len(plan.combinations)==240
    with pytest.raises(ValueError,match='BUDGET'):
        validate_live_preflight(plan,provider_host='api.deepseek.com',pricing_verified_at='2026-10-08',model_available_locally=True)
    fallback=byte_bound().model_copy(update={'strategy':'model_context','max_input_tokens':1048576,
        'max_serialized_bytes':None,'framing_allowance':None,'tokenizer_artifact_sha256':None})
    subset=select_runs(inputs,split=None,case_ids=('node-01','ai-01','android-01'),profiles=PROFILES,seed=1)
    assert not plan_budget(inputs,subset,{p:benchmark_policy(p) for p in PROFILES},model='deepseek-flash',cap_usd=Decimal('5'),bound=fallback).admitted

@pytest.fixture
async def fresh_period(test_session_factory,monkeypatch):
    monkeypatch.setattr(get_settings(),'DEV_EVAL_BUDGET_USD',5.0)
    async with test_session_factory() as db:
        await db.execute(update(BudgetPeriod).where(BudgetPeriod.scope==BudgetScope.DEVELOPMENT).values(
            period_end=datetime.now(timezone.utc)-timedelta(seconds=1)))
        period=await get_or_create_active_budget_period(db,BudgetScope.DEVELOPMENT)
        await db.commit()
        return period.id

@pytest.mark.asyncio
async def test_three_roles_share_one_experiment_cap(test_session_factory,fresh_period):
    async with test_session_factory() as db:
        for _ in range(2):
            _,req,*_,job=await setup_llm_test_context(db)
            reservation=await reserve_budget(db,job.id,Decimal('2'),BudgetScope.DEVELOPMENT,requisition_id=req.id)
            assert reservation.budget_period_id==fresh_period
            await db.commit()
        _,req,*_,job=await setup_llm_test_context(db)
        with pytest.raises(BudgetExceededError):
            await reserve_budget(db,job.id,Decimal('2'),BudgetScope.DEVELOPMENT,requisition_id=req.id)
        await db.rollback()
        period=await db.get(BudgetPeriod,fresh_period)
        assert period.reserved_usd==Decimal('4') and period.limit_usd==Decimal('5')

class ResponseProvider(BaseLLMProvider):
    def __init__(self,result):self.result=result;self.calls=0
    async def complete(self,request):
        self.calls+=1
        if isinstance(self.result,Exception):raise self.result
        return self.result

@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',['timeout','server','transport','missing_input','missing_output'])
async def test_unknown_or_missing_usage_retains_reservation(outcome,test_session_factory,fresh_period):
    responses={'timeout':LLMTimeoutError(),'server':LLMServerError(),'transport':RuntimeError('transport lost'),
        'missing_input':CompletionResult(content='{}',requested_model='deepseek-flash',output_tokens=10),
        'missing_output':CompletionResult(content='{}',requested_model='deepseek-flash',input_tokens=10)}
    provider=ResponseProvider(responses[outcome])
    async with test_session_factory() as db:
        *_,job=await setup_llm_test_context(db)
        await db.commit()
        policy=StrictReservationPolicy(budget_period_id=fresh_period,cap_usd=Decimal('5'),bound=byte_bound(),requested_model='deepseek-flash')
        request=CompletionRequest(task_kind='assessment',system_prompt='synthetic',user_prompt='synthetic',strict_reservation_policy=policy)
        with pytest.raises(Exception):
            await execute_bounded_llm_call(db,job.id,request,'agent_turn_1',1,provider_override=provider)
        invocation=await db.scalar(select(LLMInvocation).where(LLMInvocation.job_id==job.id))
        assert invocation.status.value=='outcome_unknown' and invocation.cost_actual is None
        reservation=await db.scalar(select(BudgetReservation).where(BudgetReservation.job_id==job.id))
        assert reservation.status=='outcome_unknown' and reservation.amount_usd>0
        with pytest.raises(PreconditionViolationError,match='OUTCOME_PENDING'):
            await execute_bounded_llm_call(db,job.id,request,'agent_turn_2',1,provider_override=provider)
        assert provider.calls==1

@pytest.mark.asyncio
async def test_zero_usage_is_not_replaced_by_an_estimate(test_session_factory,fresh_period):
    provider=ResponseProvider(CompletionResult(content='{}',requested_model='deepseek-flash',reported_model='deepseek-flash',
        input_tokens=0,output_tokens=0,cached_input_tokens=0))
    async with test_session_factory() as db:
        *_,job=await setup_llm_test_context(db);await db.commit()
        policy=StrictReservationPolicy(budget_period_id=fresh_period,cap_usd=Decimal('5'),bound=byte_bound(),requested_model='deepseek-flash')
        request=CompletionRequest(task_kind='assessment',system_prompt='synthetic',user_prompt='synthetic',strict_reservation_policy=policy)
        result=await execute_bounded_llm_call(db,job.id,request,'agent_turn_1',1,provider_override=provider)
        invocation=await db.scalar(select(LLMInvocation).where(LLMInvocation.job_id==job.id))
        assert result.cached_input_tokens==0 and invocation.cost_actual==Decimal('0')
        assert invocation.rate_card_version==RATE_CARD_VERSION

@pytest.mark.asyncio
async def test_cache_usage_and_model_change_are_explicit(test_session_factory,fresh_period):
    with pytest.raises(ValueError):CompletionResult(content='{}',requested_model='deepseek-flash',input_tokens=10,cached_input_tokens=11)
    assert CompletionResult(content='{}',requested_model='deepseek-flash',input_tokens=10).cached_input_tokens is None
    provider=ResponseProvider(CompletionResult(content='{}',requested_model='deepseek-flash',reported_model='other-model',input_tokens=10,output_tokens=5))
    async with test_session_factory() as db:
        *_,job=await setup_llm_test_context(db);await db.commit()
        policy=StrictReservationPolicy(budget_period_id=fresh_period,cap_usd=Decimal('5'),bound=byte_bound(),requested_model='deepseek-flash')
        request=CompletionRequest(task_kind='assessment',system_prompt='synthetic',user_prompt='synthetic',strict_reservation_policy=policy)
        with pytest.raises(LLMModelChangedError):
            await execute_bounded_llm_call(db,job.id,request,'agent_turn_1',1,provider_override=provider)
        assert provider.calls==1

@pytest.mark.asyncio
async def test_http_adapter_parses_cache_counts():
    def body(cache):
        return {'model':'deepseek-flash','choices':[{'finish_reason':'stop','message':{'content':'{}'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':2,'prompt_cache_hit_tokens':cache}}
    for cache in (0,5,11):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body(cache)))) as client:
            provider=DeepSeekHTTPXProvider(api_key='synthetic-test-key',client=client)
            request=CompletionRequest(task_kind='assessment',system_prompt='synthetic',user_prompt='synthetic')
            if cache>10:
                from app.services.llm.exceptions import LLMMalformedJSONError
                with pytest.raises(LLMMalformedJSONError):await provider.complete(request)
            else:assert (await provider.complete(request)).cached_input_tokens==cache


def test_missing_or_changed_tokenizer_artifact_cannot_enable_byte_bound(tmp_path):
    from app.services.evaluation.benchmark.preflight import verify_utf8_artifacts
    with pytest.raises(ValueError,match='PROOF_UNAVAILABLE'):verify_utf8_artifacts(tmp_path)
    (tmp_path/'tokenizer.json').write_text('{}')
    (tmp_path/'encoding.py').write_text('raise RuntimeError("must never execute")')
    with pytest.raises(ValueError,match='PROOF_UNAVAILABLE'):verify_utf8_artifacts(tmp_path)

@pytest.mark.asyncio
async def test_missing_reported_model_is_not_comparable(test_session_factory,fresh_period):
    provider=ResponseProvider(CompletionResult(content='{}',requested_model='deepseek-flash',input_tokens=10,output_tokens=5))
    async with test_session_factory() as db:
        *_,job=await setup_llm_test_context(db);await db.commit()
        policy=StrictReservationPolicy(budget_period_id=fresh_period,cap_usd=Decimal('5'),bound=byte_bound(),requested_model='deepseek-flash')
        request=CompletionRequest(task_kind='assessment',system_prompt='synthetic',user_prompt='synthetic',strict_reservation_policy=policy)
        with pytest.raises(LLMModelChangedError):
            await execute_bounded_llm_call(db,job.id,request,'agent_turn_1',1,provider_override=provider)

@pytest.mark.asyncio
async def test_graph_threads_strict_policy_to_every_request(test_session_factory,fresh_period,agent_context):
    from tests.test_assessment_agent import ScriptedProvider,_insufficient_output
    from app.db.models import AssessmentRun,RubricCriterion
    from app.services.agent.assessment_graph import run_assessment_agent
    policy=StrictReservationPolicy(budget_period_id=fresh_period,cap_usd=Decimal('5'),bound=byte_bound(),requested_model='deepseek-flash')
    provider=ScriptedProvider([CompletionResult(content=_insufficient_output(),requested_model='deepseek-flash',
        reported_model='deepseek-flash',input_tokens=0,output_tokens=0,cached_input_tokens=0)])
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()
        await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,initial_pack={'source_span_ids':[],'criteria_retrieval_map':{}},
            provider_override=provider,strict_reservation_policy=policy)
    assert len(provider.requests)==1 and provider.requests[0].strict_reservation_policy is policy


@pytest.mark.asyncio
async def test_new_fractional_budget_matches_reloaded_decimal_cap(test_session_factory,monkeypatch):
    cap=Decimal('0.14863554')
    monkeypatch.setattr(get_settings(),'DEV_EVAL_BUDGET_USD',float(cap))
    async with test_session_factory() as db:
        await db.execute(update(BudgetPeriod).where(BudgetPeriod.scope==BudgetScope.DEVELOPMENT).values(
            period_end=datetime.now(timezone.utc)-timedelta(seconds=1)))
        period=await get_or_create_active_budget_period(db,BudgetScope.DEVELOPMENT)
        assert period.limit_usd==cap
        await db.commit()
        await db.refresh(period)
        assert period.limit_usd==cap
