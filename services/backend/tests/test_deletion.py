"""Integration tests for Data Deletion, Retention Policy, Verification Reports, and SEC-10/11 Compliance (Task B17)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import uuid

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Application,
    CriterionAssessment,
    AssessmentRun,
    Candidate,
    CriterionEvidence,
    Decision,
    DeletionRequest,
    Document,
    HRRevision,
    JDVersion,
    Job,
    RawAccessGrant,
    Requisition,
    RequisitionMembership,
    RubricCriterion,
    RubricVersion,
    SanitizedVersion,
    SourceSpan,
    User,
    UserAccountRole,
)
from app.domain.enums import (
    AccountRole,
    CriterionOutcome,
    DeletionScope,
    DeletionStatus,
    DocumentSafetyStatus,
    JobStatus,
    JobType,
    MembershipRole,
    RequisitionStatus,
    RubricStatus,
    SanitizedVersionStatus,
    UserStatus,
)
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session
from app.services.deletion import apply_deletion_ledger, execute_purge_job, retention_sweep
from app.services.llm.provider import MockLLMProvider
from app.services.storage import delete_private_blob, resolve_blob_path, save_private_blob
from sqlalchemy import delete

SESSION_COOKIE_NAME = "talentscreen_session"


@pytest.fixture(autouse=True)
async def cleanup_deletion_tables(test_session_factory):
    async with test_session_factory() as session:
        await session.execute(delete(DeletionRequest))
        await session.commit()


async def setup_deletion_fixture(session: AsyncSession) -> dict:
    """Fixture providing Owner, Reviewer, Requisition, Candidate, Application with Document and Spans."""
    from app.services.requisition import get_or_create_default_org
    org = await get_or_create_default_org(session)
    now = datetime.now(timezone.utc)

    # 1. Users
    owner = User(
        id=uuid.uuid4(),
        login_name=f"owner_{uuid.uuid4().hex[:8]}",
        display_name="Owner User",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    reviewer = User(
        id=uuid.uuid4(),
        login_name=f"rev_{uuid.uuid4().hex[:8]}",
        display_name="Reviewer User",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    session.add_all([owner, reviewer])
    await session.flush()

    session.add(UserAccountRole(user_id=owner.id, role=AccountRole.ADMIN))
    session.add(UserAccountRole(user_id=reviewer.id, role=AccountRole.RECRUITER))
    await session.flush()

    o_token, o_csrf, _ = await create_session(session, owner)
    r_token, r_csrf, _ = await create_session(session, reviewer)

    # 2. Requisition & Memberships
    req = Requisition(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Senior Python Backend Engineer",
        status=RequisitionStatus.OPEN,
        row_version=1,
    )
    session.add(req)
    await session.flush()

    mem_owner = RequisitionMembership(
        requisition_id=req.id,
        user_id=owner.id,
        membership_role=MembershipRole.OWNER,
    )
    mem_rev = RequisitionMembership(
        requisition_id=req.id,
        user_id=reviewer.id,
        membership_role=MembershipRole.REVIEWER,
    )
    session.add_all([mem_owner, mem_rev])
    await session.flush()

    # 3. Candidate & Application
    candidate = Candidate(
        id=uuid.uuid4(),
        organization_id=org.id,
        public_label=f"APP-{uuid.uuid4().hex[:8].upper()}",
        status="active",
    )
    session.add(candidate)
    await session.flush()

    application = Application(
        id=uuid.uuid4(),
        requisition_id=req.id,
        candidate_id=candidate.id,
        status="active",
        generation=1,
        row_version=1,
    )
    session.add(application)
    await session.flush()

    # 4. Document & Physical Blob on disk
    doc_id = uuid.uuid4()
    blob_key = f"documents/{application.id}/{doc_id}.bin"
    file_bytes = b"%PDF-1.4 Mock CV Content for deletion testing."
    save_private_blob(blob_key, file_bytes)

    doc = Document(
        id=doc_id,
        application_id=application.id,
        version_no=1,
        kind="cv",
        original_name_private="NguyenVanA_CV.pdf",
        mime_verified="application/pdf",
        byte_size=len(file_bytes),
        sha256="d" * 64,
        blob_key=blob_key,
        ingestion_status="succeeded",
        safety_status=DocumentSafetyStatus.PASSED,
        created_by=owner.id,
    )
    session.add(doc)
    await session.flush()
    application.current_document_id = doc.id

    # 5. Sanitized Version & Span
    sanitized = SanitizedVersion(
        id=uuid.uuid4(),
        application_id=application.id,
        document_id=doc.id,
        version_no=1,
        status=SanitizedVersionStatus.APPROVED,
        canonical_text="Kinh nghiem lap trinh Python backend.",
        sha256="s" * 64,
        approved_by=owner.id,
        approved_at=now,
    )
    session.add(sanitized)
    await session.flush()
    application.current_sanitized_version_id = sanitized.id

    span = SourceSpan(
        span_id=f"spn_{uuid.uuid4().hex[:12]}",
        full_hash="h" * 64,
        sanitized_version_id=sanitized.id,
        start_cp=0,
        end_cp=35,
        page_number=1,
        language="vi",
        text="Kinh nghiem lap trinh Python backend.",
    )
    session.add(span)
    await session.flush()

    # 6. JD & Rubric Version & Criteria
    jd = JDVersion(
        id=uuid.uuid4(),
        requisition_id=req.id,
        version_no=1,
        source_text="Senior Python Backend Engineer JD",
        text_hash="a" * 64,
        created_by=owner.id,
    )
    session.add(jd)
    await session.flush()
    req.current_jd_version_id = jd.id

    rubric = RubricVersion(
        id=uuid.uuid4(),
        requisition_id=req.id,
        jd_version_id=jd.id,
        version_no=1,
        status=RubricStatus.APPROVED,
        content_hash="b" * 64,
        approved_by=owner.id,
        approved_at=now,
    )
    session.add(rubric)
    await session.flush()

    crit = RubricCriterion(
        rubric_version_id=rubric.id,
        criterion_id="python_backend",
        label_vi="Python Backend",
        description_vi="Thành thạo Python",
        weight=100,
        anchors={"0": "None", "1": "Basic", "2": "Good", "3": "Solid", "4": "Expert"},
    )
    session.add(crit)
    await session.flush()
    req.current_rubric_version_id = rubric.id

    # 7. Assessment Run & Evidence
    run_job = Job(
        id=uuid.uuid4(),
        type=JobType.ASSESS_APPLICATION,
        target_type="application",
        status=JobStatus.SUCCEEDED,
        target_id=application.id,
        input_snapshot_hash="h" * 64,
        payload_ref={},
    )
    session.add(run_job)
    await session.flush()

    run = AssessmentRun(
        id=uuid.uuid4(),
        application_id=application.id,
        job_id=run_job.id,
        rubric_version_id=rubric.id,
        document_id=doc.id,
        sanitized_version_id=sanitized.id,
        run_no=1,
        status="succeeded",
        snapshot={},
        snapshot_hash="f" * 64,
        application_generation=1,
        observed_score=80.0,
        coverage=1.0,
        comparable_score=80.0,
        recommendation="consider_next_round",
    )
    session.add(run)
    await session.flush()

    c_ass = CriterionAssessment(
        run_id=run.id,
        criterion_id="python_backend",
        status=CriterionOutcome.ASSESSED,
        score=3,
        rationale="Solid experience",
    )
    c_ev = CriterionEvidence(
        run_id=run.id,
        criterion_id="python_backend",
        span_id=span.span_id,
        quote="Kinh nghiem lap trinh Python backend.",
        resolved_start_cp=0,
        resolved_end_cp=35,
    )
    session.add_all([c_ass, c_ev])

    # 8. Raw access grant
    grant = RawAccessGrant(
        application_id=application.id,
        grantee_user_id=reviewer.id,
        granted_by=owner.id,
        scopes=["raw_cv"],
        reason="Manual CV verification",
        expires_at=now + timedelta(hours=2),
    )
    session.add(grant)

    application.current_assessment_run_id = run.id
    await session.commit()

    return {
        "owner_id": owner.id,
        "reviewer_id": reviewer.id,
        "o_token": o_token,
        "o_csrf": o_csrf,
        "r_token": r_token,
        "r_csrf": r_csrf,
        "req_id": req.id,
        "cand_id": candidate.id,
        "app_id": application.id,
        "doc_id": doc.id,
        "blob_key": blob_key,
        "run_id": run.id,
        "rubric_id": rubric.id,
    }


@pytest.mark.asyncio
async def test_deletion_rbac_and_immediate_tombstone(test_session_factory):
    """Test RBAC restrictions (Reviewer 403, Owner 201), immediate tombstone, and access cutoff."""
    async with test_session_factory() as session:
        ctx = await setup_deletion_fixture(session)

    transport = ASGITransport(app=app)

    # 1. Reviewer tries to request deletion -> 403 Forbidden
    r_cookies = {SESSION_COOKIE_NAME: ctx["r_token"]}
    r_headers = {"X-CSRF-Token": ctx["r_csrf"]}
    async with AsyncClient(transport=transport, base_url="http://test", cookies=r_cookies, headers=r_headers) as client:
        res_denied = await client.post(
            "/api/v1/deletion-requests",
            json={
                "scope": "application",
                "target_id": str(ctx["app_id"]),
                "reason_category": "candidate_request",
            },
        )
        assert res_denied.status_code == 403

    # 2. Owner requests deletion -> 201 Created
    o_cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    o_headers = {"X-CSRF-Token": ctx["o_csrf"]}
    async with AsyncClient(transport=transport, base_url="http://test", cookies=o_cookies, headers=o_headers) as client:
        res_create = await client.post(
            "/api/v1/deletion-requests",
            json={
                "scope": "application",
                "target_id": str(ctx["app_id"]),
                "reason_category": "candidate_request",
            },
        )
        assert res_create.status_code == 201
        del_data = res_create.json()
        del_id = del_data["id"]
        assert del_data["status"] == "requested"
        assert del_data["local_purge_complete"] is False

        # Idempotent retry: Returns existing active request
        res_retry = await client.post(
            "/api/v1/deletion-requests",
            json={
                "scope": "application",
                "target_id": str(ctx["app_id"]),
                "reason_category": "candidate_request",
            },
        )
        assert res_retry.status_code in (200, 201)
        assert res_retry.json()["id"] == del_id

        # Immediate Access Cutoff: All read endpoints return 404
        res_app = await client.get(f"/api/v1/applications/{ctx['app_id']}")
        assert res_app.status_code == 404

        # Listing does not leak tombstoned application
        res_list = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/applications")
        assert res_list.status_code == 200
        app_ids_in_list = [a["id"] for a in res_list.json()]
        assert str(ctx["app_id"]) not in app_ids_in_list

        # Source spans endpoint returns 404
        res_spans = await client.get(f"/api/v1/applications/{ctx['app_id']}/sanitized-versions")
        assert res_spans.status_code == 404

    # 3. Check DB state: status == 'deleted', generation bumped, grant revoked
    async with test_session_factory() as session:
        stmt_app = select(Application).where(Application.id == ctx["app_id"])
        app_db = (await session.execute(stmt_app)).scalar_one()
        assert app_db.status == "deleted"
        assert app_db.generation == 2
        assert app_db.current_document_id is None

        stmt_grant = select(RawAccessGrant).where(RawAccessGrant.application_id == ctx["app_id"])
        grant_db = (await session.execute(stmt_grant)).scalar_one()
        assert grant_db.revoked_at is not None


@pytest.mark.asyncio
async def test_purge_worker_execution_and_clean_verification_report(test_session_factory):
    """Test purge worker deletes physical blob, cleans database child records, and writes verification report."""
    async with test_session_factory() as session:
        ctx = await setup_deletion_fixture(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    headers = {"X-CSRF-Token": ctx["o_csrf"]}

    del_id = None
    job_id = None

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.post(
            "/api/v1/deletion-requests",
            json={
                "scope": "application",
                "target_id": str(ctx["app_id"]),
                "reason_category": "gdpr_erasure",
            },
        )
        assert res.status_code == 201
        del_id = res.json()["id"]
        job_id = res.json()["job_id"]

    # Verify physical file exists before worker runs
    blob_path = resolve_blob_path(ctx["blob_key"])
    assert blob_path.exists() is True

    # Execute purge worker
    async with test_session_factory() as session:
        await execute_purge_job(session, job_id=uuid.UUID(job_id))
        await session.commit()

    # Verify physical file is unlinked from storage
    assert blob_path.exists() is False

    # Check DeletionRequest state and verification report
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res_del = await client.get(f"/api/v1/deletion-requests/{del_id}")
        assert res_del.status_code == 200
        del_data = res_del.json()
        assert del_data["local_purge_complete"] is True
        assert del_data["status"] == "awaiting_external"
        assert del_data["backup_status"] == "pending_expiry"
        assert del_data["verification_report"]["clean"] is True
        assert del_data["verification_report"]["files_unlinked"] >= 1
        assert del_data["verification_report"]["documents_purged"] >= 1

    # Verify child DB records are completely wiped
    async with test_session_factory() as session:
        # Documents wiped
        stmt_docs = select(Document).where(Document.application_id == ctx["app_id"])
        assert len((await session.execute(stmt_docs)).scalars().all()) == 0

        # Assessment runs and criteria wiped
        stmt_runs = select(AssessmentRun).where(AssessmentRun.application_id == ctx["app_id"])
        assert len((await session.execute(stmt_runs)).scalars().all()) == 0


@pytest.mark.asyncio
async def test_sec_10_late_arrival_discarded_after_tombstone(test_session_factory):
    """SEC-10: Late LLM response arrival after application is deleted/tombstoned is discarded."""
    async with test_session_factory() as session:
        ctx = await setup_deletion_fixture(session)

        # Create an assessment run in running state
        run_job = Job(
            id=uuid.uuid4(),
            type=JobType.ASSESS_APPLICATION,
            target_type="application",
            status=JobStatus.RUNNING,
            target_id=ctx["app_id"],
            input_snapshot_hash="h" * 64,
            payload_ref={},
        )
        session.add(run_job)
        await session.flush()

        stmt_app = select(Application).where(Application.id == ctx["app_id"])
        app_obj = (await session.execute(stmt_app)).scalar_one()

        run = AssessmentRun(
            id=uuid.uuid4(),
            application_id=ctx["app_id"],
            job_id=run_job.id,
            rubric_version_id=ctx["rubric_id"],
            document_id=ctx["doc_id"],
            sanitized_version_id=app_obj.current_sanitized_version_id,
            run_no=2,
            status="running",
            snapshot={},
            snapshot_hash="f" * 64,
            application_generation=1,
        )
        session.add(run)

        # Deletion occurs before LLM response is committed
        app_obj.status = "deleted"
        app_obj.generation = 99  # incremented
        await session.commit()

        job_id = run_job.id
        run_id = run.id

    from app.services.assessment.service import execute_assessment_job
    from app.services.llm.provider import MockLLMProvider

    mock_llm = MockLLMProvider()

    async with test_session_factory() as session:
        # Worker attempts to execute assessment job
        await execute_assessment_job(session, job_id=job_id, provider_override=mock_llm)
        await session.commit()

    # Verify run failed with APPLICATION_TOMBSTONED, no criteria persisted
    async with test_session_factory() as session:
        stmt_run = select(AssessmentRun).where(AssessmentRun.id == run_id)
        run_db = (await session.execute(stmt_run)).scalar_one()
        assert run_db.status == "failed"
        assert run_db.failure_code == "APPLICATION_TOMBSTONED"

        # Zero criteria created
        stmt_crit = select(CriterionAssessment).where(CriterionAssessment.run_id == run_id)
        assert len((await session.execute(stmt_crit)).scalars().all()) == 0


@pytest.mark.asyncio
async def test_sec_11_apply_deletion_ledger_after_backup_restore(test_session_factory):
    """SEC-11: Re-applying deletion ledger re-tombstones any candidate/application restored from backup."""
    async with test_session_factory() as session:
        ctx = await setup_deletion_fixture(session)

        # Record a completed deletion request in the ledger
        del_req = DeletionRequest(
            id=uuid.uuid4(),
            scope=DeletionScope.APPLICATION,
            target_id=ctx["app_id"],
            status=DeletionStatus.COMPLETED,
            local_purge_complete=True,
            backup_status="pending_expiry",
            external_retention_status="not_applicable",
            reason_category="gdpr_erasure",
            requested_by=ctx["owner_id"],
            requested_at=datetime.now(timezone.utc),
        )
        session.add(del_req)

        # Simulate restored database state where application has status="active"
        stmt_app = select(Application).where(Application.id == ctx["app_id"])
        app_db = (await session.execute(stmt_app)).scalar_one()
        app_db.status = "active"
        app_db.generation = 1
        await session.commit()

    # Apply deletion ledger
    async with test_session_factory() as session:
        report = await apply_deletion_ledger(session)
        assert report["re_purged_applications_count"] == 1
        await session.commit()

    # Check application was re-tombstoned immediately
    async with test_session_factory() as session:
        stmt_app = select(Application).where(Application.id == ctx["app_id"])
        app_db = (await session.execute(stmt_app)).scalar_one()
        assert app_db.status == "deleted"
        assert app_db.generation == 2


@pytest.mark.asyncio
async def test_retention_policy_and_sweep(test_session_factory):
    """Test retention policy endpoint and sweep of expired temp files and backup expiry."""
    async with test_session_factory() as session:
        ctx = await setup_deletion_fixture(session)

        # Create expired backup record
        del_req = DeletionRequest(
            id=uuid.uuid4(),
            scope=DeletionScope.APPLICATION,
            target_id=ctx["app_id"],
            status=DeletionStatus.AWAITING_EXTERNAL,
            local_purge_complete=True,
            backup_status="pending_expiry",
            backup_expiry_at=datetime.now(timezone.utc) - timedelta(days=1),  # expired!
            external_retention_status="not_applicable",
            reason_category="retention_sweep",
            requested_by=ctx["owner_id"],
            requested_at=datetime.now(timezone.utc) - timedelta(days=8),
        )
        session.add(del_req)
        await session.commit()
        del_id = del_req.id

    # Create an expired temporary file in storage
    temp_dir = resolve_blob_path("tmp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"test_expired_{uuid.uuid4().hex[:8]}.tmp"
    temp_file.write_bytes(b"temporary scratch data")
    # Set mtime to 48 hours ago
    past_time = (datetime.now(timezone.utc) - timedelta(hours=48)).timestamp()
    os.utime(temp_file, (past_time, past_time))
    assert temp_file.exists() is True

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    headers = {"X-CSRF-Token": ctx["o_csrf"]}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # 1. Check retention policy endpoint
        res_policy = await client.get("/api/v1/retention-policy")
        assert res_policy.status_code == 200
        policy_data = res_policy.json()
        assert policy_data["sandbox_ttl_days"] == 30
        assert policy_data["backup_retention_days"] == 7
        assert policy_data["temp_file_ttl_hours"] == 24

        # 2. Run retention sweep endpoint
        res_sweep = await client.post("/api/v1/retention-sweep")
        assert res_sweep.status_code == 200
        sweep_data = res_sweep.json()
        assert sweep_data["swept_temp_files_count"] >= 1
        assert sweep_data["swept_expired_backups_count"] >= 1

    # Verify temp file unlinked
    assert temp_file.exists() is False

    # Verify DeletionRequest is now COMPLETED
    async with test_session_factory() as session:
        stmt_del = select(DeletionRequest).where(DeletionRequest.id == del_id)
        del_db = (await session.execute(stmt_del)).scalar_one()
        assert del_db.backup_status == "expired"
        assert del_db.status == DeletionStatus.COMPLETED
