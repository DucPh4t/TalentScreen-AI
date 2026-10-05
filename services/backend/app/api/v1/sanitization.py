"""API v1 endpoints for Sanitization, HR approval, Raw Grants, and Source Viewer."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, Header, Response, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.schemas.sanitization import (
    RawGrantCreateRequest,
    RawGrantResponse,
    SanitizedApproveRequest,
    SanitizedEditRequest,
    SanitizedRevokeRequest,
    SanitizedVersionDetailResponse,
    SanitizedVersionSummaryResponse,
)
from app.services.sanitization import (
    approve_sanitized_version,
    create_raw_access_grant,
    edit_sanitized_version,
    get_document_raw_preview,
    get_sanitized_version_detail,
    list_sanitized_versions,
    revoke_raw_access_grant,
    revoke_sanitized_version,
)

router = APIRouter(tags=["Sanitization & Source Viewer"])


# ---------------- Raw Access Grants ---------------- #


@router.post(
    "/applications/{id}/raw-grants",
    response_model=RawGrantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_create_raw_grant(
    id: uuid.UUID,
    payload: RawGrantCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Issue a scoped raw access grant to a member for reviewing raw CV."""
    res = await create_raw_access_grant(db, id, payload, ctx)
    await db.commit()
    return res


@router.delete(
    "/applications/{id}/raw-grants/{grant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_raw_grant(
    id: uuid.UUID,
    grant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Revoke an active raw access grant immediately."""
    await revoke_raw_access_grant(db, id, grant_id, ctx)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------- Sanitized Versions ---------------- #


@router.get(
    "/documents/{id}/sanitized-versions",
    response_model=list[SanitizedVersionSummaryResponse],
)
async def get_sanitized_versions_by_document(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List sanitized versions. Unapproved drafts and revoked versions are visible ONLY with active raw_cv grant."""
    return await list_sanitized_versions(db, id, ctx)


@router.get(
    "/sanitized-versions/{id}",
    response_model=SanitizedVersionDetailResponse,
)
async def get_sanitized_version(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve detailed sanitized canonical text and quality flags. Drafts/revoked require raw_cv grant."""
    return await get_sanitized_version_detail(db, id, ctx)


@router.post(
    "/documents/{id}/sanitized-versions",
    response_model=SanitizedVersionDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_edit_sanitized_version(
    id: uuid.UUID,
    payload: SanitizedEditRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Submit a manual edit/redaction to create a new draft sanitized version and source spans."""
    res = await edit_sanitized_version(db, id, payload, ctx)
    await db.commit()
    return res


@router.post(
    "/sanitized-versions/{id}/approve",
    response_model=SanitizedVersionDetailResponse,
)
async def post_approve_sanitized_version(
    id: uuid.UUID,
    payload: SanitizedApproveRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Approve a specific sanitized version for evaluation. Requires Owner role + active raw_cv grant."""
    res = await approve_sanitized_version(db, id, payload, ctx)
    await db.commit()
    return res


@router.post(
    "/sanitized-versions/{id}/revoke",
    response_model=SanitizedVersionDetailResponse,
)
async def post_revoke_sanitized_version(
    id: uuid.UUID,
    payload: SanitizedRevokeRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Revoke an approved sanitized version when PII or forbidden criterion is discovered."""
    res = await revoke_sanitized_version(db, id, payload, ctx)
    await db.commit()
    return res


@router.get("/documents/{id}/raw-preview")
async def get_document_raw_preview_endpoint(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Stream raw document bytes for secure side-by-side verification. Requires active raw_cv grant."""
    raw_bytes, mime_type = await get_document_raw_preview(db, id, ctx)
    await db.commit()
    return FastAPIResponse(
        content=raw_bytes,
        media_type=mime_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "Cross-Origin-Resource-Policy": "same-origin",
        },
    )
