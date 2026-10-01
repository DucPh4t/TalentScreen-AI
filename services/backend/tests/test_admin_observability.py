"""Integration tests for Admin Observability, SLIs, and Readiness (Task B23)."""
from datetime import datetime, timezone
import uuid
from types import SimpleNamespace
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import User, UserAccountRole
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import AccountRole, UserStatus
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session
from app.api.v1 import admin
from app.config import Settings


async def create_admin_user(session) -> tuple[User, str, str]:
    user = User(
        id=uuid.uuid4(),
        login_name=f"admin_obs_{uuid.uuid4().hex[:8]}",
        display_name="Admin Observability User",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    session.add(UserAccountRole(user_id=user.id, role=AccountRole.ADMIN))
    await session.flush()
    token, csrf, _ = await create_session(session, user)
    await session.commit()
    return user, token, csrf


async def create_reviewer_user(session) -> tuple[User, str, str]:
    user = User(
        id=uuid.uuid4(),
        login_name=f"rev_obs_{uuid.uuid4().hex[:8]}",
        display_name="Reviewer User",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    session.add(UserAccountRole(user_id=user.id, role=AccountRole.REVIEWER))
    await session.flush()
    token, csrf, _ = await create_session(session, user)
    await session.commit()
    return user, token, csrf


@pytest.mark.asyncio
async def test_readiness_probe():
    """Verify system readiness probe returns 200 with DB and storage status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/admin/readiness")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["database"] is True
        assert data["storage"] is True
        assert data["schema"] is True


@pytest.mark.asyncio
async def test_readiness_rejects_schema_that_needs_migration(monkeypatch):
    monkeypatch.setattr(admin.ScriptDirectory, "from_config", lambda _: SimpleNamespace(get_heads=lambda: ["future_revision"]))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/readiness")
        assert response.status_code == 503
        assert response.json()["detail"]["schema"] is False


@pytest.mark.asyncio
async def test_admin_metrics_endpoint_role_protected(test_session_factory, monkeypatch):
    """Verify non-admin cannot access metrics, while admin receives SLIs and telemetry."""
    async with test_session_factory() as session:
        _, rev_token, rev_csrf = await create_reviewer_user(session)
        _, adm_token, adm_csrf = await create_admin_user(session)
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(_env_file=None, RATE_CARD_VERIFIED_AT=None))

    transport = ASGITransport(app=app)

    # 1. Non-admin is rejected with 403 Forbidden
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: rev_token},
        headers={"X-CSRF-Token": rev_csrf},
    ) as client:
        resp_rev = await client.get("/api/v1/admin/metrics")
        assert resp_rev.status_code == 403

    # 2. Admin receives metrics
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={SESSION_COOKIE_NAME: adm_token},
        headers={"X-CSRF-Token": adm_csrf},
    ) as client:
        resp_adm = await client.get("/api/v1/admin/metrics")
        assert resp_adm.status_code == 200
        metrics = resp_adm.json()

        assert "jobs_summary" in metrics
        assert "latencies" in metrics
        assert "budget_summary" in metrics
        assert "worker_health" in metrics
        assert "sli_report" in metrics
        assert metrics["budget_summary"]["rate_card_verified"] is False
        assert metrics["latencies"]["avg_queue_wait_seconds"] is None

        sli = metrics["sli_report"]
        assert "queue_latency_ok" in sli
        assert "budget_cap_ok" in sli
        assert "worker_health_ok" in sli
        assert "error_rate_ok" in sli
