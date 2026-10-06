"""Bounded LLM invocation orchestrator with approval preconditions, attempt counters, and cost tracking."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.document import SanitizedVersion
from app.db.models.ops import LLMInvocation
from app.domain.enums import BudgetScope, LLMInvocationStatus, SanitizedVersionStatus
from app.services.llm.cost import (
    calculate_actual_cost,
    calculate_jev_actual_cost,
    estimate_jev_request_cost,
    estimate_request_cost,
)
from app.services.llm.exceptions import (
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
from app.services.llm.ledger import reserve_budget, settle_budget
from app.services.llm.provider import BaseLLMProvider, get_llm_provider
from app.services.llm.types import CompletionRequest, CompletionResult
from app.services.sanitizer import residual_contact_types

logger = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_STAGE = 2
MAX_EXTERNAL_CALLS_PER_RUN = 4


def _serialized_request_payload(request: CompletionRequest) -> str:
    """Canonical request material for accurate token estimates and idempotency hashes."""
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
    # Estimate the complete serialized request, including conversation history
    # and JSON tool schemas, rather than only the legacy system/user strings.
    serialized_request = _serialized_request_payload(request)
    estimated_input_tokens = _estimate_input_tokens(request)
    if request.provider == "jev":
        settings = get_settings()
        if settings.JEV_MODE != "shadow" or not settings.JEV_DATA_PROCESSING_APPROVED:
            raise PreconditionViolationError("JEV_EGRESS_DISABLED: Jev shadow processing is not approved and enabled.")
        if settings.JEV_INPUT_PRICE_PER_MILLION_USD is None or not settings.JEV_RATE_CARD_VERIFIED_AT:
            raise PreconditionViolationError("JEV_RATE_CARD_UNVERIFIED: Jev budget rate must be verified before egress.")
        estimated_cost = estimate_jev_request_cost(estimated_input_tokens, settings.JEV_INPUT_PRICE_PER_MILLION_USD)
    else:
        estimated_cost = estimate_request_cost(
            input_tokens=estimated_input_tokens,
            max_output_tokens=request.max_output_tokens,
            model=request.model,
        )
    budget_scope = BudgetScope.DEVELOPMENT if get_settings().APP_ENV == "sandbox" else BudgetScope.PILOT
    reservation = await reserve_budget(db, job_id=job_id, amount_usd=estimated_cost, scope=budget_scope)
    await db.commit()  # commit reservation before network I/O

    # 3. Create invocation record in RESERVED status
    req_hash = hashlib.sha256(serialized_request.encode("utf-8")).hexdigest()
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
    except (LLMTimeoutError, LLMTruncatedError, LLMEmptyResponseError, LLMMalformedJSONError, LLMRefusalError) as e:
        # A request may have completed and been billed even without usable content.
        # Hold the reservation until usage is reconciled rather than marking it free.
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
        elif call_error:
            inv_record.status = LLMInvocationStatus.FAILED
            inv_record.finished_at = finished_now
            await settle_budget(db, reservation_id=reservation.id, actual_cost_usd=None)
        else:
            # Success case
            if request.provider == "jev":
                price = get_settings().JEV_INPUT_PRICE_PER_MILLION_USD
                if price is None:
                    raise ValueError("Jev price card became unavailable during settlement")
                actual_cost = calculate_jev_actual_cost(
                    input_tokens=result.input_tokens or estimated_input_tokens,
                    price_per_million_usd=price,
                )
            else:
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

    if call_error:
        raise call_error
    return result
