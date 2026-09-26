"""Authorization policies, dependencies, and role/membership/raw_grant guards."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Callable, Optional, Sequence
import uuid

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.candidate import Application, RawAccessGrant
from app.db.models.org_user import SessionRecord, User
from app.db.models.requisition import RequisitionMembership
from app.db.session import get_db
from app.domain.enums import AccountRole, MembershipRole
from app.services.auth import (
    AuthenticationError,
    CSRFValidationError,
    SessionExpiredError,
    validate_session,
)

SESSION_COOKIE_NAME = "talentscreen_session"


class AuthenticatedContext:
    def __init__(
        self,
        user: User,
        roles: list[AccountRole],
        session_record: SessionRecord,
    ):
        self.user = user
        self.roles = roles
        self.session_record = session_record

    def has_role(self, *roles: AccountRole) -> bool:
        return any(r in self.roles for r in roles)


async def get_current_context(
    request: Request,
    db: AsyncSession = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    csrf_token: Optional[str] = Header(default=None, alias="X-CSRF-Token"),
) -> AuthenticatedContext:
    """Dependency that extracts session cookie, validates against DB and enforces CSRF on mutations."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    is_mutation = request.method in ("POST", "PUT", "PATCH", "DELETE")

    try:
        user, roles, session_rec = await validate_session(
            db=db,
            session_token=session_token,
            csrf_token=csrf_token,
            is_mutation=is_mutation,
        )
        return AuthenticatedContext(user=user, roles=roles, session_record=session_rec)
    except CSRFValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except (AuthenticationError, SessionExpiredError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )


def require_role(*required_roles: AccountRole) -> Callable:
    """Dependency factory checking that user holds at least one of the specified account roles."""
    async def role_checker(
        ctx: AuthenticatedContext = Depends(get_current_context),
    ) -> AuthenticatedContext:
        if not ctx.has_role(*required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            )
        return ctx

    return role_checker


async def check_requisition_membership(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    user_id: uuid.UUID,
    required_roles: Optional[Sequence[MembershipRole]] = None,
) -> RequisitionMembership:
    """Verify that a user is an active member of a requisition with optional required membership role."""
    stmt = (
        select(RequisitionMembership)
        .where(
            RequisitionMembership.requisition_id == requisition_id,
            RequisitionMembership.user_id == user_id,
            RequisitionMembership.active.is_(True),
        )
    )
    result = await db.execute(stmt)
    membership = result.scalar_one_or_none()

    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: User is not an active member of this requisition",
        )

    if required_roles and membership.membership_role not in required_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Action requires requisition membership role in {[r.value for r in required_roles]}",
        )

    return membership


async def check_raw_access_grant(
    db: AsyncSession,
    application_id: uuid.UUID,
    user_id: uuid.UUID,
    required_scope: str = "raw_cv",
) -> RawAccessGrant:
    """Verify that user holds an active, non-expired grant to view raw CV data.
    Security Invariant: Admin or Recruiter without raw_access_grant CANNOT read raw CV.
    """
    now = datetime.now(timezone.utc)
    stmt = (
        select(RawAccessGrant)
        .where(
            RawAccessGrant.application_id == application_id,
            RawAccessGrant.grantee_user_id == user_id,
            RawAccessGrant.revoked_at.is_(None),
            RawAccessGrant.expires_at > now,
        )
    )
    result = await db.execute(stmt)
    grants = result.scalars().all()

    for grant in grants:
        if required_scope in grant.scopes:
            return grant

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: Viewing raw CV requires an explicit active raw_access_grant",
    )
