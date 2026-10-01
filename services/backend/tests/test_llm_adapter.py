"""Tests for Task B09: DeepSeek adapter, fault injection, capabilities probe, and budget cost ledger."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select, update
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    Application,
    BudgetReservation,
    BudgetPeriod,
    Candidate,
    Document,
    Job,
    LLMInvocation,
    Requisition,
    SanitizedVersion,
    User,
    UserAccountRole,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import (
    AccountRole,
    BudgetScope,
    DocumentSafetyStatus,
    JobStatus,
    JobType,
    LLMInvocationStatus,
    RequisitionStatus,
    SanitizedVersionStatus,
    UserStatus,
)
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session
from app.services.llm.cost import (
    calculate_actual_cost,
    estimate_request_cost,
)
from app.services.llm.exceptions import (
    BudgetExceededError,
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMModelUnavailableError,
    LLMQuotaExhaustedError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServerError,
    LLMTimeoutError,
    LLMTruncatedError,
)
from app.services.llm.ledger import (
    get_or_create_active_budget_period,
    reserve_budget,
    settle_budget,
)
from app.services.llm.orchestrator import (
    PreconditionViolationError,
    execute_bounded_llm_call,
    verify_llm_preconditions,
)
from app.services.llm.probe import run_capability_probe
from app.services.llm.provider import DeepSeekHTTPXProvider, MockLLMProvider
from app.services.llm.types import CompletionRequest


async def setup_llm_test_context(session):
    """Helper to set up organization, requisition, candidate, application, document, and job."""
    from app.services.requisition import get_or_create_default_org
    org = await get_or_create_default_org(session)

    req = Requisition(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="LLM Test Requisition",
        status=RequisitionStatus.OPEN,
        row_version=1,
    )
    session.add(req)
    await session.flush()

    cand = Candidate(
        id=uuid.uuid4(),
        organization_id=org.id,
        public_label=f"CAND-{uuid.uuid4().hex[:6].upper()}",
        status="active",
    )
    session.add(cand)
    await session.flush()

    app_obj = Application(
        id=uuid.uuid4(),
        requisition_id=req.id,
        candidate_id=cand.id,
        status="active",
        generation=1,
        row_version=1,
    )
    session.add(app_obj)
    await session.flush()

    doc = Document(
        id=uuid.uuid4(),
        application_id=app_obj.id,
        version_no=1,
        kind="cv",
        original_name_private="test.pdf",
        mime_verified="application/pdf",
        byte_size=100,
        sha256="abc" * 21 + "a",
        blob_key="dummy_key",
        ingestion_status="parsed",
        safety_status=DocumentSafetyStatus.PASSED,
    )
    session.add(doc)
    await session.flush()

    job = Job(
        id=uuid.uuid4(),
        type=JobType.ASSESS_APPLICATION,
        status=JobStatus.RUNNING,
        target_type="application",
        target_id=app_obj.id,
        input_snapshot_hash="hash_123",
        priority=5,
        lease_epoch=1,
    )
    session.add(job)
    await session.flush()

    return org, req, cand, app_obj, doc, job


def test_rate_card_calculations():
    """Test cost calculations against rate card."""
    cost_est = estimate_request_cost(input_tokens=1_000_000, max_output_tokens=1_000_000, model="deepseek-flash")
    assert cost_est == Decimal("1.50000000")

    cost_actual = calculate_actual_cost(
        input_tokens=2_000_000,
        output_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        model="deepseek-flash",
    )
    assert cost_actual == Decimal("1.50600000")

    with pytest.raises(KeyError):
        estimate_request_cost(100, 100, model="unverified-model")


@pytest.mark.asyncio
async def test_mock_provider_fault_injection():
    """Verify mock provider accurately classifies all fault injection modes."""
    req = CompletionRequest(
        task_kind="assessment",
        system_prompt="Test",
        user_prompt="Test",
    )

    with pytest.raises(LLMAuthenticationError):
        await MockLLMProvider(fault_mode="401").complete(req)

    with pytest.raises(LLMQuotaExhaustedError):
        await MockLLMProvider(fault_mode="402").complete(req)

    with pytest.raises(LLMRateLimitError):
        await MockLLMProvider(fault_mode="429").complete(req)

    with pytest.raises(LLMServerError):
        await MockLLMProvider(fault_mode="500").complete(req)

    with pytest.raises(LLMTimeoutError):
        await MockLLMProvider(fault_mode="timeout").complete(req)

    with pytest.raises(LLMRefusalError):
        await MockLLMProvider(fault_mode="refusal").complete(req)

    with pytest.raises(LLMTruncatedError):
        await MockLLMProvider(fault_mode="truncated").complete(req)

    with pytest.raises(LLMEmptyResponseError):
        await MockLLMProvider(fault_mode="empty").complete(req)

    res = await MockLLMProvider(fault_mode="success").complete(req)
    assert res.content is not None
    assert res.input_tokens is not None
    assert res.output_tokens is not None
    from app.schemas.assessment import AssessmentOutputSchema
    parsed = AssessmentOutputSchema.model_validate_json(res.content)
    assert len(parsed.criteria) == 6
    assert all(criterion.score is None and not criterion.evidence for criterion in parsed.criteria)


@pytest.mark.asyncio
async def test_truncated_provider_response_keeps_budget_reserved(test_session_factory):
    """A provider may bill a truncated 200 response; it must not be booked as free."""
    async with test_session_factory() as session:
        _, _, _, _, _, job = await setup_llm_test_context(session)
        job_id = job.id
        await session.commit()

    request = CompletionRequest(
        task_kind="rubric",
        system_prompt="Return JSON.",
        user_prompt="Synthetic rubric prompt.",
        model="deepseek-flash",
    )
    async with test_session_factory() as session:
        with pytest.raises(LLMTruncatedError):
            await execute_bounded_llm_call(
                db=session,
                job_id=job_id,
                request=request,
                logical_step="rubric_truncated",
                attempt_no=1,
                provider_override=MockLLMProvider(fault_mode="truncated"),
            )

    async with test_session_factory() as session:
        from sqlalchemy import select
        invocation = (await session.execute(select(LLMInvocation).where(LLMInvocation.job_id == job_id))).scalar_one()
        reservation = (await session.execute(select(BudgetReservation).where(BudgetReservation.job_id == job_id))).scalar_one()
        assert invocation.status == LLMInvocationStatus.OUTCOME_UNKNOWN
        assert reservation.status == "outcome_unknown"


@pytest.mark.asyncio
async def test_deepseek_adapter_secret_masking():
    """Invariant: Provider API key MUST NEVER be revealed in error messages or logs."""
    fake_secret_key = "sk-super-secret-production-key-12345"

    provider = DeepSeekHTTPXProvider(api_key=fake_secret_key, api_url="http://invalid-deepseek-host-fail.local")
    req = CompletionRequest(task_kind="rubric", system_prompt="Sys", user_prompt="User", timeout_seconds=0.5)

    with pytest.raises((LLMTimeoutError, LLMServerError)) as exc_info:
        await provider.complete(req)

    error_msg = str(exc_info.value)
    assert fake_secret_key not in error_msg


@pytest.mark.asyncio
async def test_budget_ledger_atomic_reservation_and_outcome_unknown(test_session_factory):
    """Test budget limit enforcement and outcome_unknown non-free invariant."""
    async with test_session_factory() as session:
        _, _, _, _, _, job = await setup_llm_test_context(session)
        job_id = job.id

        period = await get_or_create_active_budget_period(session, scope=BudgetScope.PILOT, for_update=True)
        period.limit_usd = 10.0
        period.reserved_usd = 0.0
        period.spent_usd = 0.0
        await session.commit()

    # 2. Reserve $8.00 -> succeeds
    async with test_session_factory() as session:
        res1 = await reserve_budget(session, job_id=job_id, amount_usd=Decimal("8.00"))
        await session.commit()
        res1_id = res1.id

    # 3. Reserve another $3.00 -> exceeds $10.00 limit -> BudgetExceededError
    async with test_session_factory() as session:
        with pytest.raises(BudgetExceededError):
            await reserve_budget(session, job_id=job_id, amount_usd=Decimal("3.00"))

    # 4. Settle with outcome_unknown -> Invariant: Funds remain held and are NOT treated as free!
    async with test_session_factory() as session:
        settled_res = await settle_budget(session, reservation_id=res1_id, outcome_unknown=True)
        await session.commit()
        assert settled_res.status == "outcome_unknown"

    # Verify period still has funds reserved
    async with test_session_factory() as session:
        period = await get_or_create_active_budget_period(session, scope=BudgetScope.PILOT)
        assert period.reserved_usd == 8.0
        assert period.spent_usd == 0.0


@pytest.mark.asyncio
async def test_first_budget_period_is_shared_by_concurrent_workers(test_session_factory, monkeypatch):
    async with test_session_factory() as session:
        *_, job = await setup_llm_test_context(session)
        job_id = job.id
        await session.execute(update(BudgetPeriod).where(BudgetPeriod.scope == BudgetScope.DEVELOPMENT)
                              .values(period_end=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await session.commit()

    winner_committed = asyncio.Event()

    async def reserve(wait_for_winner=False):
        async with test_session_factory() as session:
            if wait_for_winner:
                execute = session.execute

                async def delayed_lock(statement, *args, **kwargs):
                    if "pg_advisory_xact_lock" in str(statement):
                        await winner_committed.wait()
                    return await execute(statement, *args, **kwargs)

                monkeypatch.setattr(session, "execute", delayed_lock)
            try:
                reservation = await reserve_budget(session, job_id, Decimal("8"), BudgetScope.DEVELOPMENT)
                await session.commit()
                return reservation.id
            except BudgetExceededError:
                await session.rollback()
                return None
            finally:
                if not wait_for_winner:
                    winner_committed.set()
    # The first caller enters earlier but acquires the lock after the second
    # caller creates its period. A timestamp captured before locking is stale.
    results = await asyncio.wait_for(asyncio.gather(reserve(True), reserve()), timeout=10)
    admitted = [result for result in results if result is not None]
    assert len(admitted) == 1
    async with test_session_factory() as session:
        # Repeated settlement must not charge the same completion twice.
        await settle_budget(session, admitted[0], Decimal("1"))
        await settle_budget(session, admitted[0], Decimal("1"))
        period = await get_or_create_active_budget_period(session, BudgetScope.DEVELOPMENT)
        assert period.spent_usd == Decimal("1")
        assert period.reserved_usd == Decimal("0")
        await session.commit()


@pytest.mark.asyncio
async def test_bounded_orchestrator_preconditions(test_session_factory):
    """Test attempt bounding (max 2/stage, max 4/run) and unapproved CV egress block."""
    unapproved_version_id = uuid.uuid4()
    approved_version_id = uuid.uuid4()

    async with test_session_factory() as session:
        _, _, _, app_obj, doc, job = await setup_llm_test_context(session)
        job_id = job.id
        app_id = app_obj.id
        doc_id = doc.id

        # Create unapproved sanitized version (DRAFT)
        v_draft = SanitizedVersion(
            id=unapproved_version_id,
            application_id=app_id,
            document_id=doc_id,
            version_no=1,
            status=SanitizedVersionStatus.DRAFT,
            canonical_text="Draft CV Text",
            sha256="abc" * 21 + "a",
        )
        # Create approved version
        v_appr = SanitizedVersion(
            id=approved_version_id,
            application_id=app_id,
            document_id=doc_id,
            version_no=2,
            status=SanitizedVersionStatus.APPROVED,
            canonical_text="Approved CV Text",
            sha256="def" * 21 + "d",
        )
        session.add_all([v_draft, v_appr])
        await session.commit()

    # 1. Attempting assessment on DRAFT sanitized version -> MUST FAIL
    async with test_session_factory() as session:
        with pytest.raises(PreconditionViolationError) as exc_info:
            await verify_llm_preconditions(
                session,
                job_id=job_id,
                task_kind="assessment",
                sanitized_version_id=unapproved_version_id,
                stage_attempt_no=1,
            )
        assert "CANNOT_EGRESS_UNAPPROVED_CV" in str(exc_info.value)

    # A legacy or manually altered APPROVED version must still be blocked at egress.
    async with test_session_factory() as session:
        version = await session.get(SanitizedVersion, approved_version_id)
        version.canonical_text = "Python developer. Contact: 0912 345 678."
        await session.commit()
    async with test_session_factory() as session:
        with pytest.raises(PreconditionViolationError) as exc_info:
            await verify_llm_preconditions(
                session,
                job_id=job_id,
                task_kind="assessment",
                sanitized_version_id=approved_version_id,
                stage_attempt_no=1,
            )
        assert "RESIDUAL_CONTACT_DATA" in str(exc_info.value)

    # 2. Stage attempt > 2 -> MUST FAIL
    async with test_session_factory() as session:
        with pytest.raises(PreconditionViolationError) as exc_info:
            await verify_llm_preconditions(
                session,
                job_id=job_id,
                task_kind="assessment",
                sanitized_version_id=approved_version_id,
                stage_attempt_no=3,
            )
        assert "MAX_STAGE_ATTEMPTS_EXCEEDED" in str(exc_info.value)

    # 3. Simulate 4 prior invocations -> 5th external call must fail with MAX_RUN_EXTERNAL_CALLS_EXCEEDED
    async with test_session_factory() as session:
        for i in range(4):
            inv = LLMInvocation(
                id=uuid.uuid4(),
                job_id=job_id,
                logical_step="assessment",
                attempt_no=i + 1,
                status=LLMInvocationStatus.FAILED,
                provider="MockLLMProvider",
                model_resolved="deepseek-chat",
                request_hash=f"hash_{i}",
                cost_reserved=0.01,
            )
            session.add(inv)
        await session.commit()

    async with test_session_factory() as session:
        with pytest.raises(PreconditionViolationError) as exc_info:
            await verify_llm_preconditions(
                session,
                job_id=job_id,
                task_kind="assessment",
                sanitized_version_id=approved_version_id,
                stage_attempt_no=1,
            )
        assert "MAX_RUN_EXTERNAL_CALLS_EXCEEDED" in str(exc_info.value)


@pytest.mark.asyncio
async def test_end_to_end_bounded_orchestration_flow(test_session_factory):
    """Test successful bounded LLM call with budget reservation and invocation record creation."""
    v_id = uuid.uuid4()

    async with test_session_factory() as session:
        _, _, _, app_obj, doc, job = await setup_llm_test_context(session)
        job_id = job.id
        app_id = app_obj.id
        doc_id = doc.id

        v_appr = SanitizedVersion(
            id=v_id,
            application_id=app_id,
            document_id=doc_id,
            version_no=1,
            status=SanitizedVersionStatus.APPROVED,
            canonical_text="Approved Python Developer CV",
            sha256="abc" * 21 + "a",
        )
        session.add(v_appr)
        await session.commit()

    req = CompletionRequest(
        task_kind="assessment",
        system_prompt="You are an assessment engine. Respond in JSON.",
        user_prompt="Evaluate candidate evidence.",
        model="deepseek-flash",
        max_output_tokens=500,
    )

    mock_llm = MockLLMProvider(fault_mode="success")

    async with test_session_factory() as session:
        result = await execute_bounded_llm_call(
            db=session,
            job_id=job_id,
            request=req,
            logical_step="assessment_step_1",
            attempt_no=1,
            sanitized_version_id=v_id,
            provider_override=mock_llm,
        )
        assert result.content is not None
        assert mock_llm.invocation_count == 1

    # Verify LLMInvocation record exists in database
    async with test_session_factory() as session:
        from sqlalchemy import select
        stmt = select(LLMInvocation).where(LLMInvocation.job_id == job_id)
        inv = (await session.execute(stmt)).scalar_one()
        assert inv.status == LLMInvocationStatus.SUCCEEDED
        assert inv.input_tokens == 200
        assert inv.output_tokens == 100
        assert inv.cost_actual is not None


@pytest.mark.asyncio
async def test_llm_capability_probe():
    """Test synthetic capability probe."""
    mock_llm = MockLLMProvider(fault_mode="success")
    report = await run_capability_probe(provider=mock_llm)
    assert report["success"] is True
    assert report["probes"]["authentication"] is True
    assert report["probes"]["model_accepted"] is True
    assert report["probes"]["json_mode"] is True
    assert report["probes"]["usage_reporting"] is True


@pytest.mark.asyncio
async def test_budget_status_api(test_session_factory):
    """Test GET /api/v1/budget/status endpoint."""
    user = User(
        id=uuid.uuid4(),
        login_name=f"admin_{uuid.uuid4().hex[:8]}",
        display_name="Admin",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    async with test_session_factory() as session:
        session.add(user)
        await session.flush()
        session.add(UserAccountRole(user_id=user.id, role=AccountRole.ADMIN))
        await session.flush()
        token, csrf, _ = await create_session(session, user)
        await session.commit()

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: token}
    headers = {"X-CSRF-Token": csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.get("/api/v1/budget/status")
        assert res.status_code == 200
        data = res.json()
        assert "limit_usd" in data
        assert "reserved_usd" in data
        assert "spent_usd" in data
        assert data["scope"] == "pilot"
