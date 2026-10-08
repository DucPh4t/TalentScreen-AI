"""Requisition, Membership, and JD Version domain services."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any, Optional
import unicodedata
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.candidate import RawAccessGrant
from app.db.models.org_user import Organization, User
from app.db.models.requisition import JDVersion, Requisition, RequisitionMembership, RubricVersion
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole, EnvironmentMode, MembershipRole, RequisitionStatus, RubricStatus
from app.schemas.requisition import (
    JDEgressApproveRequest,
    JDVersionCreateRequest,
    MemberAddUpdateRequest,
    RequisitionCreateRequest,
    RequisitionUpdateRequest,
)
from app.services.audit import record_audit_event


def normalize_nfc_text(text: str) -> str:
    """Normalize text into canonical Unicode NFC with uniform LF newlines."""
    normalized = unicodedata.normalize("NFC", text)
    return normalized.replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_jd_source_refs(source_text: str) -> dict[str, Any]:
    """Extract requirement citations (e.g. JD-PY-01, JD-API-01) from JD source text."""
    # Pattern matching tables like: | `JD-PY-01` | `python_backend` /20 | <quote> |
    table_pattern = re.compile(
        r"\|\s*`?(JD-[A-Z]+-\d+)`?\s*\|\s*`?([a-z_]+)`?\s*/\s*(\d+)\s*\|\s*([^\|]+)\s*\|"
    )
    requirements = []
    for match in table_pattern.finditer(source_text):
        req_id = match.group(1).strip()
        criterion_id = match.group(2).strip()
        weight = int(match.group(3).strip())
        quote = match.group(4).strip()
        requirements.append(
            {
                "requirement_id": req_id,
                "criterion_id": criterion_id,
                "weight": weight,
                "quote": quote,
            }
        )

    # Secondary scan for standalone requirement ID markers if table is absent
    if not requirements:
        marker_pattern = re.compile(r"`?(JD-[A-Z]+-\d+)`?:\s*([^\n]+)")
        for match in marker_pattern.finditer(source_text):
            req_id = match.group(1).strip()
            quote = match.group(2).strip()
            requirements.append(
                {
                    "requirement_id": req_id,
                    "criterion_id": "general",
                    "weight": 0,
                    "quote": quote,
                }
            )

    return {
        "requirements": requirements,
        "extracted_count": len(requirements),
    }


async def get_or_create_default_org(db: AsyncSession) -> Organization:
    """Retrieve the primary organization or create a default sandbox organization."""
    stmt = select(Organization).order_by(Organization.created_at.asc()).limit(1)
    res = await db.execute(stmt)
    org = res.scalar_one_or_none()
    if not org:
        org = Organization(
            id=uuid.uuid4(),
            name="TalentScreen University Org",
            environment=EnvironmentMode.SANDBOX,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(org)
        await db.flush()
    return org


async def create_requisition(
    db: AsyncSession,
    payload: RequisitionCreateRequest,
    ctx: AuthenticatedContext,
) -> Requisition:
    """Create a new Requisition in DRAFT state and assign the owner membership."""
    title = payload.title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Tên yêu cầu tuyển dụng không được để trống.",
        )

    org_id = payload.organization_id
    if not org_id:
        org = await get_or_create_default_org(db)
        org_id = org.id

    is_admin = AccountRole.ADMIN in ctx.roles
    is_recruiter = AccountRole.RECRUITER in ctx.roles

    if not (is_admin or is_recruiter):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Recruiter hoặc Admin mới có quyền tạo Requisition.",
        )

    # Determine owner: recruiter defaults to self; admin can specify or self
    if is_recruiter and not is_admin:
        owner_id = ctx.user.id
    elif payload.owner_user_id:
        # Verify target owner user exists
        stmt_user = select(User).where(User.id == payload.owner_user_id, User.status == User.status.ACTIVE)
        res_user = await db.execute(stmt_user)
        target_user = res_user.scalar_one_or_none()
        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User chỉ định làm Owner không tồn tại hoặc bị vô hiệu hóa.",
            )
        owner_id = target_user.id
    else:
        owner_id = ctx.user.id

    requisition = Requisition(
        id=uuid.uuid4(),
        organization_id=org_id,
        title=title,
        status=RequisitionStatus.DRAFT,
        row_version=1,
    )
    db.add(requisition)
    await db.flush()

    # Assign owner membership
    membership = RequisitionMembership(
        requisition_id=requisition.id,
        user_id=owner_id,
        membership_role=MembershipRole.OWNER,
        active=True,
    )
    db.add(membership)
    await db.flush()

    # Audit event
    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="requisition.create",
        entity_type="requisition",
        entity_id=requisition.id,
        requisition_id=requisition.id,
        before_version=None,
        after_version=requisition.row_version,
        safe_metadata={"title": title, "owner_id": str(owner_id)},
    )

    return requisition


async def list_requisitions(
    db: AsyncSession,
    ctx: AuthenticatedContext,
    status_filter: Optional[RequisitionStatus] = None,
) -> list[dict[str, Any]]:
    """List requisitions accessible to the current user (all for admin, membership-based for others)."""
    is_admin = AccountRole.ADMIN in ctx.roles

    if is_admin:
        stmt = select(Requisition).order_by(Requisition.created_at.desc())
        if status_filter:
            stmt = stmt.where(Requisition.status == status_filter)
        res = await db.execute(stmt)
        reqs = res.scalars().all()
        # Admin gets full list
        return [
            {
                "id": req.id,
                "organization_id": req.organization_id,
                "title": req.title,
                "status": req.status,
                "current_jd_version_id": req.current_jd_version_id,
                "current_rubric_version_id": req.current_rubric_version_id,
                "opened_at": req.opened_at,
                "closed_at": req.closed_at,
                "row_version": req.row_version,
                "created_at": req.created_at,
                "updated_at": req.updated_at,
                "my_role": "admin",
            }
            for req in reqs
        ]

    # Recruiter / Reviewer query through RequisitionMembership
    stmt = (
        select(Requisition, RequisitionMembership.membership_role)
        .join(RequisitionMembership, Requisition.id == RequisitionMembership.requisition_id)
        .where(
            RequisitionMembership.user_id == ctx.user.id,
            RequisitionMembership.active.is_(True),
        )
        .order_by(Requisition.created_at.desc())
    )
    if status_filter:
        stmt = stmt.where(Requisition.status == status_filter)

    res = await db.execute(stmt)
    items = []
    for req, role in res.all():
        items.append(
            {
                "id": req.id,
                "organization_id": req.organization_id,
                "title": req.title,
                "status": req.status,
                "current_jd_version_id": req.current_jd_version_id,
                "current_rubric_version_id": req.current_rubric_version_id,
                "opened_at": req.opened_at,
                "closed_at": req.closed_at,
                "row_version": req.row_version,
                "created_at": req.created_at,
                "updated_at": req.updated_at,
                "my_role": role.value,
            }
        )
    return items


async def get_requisition_detail(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> dict[str, Any]:
    """Get requisition details, counts, and current JD / rubric summaries."""
    is_admin = AccountRole.ADMIN in ctx.roles

    # Check membership
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    res_mem = await db.execute(stmt_mem)
    membership = res_mem.scalar_one_or_none()

    if not is_admin and not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập Requisition này.",
        )

    my_role = "admin" if is_admin and not membership else (membership.membership_role.value if membership else "admin")

    stmt_req = select(Requisition).where(Requisition.id == requisition_id)
    res_req = await db.execute(stmt_req)
    req = res_req.scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisition không tồn tại.",
        )

    # Compute counts
    from app.db.models.candidate import Application
    stmt_app_count = select(func.count()).select_from(Application).where(Application.requisition_id == requisition_id)
    app_count = (await db.execute(stmt_app_count)).scalar() or 0

    stmt_jd_count = select(func.count()).select_from(JDVersion).where(JDVersion.requisition_id == requisition_id)
    jd_count = (await db.execute(stmt_jd_count)).scalar() or 0

    stmt_rubric_count = select(func.count()).select_from(RubricVersion).where(RubricVersion.requisition_id == requisition_id)
    rubric_count = (await db.execute(stmt_rubric_count)).scalar() or 0

    stmt_mem_count = select(func.count()).select_from(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.active.is_(True),
    )
    mem_count = (await db.execute(stmt_mem_count)).scalar() or 0

    current_jd = None
    if req.current_jd_version_id:
        stmt_jd = select(JDVersion).where(JDVersion.id == req.current_jd_version_id)
        jd_res = await db.execute(stmt_jd)
        jd_obj = jd_res.scalar_one_or_none()
        if jd_obj:
            current_jd = {
                "id": jd_obj.id,
                "version_no": jd_obj.version_no,
                "text_hash": jd_obj.text_hash,
                "egress_reviewed": jd_obj.egress_reviewed_at is not None,
                "created_at": jd_obj.created_at,
            }

    current_rubric = None
    if req.current_rubric_version_id:
        stmt_rb = select(RubricVersion).where(RubricVersion.id == req.current_rubric_version_id)
        rb_res = await db.execute(stmt_rb)
        rb_obj = rb_res.scalar_one_or_none()
        if rb_obj:
            current_rubric = {
                "id": rb_obj.id,
                "version_no": rb_obj.version_no,
                "status": rb_obj.status.value,
                "content_hash": rb_obj.content_hash,
                "approved_at": rb_obj.approved_at,
            }

    return {
        "id": req.id,
        "organization_id": req.organization_id,
        "title": req.title,
        "status": req.status,
        "current_jd_version_id": req.current_jd_version_id,
        "current_rubric_version_id": req.current_rubric_version_id,
        "opened_at": req.opened_at,
        "closed_at": req.closed_at,
        "row_version": req.row_version,
        "created_at": req.created_at,
        "updated_at": req.updated_at,
        "my_role": my_role,
        "counts": {
            "applications_count": app_count,
            "jd_versions_count": jd_count,
            "rubric_versions_count": rubric_count,
            "members_count": mem_count,
        },
        "current_jd": current_jd,
        "current_rubric": current_rubric,
    }


async def update_requisition(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    payload: RequisitionUpdateRequest,
    ctx: AuthenticatedContext,
    header_if_match: Optional[str] = None,
) -> Requisition:
    """Update requisition title or status transition with optimistic locking."""
    # Guard: Actor must be OWNER or Admin
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    res_mem = await db.execute(stmt_mem)
    mem = res_mem.scalar_one_or_none()

    is_admin = AccountRole.ADMIN in ctx.roles
    is_owner = mem is not None and mem.membership_role == MembershipRole.OWNER

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner của Requisition (hoặc Admin) mới có quyền chỉnh sửa.",
        )

    stmt_req = select(Requisition).where(Requisition.id == requisition_id).with_for_update()
    res_req = await db.execute(stmt_req)
    req = res_req.scalar_one_or_none()
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Requisition không tồn tại.",
        )

    # Optimistic locking check
    expected_v = payload.expected_version
    if expected_v is None and header_if_match:
        try:
            expected_v = int(header_if_match.strip('"'))
        except ValueError:
            pass

    if expected_v is not None and req.row_version != expected_v:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VERSION_CONFLICT: Requisition phiên bản hiện tại là {req.row_version}, khác phiên bản dự kiến {expected_v}.",
        )

    before_v = req.row_version
    changes = {}

    # Title update
    if payload.title is not None:
        new_title = payload.title.strip()
        if len(new_title) < 3:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Tên Requisition phải có ít nhất 3 ký tự.",
            )
        changes["title"] = new_title
        req.title = new_title

    # Status transitions (Section 5.1 of spec)
    if payload.status is not None and payload.status != req.status:
        old_status = req.status
        new_status = payload.status
        now = datetime.now(timezone.utc)

        if old_status == RequisitionStatus.DRAFT and new_status == RequisitionStatus.OPEN:
            # Must have approved current rubric + JD
            if not req.current_jd_version_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="VALIDATION_ERROR: Không thể mở Requisition khi chưa có JD version.",
                )
            if not req.current_rubric_version_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="VALIDATION_ERROR: Không thể mở Requisition khi chưa có Rubric version.",
                )
            # Verify rubric is approved and matches current JD
            stmt_rubric = select(RubricVersion).where(RubricVersion.id == req.current_rubric_version_id)
            res_rubric = await db.execute(stmt_rubric)
            rubric = res_rubric.scalar_one_or_none()
            if not rubric or rubric.status != RubricStatus.APPROVED:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="RUBRIC_INVALID: Rubric hiện hành chưa được phê duyệt.",
                )
            if rubric.jd_version_id != req.current_jd_version_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="JD_RUBRIC_MISMATCH: Rubric hiện hành không thuộc về phiên bản JD hiện tại.",
                )
            req.opened_at = now

        elif old_status == RequisitionStatus.OPEN and new_status == RequisitionStatus.PAUSED:
            if not payload.reason or not payload.reason.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="VALIDATION_ERROR: Bắt buộc cung cấp lý do (reason) khi tạm dừng Requisition.",
                )

        elif old_status == RequisitionStatus.PAUSED and new_status == RequisitionStatus.OPEN:
            # Check rubric still valid
            if not req.current_rubric_version_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="RUBRIC_INVALID: Không thể mở lại khi thiếu rubric.",
                )

        elif old_status in (RequisitionStatus.OPEN, RequisitionStatus.PAUSED) and new_status == RequisitionStatus.CLOSED:
            if not payload.reason or not payload.reason.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="VALIDATION_ERROR: Bắt buộc cung cấp lý do (reason) khi đóng Requisition.",
                )
            req.closed_at = now

        elif old_status == RequisitionStatus.CLOSED and new_status == RequisitionStatus.PAUSED:
            if not payload.reason or not payload.reason.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="VALIDATION_ERROR: Bắt buộc cung cấp lý do mở lại khi chuyển từ CLOSED sang PAUSED.",
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Trạng thái chuyển đổi không hợp lệ từ {old_status.value} sang {new_status.value}.",
            )

        req.status = new_status
        changes["status_from"] = old_status.value
        changes["status_to"] = new_status.value
        changes["reason"] = payload.reason

    req.row_version += 1
    req.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Audit event
    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="requisition.update",
        entity_type="requisition",
        entity_id=req.id,
        requisition_id=req.id,
        before_version=before_v,
        after_version=req.row_version,
        safe_metadata=changes,
    )

    return req


async def list_members(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[dict[str, Any]]:
    """List members of a requisition with user display details."""
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    res_mem = await db.execute(stmt_mem)
    if not is_admin and not res_mem.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền xem thành viên Requisition này.",
        )

    stmt = (
        select(RequisitionMembership, User)
        .join(User, RequisitionMembership.user_id == User.id)
        .where(
            RequisitionMembership.requisition_id == requisition_id,
            RequisitionMembership.active.is_(True),
        )
        .order_by(RequisitionMembership.assigned_at.asc())
    )
    res = await db.execute(stmt)
    results = []
    for mem, user in res.all():
        results.append(
            {
                "user_id": user.id,
                "login_name": user.login_name,
                "display_name": user.display_name,
                "membership_role": mem.membership_role,
                "active": mem.active,
                "assigned_at": mem.assigned_at,
            }
        )
    return results


async def add_or_update_member(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: MemberAddUpdateRequest,
    ctx: AuthenticatedContext,
) -> RequisitionMembership:
    """Add or update member role on a requisition. Only Owner or Admin can execute."""
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_my_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    my_mem = (await db.execute(stmt_my_mem)).scalar_one_or_none()
    is_owner = my_mem is not None and my_mem.membership_role == MembershipRole.OWNER

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner của Requisition hoặc Admin mới có quyền quản lý thành viên.",
        )

    # Check requisition
    stmt_req = select(Requisition).where(Requisition.id == requisition_id).with_for_update()
    req = (await db.execute(stmt_req)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition không tồn tại.")

    if payload.expected_requisition_version is not None and req.row_version != payload.expected_requisition_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="VERSION_CONFLICT: Requisition đã bị thay đổi trước đó.",
        )

    # Verify target user
    stmt_target = select(User).where(User.id == target_user_id)
    target_user = (await db.execute(stmt_target)).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User được gán không tồn tại.")

    # Check existing membership
    stmt_existing = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == target_user_id,
    )
    existing = (await db.execute(stmt_existing)).scalar_one_or_none()

    if existing:
        existing.membership_role = payload.membership_role
        existing.active = True
        existing.assigned_at = datetime.now(timezone.utc)
        mem = existing
    else:
        mem = RequisitionMembership(
            requisition_id=requisition_id,
            user_id=target_user_id,
            membership_role=payload.membership_role,
            active=True,
            assigned_at=datetime.now(timezone.utc),
        )
        db.add(mem)

    req.row_version += 1
    req.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="membership.upsert",
        entity_type="requisition_membership",
        entity_id=target_user_id,
        requisition_id=requisition_id,
        after_version=req.row_version,
        safe_metadata={"target_user_id": str(target_user_id), "role": payload.membership_role.value},
    )

    return mem


async def remove_member(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    target_user_id: uuid.UUID,
    ctx: AuthenticatedContext,
    expected_requisition_version: Optional[int] = None,
) -> None:
    """Remove a member from a requisition. Invariant: Cannot remove the last owner."""
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_my_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    my_mem = (await db.execute(stmt_my_mem)).scalar_one_or_none()
    is_owner = my_mem is not None and my_mem.membership_role == MembershipRole.OWNER

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner hoặc Admin mới có quyền xóa thành viên.",
        )

    stmt_req = select(Requisition).where(Requisition.id == requisition_id).with_for_update()
    req = (await db.execute(stmt_req)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition không tồn tại.")

    if expected_requisition_version is not None and req.row_version != expected_requisition_version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="VERSION_CONFLICT")

    stmt_target = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == target_user_id,
        RequisitionMembership.active.is_(True),
    )
    target_mem = (await db.execute(stmt_target)).scalar_one_or_none()
    if not target_mem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thành viên không tồn tại trong Requisition.")

    # Guard: Cannot remove last owner
    if target_mem.membership_role == MembershipRole.OWNER:
        stmt_owner_count = select(func.count()).select_from(RequisitionMembership).where(
            RequisitionMembership.requisition_id == requisition_id,
            RequisitionMembership.membership_role == MembershipRole.OWNER,
            RequisitionMembership.active.is_(True),
        )
        owner_count = (await db.execute(stmt_owner_count)).scalar() or 0
        if owner_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CANNOT_REMOVE_LAST_OWNER: Không thể xóa Owner duy nhất của Requisition.",
            )

    # Deactivate membership
    target_mem.active = False

    # Revoke raw access grants for this user in applications under this requisition
    from app.db.models.candidate import Application
    subq = select(Application.id).where(Application.requisition_id == requisition_id)
    await db.execute(
        update(RawAccessGrant)
        .where(
            RawAccessGrant.application_id.in_(subq),
            RawAccessGrant.grantee_user_id == target_user_id,
            RawAccessGrant.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )

    req.row_version += 1
    req.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="membership.remove",
        entity_type="requisition_membership",
        entity_id=target_user_id,
        requisition_id=requisition_id,
        after_version=req.row_version,
        safe_metadata={"target_user_id": str(target_user_id)},
    )


# ---------------- JD Version Domain Logic ---------------- #


async def create_jd_version(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    payload: JDVersionCreateRequest,
    ctx: AuthenticatedContext,
    header_if_match: Optional[str] = None,
) -> JDVersion:
    """Create a new immutable JDVersion for a requisition. Only Owner can create."""
    # Guard: Actor must be OWNER of the requisition
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    is_admin = AccountRole.ADMIN in ctx.roles
    is_owner = mem is not None and mem.membership_role == MembershipRole.OWNER

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner của Requisition mới có quyền tải lên phiên bản JD mới.",
        )

    stmt_req = select(Requisition).where(Requisition.id == requisition_id).with_for_update()
    req = (await db.execute(stmt_req)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition không tồn tại.")

    # Optimistic locking check
    expected_v = payload.expected_requisition_version
    if expected_v is None and header_if_match:
        try:
            expected_v = int(header_if_match.strip('"'))
        except ValueError:
            pass

    if expected_v is not None and req.row_version != expected_v:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VERSION_CONFLICT: Requisition đã được chỉnh sửa (current: {req.row_version}, expected: {expected_v}).",
        )

    # Validate and normalize source text
    normalized_text = normalize_nfc_text(payload.source_text)
    if len(normalized_text) < 50:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Nội dung JD quá ngắn (yêu cầu ít nhất 50 ký tự có nghĩa).",
        )

    text_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    source_refs = extract_jd_source_refs(normalized_text)

    # Determine next version_no
    stmt_max_v = select(func.max(JDVersion.version_no)).where(JDVersion.requisition_id == requisition_id)
    max_v = (await db.execute(stmt_max_v)).scalar() or 0
    next_version = max_v + 1

    jd_version = JDVersion(
        id=uuid.uuid4(),
        requisition_id=requisition_id,
        version_no=next_version,
        source_text=normalized_text,
        text_hash=text_hash,
        source_refs=source_refs,
        created_by=ctx.user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(jd_version)
    await db.flush()

    # Update requisition current JD pointer
    from app.db.models.candidate import Application
    from app.services.email_draft import invalidate_email_drafts
    affected_ids = list((await db.execute(select(Application.id).where(Application.requisition_id == req.id))).scalars())
    await invalidate_email_drafts(db, affected_ids)
    req.current_jd_version_id = jd_version.id
    req.row_version += 1
    req.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Audit log
    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="jd_version.create",
        entity_type="jd_version",
        entity_id=jd_version.id,
        requisition_id=requisition_id,
        after_version=req.row_version,
        safe_metadata={
            "version_no": next_version,
            "text_hash": text_hash,
            "change_reason": payload.change_reason,
            "extracted_requirements": source_refs.get("extracted_count", 0),
        },
    )

    return jd_version


async def list_jd_versions(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[JDVersion]:
    """List all JD versions for a requisition ordered by version_no DESC."""
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập.")

    stmt = (
        select(JDVersion)
        .where(JDVersion.requisition_id == requisition_id)
        .order_by(JDVersion.version_no.desc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_jd_version(
    db: AsyncSession,
    jd_version_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> JDVersion:
    """Get detail of a specific JD version."""
    stmt = select(JDVersion).where(JDVersion.id == jd_version_id)
    res = await db.execute(stmt)
    jd = res.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JD Version không tồn tại.")

    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == jd.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập JD Version này.")

    return jd


async def approve_jd_egress(
    db: AsyncSession,
    jd_version_id: uuid.UUID,
    payload: JDEgressApproveRequest,
    ctx: AuthenticatedContext,
) -> JDVersion:
    """Approve JD version for LLM egress after HR inspection of contents."""
    stmt = select(JDVersion).where(JDVersion.id == jd_version_id).with_for_update()
    res = await db.execute(stmt)
    jd = res.scalar_one_or_none()
    if not jd:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="JD Version không tồn tại.")

    # Guard: Actor must be OWNER of the requisition
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == jd.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    is_admin = AccountRole.ADMIN in ctx.roles
    is_owner = mem is not None and mem.membership_role == MembershipRole.OWNER

    if not (is_admin or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner mới có quyền phê duyệt kiểm duyệt nội dung JD (approve-egress).",
        )

    if not payload.acknowledged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bắt buộc xác nhận (acknowledged=True) đã kiểm tra nội dung JD trước khi gửi LLM.",
        )

    if payload.expected_text_hash != jd.text_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="TEXT_HASH_MISMATCH: Mã hash của nội dung JD không khớp với phiên bản dự kiến phê duyệt.",
        )

    now = datetime.now(timezone.utc)
    jd.egress_reviewed_by = ctx.user.id
    jd.egress_reviewed_at = now
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="jd_version.approve_egress",
        entity_type="jd_version",
        entity_id=jd.id,
        requisition_id=jd.requisition_id,
        safe_metadata={"text_hash": jd.text_hash, "version_no": jd.version_no},
    )

    return jd
