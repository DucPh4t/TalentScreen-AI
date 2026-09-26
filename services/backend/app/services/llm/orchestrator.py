"""Bounded LLM invocation orchestrator with approval preconditions, attempt counters, and cost tracking."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import SanitizedVersion
from app.db.models.ops import LLMInvocation
from app.domain.enums import LLMInvocationStatus, SanitizedVersionStatus
from app.services.llm.cost import calculate_actual_cost, estimate_request_cost
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMModelUnavailableError,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMTimeoutError,
)
from app.services.llm.ledger import reserve_budget, settle_budget
from app.services.llm.provider import BaseLLMProvider, get_llm_provider
from app.services.llm.types import CompletionRequest, CompletionResult

logger = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_STAGE = 2
MAX_EXTERNAL_CALLS_PER_RUN = 4


class PreconditionViolationError(Exception):
    """Raised when safety preconditions are violated before initiating an external LLM call."""
    pass


async def verify_llm_preconditions(
    db: AsyncSession,
    job_id: uuid.UUID,
    task_kind: str,
    sanitized_version_id: Optional[uuid.UUID] = None,
    stage_attempt_no: int = 1,
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
    stmt_count = select(func.count(LLMInvocation.id)).where(LLMInvocation.job_id == job_id)
    total_calls = (await db.execute(stmt_count)).scalar() or 0
    if total_calls >= MAX_EXTERNAL_CALLS_PER_RUN:
        raise PreconditionViolationError(
            f"MAX_RUN_EXTERNAL_CALLS_EXCEEDED: Total external calls ({total_calls}) reached run limit of {MAX_EXTERNAL_CALLS_PER_RUN}."
        )

    # Invariant 3: Sanitized version must be APPROVED before assessment egress
    if task_kind == "assessment" and sanitized_version_id:
        stmt_v = select(SanitizedVersion).where(SanitizedVersion.id == sanitized_version_id)
        version = (await db.execute(stmt_v)).scalar_one_or_none()
        if not version or version.status != SanitizedVersionStatus.APPROVED:
            raise PreconditionViolationError(
                "CANNOT_EGRESS_UNAPPROVED_CV: Bản sanitized phải được HR duyệt (APPROVED) trước khi gửi ra mô hình AI ngoài."
            )


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
    now = datetime.now(timezone.utc)

    # 1. Enforce preconditions
    await verify_llm_preconditions(
        db=db,
        job_id=job_id,
        task_kind=request.task_kind,
        sanitized_version_id=sanitized_version_id,
        stage_attempt_no=attempt_no,
    )

    # 2. Reserve budget
    # Estimate prompt token count
    estimated_input_tokens = len(request.system_prompt + request.user_prompt) // 3 + 200
    estimated_cost = estimate_request_cost(
        input_tokens=estimated_input_tokens,
        max_output_tokens=request.max_output_tokens,
        model=request.model,
    )
    reservation = await reserve_budget(db, job_id=job_id, amount_usd=estimated_cost)
    await db.commit()  # commit reservation before network I/O

    # 3. Create invocation record in RESERVED status
    req_hash = hashlib.sha256(f"{request.system_prompt}:{request.user_prompt}".encode("utf-8")).hexdigest()
    llm = provider_override or get_llm_provider()
    provider_name = type(llm).__name__

    invocation = LLMInvocation(
        id=uuid.uuid4(),
        job_id=job_id,
        logical_step=logical_step,
        attempt_no=attempt_no,
        status=LLMInvocationStatus.RESERVED,
        provider=provider_name,
        model_resolved=request.model,
        request_hash=req_hash,
        cost_reserved=float(estimated_cost),
        admitted_at=now,
        created_at=now,
    )
    db.add(invocation)
    await db.commit()

    # 4. Execute external provider call outside DB transaction
    result: Optional[CompletionResult] = None
    call_error: Optional[Exception] = None
    outcome_unknown = False

    try:
        result = await llm.complete(request)
    except (LLMAuthenticationError, LLMQuotaExhaustedError, LLMModelUnavailableError) as e:
        # Non-retryable configuration errors: zero actual cost if network call was not made/rejected
        call_error = e
        outcome_unknown = False
    except LLMTimeoutError as e:
        # Transport timeout: provider outcome is unknown (may or may not have billed)
        call_error = e
        outcome_unknown = True
    except Exception as e:
        call_error = e
        outcome_unknown = False

    # 5. Settle cost and persist invocation record in fresh transaction
    finished_now = datetime.now(timezone.utc)
    async with db.begin():
        # Refresh invocation
        stmt_inv = select(LLMInvocation).where(LLMInvocation.id == invocation.id).with_for_update()
        inv_record = (await db.execute(stmt_inv)).scalar_one()

        if outcome_unknown:
            inv_record.status = LLMInvocationStatus.OUTCOME_UNKNOWN
            inv_record.finished_at = finished_now
            await settle_budget(db, reservation_id=reservation.id, outcome_unknown=True)
            raise call_error

        if call_error:
            inv_record.status = LLMInvocationStatus.FAILED
            inv_record.finished_at = finished_now
            await settle_budget(db, reservation_id=reservation.id, actual_cost_usd=None)
            raise call_error

        # Success case
        actual_cost = calculate_actual_cost(
            input_tokens=result.input_tokens or estimated_input_tokens,
            output_tokens=result.output_tokens or 0,
            model=request.model,
        )

        inv_record.status = LLMInvocationStatus.SUCCEEDED
        inv_record.model_resolved = result.reported_model or request.model
        inv_record.input_tokens = result.input_tokens
        inv_record.output_tokens = result.output_tokens
        inv_record.provider_request_id = result.provider_request_id
        inv_record.cost_actual = float(actual_cost)
        inv_record.finished_at = finished_now

        await settle_budget(db, reservation_id=reservation.id, actual_cost_usd=actual_cost)

    return result
