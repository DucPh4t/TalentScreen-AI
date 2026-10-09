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
