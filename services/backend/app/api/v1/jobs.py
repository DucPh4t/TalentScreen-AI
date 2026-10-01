"""Job monitoring and cancellation endpoints."""
from __future__ import annotations

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, Document, InterviewDraft, Job, RequisitionMembership
from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context, require_role
from app.domain.enums import AccountRole, MembershipRole
from app.services.audit import record_audit_event
from app.schemas.job import JobCancelRequest, JobCancelResponse, JobResponse
from app.services.worker import cancel_job, sweep_stale_jobs

router = APIRouter(prefix="/jobs", tags=["Background Jobs"])


async def authorize_job(db: AsyncSession, job: Job, ctx: AuthenticatedContext, cancel: bool = False):
    if ctx.has_role(AccountRole.ADMIN):
        return
    application_id = None
    if job.target_type == "application":
        application_id = job.target_id
    elif job.target_type == "document":
        document = await db.get(Document, job.target_id)
        application_id = document.application_id if document else None
    elif job.target_type == "interview_draft":
        draft = await db.get(InterviewDraft, job.target_id)
        application_id = draft.application_id if draft else None
    application = await db.get(Application, application_id) if application_id else None
    membership = (await db.execute(select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == application.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    ))).scalar_one_or_none() if application else None
    if membership is None:
        raise HTTPException(404, "Tác vụ không tồn tại.")
    if cancel and membership.membership_role != MembershipRole.OWNER:
        raise HTTPException(403, "Chỉ Owner hoặc Admin được hủy tác vụ.")


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
    await authorize_job(db, job, ctx)
    return job


@router.post("/{id}/cancel", response_model=JobCancelResponse)
async def post_cancel_job(
    id: uuid.UUID,
    payload: JobCancelRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Request cooperative cancellation of a background job."""
    job = await db.get(Job, id)
    if job is None:
        raise HTTPException(404, "Tác vụ không tồn tại.")
    await authorize_job(db, job, ctx, cancel=True)
    job_status, message = await cancel_job(
        db=db,
        job_id=id,
        reason=payload.reason,
        actor_id=ctx.user.id,
    )
    await record_audit_event(db, actor_id=ctx.user.id, action="job.cancel_requested",
                             entity_type="job", entity_id=id,
                             safe_metadata={"status": job_status.value})
    await db.commit()
    return JobCancelResponse(
        id=id,
        status=job_status.value,
        message=message,
    )


@router.post("/sweep", response_model=dict[str, int], dependencies=[Depends(require_role(AccountRole.ADMIN))])
async def post_sweep_stale_jobs(
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Admin sweep endpoint to recover abandoned/stale running jobs."""
    swept_count = await sweep_stale_jobs(db)
    await db.commit()
    return {"swept_jobs": swept_count}
