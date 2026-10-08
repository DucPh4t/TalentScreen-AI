"""API v1 endpoints for Application Assessment and evaluation results."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.schemas.assessment import (
    AssessmentRunCreateRequest,
    AssessmentRunResponse,
)
from app.services.assessment.service import (
    create_assessment_run,
    get_assessment_run_detail,
)

router = APIRouter(tags=["AI Assessment & Scoring"])


@router.post(
    "/applications/{id}/assessments",
    response_model=AssessmentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_create_assessment_run(
    id: uuid.UUID,
    payload: AssessmentRunCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Enqueue a full-text assessment run for an application. Requires approved sanitized version and rubric."""
    res = await create_assessment_run(db, id, payload, ctx)
    await db.commit()
    return res


@router.get(
    "/applications/{id}/assessments/{run_id}",
    response_model=AssessmentRunResponse,
)
async def get_assessment_run(
    id: uuid.UUID,
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve detailed assessment results, scores, evidence quotes, and recommendation."""
    return await get_assessment_run_detail(db, run_id, ctx)


# ---------------- Candidate Executive Summary Endpoints ---------------- #


@router.get("/applications/{id}/summary")
async def get_candidate_summary_endpoint(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve high-density 5-sentence executive summary for rapid HR screening."""
    from app.services.candidate_summary import generate_candidate_summary
    return await generate_candidate_summary(db, application_id=id, ctx=ctx, force_refresh=False)


@router.post("/applications/{id}/summary/generate")
async def post_generate_candidate_summary_endpoint(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Force fresh regeneration of candidate executive summary."""
    from app.services.candidate_summary import generate_candidate_summary
    return await generate_candidate_summary(db, application_id=id, ctx=ctx, force_refresh=True)
