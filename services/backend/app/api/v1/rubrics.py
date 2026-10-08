"""Rubrics and Criteria API endpoints."""
from __future__ import annotations

from typing import Optional
import uuid
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.schemas.rubric import (
    RubricApproveRequest,
    RubricApproveResponse,
    RubricCreateRequest,
    RubricResponse,
    RubricUpdateRequest,
)
from app.services.rubric import (
    approve_rubric,
    create_rubric_draft,
    draft_rubric_from_jd,
    get_rubric_by_id,
    list_rubrics_for_requisition,
    update_rubric_draft,
)

router = APIRouter(tags=["Rubrics"])


@router.get("/requisitions/{id}/rubrics", response_model=list[RubricResponse])
async def get_requisition_rubrics(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    return await list_rubrics_for_requisition(db, id, ctx)


@router.post("/requisitions/{id}/rubrics", response_model=RubricResponse, status_code=status.HTTP_201_CREATED)
async def post_create_rubric(
    id: uuid.UUID,
    payload: RubricCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Create a new rubric draft via seed import, clone, or manual specification."""
    return await create_rubric_draft(db, id, payload, ctx)


@router.post("/requisitions/{id}/rubrics/draft-from-jd", response_model=RubricResponse, status_code=status.HTTP_201_CREATED)
async def post_draft_rubric_from_jd(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """AI Rubric Drafter: Automatically synthesize and propose a draft rubric from active Job Description."""
    return await draft_rubric_from_jd(db, requisition_id=id, ctx=ctx)



@router.get("/rubrics/{id}", response_model=RubricResponse)
async def get_rubric(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get a rubric version with its criteria, weights, anchors, and policy."""
    return await get_rubric_by_id(db, id, ctx)


@router.put("/rubrics/{id}", response_model=RubricResponse)
async def put_update_rubric(
    id: uuid.UUID,
    payload: RubricUpdateRequest,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Update a draft rubric. Invariant: Only DRAFT rubrics can be edited."""
    return await update_rubric_draft(db, id, payload, ctx, header_if_match=if_match)


@router.post("/rubrics/{id}/approve", response_model=RubricApproveResponse)
async def post_approve_rubric(
    id: uuid.UUID,
    payload: RubricApproveRequest,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Approve a rubric draft, setting it as active rubric for the requisition."""
    return await approve_rubric(db, id, payload, ctx, header_if_match=if_match)
