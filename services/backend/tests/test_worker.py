"""Tests for Task B07: Durable PostgreSQL worker, lease fencing, heartbeats, cancellation, and retry schedules."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import io
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from pypdf import PageObject, PdfWriter
from sqlalchemy import delete, select

from app.db.models import Job, User, UserAccountRole
from app.db.models.document import Document
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import AccountRole, DocumentSafetyStatus, JobStatus, JobType, UserStatus
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session
from app.services.worker import (
    FencingViolationError,
    cancel_job,
    claim_next_job,
    complete_job_fenced,
    heartbeat_job,
    run_worker_once,
    sweep_stale_jobs,
)


@pytest.fixture(autouse=True)
async def cleanup_jobs(test_session_factory):
    """Ensure a clean queue for each worker test."""
    async with test_session_factory() as session:
        await session.execute(delete(Job))
        await session.commit()
    yield
    async with test_session_factory() as session:
        await session.execute(delete(Job))
        await session.commit()


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    writer = PdfWriter()
    page = PageObject.create_blank_page(width=300, height=300)
    writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


async def setup_admin_user(session) -> tuple[User, str, str]:
    """Helper to create an active admin user and session."""
    user = User(
        id=uuid.uuid4(),
        login_name=f"admin_{uuid.uuid4().hex[:8]}",
        display_name="Admin Test User",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    session.add(UserAccountRole(user_id=user.id, role=AccountRole.ADMIN))
    session.add(UserAccountRole(user_id=user.id, role=AccountRole.RECRUITER))
    await session.flush()

    token, csrf, _ = await create_session(session, user)
    await session.commit()
    return user, token, csrf



@pytest.mark.asyncio
async def test_worker_claim_next_job_and_fencing(test_session_factory):
    """Test atomic claiming, lease epoch increment (fencing token), and heartbeats."""
    target_id = uuid.uuid4()
    job_id = None

    async with test_session_factory() as session:
        job = Job(
            type=JobType.INGEST_DOCUMENT,
            status=JobStatus.QUEUED,
            target_type="document",
            target_id=target_id,
            input_snapshot_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            priority=10,
            available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            lease_epoch=0,
            claim_count=0,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # Worker A claims job
    async with test_session_factory() as session:
        claimed = await claim_next_job(session, worker_id="worker_A", lease_duration_seconds=30)
        assert claimed is not None
        claimed_id, epoch_a, jtype, t_id, _ = claimed
        assert claimed_id == job_id
        assert epoch_a == 1
        assert t_id == target_id
        await session.commit()

    # Heartbeat from Worker A succeeds
    async with test_session_factory() as session:
        hb_ok = await heartbeat_job(session, job_id, worker_id="worker_A", epoch=epoch_a)
        assert hb_ok is True
        await session.commit()

    # Second worker claiming while lease is active should get None (no available jobs)
    async with test_session_factory() as session:
        claimed_b = await claim_next_job(session, worker_id="worker_B", lease_duration_seconds=30)
        assert claimed_b is None

    # Simulate Worker A dying and lease expiring
    async with test_session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        j = (await session.execute(stmt)).scalar_one()
        j.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    # Worker B claims expired job -> epoch advances to 2
    epoch_b = None
    async with test_session_factory() as session:
        claimed_b2 = await claim_next_job(session, worker_id="worker_B", lease_duration_seconds=30)
        assert claimed_b2 is not None
        _, epoch_b, _, _, _ = claimed_b2
        assert epoch_b == 2
        await session.commit()

    # Worker A (superseded) tries to complete with stale epoch 1 -> MUST FAIL with FencingViolationError
    async with test_session_factory() as session:
        with pytest.raises(FencingViolationError):
            await complete_job_fenced(
                session,
                job_id=job_id,
                worker_id="worker_A",
                epoch=epoch_a,
                success=True,
            )

    # Worker B completes with valid epoch 2 -> succeeds
    async with test_session_factory() as session:
        final_status = await complete_job_fenced(
            session,
            job_id=job_id,
            worker_id="worker_B",
            epoch=epoch_b,
            success=True,
        )
        assert final_status == JobStatus.SUCCEEDED
        await session.commit()


@pytest.mark.asyncio
async def test_worker_retry_schedule_and_max_claims(test_session_factory):
    """Test retry schedule backoff and poison pill limit (max claims = 3)."""
    target_id = uuid.uuid4()
    job_id = None

    async with test_session_factory() as session:
        job = Job(
            type=JobType.INGEST_DOCUMENT,
            status=JobStatus.QUEUED,
            target_type="document",
            target_id=target_id,
            input_snapshot_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            priority=5,
            available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            lease_epoch=0,
            claim_count=0,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # Claim 1 & fail -> transitions to RETRY_WAIT
    async with test_session_factory() as session:
        claim1 = await claim_next_job(session, "worker_1")
        assert claim1 is not None
        j_id, ep1, _, _, _ = claim1
        st1 = await complete_job_fenced(session, j_id, "worker_1", ep1, success=False, error_code="TEMPORARY_ERROR")
        assert st1 == JobStatus.RETRY_WAIT
        await session.commit()

    # Fast forward available_at
    async with test_session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        j = (await session.execute(stmt)).scalar_one()
        j.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    # Claim 2 & fail -> RETRY_WAIT
    async with test_session_factory() as session:
        claim2 = await claim_next_job(session, "worker_2")
        assert claim2 is not None
        _, ep2, _, _, _ = claim2
        st2 = await complete_job_fenced(session, job_id, "worker_2", ep2, success=False, error_code="TEMPORARY_ERROR_2")
        assert st2 == JobStatus.RETRY_WAIT
        await session.commit()

    # Fast forward available_at again
    async with test_session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        j = (await session.execute(stmt)).scalar_one()
        j.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()

    # Claim 3 & fail -> FAILED (max claims reached)
    async with test_session_factory() as session:
        claim3 = await claim_next_job(session, "worker_3")
        assert claim3 is not None
        _, ep3, _, _, _ = claim3
        st3 = await complete_job_fenced(session, job_id, "worker_3", ep3, success=False, error_code="PERSISTENT_ERROR")
        assert st3 == JobStatus.FAILED
        await session.commit()

    # Further claims should yield None
    async with test_session_factory() as session:
        no_claim = await claim_next_job(session, "worker_4")
        assert no_claim is None


@pytest.mark.asyncio
async def test_worker_cancellation(test_session_factory):
    """Test cooperative job cancellation."""
    job_id = None
    async with test_session_factory() as session:
        job = Job(
            type=JobType.INGEST_DOCUMENT,
            status=JobStatus.QUEUED,
            target_type="document",
            target_id=uuid.uuid4(),
            input_snapshot_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            priority=1,
            available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            lease_epoch=0,
            claim_count=0,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    # Cancel while in QUEUED -> immediate CANCELLED
    async with test_session_factory() as session:
        status_res, _ = await cancel_job(session, job_id, reason="User cancelled before processing")
        assert status_res == JobStatus.CANCELLED
        await session.commit()

    # Now create another job and claim it first
    job2_id = None
    async with test_session_factory() as session:
        job2 = Job(
            type=JobType.INGEST_DOCUMENT,
            status=JobStatus.QUEUED,
            target_type="document",
            target_id=uuid.uuid4(),
            input_snapshot_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            priority=1,
            available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            lease_epoch=0,
            claim_count=0,
        )
        session.add(job2)
        await session.commit()
        job2_id = job2.id

    ep = None
    async with test_session_factory() as session:
        claim = await claim_next_job(session, "worker_cancel_test")
        assert claim is not None
        _, ep, _, _, _ = claim
        await session.commit()

    # Request cancel while RUNNING -> marks cancel_requested_at
    async with test_session_factory() as session:
        status_res2, _ = await cancel_job(session, job2_id, reason="Cancel in-flight job")
        assert status_res2 == JobStatus.RUNNING
        await session.commit()

    # When worker attempts to complete, it detects cancel request and final status becomes CANCELLED
    async with test_session_factory() as session:
        final_st = await complete_job_fenced(session, job2_id, "worker_cancel_test", ep, success=True)
        assert final_st == JobStatus.CANCELLED
        await session.commit()


@pytest.mark.asyncio
async def test_sweep_stale_jobs(test_session_factory):
    """Test sweeping abandoned running jobs where lease expired and max claims was reached."""
    now = datetime.now(timezone.utc)
    job_id = None
    async with test_session_factory() as session:
        job_stale = Job(
            type=JobType.INGEST_DOCUMENT,
            status=JobStatus.RUNNING,
            target_type="document",
            target_id=uuid.uuid4(),
            input_snapshot_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            priority=1,
            available_at=now,
            lease_owner="dead_worker",
            lease_expires_at=now - timedelta(seconds=60),
            claim_count=3,
            lease_epoch=3,
        )
        session.add(job_stale)
        await session.commit()
        job_id = job_stale.id

    async with test_session_factory() as session:
        swept = await sweep_stale_jobs(session)
        assert swept >= 1
        await session.commit()

    async with test_session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        j = (await session.execute(stmt)).scalar_one()
        assert j.status == JobStatus.FAILED
        assert j.last_error_code == "STALE_LEASE_ABANDONED"


@pytest.mark.asyncio
async def test_jobs_api_flow(test_session_factory):
    """Test GET /api/v1/jobs/{id} and POST /api/v1/jobs/{id}/cancel via HTTP."""
    job_id = None
    async with test_session_factory() as session:
        _, token, csrf = await setup_admin_user(session)
        job = Job(
            type=JobType.INGEST_DOCUMENT,
            status=JobStatus.QUEUED,
            target_type="document",
            target_id=uuid.uuid4(),
            input_snapshot_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            priority=5,
            available_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            lease_epoch=0,
            claim_count=0,
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    from tests.test_admin_observability import create_reviewer_user
    async with test_session_factory() as session:
        _, outsider_token, outsider_csrf = await create_reviewer_user(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                           cookies={SESSION_COOKIE_NAME: outsider_token},
                           headers={"X-CSRF-Token": outsider_csrf}) as outsider:
        assert (await outsider.get(f"/api/v1/jobs/{job_id}")).status_code == 404
        assert (await outsider.post(f"/api/v1/jobs/{job_id}/cancel", json={"reason": "Out of scope attempt"})).status_code == 404
        assert (await outsider.post("/api/v1/jobs/sweep")).status_code == 403

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: token}
    headers = {"X-CSRF-Token": csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # GET job
        resp = await client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(job_id)
        assert data["status"] == "queued"

        # POST cancel job
        resp_cancel = await client.post(
            f"/api/v1/jobs/{job_id}/cancel",
            json={"reason": "Testing cancellation API"},
        )
        assert resp_cancel.status_code == 200
        cancel_data = resp_cancel.json()
        assert cancel_data["status"] == "cancelled"

    async with test_session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        j = (await session.execute(stmt)).scalar_one()
        assert j.status == JobStatus.CANCELLED


@pytest.mark.asyncio
async def test_end_to_end_worker_document_ingestion(test_session_factory, sample_pdf_bytes: bytes):
    """E2E: Upload candidate document -> Job is QUEUED -> run_worker_once() processes it -> SUCCEEDED & Document PARSED."""
    async with test_session_factory() as session:
        _, token, csrf = await setup_admin_user(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: token}
    headers = {"X-CSRF-Token": csrf}

    job_id = None
    doc_id = None

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # 1. Create requisition & application
        req_resp = await client.post(
            "/api/v1/requisitions",
            json={"title": "E2E Worker Job Title", "department": "Engineering"},
        )
        assert req_resp.status_code == 201
        req_id = req_resp.json()["id"]

        app_resp = await client.post(
            f"/api/v1/requisitions/{req_id}/applications",
            json={"raw_full_name": "Worker Test Candidate", "raw_email": "worker.test@example.com"},
        )
        assert app_resp.status_code == 201
        app_id = app_resp.json()["id"]

        # 2. Upload document
        files = {"file": ("worker_cv.pdf", sample_pdf_bytes, "application/pdf")}
        upload_resp = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files=files,
        )
        assert upload_resp.status_code == 202
        job_id = uuid.UUID(upload_resp.json()["job_id"])
        doc_id = uuid.UUID(upload_resp.json()["document"]["id"])

    # Verify initial states
    async with test_session_factory() as session:
        stmt_j = select(Job).where(Job.id == job_id)
        job_record = (await session.execute(stmt_j)).scalar_one()
        assert job_record.status == JobStatus.QUEUED

        stmt_d = select(Document).where(Document.id == doc_id)
        doc_record = (await session.execute(stmt_d)).scalar_one()
        assert doc_record.ingestion_status == "uploaded"

    # 3. Worker executes job
    async with test_session_factory() as session:
        processed = await run_worker_once(session, worker_id="e2e_worker_1")
        assert processed is True

    # 4. Verify post-execution states
    async with test_session_factory() as session:
        stmt_j = select(Job).where(Job.id == job_id)
        job_record = (await session.execute(stmt_j)).scalar_one()
        assert job_record.status == JobStatus.SUCCEEDED

        stmt_d = select(Document).where(Document.id == doc_id)
        doc_record = (await session.execute(stmt_d)).scalar_one()
        assert doc_record.ingestion_status == "parsed"
        assert doc_record.safety_status == DocumentSafetyStatus.PASSED
        assert doc_record.page_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("job_type,expected_status", [
    (JobType.INGEST_DOCUMENT, JobStatus.RETRY_WAIT),
    (JobType.ASSESS_APPLICATION, JobStatus.FAILED),
])
async def test_worker_recovers_failed_database_transaction(test_session_factory, monkeypatch, job_type, expected_status):
    """A real failed flush must not crash the worker while it records the outcome."""
    async with test_session_factory() as session:
        job = Job(type=job_type, status=JobStatus.QUEUED, target_type="application",
                  target_id=uuid.uuid4(), input_snapshot_hash=uuid.uuid4().hex,
                  available_at=datetime.now(timezone.utc), priority=10)
        session.add(job)
        await session.commit()
        job_id = job.id

    async def fail_during_flush(db, claimed_id, *args):
        # Missing NOT NULL fields produces IntegrityError and poisons the transaction.
        db.add(Job(id=uuid.uuid4()))
        await db.flush()

    monkeypatch.setattr("app.services.worker.execute_job_handler", fail_during_flush)
    async with test_session_factory() as session:
        assert await run_worker_once(session, worker_id="failed_transaction_test") is True
    async with test_session_factory() as session:
        result = await session.get(Job, job_id)
        assert result.status == expected_status
        assert result.last_error_code == "IntegrityError"
        assert result.claim_count == 1
