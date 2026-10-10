"""Integration and Unit tests for Rubric seed, editor, anti-discrimination policy, and approval.
Covers Task B04 requirements and invariants.
"""
from datetime import datetime, timezone
from pathlib import Path
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

SAMPLE_JD_TEXT = (Path(__file__).resolve().parents[3] / "fixtures" / "seeds" / "jd-backend-python.v3.vi.md").read_text(encoding="utf-8")


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
            assert len(c["source_requirements"]) == 1
            assert c["source_requirements"][0]["quote"] in SAMPLE_JD_TEXT

        # Verify threshold config
        policy = data["threshold_config"]
        assert policy["threshold"] == 50
        assert policy["core_minimum_scores"]["python_backend"] == 2
        assert policy["core_minimum_scores"]["api_design"] == 2
        assert policy["core_minimum_scores"]["sql_data"] == 2
        assert policy["required_criterion_ids"] == ["python_backend", "api_design", "sql_data"]


@pytest.mark.asyncio
async def test_seed_rubric_rejects_unmapped_jd(test_session_factory):
    """A seed rubric cannot silently cite a different job description."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, reviewer, r_token, r_csrf, req_id, jd_id = await setup_requisition_with_jd(session)
        jd = await session.get(JDVersion, jd_id)
        jd.source_text = "Vị trí Backend Python: phát triển dịch vụ nội bộ với API và dữ liệu quan hệ theo nhu cầu thực tế."
        jd.source_refs = {"requirements": [], "extracted_count": 0}
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={SESSION_COOKIE_NAME: o_token}, headers={"X-CSRF-Token": o_csrf}) as client:
        response = await client.post(f"/api/v1/requisitions/{req_id}/rubrics", json={"source": "seed"})
        assert response.status_code == 422
        assert "JD cần đúng một yêu cầu nguồn" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rubric_draft_can_be_reopened_by_members(test_session_factory):
    """Drafts must remain visible after reload while nonmembers cannot inspect them."""
    async with test_session_factory() as session:
        owner, o_token, o_csrf, reviewer, r_token, r_csrf, req_id, jd_id = await setup_requisition_with_jd(session)

    transport = ASGITransport(app=app)
    path = f"/api/v1/requisitions/{req_id}/rubrics"
    async with AsyncClient(transport=transport, base_url="http://test", cookies={SESSION_COOKIE_NAME: o_token}, headers={"X-CSRF-Token": o_csrf}) as client:
        create = await client.post(path, json={"source": "seed"})
        assert create.status_code == 201
        draft_id = create.json()["id"]
        listing = await client.get(path)
        assert listing.status_code == 200
        assert listing.json()[0]["id"] == draft_id
        assert listing.json()[0]["status"] == "draft"

    async with AsyncClient(transport=transport, base_url="http://test", cookies={SESSION_COOKIE_NAME: r_token}) as client:
        listing = await client.get(path)
        assert listing.status_code == 200
        assert listing.json()[0]["id"] == draft_id

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get(path)).status_code == 401


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

        # 2. Too few criteria (one criterion is below the dynamic 2..12 limit)
        missing_crit_rubric = dict(valid_rubric)
        missing_crit_rubric["criteria"] = valid_rubric["criteria"][:1]
        res_missing = await client.put(f"/api/v1/rubrics/{rubric_id}", json={"rubric": missing_crit_rubric})
        assert res_missing.status_code == 422
        assert "từ 2 đến 12" in res_missing.json()["detail"]

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
