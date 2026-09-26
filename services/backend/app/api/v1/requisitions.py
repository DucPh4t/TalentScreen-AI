"""Requisitions, Memberships, and JD Versions API endpoints."""
from __future__ import annotations

from typing import Any, Optional
import uuid
from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.domain.enums import RequisitionStatus
from app.schemas.requisition import (
    JDEgressApproveRequest,
    JDVersionCreateRequest,
    JDVersionDetailResponse,
    JDVersionResponse,
    MemberAddUpdateRequest,
    MemberResponse,
    RequisitionCreateRequest,
    RequisitionDetailResponse,
    RequisitionResponse,
    RequisitionUpdateRequest,
)
from app.services.requisition import (
    add_or_update_member,
    approve_jd_egress,
    create_jd_version,
    create_requisition,
    get_jd_version,
    get_requisition_detail,
    list_jd_versions,
    list_members,
    list_requisitions,
    remove_member,
    update_requisition,
)

router = APIRouter(tags=["Requisitions"])


# ---------------- Requisition Endpoints ---------------- #


@router.get("/requisitions", response_model=list[dict[str, Any]])
async def get_requisitions_list(
    status: Optional[RequisitionStatus] = None,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List accessible requisitions (recruiter/reviewer see assigned, admin sees all)."""
    return await list_requisitions(db, ctx, status_filter=status)


@router.post("/requisitions", response_model=RequisitionResponse, status_code=status.HTTP_201_CREATED)
async def create_new_requisition(
    payload: RequisitionCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Create a new requisition in DRAFT status with caller as owner."""
    req = await create_requisition(db, payload, ctx)
    return req


@router.get("/requisitions/{id}", response_model=RequisitionDetailResponse)
async def get_requisition_by_id(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get requisition detail, including current JD and Rubric version metadata and counts."""
    return await get_requisition_detail(db, id, ctx)


@router.patch("/requisitions/{id}", response_model=RequisitionResponse)
async def patch_requisition(
    id: uuid.UUID,
    payload: RequisitionUpdateRequest,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Update requisition title or advance state machine with optimistic locking."""
    req = await update_requisition(db, id, payload, ctx, header_if_match=if_match)
    return req


# ---------------- Membership Endpoints ---------------- #


@router.get("/requisitions/{id}/members", response_model=list[MemberResponse])
async def get_requisition_members(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List all active members assigned to this requisition."""
    return await list_members(db, id, ctx)


@router.put("/requisitions/{id}/members/{user_id}", response_model=MemberResponse)
async def put_requisition_member(
    id: uuid.UUID,
    user_id: uuid.UUID,
    payload: MemberAddUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Assign or update a member's role (OWNER/REVIEWER) on this requisition."""
    mem = await add_or_update_member(db, id, user_id, payload, ctx)
    # Fetch user info for response DTO
    from app.db.models.org_user import User
    from sqlalchemy import select
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one()
    return MemberResponse(
        user_id=user.id,
        login_name=user.login_name,
        display_name=user.display_name,
        membership_role=mem.membership_role,
        active=mem.active,
        assigned_at=mem.assigned_at,
    )


@router.delete("/requisitions/{id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_requisition_member(
    id: uuid.UUID,
    user_id: uuid.UUID,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Remove a member from this requisition. Cannot remove the last owner."""
    expected_v = None
    if if_match:
        try:
            expected_v = int(if_match.strip('"'))
        except ValueError:
            pass
    await remove_member(db, id, user_id, ctx, expected_requisition_version=expected_v)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- JD Version Endpoints ---------------- #


@router.post("/requisitions/{id}/jd-versions", response_model=JDVersionResponse, status_code=status.HTTP_201_CREATED)
async def post_jd_version(
    id: uuid.UUID,
    payload: JDVersionCreateRequest,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Create a new immutable JDVersion. Only Requisition Owner can publish."""
    jd = await create_jd_version(db, id, payload, ctx, header_if_match=if_match)
    return jd


@router.get("/requisitions/{id}/jd-versions", response_model=list[JDVersionResponse])
async def get_requisition_jd_versions(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List all JD versions for a requisition."""
    return await list_jd_versions(db, id, ctx)


@router.get("/jd-versions/{id}", response_model=JDVersionDetailResponse)
async def get_jd_version_by_id(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get JD version detail with full normalized source text."""
    return await get_jd_version(db, id, ctx)


@router.post("/jd-versions/{id}/approve-egress", response_model=JDVersionResponse)
async def post_approve_jd_egress(
    id: uuid.UUID,
    payload: JDEgressApproveRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Owner approves JD content inspection prior to LLM submission."""
    return await approve_jd_egress(db, id, payload, ctx)
