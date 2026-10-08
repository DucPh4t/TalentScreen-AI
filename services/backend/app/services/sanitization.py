"""Sanitization, HR Approval, Raw Access Grants, and Secure Preview service implementation."""
from __future__ import annotations

from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
import hashlib
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import utc_now
from app.db.models.candidate import Application, Candidate, RawAccessGrant
from app.db.models.document import Document, SanitizedVersion, SourceSpan
from app.db.models.requisition import RequisitionMembership
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole, MembershipRole, SanitizedVersionStatus
from app.schemas.sanitization import (
    RawGrantCreateRequest,
    RawGrantResponse,
    SanitizedApproveRequest,
    SanitizedEditRequest,
    SanitizedRevokeRequest,
    SanitizedVersionDetailResponse,
    SanitizedVersionSummaryResponse,
)
from app.services.audit import record_audit_event
from app.services.sanitizer import (
    build_source_spans_from_canonical,
    normalize_text_nfc_lf,
    residual_contact_types,
)
from app.services.storage import read_private_blob
from app.services.source_lock import lock_source_application


async def _verify_membership_and_grant(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    application_id: uuid.UUID,
    ctx: AuthenticatedContext,
    require_owner: bool = False,
    require_raw_grant: bool = False,
) -> tuple[RequisitionMembership, Optional[RawAccessGrant]]:
    """Helper to check requisition membership, owner role, and raw_cv grant.
    Security Invariant:
      - Admin without membership or raw grant cannot bypass.
      - Resource in other requisition returns 404.
      - Missing grant returns 403 with RAW_GRANT_REQUIRED.
    """
    is_admin = AccountRole.ADMIN in ctx.roles

    stmt_app = select(Application.status).where(Application.id == application_id)
    app_status = (await db.execute(stmt_app)).scalar_one_or_none()
    if not app_status or app_status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài nguyên.")

    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    membership = (await db.execute(stmt_mem)).scalar_one_or_none()

    if not membership and not is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tài nguyên.")

    if require_owner:
        if not membership or membership.membership_role != MembershipRole.OWNER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Thao tác này yêu cầu quyền Owner của Requisition.",
            )

    grant: Optional[RawAccessGrant] = None
    now = datetime.now(timezone.utc)
    stmt_grant = select(RawAccessGrant).where(
        RawAccessGrant.application_id == application_id,
        RawAccessGrant.grantee_user_id == ctx.user.id,
        RawAccessGrant.expires_at > now,
        RawAccessGrant.revoked_at.is_(None),
    )
    grants = (await db.execute(stmt_grant)).scalars().all()
    for g in grants:
        if "raw_cv" in g.scopes:
            grant = g
            break

    if require_raw_grant and not grant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RAW_GRANT_REQUIRED: Thao tác yêu cầu quyền truy cập Raw CV (raw_cv grant). Vui lòng yêu cầu Owner cấp quyền.",
        )

    return membership, grant


# ---------------- Raw Access Grants ---------------- #


async def create_raw_access_grant(
    db: AsyncSession,
    application_id: uuid.UUID,
    payload: RawGrantCreateRequest,
    ctx: AuthenticatedContext,
) -> RawGrantResponse:
    """Issue a scoped raw access grant to an active requisition member."""
    stmt_app = select(Application).where(Application.id == application_id)
    app_obj = (await db.execute(stmt_app)).scalar_one_or_none()
    if not app_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hồ sơ ứng viên không tồn tại.")

    await _verify_membership_and_grant(
        db=db,
        requisition_id=app_obj.requisition_id,
        application_id=application_id,
        ctx=ctx,
        require_owner=True,
    )

    # Verify grantee is an active member of the requisition
    stmt_grantee = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == app_obj.requisition_id,
        RequisitionMembership.user_id == payload.grantee_user_id,
        RequisitionMembership.active.is_(True),
    )
    grantee_mem = (await db.execute(stmt_grantee)).scalar_one_or_none()
    if not grantee_mem:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Người được cấp quyền phải là thành viên đang hoạt động của đợt tuyển dụng.",
        )

    now = datetime.now(timezone.utc)
    if payload.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Thời hạn cấp quyền (expires_at) phải nằm trong tương lai.",
        )

    grant = RawAccessGrant(
        id=uuid.uuid4(),
        application_id=application_id,
        grantee_user_id=payload.grantee_user_id,
        scopes=payload.scopes,
        granted_by=ctx.user.id,
        reason=payload.reason,
        expires_at=payload.expires_at,
        created_at=now,
    )
    db.add(grant)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="grant.issued",
        entity_type="raw_access_grant",
        entity_id=grant.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "grantee_user_id": str(payload.grantee_user_id),
            "scopes": payload.scopes,
            "expires_at": payload.expires_at.isoformat(),
        },
    )

    return RawGrantResponse.model_validate(grant)


async def revoke_raw_access_grant(
    db: AsyncSession,
    application_id: uuid.UUID,
    grant_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> None:
    """Revoke an active raw access grant immediately."""
    stmt_app = select(Application).where(Application.id == application_id)
    app_obj = (await db.execute(stmt_app)).scalar_one_or_none()
    if not app_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hồ sơ ứng viên không tồn tại.")

    await _verify_membership_and_grant(
        db=db,
        requisition_id=app_obj.requisition_id,
        application_id=application_id,
        ctx=ctx,
        require_owner=True,
    )

    stmt_grant = select(RawAccessGrant).where(
        RawAccessGrant.id == grant_id,
        RawAccessGrant.application_id == application_id,
    )
    grant = (await db.execute(stmt_grant)).scalar_one_or_none()
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quyền truy cập không tồn tại.")

    if grant.revoked_at is None:
        now = datetime.now(timezone.utc)
        grant.revoked_at = now
        await db.flush()

        await record_audit_event(
            db,
            actor_id=ctx.user.id,
            action="grant.revoked",
            entity_type="raw_access_grant",
            entity_id=grant.id,
            requisition_id=app_obj.requisition_id,
            safe_metadata={"grantee_user_id": str(grant.grantee_user_id)},
        )


# ---------------- Sanitized Versions Lifecycle ---------------- #


async def list_sanitized_versions(
    db: AsyncSession,
    document_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[SanitizedVersionSummaryResponse]:
    """List sanitized versions for a document.
    Access Control:
      - Members with active raw_cv grant see all versions (DRAFT, APPROVED, SUPERSEDED, REVOKED).
      - Members without raw_cv grant can ONLY see APPROVED or SUPERSEDED (non-revoked) versions.
    """
    stmt_doc = (
        select(Document)
        .options(selectinload(Document.application))
        .where(Document.id == document_id)
    )
    doc = (await db.execute(stmt_doc)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài liệu không tồn tại.")

    _, grant = await _verify_membership_and_grant(
        db=db,
        requisition_id=doc.application.requisition_id,
        application_id=doc.application_id,
        ctx=ctx,
    )

    stmt_v = (
        select(SanitizedVersion)
        .where(SanitizedVersion.document_id == document_id)
        .order_by(SanitizedVersion.version_no.desc())
    )
    all_versions = (await db.execute(stmt_v)).scalars().all()

    has_raw_grant = grant is not None
    results = []
    for v in all_versions:
        if has_raw_grant:
            results.append(SanitizedVersionSummaryResponse.model_validate(v))
        elif v.status in {SanitizedVersionStatus.APPROVED, SanitizedVersionStatus.SUPERSEDED}:
            results.append(SanitizedVersionSummaryResponse.model_validate(v))

    return results


async def get_sanitized_version_detail(
    db: AsyncSession,
    version_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> SanitizedVersionDetailResponse:
    """Retrieve detailed sanitized version with canonical text and quality flags.
    Access Control:
      - APPROVED is visible to all requisition members.
      - DRAFT or REVOKED strictly requires an active raw_cv grant!
    """
    stmt_v = (
        select(SanitizedVersion)
        .options(selectinload(SanitizedVersion.application))
        .where(SanitizedVersion.id == version_id)
    )
    v = (await db.execute(stmt_v)).scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phiên bản sanitized không tồn tại.")

    _, grant = await _verify_membership_and_grant(
        db=db,
        requisition_id=v.application.requisition_id,
        application_id=v.application_id,
        ctx=ctx,
    )

    if v.status in {SanitizedVersionStatus.DRAFT, SanitizedVersionStatus.REVOKED}:
        if not grant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="RAW_GRANT_REQUIRED: Phiên bản này ở trạng thái nhạy cảm (Draft hoặc Revoked). Yêu cầu quyền Raw Grant để xem.",
            )

    return SanitizedVersionDetailResponse.model_validate(v)


async def edit_sanitized_version(
    db: AsyncSession,
    document_id: uuid.UUID,
    payload: SanitizedEditRequest,
    ctx: AuthenticatedContext,
) -> SanitizedVersionDetailResponse:
    """Create a new sanitized draft version from manual edits.
    Invariant:
      - Requires active raw_cv grant.
      - Old approved/draft text is immutable; creates a brand new version.
      - Increments application generation, clears any existing approval.
    """
    await lock_source_application(db, Document, document_id)
    stmt_doc = (
        select(Document)
        .options(selectinload(Document.application))
        .where(Document.id == document_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    doc = (await db.execute(stmt_doc)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài liệu không tồn tại.")
    await _verify_membership_and_grant(
        db=db,
        requisition_id=doc.application.requisition_id,
        application_id=doc.application_id,
        ctx=ctx,
        require_raw_grant=True,
    )
    if doc.application.current_document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="DOCUMENT_STALE: Chỉ được sửa CV hiện hành.")

    base_version = (await db.execute(select(SanitizedVersion).where(
        SanitizedVersion.id == payload.base_version_id,
        SanitizedVersion.document_id == doc.id,
    ))).scalar_one_or_none()
    if not base_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bản đã che nguồn không thuộc CV hiện hành.")

    # Normalize canonical text
    canonical_text = normalize_text_nfc_lf(payload.canonical_text)
    sha256_hash = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

    # Determine next version number
    stmt_max = select(func.max(SanitizedVersion.version_no)).where(
        SanitizedVersion.document_id == document_id
    )
    max_v = (await db.execute(stmt_max)).scalar() or 0
    next_v = max_v + 1

    new_version = SanitizedVersion(
        id=uuid.uuid4(),
        application_id=doc.application_id,
        document_id=doc.id,
        version_no=next_v,
        status=SanitizedVersionStatus.DRAFT,
        canonical_text=canonical_text,
        sha256=sha256_hash,
        normalizer_version="1.0",
        sanitizer_version="1.0",
        renderer_version="1.0",
        quality_flags={
            "edit_reason": payload.edit_reason,
            "base_version_id": str(payload.base_version_id),
            "edited_by": str(ctx.user.id),
        },
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_version)
    await db.flush()

    # Generate exact source spans
    spans = build_source_spans_from_canonical(new_version.id, canonical_text)
    db.add_all(spans)

    # Invalidate current approval and increment application generation
    app_obj = doc.application
    from app.services.email_draft import invalidate_email_drafts
    await invalidate_email_drafts(db, [app_obj.id])
    app_obj.current_sanitized_version_id = new_version.id
    app_obj.generation += 1
    app_obj.row_version += 1
    app_obj.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="sanitized.edited",
        entity_type="sanitized_version",
        entity_id=new_version.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "version_no": next_v,
            "edit_reason": payload.edit_reason,
            "base_version_id": str(payload.base_version_id),
            "total_spans": len(spans),
        },
    )

    return SanitizedVersionDetailResponse.model_validate(new_version)


async def approve_sanitized_version(
    db: AsyncSession,
    version_id: uuid.UUID,
    payload: SanitizedApproveRequest,
    ctx: AuthenticatedContext,
) -> SanitizedVersionDetailResponse:
    """Approve a sanitized version for external evaluation.
    Invariant:
      - Requires Owner role + active raw_cv grant.
      - Hash and application version must match exactly (prevent race / mismatch).
      - Supersedes any existing approved version.
    """
    await lock_source_application(db, SanitizedVersion, version_id)
    stmt_v = (
        select(SanitizedVersion)
        .options(selectinload(SanitizedVersion.application), selectinload(SanitizedVersion.document))
        .where(SanitizedVersion.id == version_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    v = (await db.execute(stmt_v)).scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phiên bản sanitized không tồn tại.")

    await _verify_membership_and_grant(
        db=db,
        requisition_id=v.application.requisition_id,
        application_id=v.application_id,
        ctx=ctx,
        require_owner=True,
        require_raw_grant=True,
    )

    app_obj = v.application
    if v.document_id != app_obj.current_document_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="DOCUMENT_STALE: Chỉ được duyệt CV hiện hành.")
    if v.status != SanitizedVersionStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Chỉ được duyệt bản đã che ở trạng thái nháp.")
    if not payload.acknowledged:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Cần xác nhận đã kiểm tra bản CV sau khi che thông tin.")

    # Invariant: Must match expected application row version
    if app_obj.row_version != payload.expected_application_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VERSION_CONFLICT: Hồ sơ ứng viên đã thay đổi (hiện tại v{app_obj.row_version}, kỳ vọng v{payload.expected_application_version}). Vui lòng tải lại và duyệt lại.",
        )

    # Invariant: Must match expected content sha256
    if v.sha256 != payload.expected_sha256:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="HASH_MISMATCH: SHA256 nội dung đã duyệt không khớp với nội dung lưu trữ.",
        )

    if residual_contact_types(v.canonical_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="RESIDUAL_CONTACT_DATA: Bản CV đã che vẫn chứa thông tin liên hệ; cần sửa trước khi duyệt.",
        )

    quality_flags = v.quality_flags or {}
    if quality_flags.get("document_type_hint") != "cv" and not payload.confirmed_document_is_cv:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="DOCUMENT_TYPE_CONFIRMATION_REQUIRED: Hệ thống chưa xác nhận chắc chắn đây là CV ứng viên; cần đối chiếu tài liệu gốc và xác nhận trước khi cho phép AI xử lý.",
        )

    now = datetime.now(timezone.utc)

    # Supersede existing approved versions for this document
    stmt_supersede = (
        update(SanitizedVersion)
        .where(
            SanitizedVersion.document_id == v.document_id,
            SanitizedVersion.status == SanitizedVersionStatus.APPROVED,
        )
        .values(status=SanitizedVersionStatus.SUPERSEDED)
    )
    await db.execute(stmt_supersede)

    # Mark current version approved
    v.status = SanitizedVersionStatus.APPROVED
    v.approved_by = ctx.user.id
    v.approved_at = now

    app_obj.current_sanitized_version_id = v.id
    app_obj.row_version += 1
    app_obj.updated_at = now
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="sanitized.approved",
        entity_type="sanitized_version",
        entity_id=v.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "version_no": v.version_no,
            "sha256": v.sha256,
            "approved_at": now.isoformat(),
            "document_type_confirmed_as_cv": payload.confirmed_document_is_cv,
        },
    )

    # Auto-Assessment Trigger: When CV sanitization is approved, automatically queue assessment
    # if requisition has an approved rubric and is not closed.
    if app_obj.requisition_id:
        try:
            from app.db.models.requisition import Requisition, RubricVersion
            from app.domain.enums import RequisitionStatus, RubricStatus
            from app.schemas.assessment import AssessmentRunCreateRequest
            from app.services.assessment.service import enqueue_assessment_if_needed

            req = await db.get(Requisition, app_obj.requisition_id)
            if req and req.status != RequisitionStatus.CLOSED and req.current_rubric_version_id:
                rubric = await db.get(RubricVersion, req.current_rubric_version_id)
                if rubric and rubric.status == RubricStatus.APPROVED:
                    await enqueue_assessment_if_needed(
                        db=db,
                        application_id=app_obj.id,
                        payload=AssessmentRunCreateRequest(
                            sanitized_version_id=v.id,
                            rubric_version_id=rubric.id,
                        ),
                        ctx=ctx,
                    )
                    logger.info("Auto-triggered assessment run for application %s upon sanitization approval", app_obj.id)
        except Exception as exc:
            logger.warning("Auto-assessment trigger omitted or failed for application %s: %s", app_obj.id, exc)

    return SanitizedVersionDetailResponse.model_validate(v)


async def revoke_sanitized_version(
    db: AsyncSession,
    version_id: uuid.UUID,
    payload: SanitizedRevokeRequest,
    ctx: AuthenticatedContext,
) -> SanitizedVersionDetailResponse:
    """Revoke an approved sanitized version (e.g. if leak/forbidden criterion discovered).
    Invariant:
      - Halts egress immediately.
      - Quarantines derived data.
      - Requires Owner role + active raw_cv grant.
    """
    await lock_source_application(db, SanitizedVersion, version_id)
    stmt_v = (
        select(SanitizedVersion)
        .options(selectinload(SanitizedVersion.application))
        .where(SanitizedVersion.id == version_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    v = (await db.execute(stmt_v)).scalar_one_or_none()
    if not v:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Phiên bản sanitized không tồn tại.")

    await _verify_membership_and_grant(
        db=db,
        requisition_id=v.application.requisition_id,
        application_id=v.application_id,
        ctx=ctx,
        require_owner=True,
        require_raw_grant=True,
    )

    app_obj = v.application
    await db.refresh(app_obj)
    if app_obj.row_version != payload.expected_application_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="VERSION_CONFLICT: Hồ sơ ứng viên đã thay đổi.",
        )

    now = datetime.now(timezone.utc)
    v.status = SanitizedVersionStatus.REVOKED

    # If this was the current active sanitized version, clear it
    if app_obj.current_sanitized_version_id == v.id:
        from app.services.email_draft import invalidate_email_drafts
        await invalidate_email_drafts(db, [app_obj.id])
        app_obj.current_sanitized_version_id = None
        app_obj.current_assessment_run_id = None

    app_obj.generation += 1
    app_obj.row_version += 1
    app_obj.updated_at = now
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="sanitized.revoked",
        entity_type="sanitized_version",
        entity_id=v.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "reason": payload.reason,
            "version_no": v.version_no,
        },
    )

    return SanitizedVersionDetailResponse.model_validate(v)


async def get_document_raw_preview(
    db: AsyncSession,
    document_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> tuple[bytes, str]:
    """Retrieve raw document bytes for secure side-by-side comparison.
    Invariant: Caller MUST hold active raw_cv grant!
    """
    stmt_doc = (
        select(Document)
        .options(selectinload(Document.application))
        .where(Document.id == document_id)
    )
    doc = (await db.execute(stmt_doc)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài liệu không tồn tại.")

    await _verify_membership_and_grant(
        db=db,
        requisition_id=doc.application.requisition_id,
        application_id=doc.application_id,
        ctx=ctx,
        require_raw_grant=True,
    )

    raw_bytes = read_private_blob(doc.blob_key)

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="document.raw_viewed",
        entity_type="document",
        entity_id=doc.id,
        requisition_id=doc.application.requisition_id,
        safe_metadata={"byte_size": len(raw_bytes)},
    )

    return raw_bytes, doc.mime_verified
