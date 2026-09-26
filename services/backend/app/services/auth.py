"""Authentication and session lifecycle service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.org_user import SessionRecord, User, UserAccountRole
from app.domain.enums import AccountRole, UserStatus
from app.domain.security import generate_secure_token, hash_token, verify_password

IDLE_TIMEOUT_MINUTES = 30
ABSOLUTE_LIFETIME_HOURS = 8


class AuthenticationError(Exception):
    pass


class SessionExpiredError(AuthenticationError):
    pass


class CSRFValidationError(AuthenticationError):
    pass


async def authenticate_user(
    db: AsyncSession,
    login_name: str,
    password: str,
) -> Optional[User]:
    """Authenticate user with normalized login name and password. Returns User if valid, None otherwise."""
    normalized_login = login_name.strip().lower()
    stmt = (
        select(User)
        .where(User.login_name == normalized_login)
        .options(selectinload(User.account_roles))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if not user:
        return None

    if user.status != UserStatus.ACTIVE:
        return None

    if not verify_password(password, user.password_hash):
        return None

    return user


async def create_session(
    db: AsyncSession,
    user: User,
) -> tuple[str, str, SessionRecord]:
    """Create a new session record with opaque session token and CSRF token."""
    now = datetime.now(timezone.utc)
    session_token = generate_secure_token(32)
    csrf_token = generate_secure_token(32)

    token_hash = hash_token(session_token)
    csrf_hash = hash_token(csrf_token)

    session_record = SessionRecord(
        id=uuid.uuid4(),
        token_hash=token_hash,
        user_id=user.id,
        csrf_hash=csrf_hash,
        user_session_generation=user.session_generation,
        expires_at=now + timedelta(hours=ABSOLUTE_LIFETIME_HOURS),
        last_seen_at=now,
        created_at=now,
    )
    db.add(session_record)
    await db.flush()

    return session_token, csrf_token, session_record


async def validate_session(
    db: AsyncSession,
    session_token: str,
    csrf_token: Optional[str] = None,
    is_mutation: bool = False,
) -> tuple[User, list[AccountRole], SessionRecord]:
    """Validate session token, idle timeout, absolute lifetime, session generation, and CSRF for mutations."""
    now = datetime.now(timezone.utc)
    token_digest = hash_token(session_token)

    stmt = (
        select(SessionRecord)
        .where(SessionRecord.token_hash == token_digest)
        .options(selectinload(SessionRecord.user).selectinload(User.account_roles))
    )
    result = await db.execute(stmt)
    session_rec = result.scalar_one_or_none()

    if not session_rec:
        raise AuthenticationError("Invalid session")

    if session_rec.revoked_at is not None:
        raise AuthenticationError("Session has been revoked")

    user = session_rec.user
    if not user or user.status != UserStatus.ACTIVE:
        raise AuthenticationError("User is disabled or missing")

    # Verify session generation matches user's current generation
    if session_rec.user_session_generation != user.session_generation:
        raise AuthenticationError("Session invalidated by password change or global logout")

    # Verify absolute expiry
    if now >= session_rec.expires_at:
        raise SessionExpiredError("Session absolute lifetime expired")

    # Verify idle timeout
    if now - session_rec.last_seen_at > timedelta(minutes=IDLE_TIMEOUT_MINUTES):
        raise SessionExpiredError("Session idle timeout exceeded")

    # Verify CSRF token on mutation requests (POST/PUT/PATCH/DELETE)
    if is_mutation:
        if not csrf_token:
            raise CSRFValidationError("Missing CSRF token")
        if hash_token(csrf_token) != session_rec.csrf_hash:
            raise CSRFValidationError("Invalid CSRF token")

    # Update last_seen_at
    session_rec.last_seen_at = now
    await db.flush()

    roles = [role_assoc.role for role_assoc in user.account_roles]
    return user, roles, session_rec


async def revoke_session(db: AsyncSession, session_token: str) -> bool:
    """Revoke a specific session."""
    token_digest = hash_token(session_token)
    stmt = (
        update(SessionRecord)
        .where(SessionRecord.token_hash == token_digest, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount > 0


async def revoke_all_user_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Revoke all sessions for a user by bumping session_generation and marking records revoked."""
    now = datetime.now(timezone.utc)
    # Increment user's session_generation
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(session_generation=User.session_generation + 1)
    )
    # Revoke all existing sessions in DB
    await db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user_id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.flush()
