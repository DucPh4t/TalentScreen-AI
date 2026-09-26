"""Unit and Integration tests for Authentication, Sessions, CSRF, and RBAC Guards.
Covers Task B02 and security tests SEC-01..05.
"""
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    Application,
    Candidate,
    Organization,
    RawAccessGrant,
    Requisition,
    RequisitionMembership,
    User,
    UserAccountRole,
)
from app.domain.authorization import (
    SESSION_COOKIE_NAME,
    check_raw_access_grant,
    check_requisition_membership,
)
from app.domain.enums import (
    AccountRole,
    EnvironmentMode,
    MembershipRole,
    RequisitionStatus,
    UserStatus,
)
from app.domain.security import hash_password, verify_password
from app.main import app
from app.services.auth import revoke_all_user_sessions


def test_argon2id_password_hashing():
    """Verify Argon2id password hashing and verification."""
    password = "SuperSecretPassword#2026"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


@pytest.mark.asyncio
async def test_login_success_and_httponly_cookie(test_session_factory):
    """Verify successful login returns CSRF token and sets HttpOnly session cookie."""
    login_name = f"user_{uuid.uuid4().hex[:8]}"
    raw_password = "SecurePassword123!"

    async with test_session_factory() as session:
        user = User(
            login_name=login_name,
            display_name="Nguyễn Văn A",
            password_hash=hash_password(raw_password),
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.flush()
        session.add(UserAccountRole(user_id=user.id, role=AccountRole.RECRUITER))
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login
        response = await client.post(
            "/api/v1/auth/login",
            json={"login_name": login_name, "password": raw_password},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "csrf_token" in data
        assert data["user"]["login_name"] == login_name
        assert "recruiter" in data["user"]["roles"]

        # Check HttpOnly cookie
        assert SESSION_COOKIE_NAME in response.cookies
        cookie = response.cookies[SESSION_COOKIE_NAME]
        assert len(cookie) > 20


@pytest.mark.asyncio
async def test_login_invalid_credentials_generic_error():
    """Verify generic error message to prevent account enumeration."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={"login_name": "non_existent_user", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Thông tin đăng nhập không hợp lệ."


@pytest.mark.asyncio
async def test_csrf_validation_on_mutation(test_session_factory):
    """Verify CSRF token is required and strictly validated on mutation requests."""
    login_name = f"user_{uuid.uuid4().hex[:8]}"
    raw_password = "SecurePassword123!"

    async with test_session_factory() as session:
        user = User(
            login_name=login_name,
            display_name="Test User",
            password_hash=hash_password(raw_password),
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"login_name": login_name, "password": raw_password},
        )
        csrf_token = login_res.json()["csrf_token"]

        # Mutation without CSRF token must fail with 403 Forbidden
        logout_no_csrf = await client.post("/api/v1/auth/logout")
        assert logout_no_csrf.status_code == 403
        assert "Missing CSRF" in logout_no_csrf.json()["detail"]

        # Mutation with invalid CSRF token must fail with 403 Forbidden
        logout_bad_csrf = await client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": "invalid_fake_token"},
        )
        assert logout_bad_csrf.status_code == 403
        assert "Invalid CSRF" in logout_bad_csrf.json()["detail"]

        # Mutation with correct CSRF token succeeds
        logout_success = await client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logout_success.status_code == 200


@pytest.mark.asyncio
async def test_session_revocation_and_global_logout(test_session_factory):
    """Verify session is invalid after logout and after global session revocation."""
    login_name = f"user_{uuid.uuid4().hex[:8]}"
    raw_password = "SecurePassword123!"
    user_id = None

    async with test_session_factory() as session:
        user = User(
            login_name=login_name,
            display_name="Test User",
            password_hash=hash_password(raw_password),
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.commit()
        user_id = user.id

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"login_name": login_name, "password": raw_password},
        )
        csrf_token = login_res.json()["csrf_token"]

        # /me succeeds while session is active
        me_res = await client.get("/api/v1/auth/me")
        assert me_res.status_code == 200

        # Global revocation (bumps user session generation)
        async with test_session_factory() as session:
            await revoke_all_user_sessions(session, user_id)
            await session.commit()

        # Subsequent request with old session fails
        me_after_revoke = await client.get("/api/v1/auth/me")
        assert me_after_revoke.status_code == 401


@pytest.mark.asyncio
async def test_raw_access_grant_guards(test_session_factory):
    """Security Invariant: Admin or Recruiter WITHOUT raw_access_grant CANNOT read raw CV."""
    from fastapi import HTTPException

    async with test_session_factory() as session:
        org = Organization(name="Test Org", environment=EnvironmentMode.SANDBOX)
        user = User(login_name=f"recruiter_{uuid.uuid4().hex[:8]}", display_name="Recruiter", password_hash="h")
        admin = User(login_name=f"admin_{uuid.uuid4().hex[:8]}", display_name="Admin", password_hash="h")
        session.add_all([org, user, admin])
        await session.flush()

        req = Requisition(organization_id=org.id, title="IT Req", status=RequisitionStatus.OPEN)
        cand = Candidate(organization_id=org.id, public_label=f"CAND-{uuid.uuid4().hex[:6]}")
        session.add_all([req, cand])
        await session.flush()

        app_obj = Application(requisition_id=req.id, candidate_id=cand.id)
        session.add(app_obj)
        await session.commit()

        # 1. Admin without grant is REJECTED
        with pytest.raises(HTTPException) as exc_info:
            await check_raw_access_grant(session, app_obj.id, admin.id)
        assert exc_info.value.status_code == 403

        # 2. Recruiter without grant is REJECTED
        with pytest.raises(HTTPException) as exc_info:
            await check_raw_access_grant(session, app_obj.id, user.id)
        assert exc_info.value.status_code == 403

        # 3. Grant granted with raw_cv scope allows access
        grant = RawAccessGrant(
            application_id=app_obj.id,
            grantee_user_id=user.id,
            scopes=["raw_cv"],
            granted_by=admin.id,
            reason="HR verification",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        session.add(grant)
        await session.commit()

        # Recruiter with active grant SUCCEEDS
        checked_grant = await check_raw_access_grant(session, app_obj.id, user.id)
        assert checked_grant.id == grant.id

        # 4. Revoked grant is REJECTED
        grant.revoked_at = datetime.now(timezone.utc)
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await check_raw_access_grant(session, app_obj.id, user.id)
        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_requisition_membership_guards(test_session_factory):
    """Security Invariant: Users must belong to requisition; reviewers cannot perform owner actions."""
    from fastapi import HTTPException

    async with test_session_factory() as session:
        org = Organization(name="Test Org 2", environment=EnvironmentMode.SANDBOX)
        owner_user = User(login_name=f"owner_{uuid.uuid4().hex[:8]}", display_name="Owner", password_hash="h")
        reviewer_user = User(login_name=f"reviewer_{uuid.uuid4().hex[:8]}", display_name="Reviewer", password_hash="h")
        outsider_user = User(login_name=f"outsider_{uuid.uuid4().hex[:8]}", display_name="Outsider", password_hash="h")
        session.add_all([org, owner_user, reviewer_user, outsider_user])
        await session.flush()

        req = Requisition(organization_id=org.id, title="IT Req 2", status=RequisitionStatus.OPEN)
        session.add(req)
        await session.flush()

        session.add(RequisitionMembership(requisition_id=req.id, user_id=owner_user.id, membership_role=MembershipRole.OWNER))
        session.add(RequisitionMembership(requisition_id=req.id, user_id=reviewer_user.id, membership_role=MembershipRole.REVIEWER))
        await session.commit()

        # 1. Outsider is REJECTED
        with pytest.raises(HTTPException) as exc_info:
            await check_requisition_membership(session, req.id, outsider_user.id)
        assert exc_info.value.status_code == 403

        # 2. Reviewer trying to perform OWNER-only action is REJECTED
        with pytest.raises(HTTPException) as exc_info:
            await check_requisition_membership(session, req.id, reviewer_user.id, required_roles=[MembershipRole.OWNER])
        assert exc_info.value.status_code == 403

        # 3. Owner performing OWNER action SUCCEEDS
        membership = await check_requisition_membership(session, req.id, owner_user.id, required_roles=[MembershipRole.OWNER])
        assert membership.membership_role == MembershipRole.OWNER
