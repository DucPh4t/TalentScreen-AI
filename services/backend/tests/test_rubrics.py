"""Integration and Unit tests for Rubric seed, editor, anti-discrimination policy, and approval.
Covers Task B04 requirements and invariants.
"""
from datetime import datetime, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    JDVersion,
    Requisition,
    RubricCriterion,
    RubricVersion,
    User,
    UserAccountRole,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import (
    AccountRole,
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


async def setup_requisition_with_jd(
    session,
) -> tuple[User, str, str, User, str, str, uuid.UUID, uuid.UUID]:
    """Helper to create an owner, a reviewer, a requisition, and a JD version."""
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

    from app.db.models.requisition import RequisitionMembership
    req = Requisition(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Python Engineer Req",
        status=RequisitionStatus.DRAFT,
        row_version=1,
    )
    session.add(req)
    await session.flush()

    session.add(RequisitionMembership(requisition_id=req.id, user_id=owner.id, membership_role=MembershipRole.OWNER))
    session.add(RequisitionMembership(requisition_id=req.id, user_id=reviewer.id, membership_role=MembershipRole.REVIEWER))
    await session.flush()

    jd = JDVersion(
        id=uuid.uuid4(),
        requisition_id=req.id,
        version_no=1,
        source_text=SAMPLE_JD_TEXT,
        text_hash="abc" * 21 + "a",
        created_by=owner.id,
    )
    session.add(jd)
    await session.flush()

    req.current_jd_version_id = jd.id
    req.row_version = 2
    await session.commit()

    return owner, o_token, o_csrf, reviewer, r_token, r_csrf, req.id, jd.id


@pytest.mark.asyncio
async def test_import_seed_rubric_draft(test_session_factory):
    """Seed rubric import creates DRAFT rubric with 6 canonical criteria summing to 100%."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, reviewer, r_token, r_csrf, req_id, jd_id = await setup_requisition_with_jd(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: o_token}
    headers = {"X-CSRF-Token": o_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # Import seed
        res = await client.post(
            f"/api/v1/requisitions/{req_id}/rubrics",
            json={"source": "seed"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["status"] == "draft"  # Invariant: AI/Seed draft is NOT approved automatically
        assert data["version_no"] == 1
        assert len(data["content_hash"]) == 64
        assert data["approved_by"] is None

        # Verify 6 criteria
        criteria = data["criteria"]
        assert len(criteria) == 6
        criterion_ids = {c["id"] for c in criteria}
        assert criterion_ids == {
            "python_backend",
            "api_design",
            "sql_data",
            "testing_debugging",
            "security_privacy",
            "delivery_ops",
        }

        # Verify weights sum to 100
        total_weight = sum(c["weight"] for c in criteria)
        assert total_weight == 100

        # Verify anchors 0..4
        for c in criteria:
            scores = {a["score"] for a in c["scoring_anchors"]}
            assert scores == {0, 1, 2, 3, 4}

        # Verify threshold config
        policy = data["threshold_config"]
        assert policy["threshold"] == 70
        assert policy["core_minimum_scores"]["python_backend"] == 2
        assert policy["core_minimum_scores"]["api_design"] == 2
        assert policy["core_minimum_scores"]["sql_data"] == 2


@pytest.mark.asyncio
async def test_reviewer_approve_and_edit_denied(test_session_factory):
    """Security Invariant: Reviewer cannot create, update, or approve rubric."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, reviewer, r_token, r_csrf, req_id, jd_id = await setup_requisition_with_jd(session)

    transport = ASGITransport(app=app)

    # 1. Owner creates seed rubric
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: o_token}, headers={"X-CSRF-Token": o_csrf}
    ) as client:
        seed_res = await client.post(f"/api/v1/requisitions/{req_id}/rubrics", json={"source": "seed"})
        rubric_id = seed_res.json()["id"]

    # 2. Reviewer tries to approve rubric -> 403 Forbidden
    async with AsyncClient(
        transport=transport, base_url="http://test",
        cookies={SESSION_COOKIE_NAME: r_token}, headers={"X-CSRF-Token": r_csrf}
    ) as client:
        appr_res = await client.post(
            f"/api/v1/rubrics/{rubric_id}/approve",
            json={
                "expected_requisition_version": 2,
                "expected_jd_version_id": str(jd_id),
                "acknowledge_thresholds": True,
            },
        )
        assert appr_res.status_code == 403

        # Reviewer tries to update rubric -> 403 Forbidden
        put_res = await client.put(
            f"/api/v1/rubrics/{rubric_id}",
            json={"rubric": seed_res.json()},
        )
        assert put_res.status_code == 403


@pytest.mark.asyncio
async def test_rubric_validation_error_cases(test_session_factory):
    """Rejects missing criteria, duplicate criteria, invalid weights, and forbidden discrimination."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, reviewer, r_token, r_csrf, req_id, jd_id = await setup_requisition_with_jd(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: o_token}
    headers = {"X-CSRF-Token": o_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        seed_res = await client.post(f"/api/v1/requisitions/{req_id}/rubrics", json={"source": "seed"})
        rubric_id = seed_res.json()["id"]
        valid_rubric = seed_res.json()

        # 1. Weights do not sum to 100 (e.g. 95)
        bad_weight_rubric = dict(valid_rubric)
        bad_weight_rubric["criteria"] = [dict(c) for c in valid_rubric["criteria"]]
        bad_weight_rubric["criteria"][0]["weight"] = 15  # was 20, sum is now 95
        res_weight = await client.put(f"/api/v1/rubrics/{rubric_id}", json={"rubric": bad_weight_rubric})
        assert res_weight.status_code == 422
        assert "Tổng trọng số" in res_weight.json()["detail"]

        # 2. Missing criterion (only 5 criteria)
        missing_crit_rubric = dict(valid_rubric)
        missing_crit_rubric["criteria"] = valid_rubric["criteria"][:5]
        res_missing = await client.put(f"/api/v1/rubrics/{rubric_id}", json={"rubric": missing_crit_rubric})
        assert res_missing.status_code == 422
        assert "đúng 6 tiêu chí" in res_missing.json()["detail"]

        # 3. Duplicate criterion
        dup_rubric = dict(valid_rubric)
        dup_rubric["criteria"] = [dict(c) for c in valid_rubric["criteria"]]
        dup_rubric["criteria"][1]["id"] = dup_rubric["criteria"][0]["id"]
        res_dup = await client.put(f"/api/v1/rubrics/{rubric_id}", json={"rubric": dup_rubric})
        assert res_dup.status_code == 422
        assert "Trùng lặp" in res_dup.json()["detail"]

        # 4. Forbidden discriminatory criterion: checking age / gender
        discrim_rubric = dict(valid_rubric)
        discrim_rubric["criteria"] = [dict(c) for c in valid_rubric["criteria"]]
        discrim_rubric["criteria"][0]["description"] = "Ưu tiên ứng viên dưới 30 tuổi và tốt nghiệp trường top."
        res_discrim = await client.put(f"/api/v1/rubrics/{rubric_id}", json={"rubric": discrim_rubric})
        assert res_discrim.status_code == 422
        assert "FORBIDDEN_CRITERION_DETECTED" in res_discrim.json()["detail"]


@pytest.mark.asyncio
async def test_rubric_approval_and_immutability(test_session_factory):
    """Owner approves rubric draft -> becomes APPROVED, updating pointer. Edits after approval are rejected."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, reviewer, r_token, r_csrf, req_id, jd_id = await setup_requisition_with_jd(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: o_token}
    headers = {"X-CSRF-Token": o_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # Create seed draft
        seed_res = await client.post(f"/api/v1/requisitions/{req_id}/rubrics", json={"source": "seed"})
        rubric_id = seed_res.json()["id"]

        # 1. Mismatched expected_requisition_version returns 409 Conflict
        bad_v_res = await client.post(
            f"/api/v1/rubrics/{rubric_id}/approve",
            json={
                "expected_requisition_version": 999,
                "expected_jd_version_id": str(jd_id),
                "acknowledge_thresholds": True,
            },
        )
        assert bad_v_res.status_code == 409
        assert "VERSION_CONFLICT" in bad_v_res.json()["detail"]

        # 2. Approve succeeds
        appr_res = await client.post(
            f"/api/v1/rubrics/{rubric_id}/approve",
            json={
                "expected_requisition_version": 2,
                "expected_jd_version_id": str(jd_id),
                "acknowledge_thresholds": True,
            },
        )
        assert appr_res.status_code == 200
        data = appr_res.json()
        assert data["rubric"]["status"] == "approved"
        assert data["rubric"]["approved_by"] == str(owner.id)
        assert data["rubric"]["approved_at"] is not None
        assert data["requisition_row_version"] == 3

        # 3. Invariant: Approved rubric is IMMUTABLE (cannot PUT update)
        put_res = await client.put(
            f"/api/v1/rubrics/{rubric_id}",
            json={"rubric": data["rubric"]},
        )
        assert put_res.status_code == 422
        assert "RUBRIC_IMMUTABLE" in put_res.json()["detail"]

        # 4. Check Requisition detail points to current approved rubric
        req_detail = await client.get(f"/api/v1/requisitions/{req_id}")
        assert req_detail.json()["current_rubric_version_id"] == rubric_id
        assert req_detail.json()["current_rubric"]["status"] == "approved"
