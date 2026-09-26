"""Application Intake and Document Upload domain service."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.candidate import Application, Candidate, CandidateIdentity, RawAccessGrant
from app.db.models.document import Document
from app.db.models.ops import Job
from app.db.models.requisition import Requisition, RequisitionMembership
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole, DocumentSafetyStatus, JobStatus, JobType, MembershipRole, RequisitionStatus
from app.schemas.intake import (
    ApplicationCreateRequest,
    ApplicationDetailResponse,
    ApplicationResponse,
    DocumentSummaryDTO,
    DocumentUploadedDTO,
    DocumentUploadResponse,
)
from app.services.audit import record_audit_event
from app.services.idempotency import complete_idempotency, get_or_start_idempotency
from app.services.parser import docx_renderer_available
from app.services.storage import (
    detect_and_validate_file_type,
    sanitize_filename,
    save_private_blob,
)


async def check_requisition_access(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> tuple[Requisition, Optional[MembershipRole]]:
    """Verify requisition exists and caller has access (Admin or active Member)."""
    stmt_req = select(Requisition).where(Requisition.id == requisition_id)
    req = (await db.execute(stmt_req)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requisition không tồn tại.")

    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()

    if not is_admin and not mem:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn không có quyền truy cập hồ sơ của Requisition này.",
        )
    return req, mem.membership_role if mem else None


async def create_application(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    payload: ApplicationCreateRequest,
    ctx: AuthenticatedContext,
) -> ApplicationResponse:
    """Create a new application for a candidate under a requisition."""
    req, _ = await check_requisition_access(db, requisition_id, ctx)

    if req.status == RequisitionStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="REQUISITION_CLOSED: Không thể tiếp nhận đơn ứng tuyển cho Requisition đã đóng.",
        )

    # Resolve or create candidate
    candidate_id = payload.candidate_id
    candidate = None

    if candidate_id:
        stmt_cand = select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.organization_id == req.organization_id,
        )
        candidate = (await db.execute(stmt_cand)).scalar_one_or_none()
        if not candidate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ứng viên không tồn tại trong tổ chức.")
    else:
        # Create candidate with pseudonymized public label (e.g. CAND-8F3A2B)
        random_label = f"CAND-{uuid.uuid4().hex[:6].upper()}"
        candidate = Candidate(
            id=uuid.uuid4(),
            organization_id=req.organization_id,
            public_label=random_label,
            status="active",
        )
        db.add(candidate)
        await db.flush()

    # Enforce unique (requisition_id, candidate_id)
    stmt_existing = select(Application).where(
        Application.requisition_id == requisition_id,
        Application.candidate_id == candidate.id,
    )
    if (await db.execute(stmt_existing)).scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="APPLICATION_ALREADY_EXISTS: Ứng viên này đã có đơn ứng tuyển cho vị trí này.",
        )

    app_obj = Application(
        id=uuid.uuid4(),
        requisition_id=requisition_id,
        candidate_id=candidate.id,
        status="active",
        generation=1,
        row_version=1,
        received_at=datetime.now(timezone.utc),
    )
    db.add(app_obj)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="application.create",
        entity_type="application",
        entity_id=app_obj.id,
        requisition_id=requisition_id,
        safe_metadata={"candidate_id": str(candidate.id), "public_label": candidate.public_label},
    )

    return ApplicationResponse(
        id=app_obj.id,
        requisition_id=app_obj.requisition_id,
        candidate_id=app_obj.candidate_id,
        public_label=candidate.public_label,
        status=app_obj.status,
        generation=app_obj.generation,
        row_version=app_obj.row_version,
        current_document_id=app_obj.current_document_id,
        current_sanitized_version_id=app_obj.current_sanitized_version_id,
        current_assessment_run_id=app_obj.current_assessment_run_id,
        current_decision_id=app_obj.current_decision_id,
        received_at=app_obj.received_at,
    )


async def list_applications(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[ApplicationResponse]:
    """List applications under a requisition.
    Invariant: Pseudonymized public labels only; NO real candidate names or raw filenames.
    """
    await check_requisition_access(db, requisition_id, ctx)

    stmt = (
        select(Application, Candidate.public_label)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(Application.requisition_id == requisition_id, Application.status != "deleted")
        .order_by(Application.received_at.asc(), Application.id.asc())
    )
    res = await db.execute(stmt)

    items = []
    for app_obj, label in res.all():
        items.append(
            ApplicationResponse(
                id=app_obj.id,
                requisition_id=app_obj.requisition_id,
                candidate_id=app_obj.candidate_id,
                public_label=label,
                status=app_obj.status,
                generation=app_obj.generation,
                row_version=app_obj.row_version,
                current_document_id=app_obj.current_document_id,
                current_sanitized_version_id=app_obj.current_sanitized_version_id,
                current_assessment_run_id=app_obj.current_assessment_run_id,
                current_decision_id=app_obj.current_decision_id,
                received_at=app_obj.received_at,
            )
        )
    return items


async def get_application_detail(
    db: AsyncSession,
    application_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> ApplicationDetailResponse:
    """Get detailed application metadata.
    Invariant: original filename is revealed ONLY if caller has active raw_cv grant.
    """
    stmt = (
        select(Application, Candidate.public_label)
        .join(Candidate, Application.candidate_id == Candidate.id)
        .where(Application.id == application_id)
        .options(selectinload(Application.documents))
    )
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Đơn ứng tuyển không tồn tại.")

    app_obj, public_label = row
    if app_obj.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Đơn ứng tuyển không tồn tại.")
    await check_requisition_access(db, app_obj.requisition_id, ctx)

    # Check for active raw grant
    now = datetime.now(timezone.utc)
    stmt_grant = select(RawAccessGrant).where(
        RawAccessGrant.application_id == application_id,
        RawAccessGrant.grantee_user_id == ctx.user.id,
        RawAccessGrant.expires_at > now,
        RawAccessGrant.revoked_at.is_(None),
    )
    grant = (await db.execute(stmt_grant)).scalar_one_or_none()
    has_raw_grant = grant is not None and "raw_cv" in grant.scopes

    doc_summaries = []
    for doc in sorted(app_obj.documents, key=lambda d: d.version_no, reverse=True):
        doc_summaries.append(
            DocumentSummaryDTO(
                id=doc.id,
                version_no=doc.version_no,
                ingestion_status=doc.ingestion_status,
                byte_size=doc.byte_size,
                mime_verified=doc.mime_verified,
                created_at=doc.created_at,
                original_filename=doc.original_name_private if has_raw_grant else None,
            )
        )

    return ApplicationDetailResponse(
        id=app_obj.id,
        requisition_id=app_obj.requisition_id,
        candidate_id=app_obj.candidate_id,
        public_label=public_label,
        status=app_obj.status,
        generation=app_obj.generation,
        row_version=app_obj.row_version,
        current_document_id=app_obj.current_document_id,
        current_sanitized_version_id=app_obj.current_sanitized_version_id,
        current_assessment_run_id=app_obj.current_assessment_run_id,
        current_decision_id=app_obj.current_decision_id,
        received_at=app_obj.received_at,
        documents=doc_summaries,
    )


async def upload_application_document(
    db: AsyncSession,
    application_id: uuid.UUID,
    file_bytes: bytes,
    original_filename: str,
    ctx: AuthenticatedContext,
    if_match_version: Optional[int] = None,
    idempotency_key: Optional[str] = None,
) -> tuple[DocumentUploadResponse, int]:
    """Upload a candidate document (PDF/DOCX), store in private storage, and enqueue ingest job.
    Returns (DocumentUploadResponse, http_status_code).
    """
    stmt_app = select(Application).where(Application.id == application_id).with_for_update()
    app_obj = (await db.execute(stmt_app)).scalar_one_or_none()
    if not app_obj or app_obj.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Đơn ứng tuyển không tồn tại.")

    # Guard: Member or Admin
    await check_requisition_access(db, app_obj.requisition_id, ctx)

    # Optimistic locking
    if if_match_version is not None and app_obj.row_version != if_match_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VERSION_CONFLICT: Đơn ứng tuyển đã thay đổi (current: {app_obj.row_version}, expected: {if_match_version}).",
        )

    # Idempotency check
    idempotency_rec = None
    if idempotency_key:
        req_hash = hashlib.sha256(file_bytes).hexdigest()
        idempotency_rec, is_cached = await get_or_start_idempotency(
            db,
            actor_id=ctx.user.id,
            method="POST",
            route_scope=f"/applications/{application_id}/documents",
            key=idempotency_key,
            request_hash=req_hash,
        )
        if is_cached and idempotency_rec.resource_ref:
            cached_ref = idempotency_rec.resource_ref
            return DocumentUploadResponse(
                document=DocumentUploadedDTO(**cached_ref["document"]),
                job_id=uuid.UUID(cached_ref["job_id"]),
                application_row_version=cached_ref["application_row_version"],
                application_generation=cached_ref["application_generation"],
            ), (idempotency_rec.http_status or 202)

    # Validate file type and size
    mime = detect_and_validate_file_type(file_bytes, original_filename)
    if mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" and not docx_renderer_available():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="DOCX_RENDERER_UNAVAILABLE: Hệ thống chưa hỗ trợ xác minh số trang DOCX; vui lòng nộp PDF.",
        )
    clean_filename = sanitize_filename(original_filename)
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()

    # In-application deduplication check
    stmt_dup = select(Document).where(
        Document.application_id == application_id,
        Document.sha256 == file_sha256,
    )
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="DOCUMENT_ALREADY_CURRENT: Tập tin này đã được tải lên cho đơn ứng tuyển.",
        )

    # Determine next document version_no
    stmt_v = select(func.max(Document.version_no)).where(Document.application_id == application_id)
    max_v = (await db.execute(stmt_v)).scalar() or 0
    next_version = max_v + 1

    doc_id = uuid.uuid4()
    blob_key = f"documents/{application_id}/{doc_id}.bin"

    # Save to private storage
    save_private_blob(blob_key, file_bytes)

    # Create Document record
    doc = Document(
        id=doc_id,
        application_id=application_id,
        version_no=next_version,
        kind="cv",
        original_name_private=clean_filename,
        mime_verified=mime,
        byte_size=len(file_bytes),
        sha256=file_sha256,
        blob_key=blob_key,
        ingestion_status="uploaded",
        safety_status=DocumentSafetyStatus.PENDING,
        created_by=ctx.user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(doc)

    # Advance application generation & row_version, point current document
    app_obj.current_document_id = doc.id
    app_obj.current_sanitized_version_id = None  # New raw doc requires new sanitization
    app_obj.generation += 1
    app_obj.row_version += 1
    app_obj.updated_at = datetime.now(timezone.utc)

    # Enqueue durable ingestion Job
    job = Job(
        id=uuid.uuid4(),
        type=JobType.INGEST_DOCUMENT,
        status=JobStatus.QUEUED,
        target_type="document",
        target_id=doc.id,
        input_snapshot_hash=file_sha256,
        payload_ref={
            "application_id": str(application_id),
            "document_id": str(doc.id),
            "blob_key": blob_key,
            "mime": mime,
        },
        priority=0,
        available_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    # Audit log
    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="document.upload",
        entity_type="document",
        entity_id=doc.id,
        requisition_id=app_obj.requisition_id,
        after_version=app_obj.row_version,
        safe_metadata={
            "document_version": next_version,
            "byte_size": len(file_bytes),
            "mime": mime,
            "job_id": str(job.id),
        },
    )

    result_dto = DocumentUploadResponse(
        document=DocumentUploadedDTO(
            id=doc.id,
            version_no=doc.version_no,
            ingestion_status=doc.ingestion_status,
            byte_size=doc.byte_size,
        ),
        job_id=job.id,
        application_row_version=app_obj.row_version,
        application_generation=app_obj.generation,
    )

    if idempotency_rec:
        await complete_idempotency(
            db,
            idempotency_rec,
            http_status=202,
            resource_ref={
                "document": {
                    "id": str(doc.id),
                    "version_no": doc.version_no,
                    "ingestion_status": doc.ingestion_status,
                    "byte_size": doc.byte_size,
                },
                "job_id": str(job.id),
                "application_row_version": app_obj.row_version,
                "application_generation": app_obj.generation,
            },
        )

    return result_dto, 202
