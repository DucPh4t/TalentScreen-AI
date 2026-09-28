"""Tests for Task B08: Sanitization, HR approval, Raw Access Grants, and Source Viewer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    Application,
    Candidate,
    CandidateIdentity,
    Document,
    Organization,
    RawAccessGrant,
    Requisition,
    RequisitionMembership,
    SanitizedVersion,
    SourceSpan,
    User,
    UserAccountRole,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import (
    AccountRole,
    DocumentSafetyStatus,
    MembershipRole,
    RequisitionStatus,
    SanitizedVersionStatus,
    UserStatus,
)
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session
from app.services.sanitizer import (
    build_source_spans_from_canonical,
    normalize_text_nfc_lf,
    sanitize_text,
)
from app.services.storage import save_private_blob


def test_sanitizer_rules_and_technical_preservation():
    """Test Vietnamese & English PII detectors and tech vs organization invariant."""
    sample_text = """
    Họ và tên: Nguyễn Văn An
    Ngày sinh: 15/08/1995 (28 tuổi)
    Giới tính: Nam. Tình trạng hôn nhân: Độc thân.
    Email: an.nguyen@example.com
    Số điện thoại: 0987654321
    Địa chỉ: 123 Đường Cầu Giấy, Hà Nội
    Học vấn: Tốt nghiệp Đại học Bách Khoa Hà Nội và Stanford University.
    Kinh nghiệm:
    Lập trình viên backend tại Công ty Cổ phần Công nghệ ABC.
    Sử dụng Python, FastAPI, Docker, và cơ sở dữ liệu PostgreSQL để phát triển microservices.
    Triển khai trên AWS và Kubernetes.
    """

    sanitized, redactions, flags = sanitize_text(sample_text, candidate_name="Nguyễn Văn An")

    # 1. PII and demographic attributes redacted
    assert "an.nguyen@example.com" not in sanitized
    assert "[EMAIL]" in sanitized
    assert "0987654321" not in sanitized
    assert "[SỐ_ĐIỆN_THOẠI]" in sanitized
    assert "15/08/1995" not in sanitized
    assert "[NGÀY_SINH/TUỔI]" in sanitized
    assert "Nguyễn Văn An" not in sanitized
    assert "[ỨNG_VIÊN]" in sanitized

    # 2. University / School names redacted (anti-discrimination)
    assert "Đại học Bách Khoa" not in sanitized
    assert "Stanford" not in sanitized
    assert "[TRƯỜNG_ĐẠI_HỌC]" in sanitized

    # 3. Technical keywords MUST BE PRESERVED (Synonym tech vs organization)
    assert "Python" in sanitized
    assert "FastAPI" in sanitized
    assert "Docker" in sanitized
    assert "PostgreSQL" in sanitized
    assert "AWS" in sanitized
    assert "Kubernetes" in sanitized


def test_sanitizer_redacts_header_name_and_international_phone_without_identity_record():
    cv_text = "BOGDAN SZABO\nSenior Software Developer Berlin, DE  bogdan@example.org  +49 176 29983069\nBuilt HTTP APIs with Node.js."
    sanitized, _, flags = sanitize_text(cv_text)
    assert "BOGDAN SZABO" not in sanitized
    assert "+49 176 29983069" not in sanitized
    assert "[ỨNG_VIÊN]" in sanitized
    assert "[SỐ_ĐIỆN_THOẠI]" in sanitized
    assert "Node.js" in sanitized
    assert flags["contains_phone_placeholder"] is True


def test_sanitizer_redacts_mixed_case_header_name_and_repetition():
    cv_text = (
        "Nguyễn Minh Phát | Backend Developer\n"
        "Built Python APIs with FastAPI.\n"
        "Nguyễn Minh Phát owned the authentication module."
    )
    sanitized, redactions, _ = sanitize_text(cv_text)
    assert "Nguyễn Minh Phát" not in sanitized
    assert sanitized.count("[ỨNG_VIÊN]") == 2
    assert "Backend Developer" in sanitized
    assert "FastAPI" in sanitized
    assert sum(r["entity_type"] == "candidate_name_heuristic" for r in redactions) == 2


def test_sanitizer_preserves_role_only_header():
    sanitized, _, _ = sanitize_text("Senior Python Backend Engineer\nBuilt APIs with FastAPI.")
    assert "Senior Python Backend Engineer" in sanitized


def test_sanitizer_redacts_unlabeled_location_and_suffix_school_name():
    cv_text = "Lê Minh An\nHanoi, Vietnam\nBachelor of Science at Northern Technical University\nBuilt Python APIs."
    sanitized, _, _ = sanitize_text(cv_text)
    assert "Hanoi" not in sanitized
    assert "Vietnam" not in sanitized
    assert "Northern Technical University" not in sanitized
    assert "Bachelor of Science" in sanitized
    assert "Python APIs" in sanitized


def test_source_spans_exact_codepoints():
    """Verify source span codepoints exactly match canonical_text[start:end] == span.text."""
    text = normalize_text_nfc_lf(
        "Kinh nghiệm làm việc\n\nPhát triển hệ thống backend với Python và FastAPI.\n\nTối ưu hóa truy vấn PostgreSQL."
    )
    v_id = uuid.uuid4()
    spans = build_source_spans_from_canonical(v_id, text)

    assert len(spans) == 3
    for s in spans:
        extracted = text[s.start_cp : s.end_cp]
        assert extracted == s.text, f"Mismatch at [{s.start_cp}:{s.end_cp}]: '{extracted}' vs '{s.text}'"
        assert len(s.text) <= 1200


def test_source_spans_separate_conflicting_sentences_on_one_line():
    text = "I implemented a Python endpoint. I did not write any backend code."
    spans = build_source_spans_from_canonical(uuid.uuid4(), text)
    assert [span.text for span in spans] == [
        "I implemented a Python endpoint.",
        "I did not write any backend code.",
    ]
    assert all(span.text == text[span.start_cp:span.end_cp] for span in spans)


async def setup_test_context(session):
    """Helper to set up organization, requisition, owner, reviewer, candidate, and document."""
    from app.services.requisition import get_or_create_default_org
    org = await get_or_create_default_org(session)

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
        display_name="Reviewer IT",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    outsider = User(
        id=uuid.uuid4(),
        login_name=f"out_{uuid.uuid4().hex[:8]}",
        display_name="Outsider",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    session.add_all([owner, reviewer, outsider])
    await session.flush()

    session.add(UserAccountRole(user_id=owner.id, role=AccountRole.RECRUITER))
    session.add(UserAccountRole(user_id=reviewer.id, role=AccountRole.REVIEWER))
    session.add(UserAccountRole(user_id=outsider.id, role=AccountRole.REVIEWER))
    await session.flush()

    o_token, o_csrf, _ = await create_session(session, owner)
    r_token, r_csrf, _ = await create_session(session, reviewer)
    out_token, out_csrf, _ = await create_session(session, outsider)

    req = Requisition(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Sanitization Backend Dev",
        status=RequisitionStatus.OPEN,
        row_version=1,
    )
    session.add(req)
    await session.flush()

    session.add(RequisitionMembership(requisition_id=req.id, user_id=owner.id, membership_role=MembershipRole.OWNER))
    session.add(RequisitionMembership(requisition_id=req.id, user_id=reviewer.id, membership_role=MembershipRole.REVIEWER))
    await session.flush()

    cand = Candidate(id=uuid.uuid4(), organization_id=org.id, public_label=f"CAND-{uuid.uuid4().hex[:6].upper()}", status="active")
    session.add(cand)
    await session.flush()

    ident = CandidateIdentity(candidate_id=cand.id, name="Test Candidate")
    session.add(ident)
    await session.flush()

    app_obj = Application(id=uuid.uuid4(), requisition_id=req.id, candidate_id=cand.id, status="active", generation=1, row_version=1)
    session.add(app_obj)
    await session.flush()

    doc_id = uuid.uuid4()
    blob_key = f"documents/{app_obj.id}/{doc_id}.bin"
    raw_content = b"%PDF-1.4 Fake CV Bytes"
    save_private_blob(blob_key, raw_content)

    doc = Document(
        id=doc_id,
        application_id=app_obj.id,
        version_no=1,
        kind="cv",
        original_name_private="NguyenVanA_CV.pdf",
        mime_verified="application/pdf",
        byte_size=len(raw_content),
        sha256=hashlib.sha256(raw_content).hexdigest(),
        blob_key=blob_key,
        ingestion_status="parsed",
        safety_status=DocumentSafetyStatus.PASSED,
        created_by=owner.id,
    )
    session.add(doc)
    await session.flush()

    # Create initial SanitizedVersion (DRAFT)
    canonical = "Kinh nghiệm làm việc\n\nPhát triển API với Python và FastAPI."
    s_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    sanitized = SanitizedVersion(
        id=uuid.uuid4(),
        application_id=app_obj.id,
        document_id=doc.id,
        version_no=1,
        status=SanitizedVersionStatus.DRAFT,
        canonical_text=canonical,
        sha256=s_hash,
    )
    session.add(sanitized)
    await session.flush()

    app_obj.current_document_id = doc.id
    app_obj.current_sanitized_version_id = sanitized.id
    await session.commit()

    return {
        "owner": owner,
        "o_token": o_token,
        "o_csrf": o_csrf,
        "reviewer": reviewer,
        "r_token": r_token,
        "r_csrf": r_csrf,
        "outsider": outsider,
        "out_token": out_token,
        "out_csrf": out_csrf,
        "req_id": req.id,
        "app_id": app_obj.id,
        "doc_id": doc.id,
        "sanitized_id": sanitized.id,
        "sanitized_hash": s_hash,
    }


@pytest.mark.asyncio
async def test_sanitized_version_access_control(test_session_factory):
    """Test access control: Reviewer without raw_cv grant cannot view draft or approve."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session)

    transport = ASGITransport(app=app)

    # 1. Outsider cannot access at all -> 404
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["out_token"]},
        headers={"X-CSRF-Token": ctx["out_csrf"]},
    ) as client:
        res = await client.get(f"/api/v1/sanitized-versions/{ctx['sanitized_id']}")
        assert res.status_code == 404

    # 2. Reviewer without raw grant tries to read DRAFT -> 403 RAW_GRANT_REQUIRED
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["r_token"]},
        headers={"X-CSRF-Token": ctx["r_csrf"]},
    ) as client:
        res = await client.get(f"/api/v1/sanitized-versions/{ctx['sanitized_id']}")
        assert res.status_code == 403
        assert "RAW_GRANT_REQUIRED" in res.json()["detail"]

        # Reviewer cannot list drafts
        list_res = await client.get(f"/api/v1/documents/{ctx['doc_id']}/sanitized-versions")
        assert list_res.status_code == 200
        assert len(list_res.json()) == 0  # No approved version yet, drafts hidden


@pytest.mark.asyncio
async def test_raw_access_grant_issuance_and_review(test_session_factory):
    """Test issuing raw_cv grant and accessing draft with granted permissions."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session)

    transport = ASGITransport(app=app)

    # 1. Reviewer tries to issue grant -> 403 Forbidden (only owner can issue)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["r_token"]},
        headers={"X-CSRF-Token": ctx["r_csrf"]},
    ) as client:
        res_fail = await client.post(
            f"/api/v1/applications/{ctx['app_id']}/raw-grants",
            json={
                "grantee_user_id": str(ctx["reviewer"].id),
                "scopes": ["raw_cv"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "reason": "Self grant attempt",
            },
        )
        assert res_fail.status_code == 403

    # 2. Owner issues raw grant to Reviewer
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["o_token"]},
        headers={"X-CSRF-Token": ctx["o_csrf"]},
    ) as client:
        res_grant = await client.post(
            f"/api/v1/applications/{ctx['app_id']}/raw-grants",
            json={
                "grantee_user_id": str(ctx["reviewer"].id),
                "scopes": ["raw_cv"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "reason": "Phân công rà soát CV thô và đối chiếu sanitized",
            },
        )
        assert res_grant.status_code == 201
        grant_id = res_grant.json()["id"]

    # 3. Now Reviewer can read draft sanitized version
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["r_token"]},
        headers={"X-CSRF-Token": ctx["r_csrf"]},
    ) as client:
        res_draft = await client.get(f"/api/v1/sanitized-versions/{ctx['sanitized_id']}")
        assert res_draft.status_code == 200
        assert res_draft.json()["status"] == "draft"

        # Reviewer can also preview raw document
        res_preview = await client.get(f"/api/v1/documents/{ctx['doc_id']}/raw-preview")
        assert res_preview.status_code == 200
        assert res_preview.content == b"%PDF-1.4 Fake CV Bytes"


@pytest.mark.asyncio
async def test_edit_sanitized_creates_new_version(test_session_factory):
    """Test editing sanitized text creates immutable new version and increments application generation."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session)

    transport = ASGITransport(app=app)

    # Issue raw grant to owner
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["o_token"]},
        headers={"X-CSRF-Token": ctx["o_csrf"]},
    ) as client:
        await client.post(
            f"/api/v1/applications/{ctx['app_id']}/raw-grants",
            json={
                "grantee_user_id": str(ctx["owner"].id),
                "scopes": ["raw_cv"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "reason": "Owner review grant",
            },
        )

        # Edit sanitized version
        new_text = "Kinh nghiệm làm việc\n\nXây dựng hệ thống backend với Python, FastAPI và PostgreSQL."
        edit_res = await client.post(
            f"/api/v1/documents/{ctx['doc_id']}/sanitized-versions",
            json={
                "base_version_id": str(ctx["sanitized_id"]),
                "canonical_text": new_text,
                "edit_reason": "Sửa lỗi chính tả và che thêm thông tin nhạy cảm",
            },
        )
        assert edit_res.status_code == 201
        data = edit_res.json()
        assert data["version_no"] == 2
        assert data["status"] == "draft"
        assert data["canonical_text"] == new_text

    # Verify old version was NOT modified in database
    async with test_session_factory() as session:
        from sqlalchemy import select
        stmt = select(SanitizedVersion).where(SanitizedVersion.id == ctx["sanitized_id"])
        v1 = (await session.execute(stmt)).scalar_one()
        assert v1.version_no == 1
        assert v1.status == SanitizedVersionStatus.DRAFT

        # Check application generation incremented
        stmt_app = select(Application).where(Application.id == ctx["app_id"])
        app_rec = (await session.execute(stmt_app)).scalar_one()
        assert app_rec.generation == 2
        assert app_rec.row_version == 2


@pytest.mark.asyncio
async def test_approve_and_revoke_lifecycle(test_session_factory):
    """Test approval with hash verification, superseding, and revoking approval."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session)

    transport = ASGITransport(app=app)

    # 1. Issue raw grant to owner
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["o_token"]},
        headers={"X-CSRF-Token": ctx["o_csrf"]},
    ) as client:
        await client.post(
            f"/api/v1/applications/{ctx['app_id']}/raw-grants",
            json={
                "grantee_user_id": str(ctx["owner"].id),
                "scopes": ["raw_cv"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "reason": "Owner review grant",
            },
        )

        # 2. Attempt approve with wrong SHA256 -> 409 Conflict
        bad_hash_res = await client.post(
            f"/api/v1/sanitized-versions/{ctx['sanitized_id']}/approve",
            json={
                "expected_application_version": 1,
                "expected_sha256": "0" * 64,
                "acknowledged": True,
            },
        )
        assert bad_hash_res.status_code == 409
        assert "HASH_MISMATCH" in bad_hash_res.json()["detail"]

        # 3. Approve with correct hash & version
        approve_res = await client.post(
            f"/api/v1/sanitized-versions/{ctx['sanitized_id']}/approve",
            json={
                "expected_application_version": 1,
                "expected_sha256": ctx["sanitized_hash"],
                "acknowledged": True,
            },
        )
        assert approve_res.status_code == 200
        assert approve_res.json()["status"] == "approved"
        assert approve_res.json()["approved_by"] == str(ctx["owner"].id)

    # 4. Now Reviewer WITHOUT raw grant CAN view the approved version!
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["r_token"]},
        headers={"X-CSRF-Token": ctx["r_csrf"]},
    ) as client:
        view_approved = await client.get(f"/api/v1/sanitized-versions/{ctx['sanitized_id']}")
        assert view_approved.status_code == 200
        assert view_approved.json()["status"] == "approved"

    # 5. Revoke approval due to discovered leak
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["o_token"]},
        headers={"X-CSRF-Token": ctx["o_csrf"]},
    ) as client:
        revoke_res = await client.post(
            f"/api/v1/sanitized-versions/{ctx['sanitized_id']}/revoke",
            json={
                "expected_application_version": 2,
                "reason": "Phát hiện còn sót thông tin nhận diện cá nhân trong văn bản",
            },
        )
        assert revoke_res.status_code == 200
        assert revoke_res.json()["status"] == "revoked"

    # 6. Once REVOKED, Reviewer WITHOUT raw grant is immediately BLOCKED (Quarantine)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: ctx["r_token"]},
        headers={"X-CSRF-Token": ctx["r_csrf"]},
    ) as client:
        blocked_res = await client.get(f"/api/v1/sanitized-versions/{ctx['sanitized_id']}")
        assert blocked_res.status_code == 403
        assert "RAW_GRANT_REQUIRED" in blocked_res.json()["detail"]
