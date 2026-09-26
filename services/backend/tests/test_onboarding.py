"""Integration tests for Sandbox Onboarding & Interactive Training (Task B21)."""
from datetime import datetime, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import Organization, User, UserAccountRole
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import AccountRole, UserStatus
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session


async def create_test_user(session, role: AccountRole = AccountRole.RECRUITER) -> tuple[User, str, str]:
    user = User(
        id=uuid.uuid4(),
        login_name=f"onboard_user_{uuid.uuid4().hex[:8]}",
        display_name="HR Trainee User",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    session.add(UserAccountRole(user_id=user.id, role=role))
    await session.flush()
    token, csrf, _ = await create_session(session, user)
    await session.commit()
    return user, token, csrf


@pytest.mark.asyncio
async def test_get_onboarding_scenarios():
    """Verify preloaded 5 sandbox training scenarios are returned."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/onboarding/scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        assert len(scenarios) == 5
        ids = [s["id"] for s in scenarios]
        assert "scenario_1_evidence_inspection" in ids
        assert "scenario_2_missing_evidence" in ids
        assert "scenario_3_hr_override" in ids
        assert "scenario_4_attested_decision" in ids
        assert "scenario_5_audit_trail" in ids


@pytest.mark.asyncio
async def test_onboarding_lifecycle(test_session_factory):
    """Test full onboarding walkthrough progression, step completion, and reset."""
    async with test_session_factory() as session:
        user, token, csrf = await create_test_user(session)

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: token}
    headers = {"X-CSRF-Token": csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # 1. Initial status: 0 steps completed
        init_res = await client.get("/api/v1/onboarding")
        assert init_res.status_code == 200
        data = init_res.json()
        assert data["is_completed"] is False
        assert len(data["remaining_steps"]) == 5

        # 2. Complete Step 1: inspect source
        s1 = await client.post(
            "/api/v1/onboarding/step",
            json={
                "step_id": "step_1_inspect_source",
                "exercise_result": {"inspected_quote": True, "span_id": "spn_sandbox_01_sql"},
            },
        )
        assert s1.status_code == 200
        assert s1.json()["completed_steps"]["step_1_inspect_source"]["completed"] is True
        assert len(s1.json()["remaining_steps"]) == 4

        # 3. Complete remaining steps (2, 3, 4, 5)
        for st in ["step_2_missing_evidence", "step_3_hr_override", "step_4_attested_decision", "step_5_audit_trail"]:
            res = await client.post(
                "/api/v1/onboarding/step",
                json={"step_id": st, "exercise_result": {"notes": f"Completed {st}"}},
            )
            assert res.status_code == 200

        final_res = await client.get("/api/v1/onboarding")
        assert final_res.status_code == 200
        final_data = final_res.json()
        assert final_data["is_completed"] is True
        assert len(final_data["remaining_steps"]) == 0
        assert final_data["completed_at"] is not None

        # 4. Reset onboarding
        reset_res = await client.post("/api/v1/onboarding/reset")
        assert reset_res.status_code == 200
        reset_data = reset_res.json()
        assert reset_data["is_completed"] is False
        assert len(reset_data["remaining_steps"]) == 5
