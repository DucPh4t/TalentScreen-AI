from datetime import date
import asyncio
from decimal import Decimal
import pytest
from sqlalchemy import select
from app.db.models import AssessmentRun,LLMInvocation,BudgetReservation
from app.services.llm.types import CompletionRequest,CompletionResult
from app.services.llm.orchestrator import execute_bounded_llm_call,PreconditionViolationError
from tests.test_llm_adapter import setup_llm_test_context
from tests.test_ai_benchmark_budget import fresh_period,ResponseProvider
from tests.test_rerank_kernel import policy,pair
from tests.test_assessment_agent import agent_context


@pytest.mark.asyncio
async def test_atomic_off_admission_race_last_slot(test_session_factory,fresh_period):
    from app.services.llm.orchestrator import admit_invocation
    async with test_session_factory() as db:
        *_,job=await setup_llm_test_context(db);await db.commit();job_id=job.id
        for n in range(3):
            request=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt='{}',model='mock')
            await execute_bounded_llm_call(db,job_id,request,f'primary_{n}',1,
                provider_override=ResponseProvider(CompletionResult(content='{}',requested_model='mock',input_tokens=0,output_tokens=0)))
    async def admit(n):
        async with test_session_factory() as db:
            try:
                await admit_invocation(db,job_id=job_id,request=request,logical_step=f'last_{n}',attempt_no=1,sanitized_version_id=None)
                return True
            except PreconditionViolationError:
                await db.rollback();return False
    assert sorted(await asyncio.gather(admit(1),admit(2)))==[False,True]
    async with test_session_factory() as db:
        invocations=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==job_id))).all()
        assert len(invocations)==4


def test_provider_ceilings_use_frozen_policy():
    from app.services.llm.call_policy import InvocationBudgetPolicy
    p=policy();c=InvocationBudgetPolicy.from_snapshot({'reranking_policy':p.model_dump(mode='json'),'reranking_policy_hash':p.digest})
    assert (c.primary_limit,c.rerank_limit,c.total_limit)==(4,9,13)
    assert InvocationBudgetPolicy.from_snapshot({}).total_limit==4

@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['rerank_limit','primary_limit','unknown_usage'])
async def test_rerank_provider_limits_and_unknown_usage(kind,test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.config import get_settings
    from app.services.llm.call_policy import JevReservationPolicy
    from app.domain.enums import LLMInvocationStatus
    from app.services.reranking.contracts import canonical
    from app.services.reranking.prompt import build_jev_payload
    from tests.test_rerank_journal import rerank_context,ChoiceProvider
    from app.services.llm.exceptions import LLMUsageUnavailableError
    import uuid
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pairs=await rerank_context(db,agent_context)
        f=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        request=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt=canonical(build_jev_payload(tuple(pairs['api_design']),p)),model=p.requested_model,
            provider='jev',purpose='jev_rerank',max_output_tokens=0,jev_reservation_policy=f)
        if kind=='unknown_usage':
            result=CompletionResult(content='{}',requested_model=p.requested_model,reported_model=p.accepted_models[0],output_tokens=0)
            with pytest.raises(LLMUsageUnavailableError):
                await execute_bounded_llm_call(db,run.job_id,request,'jev_rerank_initial_1',1,provider_override=ResponseProvider(result))
            assert (await db.scalar(select(BudgetReservation).where(BudgetReservation.job_id==run.job_id))).status=='outcome_unknown'
            with pytest.raises(PreconditionViolationError,match='OUTCOME_PENDING'):
                await execute_bounded_llm_call(db,run.job_id,request,'jev_rerank_initial_2',1,provider_override=ChoiceProvider())
        else:
            count=9 if kind=='rerank_limit' else 4
            for n in range(count):
                db.add(LLMInvocation(id=uuid.uuid4(),job_id=run.job_id,logical_step=f'jev_rerank_initial_{n+1}' if kind=='rerank_limit' else f'agent_turn_{n+1}',
                    attempt_no=1,status=LLMInvocationStatus.FAILED,provider='jev' if kind=='rerank_limit' else 'mock',model_resolved='mock',request_hash='a'*64,cost_reserved=0))
            await db.commit()
            if kind=='primary_limit':request=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt='{}',model='mock')
            with pytest.raises(PreconditionViolationError,match='MAX_PROVIDER_CALLS'):
                await execute_bounded_llm_call(db,run.job_id,request,'jev_rerank_tool_1_1' if kind=='rerank_limit' else 'repair',1,provider_override=ChoiceProvider())
