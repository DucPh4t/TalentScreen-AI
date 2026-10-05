"""Integration and Unit tests for Application Intake, Document Upload, Private Storage, and Idempotency.
Covers Task B05 requirements and security invariants.
"""
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    Application,
    Candidate,
    Document,
    Job,
    RawAccessGrant,
    Requisition,
    RequisitionMembership,
    User,
    UserAccountRole,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import (
    AccountRole,
    MembershipRole,
    RequisitionStatus,
    UserStatus,
)
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session
from app.services.storage import MAX_FILE_SIZE_BYTES, resolve_blob_path, sanitize_filename


VALID_PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
VALID_DOCX_BYTES = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 50


async def setup_test_requisition(
    session,
) -> tuple[User, str, str, User, str, str, uuid.UUID]:
    """Helper to create an owner recruiter, a reviewer, and an active requisition."""
    owner = User(
        id=uuid.uuid4(),
        login_name=f"owner_{uuid.uuid4().hex[:8]}",
        display_name="Owner Recruiter",
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
    session.add(UserAccountRole(user_id=owner.id, role=AccountRole.RECRUITER))
    session.add(UserAccountRole(user_id=reviewer.id, role=AccountRole.REVIEWER))
    await session.flush()

    o_token, o_csrf, _ = await create_session(session, owner)
    r_token, r_csrf, _ = await create_session(session, reviewer)

    from app.services.requisition import get_or_create_default_org
    org = await get_or_create_default_org(session)

    req = Requisition(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Intake Test Req",
        status=RequisitionStatus.DRAFT,
        row_version=1,
    )
    session.add(req)
    await session.flush()

    session.add(RequisitionMembership(requisition_id=req.id, user_id=owner.id, membership_role=MembershipRole.OWNER))
    session.add(RequisitionMembership(requisition_id=req.id, user_id=reviewer.id, membership_role=MembershipRole.REVIEWER))
    await session.commit()

    return owner, o_token, o_csrf, reviewer, r_token, r_csrf, req.id


def test_storage_path_traversal_guards():
    """Security Invariant: Path traversal attempts in filenames and blob keys must be blocked."""
    assert ".." not in sanitize_filename("../../etc/passwd.pdf")
    assert "/" not in sanitize_filename("sub/dir/cv.pdf")
    assert "\\" not in sanitize_filename("..\\..\\windows\\cv.docx")

    with pytest.raises(Exception) as exc_info:
        resolve_blob_path("../../../etc/shadow")
    assert "PATH_TRAVERSAL_DETECTED" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_application_with_pseudonymized_label(test_session_factory):
    """Creating an application generates a pseudonymized public label (e.g. CAND-XXXXXX)."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, _, _, _, req_id = await setup_test_requisition(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: o_token}
    headers = {"X-CSRF-Token": o_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.post(
            f"/api/v1/requisitions/{req_id}/applications",
            json={},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["public_label"].startswith("CAND-")
        assert data["status"] == "active"
        assert data["generation"] == 1
        assert data["row_version"] == 1
        app_id = data["id"]

        second_res = await client.post(f"/api/v1/requisitions/{req_id}/applications", json={})
        assert second_res.status_code == 201
        second_id = second_res.json()["id"]

        # The reviewer sees oldest applications first (FIFO), not newest first.
        list_res = await client.get(f"/api/v1/requisitions/{req_id}/applications")
        assert list_res.status_code == 200
        apps = list_res.json()
        assert [a["id"] for a in apps if a["id"] in {app_id, second_id}] == [app_id, second_id]


@pytest.mark.asyncio
async def test_upload_valid_pdf_and_docx(test_session_factory):
    """Uploading valid PDF and DOCX documents returns 202 Accepted and creates durable Ingest Job."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, _, _, _, req_id = await setup_test_requisition(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: o_token}
    headers = {"X-CSRF-Token": o_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # 1. Create application
        app_res = await client.post(f"/api/v1/requisitions/{req_id}/applications", json={})
        app_id = app_res.json()["id"]

        # 2. Upload PDF
        pdf_res = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("candidate_cv.pdf", VALID_PDF_BYTES, "application/pdf")},
        )
        assert pdf_res.status_code == 202
        pdf_data = pdf_res.json()
        assert pdf_data["document"]["version_no"] == 1
        assert pdf_data["document"]["ingestion_status"] == "uploaded"
        assert pdf_data["document"]["byte_size"] == len(VALID_PDF_BYTES)
        assert pdf_data["application_generation"] == 2
        assert pdf_data["application_row_version"] == 2

        # Verify Job in DB
        async with test_session_factory() as session:
            job = (await session.execute(Job.__table__.select().where(Job.id == uuid.UUID(pdf_data["job_id"])))).fetchone()
            assert job is not None
            assert job.status == "queued"
            assert job.type == "ingest_document"

        # 3. Upload DOCX as version 2
        docx_res = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("candidate_cv_updated.docx", VALID_DOCX_BYTES, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert docx_res.status_code == 202
        docx_data = docx_res.json()
        assert docx_data["document"]["version_no"] == 2
        assert docx_data["application_generation"] == 3


@pytest.mark.asyncio
async def test_upload_invalid_mime_and_fake_extensions(test_session_factory):
    """Rejects fake extension, empty files, and oversized files."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, _, _, _, req_id = await setup_test_requisition(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: o_token}
    headers = {"X-CSRF-Token": o_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        app_res = await client.post(f"/api/v1/requisitions/{req_id}/applications", json={})
        app_id = app_res.json()["id"]

        # 1. Fake PDF (plain text content with .pdf extension)
        fake_pdf = b"This is plain text without PDF magic bytes header."
        res_fake = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("fake_cv.pdf", fake_pdf, "application/pdf")},
        )
        assert res_fake.status_code == 415
        assert "UNSUPPORTED_FILE_TYPE" in res_fake.json()["detail"]

        # 2. Empty file (0 bytes)
        res_empty = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert res_empty.status_code == 422
        assert "EMPTY_FILE" in res_empty.json()["detail"]

        # 3. Oversized file (>10MB)
        oversized = b"%PDF-" + b"0" * (MAX_FILE_SIZE_BYTES + 1024)
        res_over = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("huge.pdf", oversized, "application/pdf")},
        )
        assert res_over.status_code == 413
        assert "FILE_TOO_LARGE" in res_over.json()["detail"]


@pytest.mark.asyncio
async def test_upload_idempotency_key(test_session_factory):
    """Submitting duplicate request with same Idempotency-Key returns cached response without duplicate."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, _, _, _, req_id = await setup_test_requisition(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: o_token}
    headers = {"X-CSRF-Token": o_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        app_res = await client.post(f"/api/v1/requisitions/{req_id}/applications", json={})
        app_id = app_res.json()["id"]

        idempotency_key = f"idem_{uuid.uuid4().hex}"
        upload_headers = {"Idempotency-Key": idempotency_key, "X-CSRF-Token": o_csrf}

        # 1. First upload
        res1 = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("cv.pdf", VALID_PDF_BYTES, "application/pdf")},
            headers=upload_headers,
        )
        assert res1.status_code == 202
        data1 = res1.json()

        # 2. Re-send with identical Idempotency-Key
        res2 = await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("cv.pdf", VALID_PDF_BYTES, "application/pdf")},
            headers=upload_headers,
        )
        assert res2.status_code == 202
        data2 = res2.json()

        # Cached response identical to first
        assert data2["document"]["id"] == data1["document"]["id"]
        assert data2["job_id"] == data1["job_id"]
        assert data2["application_row_version"] == data1["application_row_version"]

        # Verify only 1 document exists in application
        docs_res = await client.get(f"/api/v1/applications/{app_id}/documents")
        assert len(docs_res.json()) == 1


@pytest.mark.asyncio
async def test_privacy_raw_filename_masking(test_session_factory):
    """Security Invariant: original_filename is hidden from reviewers unless RawAccessGrant exists."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, reviewer, r_token, r_csrf, req_id = await setup_test_requisition(session)

    transport = ASGITransport(app=app)

    # 1. Owner creates application and uploads document
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: o_token}, headers={"X-CSRF-Token": o_csrf}
    ) as client:
        app_res = await client.post(f"/api/v1/requisitions/{req_id}/applications", json={})
        app_id = app_res.json()["id"]

        await client.post(
            f"/api/v1/applications/{app_id}/documents",
            files={"file": ("Nguyen_Van_A_Confidential_CV.pdf", VALID_PDF_BYTES, "application/pdf")},
        )

    # 2. Reviewer WITHOUT grant views detail -> original_filename is None
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: r_token}, headers={"X-CSRF-Token": r_csrf}
    ) as client:
        det1 = await client.get(f"/api/v1/applications/{app_id}")
        assert det1.status_code == 200
        assert det1.json()["documents"][0]["original_filename"] is None

    # 3. Grant raw_cv access to Reviewer in DB
    async with test_session_factory() as session:
        grant = RawAccessGrant(
            id=uuid.uuid4(),
            application_id=uuid.UUID(app_id),
            grantee_user_id=reviewer.id,
            scopes=["raw_cv"],
            granted_by=owner.id,
            reason="HR Document Validation",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        session.add(grant)
        await session.commit()

    # 4. Reviewer WITH active grant views detail -> original_filename is revealed
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: r_token}, headers={"X-CSRF-Token": r_csrf}
    ) as client:
        det2 = await client.get(f"/api/v1/applications/{app_id}")
        assert det2.status_code == 200
        assert det2.json()["documents"][0]["original_filename"] == "Nguyen_Van_A_Confidential_CV.pdf"

    # Renewing access before expiry must not crash or hide an existing valid scope.
    async with test_session_factory() as session:
        session.add(RawAccessGrant(
            id=uuid.uuid4(), application_id=uuid.UUID(app_id),
            grantee_user_id=reviewer.id, scopes=["identity"], granted_by=owner.id,
            reason="Overlapping grant regression", expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        await session.commit()
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: r_token}, headers={"X-CSRF-Token": r_csrf}
    ) as client:
        detail = await client.get(f"/api/v1/applications/{app_id}")
        assert detail.status_code == 200
        assert detail.json()["documents"][0]["original_filename"] == "Nguyen_Van_A_Confidential_CV.pdf"
    # Revoked and expired raw grants do not confer access, even when another scope is active.
    async with test_session_factory() as session:
        grant = await session.get(RawAccessGrant, grant.id)
        grant.revoked_at = datetime.now(timezone.utc)
        session.add(RawAccessGrant(
            id=uuid.uuid4(), application_id=uuid.UUID(app_id),
            grantee_user_id=reviewer.id, scopes=["raw_cv"], granted_by=owner.id,
            reason="Expired grant regression", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        ))
        await session.commit()
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: r_token}, headers={"X-CSRF-Token": r_csrf}
    ) as client:
        detail = await client.get(f"/api/v1/applications/{app_id}")
        assert detail.status_code == 200
        assert detail.json()["documents"][0]["original_filename"] is None
