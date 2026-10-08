"""Routes for explicit human screening and interview-round orchestration."""
import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.domain.authorization import get_current_context, AuthenticatedContext
from app.schemas.hr_workflow import ReviewProgressUpdate, ScreeningDecisionRequest, InterviewRoundUpdate, InterviewConclusionRequest
from app.schemas.decision import DecisionResponse
from app.services import hr_workflow as service
router = APIRouter(tags=['HR screening and interview workflow'])

@router.get('/applications/{id}/review-progress')
async def get_progress(id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    return await service.review_progress(db, id, ctx)

@router.put('/applications/{id}/review-progress')
async def put_progress(id: uuid.UUID, payload: ReviewProgressUpdate, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    return await service.review_progress(db, id, ctx, payload)

@router.post('/applications/{id}/screening-decision', status_code=201, response_model=DecisionResponse)
async def post_screening(id: uuid.UUID, payload: ScreeningDecisionRequest, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    return await service.screening_decision(db, id, ctx, payload)

@router.get('/applications/{id}/interview-rounds/{round_no}')
async def get_round(id: uuid.UUID, round_no: int, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    return await service.interview_round(db, id, round_no, ctx)

@router.put('/applications/{id}/interview-rounds/{round_no}')
async def put_round(id: uuid.UUID, round_no: int, payload: InterviewRoundUpdate, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    return await service.interview_round(db, id, round_no, ctx, payload)

@router.post('/applications/{id}/interview-rounds/{round_no}/conclusions', status_code=201)
async def post_conclusion(id: uuid.UUID, round_no: int, payload: InterviewConclusionRequest, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    return await service.conclude_round(db, id, round_no, ctx, payload)
