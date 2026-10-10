"""Bounded LLM invocation orchestrator with approval preconditions, attempt counters, and cost tracking."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import re
import hashlib
import json
import logging
from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.observability import observed, record_trace_metadata
from app.db.models import Application, AssessmentRun
from app.db.models.document import SanitizedVersion
from app.db.models.ops import LLMInvocation, BudgetReservation, Job
from app.domain.enums import BudgetScope, LLMInvocationStatus, SanitizedVersionStatus
from app.services.llm.cost import (
    RATE_CARD_VERSION, RATE_CARD_PRICING,
    calculate_actual_cost,
    calculate_jev_actual_cost,
    estimate_jev_request_cost,
    estimate_request_cost,
)
from app.services.llm.exceptions import (
    LLMUsageUnavailableError,
    LLMModelChangedError,
    LLMUsageBoundError,
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMMalformedJSONError,
    LLMModelUnavailableError,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMRefusalError,
    LLMTruncatedError,
    LLMTimeoutError,
)
from app.services.llm.ledger import reserve_budget, settle_budget, get_or_create_active_budget_period
from app.services.llm.provider import BaseLLMProvider, get_llm_provider
from app.services.llm.types import CompletionRequest, CompletionResult
from app.services.sanitizer import residual_contact_types

logger = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_STAGE = 2


def _serialized_request_payload(request: CompletionRequest) -> str:
    """Canonical request material for accurate token estimates and idempotency hashes."""
    if request.provider == 'jev':
        envelope=json.loads(request.user_prompt)
        if not isinstance(envelope,dict) or set(envelope)-{'model','state','questions'} or not {'state','questions'}<=set(envelope):
            raise ValueError('JEV_REQUEST_INVALID')
        return json.dumps({**envelope,'model':request.model},sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    messages = request.messages if request.messages is not None else [
        {"role": "system", "content": request.system_prompt},
        {"role": "user", "content": request.user_prompt},
    ]
    payload = {
        "model": request.model,
        "messages": messages,
        "tools": request.tools,
        "tool_choice": request.tool_choice,
        "response_format": request.response_format,
        "max_tokens": request.max_output_tokens,
        "temperature": request.temperature,
        "thinking": {"type": request.thinking_mode} if request.thinking_mode is not None else None,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _estimate_input_tokens(request: CompletionRequest) -> int:
    return len(_serialized_request_payload(request)) // 3 + 200


class PreconditionViolationError(Exception):
    """Raised when safety preconditions are violated before initiating an external LLM call."""
    pass


async def verify_llm_preconditions(
    db: AsyncSession,
    job_id: uuid.UUID,
    task_kind: str,
    sanitized_version_id: Optional[uuid.UUID] = None,
    stage_attempt_no: int = 1,
    max_external_calls: int | None = None,
) -> None:
    """Enforce strict safety and boundedness invariants before calling external LLM.
    Invariants:
      1. Real CV data cannot egress before Owner+RawGrant approval (SanitizedVersion status == APPROVED).
      2. Max 2 attempts per stage.
      3. Max 4 external calls per run.
    """
    # Invariant 1: Bounded stage attempts
    if stage_attempt_no > MAX_ATTEMPTS_PER_STAGE:
        raise PreconditionViolationError(
            f"MAX_STAGE_ATTEMPTS_EXCEEDED: Stage attempt {stage_attempt_no} exceeds limit of {MAX_ATTEMPTS_PER_STAGE}."
        )

    # Invariant 2: Bounded total external calls per run
    max_external_calls = max_external_calls or get_settings().ASSESSMENT_MAX_EXTERNAL_CALLS
    stmt_count = select(func.count(LLMInvocation.id)).where(LLMInvocation.job_id == job_id)
    total_calls = (await db.execute(stmt_count)).scalar() or 0
    if total_calls >= max_external_calls:
        raise PreconditionViolationError(
            f"MAX_RUN_EXTERNAL_CALLS_EXCEEDED: Total external calls ({total_calls}) reached run limit of {max_external_calls}."
        )

    # Invariant 3: Every candidate-derived prompt needs an approved, contact-free source.
    if sanitized_version_id:
        stmt_v = select(SanitizedVersion).where(SanitizedVersion.id == sanitized_version_id)
        version = (await db.execute(stmt_v)).scalar_one_or_none()
        if not version or version.status != SanitizedVersionStatus.APPROVED:
            raise PreconditionViolationError(
                "CANNOT_EGRESS_UNAPPROVED_CV: Bản sanitized phải được HR duyệt (APPROVED) trước khi gửi ra mô hình AI ngoài."
            )
        if residual_contact_types(version.canonical_text):
            raise PreconditionViolationError(
                "RESIDUAL_CONTACT_DATA: Bản sanitized vẫn chứa thông tin liên hệ; chặn gửi ra mô hình AI ngoài."
            )


async def _resolve_requisition_id_for_job(db: AsyncSession, job_id: uuid.UUID) -> uuid.UUID | None:
    """Resolve an assessment job's requisition for its independent spend ceiling."""
    stmt = (
        select(Application.requisition_id)
        .join(AssessmentRun, AssessmentRun.application_id == Application.id)
        .where(AssessmentRun.job_id == job_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def admit_invocation(db: AsyncSession, *, job_id: uuid.UUID, request: CompletionRequest,
    logical_step: str, attempt_no: int, sanitized_version_id: uuid.UUID | None,
    provider_name: str | None = None):
    from app.services.llm.call_policy import InvocationBudgetPolicy,AdmittedInvocation
    from app.services.reranking.policy import load_rerank_policy
    job=await db.scalar(select(Job).where(Job.id==job_id).with_for_update())
    if job is None or job.cancel_requested_at is not None:
        raise PreconditionViolationError('JOB_CANCELLED_OR_MISSING')
    run=await db.scalar(select(AssessmentRun).where(AssessmentRun.job_id==job_id))
    snapshot=run.snapshot if run else {}
    policy=load_rerank_policy(snapshot)
    limits=InvocationBudgetPolicy.from_snapshot(snapshot)
    if not policy.enabled:limits=InvocationBudgetPolicy(get_settings().ASSESSMENT_MAX_EXTERNAL_CALLS,0,get_settings().ASSESSMENT_MAX_EXTERNAL_CALLS)
    is_rerank=request.purpose=='jev_rerank'
    is_jev_primary=request.purpose=='jev_primary'
    is_jev_explanation=request.purpose=='jev_primary_explanation'
    namespace=bool(re.fullmatch(r'jev_rerank_(initial|tool_[12])_[1-9][0-9]*',logical_step))
    primary_namespace=logical_step=='jev_primary_score'
    explanation_namespace=logical_step=='jev_primary_explanation'
    if (is_rerank != namespace or is_jev_primary != primary_namespace
        or is_jev_explanation != explanation_namespace
        or (is_rerank and (request.provider!='jev' or not policy.enabled))
        or (is_jev_primary and (request.provider!='jev' or policy.enabled
            or snapshot.get('scorer_mode')!='jev' or get_settings().ASSESSMENT_SCORER_MODE!='jev'))
        or (is_jev_explanation and (request.provider!='deepseek' or policy.enabled
            or snapshot.get('scorer_mode')!='jev' or get_settings().ASSESSMENT_SCORER_MODE!='jev'))):
        raise PreconditionViolationError('INVOCATION_PURPOSE_MISMATCH')
    if policy.enabled and request.provider=='jev' and not is_rerank:
        raise PreconditionViolationError('JEV_PURPOSE_CONFLICT')
    if (is_jev_primary or is_jev_explanation) and attempt_no != 1:
        raise PreconditionViolationError('JEV_PRIMARY_REPLAY_BLOCKED')
    jev_primary_run = snapshot.get('scorer_mode') == 'jev'
    run_call_limit = min(4, limits.total_limit) if jev_primary_run else limits.total_limit
    await verify_llm_preconditions(db,job_id,request.task_kind,sanitized_version_id,attempt_no,run_call_limit)
    rows=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==job_id))).all()
    count=sum(i.logical_step.startswith('jev_rerank_') for i in rows)
    jev_primary_count=sum(i.logical_step=='jev_primary_score' for i in rows)
    normal_primary_count = len(rows) - count - jev_primary_count
    if ((is_rerank and count>=limits.rerank_limit) or (not is_rerank and not is_jev_primary and normal_primary_count>=limits.primary_limit)
        or (is_jev_primary and jev_primary_count>=1)):
        raise PreconditionViolationError('MAX_PROVIDER_CALLS_EXCEEDED')
    if any(i.logical_step==logical_step and i.attempt_no==attempt_no for i in rows):
        raise PreconditionViolationError('INVOCATION_ALREADY_ADMITTED')
    strict=request.strict_reservation_policy
    financial=request.jev_reservation_policy
    if policy.enabled and policy.provider_kind=='scripted' and (get_settings().APP_ENV!='sandbox' or not snapshot.get('assessment_execution_policy')):
        raise PreconditionViolationError('SCRIPTED_RERANK_SANDBOX_ONLY')
    if is_rerank and (financial is None or request.model!=policy.requested_model
        or financial.accepted_models!=frozenset(policy.accepted_models)
        or financial.provider_endpoint!=policy.endpoint or financial.rate_per_million_usd!=Decimal(str(policy.rate_per_million_usd))
        or financial.rate_verified_at!=policy.rate_verified_at):
        raise PreconditionViolationError('JEV_REQUEST_POLICY_MISMATCH')
    if is_jev_primary:
        settings=get_settings()
        if (financial is None or request.model!=snapshot.get('scorer_model')
            or financial.accepted_models!=frozenset({snapshot.get('scorer_model')})
            or financial.provider_endpoint!=snapshot.get('scorer_endpoint')
            or financial.rate_per_million_usd!=Decimal(str(snapshot.get('scorer_input_rate_per_million_usd')))
            or financial.rate_verified_at!=snapshot.get('scorer_rate_verified_at')
            or not settings.JEV_DATA_PROCESSING_APPROVED):
            raise PreconditionViolationError('JEV_PRIMARY_REQUEST_POLICY_MISMATCH')
    if strict and financial:raise PreconditionViolationError('INVOCATION_PURPOSE_MISMATCH')
    estimate=financial.input_reservation_tokens(request) if financial else strict.input_reservation_tokens(request) if strict else _estimate_input_tokens(request)
    scope=BudgetScope.DEVELOPMENT if get_settings().APP_ENV=='sandbox' else BudgetScope.PILOT
    period=await get_or_create_active_budget_period(db,scope,for_update=True)
    if strict or financial:
        budget_policy=financial or strict
        if (strict and get_settings().APP_ENV!='sandbox') or period.id!=budget_policy.budget_period_id or period.limit_usd!=budget_policy.cap_usd:
            raise PreconditionViolationError('BENCHMARK_BUDGET_PERIOD_MISMATCH')
    if strict or financial or policy.enabled:
        pending=await db.scalar(select(BudgetReservation.id).where(BudgetReservation.budget_period_id==period.id,
            BudgetReservation.status.in_(('reserved','outcome_unknown')),BudgetReservation.amount_usd>0).limit(1))
        if pending is not None:raise PreconditionViolationError('BENCHMARK_OUTCOME_PENDING')
    if request.provider=='jev':
        settings=get_settings()
        if (policy.provider_kind!='scripted' and not settings.JEV_DATA_PROCESSING_APPROVED) or (
            not is_rerank and not is_jev_primary and settings.JEV_MODE!='shadow'
        ):
            raise PreconditionViolationError('JEV_EGRESS_DISABLED')
        rate=financial.rate_per_million_usd if financial else settings.JEV_INPUT_PRICE_PER_MILLION_USD
        if rate is None or (not financial and not settings.JEV_RATE_CARD_VERIFIED_AT):
            raise PreconditionViolationError('JEV_RATE_CARD_UNVERIFIED')
        cost=Decimal(0) if policy.provider_kind=='scripted' else estimate_jev_request_cost(estimate,rate)
        input_rate=Decimal(str(rate));output_rate=Decimal(0)
        accepted=financial.accepted_models if financial else frozenset()
    else:
        cost=estimate_request_cost(estimate,request.max_output_tokens,request.model)
        input_rate=RATE_CARD_PRICING[request.model]['input_cache_miss_per_million']
        output_rate=RATE_CARD_PRICING[request.model]['output_per_million']
        accepted=frozenset(strict.accepted_reported_models) if strict else frozenset()
    req_id=await _resolve_requisition_id_for_job(db,job_id)
    reservation=await reserve_budget(db,job_id,cost,scope,requisition_id=req_id)
    now=datetime.now(timezone.utc)
    invocation=LLMInvocation(id=uuid.uuid4(),job_id=job_id,logical_step=logical_step,attempt_no=attempt_no,
        status=LLMInvocationStatus.RESERVED,provider=provider_name or request.provider,model_resolved=request.model,
        request_hash=hashlib.sha256(_serialized_request_payload(request).encode()).hexdigest(),cost_reserved=cost,
        rate_card_version=RATE_CARD_VERSION if request.provider!='jev' else policy.rate_verified_at,
        admitted_at=now,created_at=now)
    db.add(invocation)
    await db.commit()
    return AdmittedInvocation(invocation.id,reservation.id,cost,estimate,input_rate,output_rate,accepted)


@observed("bounded_llm_call", run_type="llm", input_metadata=lambda args: {
    "job_id": str(args["job_id"]), "task_kind": args["request"].task_kind,
    "attempt_no": args["attempt_no"], "model": args["request"].model,
    "ls_model_name": args["request"].model, "external_call_count": 0,
}, result_metadata=lambda result: {
    "outcome": "succeeded", "tool_call_count": len(result.tool_calls),
    "model": result.reported_model or result.requested_model,
    "ls_model_name": result.reported_model or result.requested_model,
    "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
    "provider_latency_ms": result.latency_ms, "cached_input_tokens": result.cached_input_tokens,
    "usage_metadata": {"input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
        "total_tokens": (result.input_tokens + result.output_tokens)
            if result.input_tokens is not None and result.output_tokens is not None else None},
})
async def execute_bounded_llm_call(
    db: AsyncSession,
    job_id: uuid.UUID,
    request: CompletionRequest,
    logical_step: str,
    attempt_no: int,
    sanitized_version_id: Optional[uuid.UUID] = None,
    provider_override: Optional[BaseLLMProvider] = None,
) -> CompletionResult:
    """Execute a single bounded LLM call with budget reservation, invocation persistence, and cost settlement."""
    llm = provider_override or get_llm_provider()
    admission = await admit_invocation(db, job_id=job_id, request=request, logical_step=logical_step,
        attempt_no=attempt_no, sanitized_version_id=sanitized_version_id, provider_name=type(llm).__name__)
    invocation_id=admission.invocation_id
    reservation_id=admission.reservation_id
    estimated_input_tokens=admission.input_upper_tokens
    strict_policy=request.strict_reservation_policy
    jev_policy=request.jev_reservation_policy
    provider_label='jev' if request.provider=='jev' else 'mock' if 'mock' in type(llm).__name__.lower() else 'deepseek'
    record_trace_metadata({'provider':provider_label,'ls_provider':provider_label})

    # 4. Execute external provider call outside DB transaction
    result: Optional[CompletionResult] = None
    call_error: Optional[Exception] = None
    outcome_unknown = False

    try:
        record_trace_metadata({"external_call_count": 1})
        result = await llm.complete(request)
        if strict_policy or jev_policy:
            if result.input_tokens is None or result.output_tokens is None:
                raise LLMUsageUnavailableError()
            if result.reported_model not in admission.accepted_models:
                raise LLMModelChangedError()
            if (result.input_tokens > admission.input_upper_tokens
                or result.output_tokens > request.max_output_tokens):
                raise LLMUsageBoundError()
    except (LLMAuthenticationError, LLMQuotaExhaustedError, LLMModelUnavailableError) as e:
        # Non-retryable configuration errors: zero actual cost if network call was not made/rejected
        call_error = e
        outcome_unknown = False
    except (LLMTimeoutError, LLMTruncatedError, LLMEmptyResponseError, LLMMalformedJSONError, LLMRefusalError) as e:
        # A request may have completed and been billed even without usable content.
        # Hold the reservation until usage is reconciled rather than marking it free.
        call_error = e
        outcome_unknown = True
    except Exception as e:
        call_error = e
        outcome_unknown = strict_policy is not None or jev_policy is not None or request.purpose=="jev_rerank"

    # 5. Settle cost and persist invocation record in fresh transaction
    finished_now = datetime.now(timezone.utc)
    async with db.begin():
        # Refresh invocation
        stmt_inv = select(LLMInvocation).where(LLMInvocation.id == invocation_id).with_for_update()
        inv_record = (await db.execute(stmt_inv)).scalar_one()

        if result is not None:
            inv_record.input_tokens = result.input_tokens
            inv_record.output_tokens = result.output_tokens
            inv_record.model_resolved = result.reported_model or request.model
        if outcome_unknown:
            inv_record.status = LLMInvocationStatus.OUTCOME_UNKNOWN
            inv_record.finished_at = finished_now
            await settle_budget(db, reservation_id=reservation_id, outcome_unknown=True)
        elif call_error:
            inv_record.status = LLMInvocationStatus.FAILED
            inv_record.finished_at = finished_now
            await settle_budget(db, reservation_id=reservation_id, actual_cost_usd=None)
        else:
            # Success case
            if request.provider == "jev":
                price = admission.input_rate_per_million_usd
                actual_cost = Decimal(0) if price==0 else calculate_jev_actual_cost(
                    input_tokens=result.input_tokens if result.input_tokens is not None else estimated_input_tokens,
                    price_per_million_usd=price,
                )
            else:
                actual_cost = calculate_actual_cost(
                    input_tokens=result.input_tokens if result.input_tokens is not None else estimated_input_tokens,
                    output_tokens=result.output_tokens if result.output_tokens is not None else 0,
                    cached_input_tokens=result.cached_input_tokens or 0,
                    model=request.model,
                )

            inv_record.status = LLMInvocationStatus.SUCCEEDED
            inv_record.model_resolved = result.reported_model or request.model
            inv_record.input_tokens = result.input_tokens
            inv_record.output_tokens = result.output_tokens
            inv_record.provider_request_id = result.provider_request_id
            inv_record.cost_actual = float(actual_cost)
            record_trace_metadata({"cost_actual_usd": float(actual_cost)})
            inv_record.finished_at = finished_now

            await settle_budget(db, reservation_id=reservation_id, actual_cost_usd=actual_cost)

    if call_error:
        raise call_error
    return result
