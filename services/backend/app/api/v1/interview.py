"""API router for Task B14: Interview Question Banks and Interview Agent."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.schemas.interview import (
    InterviewDraftCreateRequest,
    InterviewDraftResponse,
    InterviewRevisionCreateRequest,
    InterviewRevisionResponse,
    QuestionBankApproveRequest,
    QuestionBankCreateRequest,
    QuestionBankResponse,
    QuestionBankUpdateRequest,
)
from app.services.interview import (
    approve_question_bank,
    create_interview_draft_job,
    create_interview_revision,
    create_question_bank,
    get_interview_draft_detail,
    list_interview_revisions,
    list_question_banks,
    update_question_bank,
)

router = APIRouter(tags=["Interview Question Banks & Agent"])


# ---------------- Question Bank Endpoints ---------------- #


@router.get(
    "/rubrics/{id}/interview-question-banks",
    response_model=list[QuestionBankResponse],
)
async def get_rubric_question_banks(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List question banks associated with a rubric version."""
    return await list_question_banks(db, id, ctx)


@router.post(
    "/rubrics/{id}/interview-question-banks",
    response_model=QuestionBankResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_create_question_bank(
    id: uuid.UUID,
    payload: QuestionBankCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Create a new Question Bank draft (seed import or clone). Owner only."""
    return await create_question_bank(db, id, payload, ctx)


@router.put(
    "/interview-question-banks/{id}",
    response_model=QuestionBankResponse,
)
async def put_update_question_bank(
    id: uuid.UUID,
    payload: QuestionBankUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Update a draft question bank with core questions and change reason. Owner only."""
    return await update_question_bank(db, id, payload, ctx)


@router.post(
    "/interview-question-banks/{id}/approve",
    response_model=QuestionBankResponse,
)
async def post_approve_question_bank(
    id: uuid.UUID,
    payload: QuestionBankApproveRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Approve a question bank, freezing it as the immutable active bank for this rubric. Owner only."""
    return await approve_question_bank(db, id, payload, ctx)


# ---------------- Interview Draft Endpoints ---------------- #


@router.post(
    "/applications/{id}/interview-drafts",
    response_model=InterviewDraftResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def post_create_interview_draft(
    id: uuid.UUID,
    payload: InterviewDraftCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Enqueue an on-demand candidate interview follow-up generation job."""
    return await create_interview_draft_job(db, id, payload, ctx)


@router.get(
    "/applications/{id}/interview-drafts/latest",
    response_model=InterviewDraftResponse | None,
)
async def get_latest_application_interview_draft(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve the latest interview job state and its questions for page reloads."""
    from app.services.interview import get_latest_interview_draft
    return await get_latest_interview_draft(db, id, ctx)


@router.get(
    "/interview-drafts/{id}",
    response_model=InterviewDraftResponse,
)
async def get_single_interview_draft(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Get complete interview draft with read-only core questions, AI followups, and latest HR edits."""
    return await get_interview_draft_detail(db, id, ctx)


@router.post(
    "/interview-drafts/{id}/revisions",
    response_model=InterviewRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_create_interview_revision(
    id: uuid.UUID,
    payload: InterviewRevisionCreateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Save HR edits to candidate-specific follow-ups. Invariant: Core bank questions cannot be modified here."""
    return await create_interview_revision(db, id, payload, ctx)


@router.get(
    "/interview-drafts/{id}/revisions",
    response_model=list[InterviewRevisionResponse],
)
async def get_interview_draft_revisions(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """List historical follow-up revisions for an interview draft."""
    return await list_interview_revisions(db, id, ctx)
