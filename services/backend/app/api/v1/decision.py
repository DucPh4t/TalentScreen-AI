"""API router for Task B13: HR Revisions, Review Attestation, and Decision Flow."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.schemas.decision import (
    AttestationCreateRequest,
    DecisionCreateRequest,
    DecisionResponse,
    HRRevisionCreateRequest,
    HRRevisionFinalizeRequest,
    HRRevisionResponse,
    HRRevisionUpdateRequest,
    ReviewAttestationResponse,
)
from app.services.decision import (
    create_decision,
    create_hr_revision,
    create_review_attestation,
    finalize_hr_revision,
    get_hr_revision_detail,
    list_decisions,
    list_hr_revisions,
    update_hr_revision,
)

router = APIRouter(tags=["HR Revisions, Attestation & Decisions"])


# ---------------- HR Revision Endpoints ---------------- #


@router.post(
    "/applications/{id}/hr-revisions",
    response_model=HRRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_create_hr_revision(
    id: uuid.UUID,
    payload: HRRevisionCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Create a new draft HR Revision with server-side deterministic scoring and anti-discrimination scanning."""
    return await create_hr_revision(db, id, payload, ctx)


@router.get(
    "/applications/{id}/hr-revisions",
    response_model=list[HRRevisionResponse],
)
async def get_application_hr_revisions(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List all HR revisions for a candidate application."""
    return await list_hr_revisions(db, id, ctx)


@router.get(
    "/hr-revisions/{id}",
    response_model=HRRevisionResponse,
)
async def get_single_hr_revision(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get HR revision detail with staleness analysis."""
    return await get_hr_revision_detail(db, id, ctx)


@router.put(
    "/hr-revisions/{id}",
    response_model=HRRevisionResponse,
)
async def put_update_hr_revision(
    id: uuid.UUID,
    payload: HRRevisionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Update a draft HR revision."""
    return await update_hr_revision(db, id, payload, ctx)


@router.post(
    "/hr-revisions/{id}/finalize",
    response_model=HRRevisionResponse,
)
async def post_finalize_hr_revision(
    id: uuid.UUID,
    payload: HRRevisionFinalizeRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Freeze a draft HR revision into an immutable finalized revision."""
    return await finalize_hr_revision(db, id, payload, ctx)


# ---------------- Review Attestation Endpoints ---------------- #


@router.post(
    "/applications/{id}/review-attestations",
    response_model=ReviewAttestationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_create_review_attestation(
    id: uuid.UUID,
    payload: AttestationCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Create a signed ReviewAttestation bound to the caller, decision basis, and source snapshot hash."""
    return await create_review_attestation(db, id, payload, ctx)


# ---------------- Final Decision Endpoints ---------------- #


@router.post(
    "/applications/{id}/decisions",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_create_decision(
    id: uuid.UUID,
    payload: DecisionCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Record an attested, immutable hiring decision. Owner role ONLY."""
    return await create_decision(db, id, payload, ctx)


@router.get(
    "/applications/{id}/decisions",
    response_model=list[DecisionResponse],
)
async def get_application_decisions(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List historical decisions for an application."""
    return await list_decisions(db, id, ctx)
