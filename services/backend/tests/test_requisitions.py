"""Integration and Unit tests for Requisition, Membership, and JD Version lifecycle.
Covers Task B03 requirements and state machines.
"""
from datetime import datetime, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    AuditEvent,
    JDVersion,
    Organization,
    Requisition,
    RequisitionMembership,
    RubricCriterion,
    RubricVersion,
    User,
    UserAccountRole,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import (
    AccountRole,
    EnvironmentMode,
    MembershipRole,
    RequisitionStatus,
    RubricStatus,
    UserStatus,
)
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session

SAMPLE_JD_TEXT = """# Tuyển dụng Kỹ sư Backend Python
## Sáu yêu cầu năng lực được phép đánh giá
| Requirement ID | Criterion ID / trọng số | Nội dung yêu cầu chuẩn để trích dẫn |
|---|---|---|
| `JD-PY-01` | `python_backend` /20 | Triển khai chức năng backend bằng Python từ một yêu cầu nghiệp vụ rõ ràng. |
| `JD-API-01` | `api_design` /25 | Thiết kế và triển khai HTTP API có hợp đồng đầu vào, đầu ra phù hợp. |
| `JD-SQL-01` | `sql_data` /20 | Làm việc với cơ sở dữ liệu quan hệ PostgreSQL để lưu và truy vấn dữ liệu. |
| `JD-TEST-01` | `testing_debugging` /15 | Kiểm thử hành vi backend và tái hiện lỗi từ tình huống cụ thể. |
| `JD-SEC-01` | `security_privacy` /10 | Áp dụng xác thực và phân quyền, bảo vệ dữ liệu cá nhân. |
| `JD-OPS-01` | `delivery_ops` /10 | Đưa thay đổi backend qua quy trình Git và Docker kiểm soát. |
"""


async def create_test_user_and_session(
    session,
    roles: list[AccountRole],
    login_prefix: str = "user",
) -> tuple[User, str, str]:
    """Helper to create an active user with roles and an active session."""
    user = User(
        id=uuid.uuid4(),
        login_name=f"{login_prefix}_{uuid.uuid4().hex[:8]}",
        display_name=f"Test {login_prefix.title()}",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    for role in roles:
        session.add(UserAccountRole(user_id=user.id, role=role))
    await session.flush()

    token, csrf, _ = await create_session(session, user)
    await session.commit()
    return user, token, csrf


@pytest.mark.asyncio
async def test_create_requisition_recruiter_becomes_owner(test_session_factory):
    """Recruiter creates requisition -> status DRAFT, assigned as OWNER."""
    async with test_session_factory() as session:
        user, token, csrf = await create_test_user_and_session(session, [AccountRole.RECRUITER], "recruiter")

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: token}
    headers = {"X-CSRF-Token": csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.post(
            "/api/v1/requisitions",
            json={"title": "Chuyên viên phát triển phần mềm Backend Python"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["title"] == "Chuyên viên phát triển phần mềm Backend Python"
        assert data["status"] == "draft"
        assert data["row_version"] == 1
        req_id = uuid.UUID(data["id"])

        # Check membership
        mem_res = await client.get(f"/api/v1/requisitions/{req_id}/members")
        assert mem_res.status_code == 200
        members = mem_res.json()
        assert len(members) == 1
        assert members[0]["user_id"] == str(user.id)
        assert members[0]["membership_role"] == "owner"


@pytest.mark.asyncio
async def test_list_and_detail_requisitions_isolation(test_session_factory):
    """Reviewer only sees requisitions where assigned; Admin sees all."""
    async with test_session_factory() as session:
        recruiter, rec_token, rec_csrf = await create_test_user_and_session(session, [AccountRole.RECRUITER], "rec")
        reviewer, rev_token, rev_csrf = await create_test_user_and_session(session, [AccountRole.REVIEWER], "rev")
        admin, adm_token, adm_csrf = await create_test_user_and_session(session, [AccountRole.ADMIN], "admin")

    transport = ASGITransport(app=app)

    # 1. Recruiter creates requisition 1
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        res1 = await client.post("/api/v1/requisitions", json={"title": "Req 1"})
        req1_id = res1.json()["id"]

    # 2. Reviewer cannot see Req 1 yet
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rev_token}, headers={"X-CSRF-Token": rev_csrf}
    ) as client:
        list_res = await client.get("/api/v1/requisitions")
        assert list_res.status_code == 200
        assert not any(r["id"] == req1_id for r in list_res.json())

        # Direct detail access is 403 Forbidden
        det_res = await client.get(f"/api/v1/requisitions/{req1_id}")
        assert det_res.status_code == 403

    # 3. Recruiter adds Reviewer to Req 1
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        add_mem = await client.put(
            f"/api/v1/requisitions/{req1_id}/members/{reviewer.id}",
            json={"membership_role": "reviewer"},
        )
        assert add_mem.status_code == 200

    # 4. Now Reviewer can list and view detail
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rev_token}, headers={"X-CSRF-Token": rev_csrf}
    ) as client:
        list_res2 = await client.get("/api/v1/requisitions")
        assert any(r["id"] == req1_id for r in list_res2.json())
        det_res2 = await client.get(f"/api/v1/requisitions/{req1_id}")
        assert det_res2.status_code == 200
        assert det_res2.json()["my_role"] == "reviewer"

    # 5. Admin can see all requisitions
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: adm_token}, headers={"X-CSRF-Token": adm_csrf}
    ) as client:
        adm_list = await client.get("/api/v1/requisitions")
        assert any(r["id"] == req1_id for r in adm_list.json())


@pytest.mark.asyncio
async def test_last_owner_cannot_be_removed(test_session_factory):
    """Security Invariant: Requisition must retain at least one OWNER."""
    async with test_session_factory() as session:
        recruiter, rec_token, rec_csrf = await create_test_user_and_session(session, [AccountRole.RECRUITER], "rec")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        res = await client.post("/api/v1/requisitions", json={"title": "Req Owner Guard"})
        req_id = res.json()["id"]

        # Attempt to remove the only owner
        del_res = await client.delete(f"/api/v1/requisitions/{req_id}/members/{recruiter.id}")
        assert del_res.status_code == 400
        assert "CANNOT_REMOVE_LAST_OWNER" in del_res.json()["detail"]


@pytest.mark.asyncio
async def test_jd_version_creation_and_requirement_extraction(test_session_factory):
    """Owner creates JDVersion -> version 1 created, requirements parsed, pointer updated."""
    async with test_session_factory() as session:
        recruiter, rec_token, rec_csrf = await create_test_user_and_session(session, [AccountRole.RECRUITER], "rec")
        reviewer, rev_token, rev_csrf = await create_test_user_and_session(session, [AccountRole.REVIEWER], "rev")

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        req_res = await client.post("/api/v1/requisitions", json={"title": "Python Engineer"})
        req_id = req_res.json()["id"]

        # Add reviewer
        await client.put(f"/api/v1/requisitions/{req_id}/members/{reviewer.id}", json={"membership_role": "reviewer"})

    # 1. Reviewer tries to create JD -> 403 Forbidden (Only Owner can change JD)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rev_token}, headers={"X-CSRF-Token": rev_csrf}
    ) as client:
        rev_jd = await client.post(
            f"/api/v1/requisitions/{req_id}/jd-versions",
            json={"source_text": SAMPLE_JD_TEXT, "change_reason": "Reviewer attempt"},
        )
        assert rev_jd.status_code == 403

    # 2. Owner creates JD Version 1
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        jd_res = await client.post(
            f"/api/v1/requisitions/{req_id}/jd-versions",
            json={"source_text": SAMPLE_JD_TEXT, "change_reason": "Khởi tạo JD v1"},
        )
        assert jd_res.status_code == 201
        jd1 = jd_res.json()
        assert jd1["version_no"] == 1
        assert len(jd1["text_hash"]) == 64
        assert jd1["source_refs"]["extracted_count"] == 6
        assert jd1["source_refs"]["requirements"][0]["requirement_id"] == "JD-PY-01"

        # Verify requisition current_jd_version_id is updated
        detail = await client.get(f"/api/v1/requisitions/{req_id}")
        assert detail.json()["current_jd_version_id"] == jd1["id"]
        assert detail.json()["current_jd"]["version_no"] == 1

        # 3. Owner creates JD Version 2 (immutable history)
        new_text = SAMPLE_JD_TEXT + "\n\nBổ sung thêm yêu cầu tiếng Anh giao tiếp kỹ thuật."
        jd2_res = await client.post(
            f"/api/v1/requisitions/{req_id}/jd-versions",
            json={"source_text": new_text, "change_reason": "Cập nhật tiếng Anh"},
        )
        assert jd2_res.status_code == 201
        jd2 = jd2_res.json()
        assert jd2["version_no"] == 2
        assert jd2["id"] != jd1["id"]

        # List shows both versions in DESC order
        list_jd = await client.get(f"/api/v1/requisitions/{req_id}/jd-versions")
        assert list_jd.status_code == 200
        assert len(list_jd.json()) == 2
        assert list_jd.json()[0]["version_no"] == 2
        assert list_jd.json()[1]["version_no"] == 1


@pytest.mark.asyncio
async def test_concurrent_edit_optimistic_locking(test_session_factory):
    """Concurrent edit returns 409 Conflict when expected_version or If-Match doesn't match."""
    async with test_session_factory() as session:
        recruiter, rec_token, rec_csrf = await create_test_user_and_session(session, [AccountRole.RECRUITER], "rec")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        req_res = await client.post("/api/v1/requisitions", json={"title": "Concurrency Test"})
        req_id = req_res.json()["id"]
        current_version = req_res.json()["row_version"]  # 1

        # Update succeeds with matching expected_version
        patch_ok = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"title": "Concurrency Test Updated", "expected_version": current_version},
        )
        assert patch_ok.status_code == 200
        new_version = patch_ok.json()["row_version"]  # 2

        # Stale update with old expected_version fails with 409 Conflict
        patch_stale = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"title": "Stale Update", "expected_version": current_version},
        )
        assert patch_stale.status_code == 409
        assert "VERSION_CONFLICT" in patch_stale.json()["detail"]

        # Stale update with If-Match header fails with 409 Conflict
        patch_if_match = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"title": "Stale If-Match"},
            headers={"If-Match": f'"{current_version}"'},
        )
        assert patch_if_match.status_code == 409


@pytest.mark.asyncio
async def test_requisition_state_machine_transitions(test_session_factory):
    """Enforces state machine rules: DRAFT -> OPEN requires approved rubric; PAUSE/CLOSE requires reason."""
    async with test_session_factory() as session:
        recruiter, rec_token, rec_csrf = await create_test_user_and_session(session, [AccountRole.RECRUITER], "rec")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        req_res = await client.post("/api/v1/requisitions", json={"title": "State Machine Req"})
        req_id = req_res.json()["id"]

        # 1. Opening without JD and Rubric is REJECTED
        open_fail = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"status": "open"},
        )
        assert open_fail.status_code == 422
        assert "VALIDATION_ERROR" in open_fail.json()["detail"]

        # Add JD
        jd_res = await client.post(
            f"/api/v1/requisitions/{req_id}/jd-versions",
            json={"source_text": SAMPLE_JD_TEXT, "change_reason": "Init JD"},
        )
        jd_id = uuid.UUID(jd_res.json()["id"])

        # Create approved rubric in DB
        async with test_session_factory() as db:
            rubric = RubricVersion(
                id=uuid.uuid4(),
                requisition_id=uuid.UUID(req_id),
                jd_version_id=jd_id,
                version_no=1,
                status=RubricStatus.APPROVED,
                content_hash="abc" * 21 + "a",
                approved_at=datetime.now(timezone.utc),
            )
            db.add(rubric)
            await db.flush()
            # Link rubric to requisition
            req_db = (await db.execute(Requisition.__table__.select().where(Requisition.id == uuid.UUID(req_id)))).fetchone()
            from sqlalchemy import update
            await db.execute(update(Requisition).where(Requisition.id == uuid.UUID(req_id)).values(current_rubric_version_id=rubric.id))
            await db.commit()

        # 2. Opening WITH approved rubric SUCCEEDS
        open_ok = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"status": "open"},
        )
        assert open_ok.status_code == 200
        assert open_ok.json()["status"] == "open"
        assert open_ok.json()["opened_at"] is not None

        # 3. Pausing without reason is REJECTED
        pause_no_reason = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"status": "paused"},
        )
        assert pause_no_reason.status_code == 422

        # 4. Pausing with reason SUCCEEDS
        pause_ok = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"status": "paused", "reason": "Tạm dừng nhận thêm hồ sơ để phỏng vấn đợt 1"},
        )
        assert pause_ok.status_code == 200
        assert pause_ok.json()["status"] == "paused"

        # 5. Closing without reason is REJECTED
        close_no_reason = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"status": "closed"},
        )
        assert close_no_reason.status_code == 422

        # 6. Closing with reason SUCCEEDS
        close_ok = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"status": "closed", "reason": "Đã tuyển đủ chỉ tiêu"},
        )
        assert close_ok.status_code == 200
        assert close_ok.json()["status"] == "closed"
        assert close_ok.json()["closed_at"] is not None

        # 7. Direct transition CLOSED -> OPEN is illegal (must reopen to PAUSED first)
        illegal_reopen = await client.patch(
            f"/api/v1/requisitions/{req_id}",
            json={"status": "open", "reason": "Illegal jump"},
        )
        assert illegal_reopen.status_code == 422


@pytest.mark.asyncio
async def test_jd_egress_approval_flow(test_session_factory):
    """Owner approves JD inspection for LLM egress with hash check."""
    async with test_session_factory() as session:
        recruiter, rec_token, rec_csrf = await create_test_user_and_session(session, [AccountRole.RECRUITER], "rec")
        reviewer, rev_token, rev_csrf = await create_test_user_and_session(session, [AccountRole.REVIEWER], "rev")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rec_token}, headers={"X-CSRF-Token": rec_csrf}
    ) as client:
        req_res = await client.post("/api/v1/requisitions", json={"title": "Egress Test"})
        req_id = req_res.json()["id"]

        jd_res = await client.post(
            f"/api/v1/requisitions/{req_id}/jd-versions",
            json={"source_text": SAMPLE_JD_TEXT, "change_reason": "Init for egress"},
        )
        jd_id = jd_res.json()["id"]
        text_hash = jd_res.json()["text_hash"]

        # 1. Non-acknowledged fails
        bad_ack = await client.post(
            f"/api/v1/jd-versions/{jd_id}/approve-egress",
            json={"expected_text_hash": text_hash, "acknowledged": False},
        )
        assert bad_ack.status_code == 400

        # 2. Hash mismatch fails with 409
        bad_hash = await client.post(
            f"/api/v1/jd-versions/{jd_id}/approve-egress",
            json={"expected_text_hash": "wronghash" + "0" * 55, "acknowledged": True},
        )
        assert bad_hash.status_code == 409
        assert "TEXT_HASH_MISMATCH" in bad_hash.json()["detail"]

        # 3. Successful egress approval
        good_app = await client.post(
            f"/api/v1/jd-versions/{jd_id}/approve-egress",
            json={"expected_text_hash": text_hash, "acknowledged": True},
        )
        assert good_app.status_code == 200
        assert good_app.json()["egress_reviewed_by"] == str(recruiter.id)
        assert good_app.json()["egress_reviewed_at"] is not None
