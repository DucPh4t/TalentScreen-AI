"""Job monitoring and cancellation endpoints."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import Job
from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.schemas.job import JobCancelRequest, JobCancelResponse, JobResponse
from app.services.worker import cancel_job, sweep_stale_jobs

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


@router.get("/{id}", response_model=JobResponse)
async def get_job(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve details, lease status, and progress for a background job."""
    stmt = select(Job).where(Job.id == id)
    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tác vụ không tồn tại.",
        )
    return job


@router.post("/{id}/cancel", response_model=JobCancelResponse)
async def post_cancel_job(
    id: uuid.UUID,
    payload: JobCancelRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Request cooperative cancellation of a background job."""
    job_status, message = await cancel_job(
        db=db,
        job_id=id,
        reason=payload.reason,
        actor_id=ctx.user.id,
    )
    await db.commit()
    return JobCancelResponse(
        id=id,
        status=job_status.value,
        message=message,
    )


@router.post("/sweep", response_model=dict[str, int])
async def post_sweep_stale_jobs(
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Admin sweep endpoint to recover abandoned/stale running jobs."""
    swept_count = await sweep_stale_jobs(db)
    await db.commit()
    return {"swept_jobs": swept_count}
