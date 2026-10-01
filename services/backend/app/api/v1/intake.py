"""Application Intake and Document Upload API endpoints."""
from __future__ import annotations

from typing import Optional
import uuid
from fastapi import APIRouter, Depends, File, Header, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.config import get_settings
from fastapi import HTTPException
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.schemas.intake import (
    ApplicationCreateRequest,
    ApplicationDetailResponse,
    ApplicationResponse,
    DocumentSummaryDTO,
    DocumentUploadResponse,
    SourceSpanResponse,
)
from app.services.intake import (
    create_application,
    get_application_detail,
    list_applications,
    upload_application_document,
)

router = APIRouter(tags=["Application Intake & Documents"])


@router.get("/requisitions/{id}/applications", response_model=list[ApplicationResponse])
async def get_applications_by_requisition(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List applications under a requisition with pseudonymized public labels."""
    return await list_applications(db, id, ctx)


@router.post("/requisitions/{id}/applications", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def post_create_application(
    id: uuid.UUID,
    payload: ApplicationCreateRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Create a new candidate application under a requisition."""
    from app.services.intake import check_requisition_access, get_application_detail
    from app.services.idempotency import get_or_start_idempotency, complete_idempotency
    import hashlib, json
    await check_requisition_access(db, id, ctx)
    record = None
    if idempotency_key:
        if len(idempotency_key) > 128:
            raise HTTPException(422, "Idempotency-Key quá dài.")
        # Serialize equal keys even if both callers arrive before a record exists.
        from sqlalchemy import text
        scope = f"create-application:{id}"
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                         {"key": f"{ctx.user.id}:{scope}:{idempotency_key}"})
        request_hash = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
        record, cached = await get_or_start_idempotency(db, actor_id=ctx.user.id, method="POST",
            route_scope=scope, key=idempotency_key, request_hash=request_hash)
        if cached:
            if record.request_hash != request_hash:
                raise HTTPException(409, "Idempotency-Key đã dùng cho nội dung khác.")
            return await get_application_detail(db, uuid.UUID(record.resource_ref["application_id"]), ctx)
    result = await create_application(db, id, payload, ctx)
    if record:
        await complete_idempotency(db, record, 201, {"application_id": str(result.id)})
    return result


@router.get("/applications/{id}", response_model=ApplicationDetailResponse)
async def get_application(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get application details. Real filenames are masked unless caller has active raw_cv grant."""
    return await get_application_detail(db, id, ctx)


@router.get("/applications/{id}/documents", response_model=list[DocumentSummaryDTO])
async def get_application_documents(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get document versions associated with an application."""
    detail = await get_application_detail(db, id, ctx)
    return detail.documents


@router.post(
    "/applications/{id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_upload_document(
    id: uuid.UUID,
    response: Response,
    file: UploadFile = File(...),
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Upload a candidate document (PDF or DOCX), securely stored in private storage with an ingestion job.
    Accepts multipart/form-data. Returns HTTP 202 Accepted with job metadata.
    """
    if_match_v = None
    if if_match:
        try:
            if_match_v = int(if_match.strip('"'))
        except ValueError:
            pass

    max_bytes = min(get_settings().UPLOAD_MAX_BYTES, 10 * 1024 * 1024)
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "FILE_TOO_LARGE: CV vượt giới hạn tải lên.")
    filename = file.filename or "uploaded_document.pdf"

    result_dto, status_code = await upload_application_document(
        db=db,
        application_id=id,
        file_bytes=content,
        original_filename=filename,
        ctx=ctx,
        if_match_version=if_match_v,
        idempotency_key=idempotency_key,
    )

    response.status_code = status_code
    return result_dto


@router.get("/source-spans/{span_id}", response_model=SourceSpanResponse)
async def get_source_span_endpoint(
    span_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve an individual source span with exact codepoint coordinates and provenance metadata."""
    from app.services.provenance import get_source_span
    return await get_source_span(db, span_id, ctx)
