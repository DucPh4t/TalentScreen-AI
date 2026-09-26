"""Provenance service: Document parsing execution, Source Span Registry persistence, and span queries."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.candidate import Application, RawAccessGrant
from app.db.models.document import Document, SanitizedVersion, SourceSpan
from app.db.models.requisition import RequisitionMembership
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole, DocumentSafetyStatus, SanitizedVersionStatus
from app.schemas.intake import SourceSpanResponse
from app.services.audit import record_audit_event
from app.services.parser import DocumentParsingError, parse_document_content
from app.services.storage import read_private_blob


async def ingest_and_parse_document(
    db: AsyncSession,
    document_id: uuid.UUID,
) -> SanitizedVersion:
    """Execute parsing on an uploaded document, build canonical text, and register source spans."""
    stmt_doc = (
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.application))
        .with_for_update()
    )
    res_doc = await db.execute(stmt_doc)
    doc = res_doc.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài liệu không tồn tại.")

    # Read binary content from private storage
    content = read_private_blob(doc.blob_key)

    try:
        parse_result = parse_document_content(content, doc.mime_verified)
    except DocumentParsingError as e:
        doc.ingestion_status = "failed"
        doc.safety_status = DocumentSafetyStatus.REJECTED
        doc.quality_report = {"error_code": e.error_code, "error_message": e.message}
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"PARSING_FAILED ({e.error_code}): {e.message}",
        )

    # Ingestion success: update document metadata
    doc.page_count = parse_result.page_count
    doc.ingestion_status = "parsed"
    doc.quality_report = parse_result.quality_report
    doc.safety_status = DocumentSafetyStatus.PASSED

    # Determine next SanitizedVersion version_no
    stmt_v = select(func.max(SanitizedVersion.version_no)).where(
        SanitizedVersion.document_id == doc.id
    )
    max_v = (await db.execute(stmt_v)).scalar() or 0
    next_v = max_v + 1

    sanitized = SanitizedVersion(
        id=uuid.uuid4(),
        application_id=doc.application_id,
        document_id=doc.id,
        version_no=next_v,
        status=SanitizedVersionStatus.DRAFT,
        canonical_text=parse_result.canonical_text,
        sha256=parse_result.sha256,
        quality_flags=parse_result.quality_report,
        created_at=datetime.now(timezone.utc),
    )
    db.add(sanitized)
    await db.flush()

    # Bulk insert registered spans
    span_models = []
    for s in parse_result.spans:
        span_models.append(
            SourceSpan(
                span_id=s.span_id,
                full_hash=s.full_hash,
                sanitized_version_id=sanitized.id,
                start_cp=s.start_cp,
                end_cp=s.end_cp,
                page_number=s.page_number,
                section_label=s.section_label,
                language=s.language,
                text=s.text,
                created_at=datetime.now(timezone.utc),
            )
        )
    db.add_all(span_models)

    # Point application to current sanitized version
    doc.application.current_sanitized_version_id = sanitized.id
    doc.application.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=doc.created_by,
        action="document.parsed",
        entity_type="document",
        entity_id=doc.id,
        requisition_id=doc.application.requisition_id,
        safe_metadata={
            "page_count": parse_result.page_count,
            "total_spans": len(parse_result.spans),
            "sanitized_version_id": str(sanitized.id),
        },
    )

    return sanitized


async def get_source_span(
    db: AsyncSession,
    span_id: str,
    ctx: AuthenticatedContext,
) -> SourceSpanResponse:
    """Retrieve an individual source span with provenance metadata.
    Enforces authorization: Caller must belong to the application's requisition.
    """
    stmt = (
        select(SourceSpan, SanitizedVersion, Application)
        .join(SanitizedVersion, SourceSpan.sanitized_version_id == SanitizedVersion.id)
        .join(Application, SanitizedVersion.application_id == Application.id)
        .where(SourceSpan.span_id == span_id)
    )
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy Source Span.")

    span, sanitized, app_obj = row

    # Access control check
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == app_obj.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập Source Span này.")

    # If sanitized version is REVOKED, only users with raw grant can inspect
    if sanitized.status == SanitizedVersionStatus.REVOKED:
        now = datetime.now(timezone.utc)
        stmt_grant = select(RawAccessGrant).where(
            RawAccessGrant.application_id == app_obj.id,
            RawAccessGrant.grantee_user_id == ctx.user.id,
            RawAccessGrant.expires_at > now,
            RawAccessGrant.revoked_at.is_(None),
        )
        if not (await db.execute(stmt_grant)).scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Source Span thuộc phiên bản đã bị thu hồi (revoked); chỉ người có Raw Grant mới có quyền tra cứu.",
            )

    return SourceSpanResponse(
        span_id=span.span_id,
        sanitized_version_id=span.sanitized_version_id,
        source_hash=span.full_hash,
        coordinate_system="unicode_codepoints_nfc_lf",
        start_cp=span.start_cp,
        end_cp=span.end_cp,
        page_number=span.page_number,
        section_label=span.section_label,
        text=span.text,
        language=span.language,
    )
