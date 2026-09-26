"""Durable PostgreSQL background worker engine with lease fencing, heartbeats, and retry schedules."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable, Coroutine, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ops import Job
from app.domain.enums import JobStatus, JobType
from app.services.audit import record_audit_event

logger = logging.getLogger(__name__)

DEFAULT_LEASE_SECONDS = 30
DEFAULT_MAX_CLAIMS = 3
RETRY_DELAYS_SECONDS = [5, 15, 30]


class FencingViolationError(Exception):
    """Raised when an operation is attempted with a stale lease epoch."""
    pass


class JobCancelledError(Exception):
    """Raised when job processing detects cancellation requested."""
    pass


async def claim_next_job(
    db: AsyncSession,
    worker_id: str,
    lease_duration_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Optional[tuple[uuid.UUID, int, JobType, uuid.UUID, dict[str, Any]]]:
    """Atomically claim the highest priority available job using FOR UPDATE SKIP LOCKED.
    Increments lease_epoch (fencing token) and updates lease_expires_at.
    Returns (job_id, claimed_epoch, job_type, target_id, payload_ref) or None.
    """
    now = datetime.now(timezone.utc)

    # Claimable condition:
    # 1. status = QUEUED and available_at <= now
    # 2. status = RETRY_WAIT and available_at <= now
    # 3. status = RUNNING and lease_expires_at < now (stale lease recovery)
    stmt = (
        select(Job)
        .where(
            Job.cancel_requested_at.is_(None),
            or_(
                Job.status == JobStatus.QUEUED,
                (Job.status == JobStatus.RETRY_WAIT) & (Job.available_at <= now),
                (Job.status == JobStatus.RUNNING) & (Job.lease_expires_at < now),
            ),
        )
        .order_by(Job.priority.desc(), Job.available_at.asc(), Job.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    )

    res = await db.execute(stmt)
    job = res.scalar_one_or_none()
    if not job:
        return None

    # Check max claims (poison pill protection)
    if job.claim_count >= DEFAULT_MAX_CLAIMS:
        job.status = JobStatus.FAILED
        job.last_error_code = "MAX_CLAIMS_EXCEEDED"
        job.updated_at = now
        await db.flush()
        return None

    # Advance fencing token and lease
    job.status = JobStatus.RUNNING
    job.lease_owner = worker_id
    job.lease_epoch += 1
    job.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
    job.claim_count += 1
    job.updated_at = now
    await db.flush()

    claimed_epoch = job.lease_epoch
    job_id = job.id
    job_type = job.type
    target_id = job.target_id
    payload_ref = job.payload_ref or {}

    return job_id, claimed_epoch, job_type, target_id, payload_ref


async def heartbeat_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    worker_id: str,
    epoch: int,
    lease_duration_seconds: int = DEFAULT_LEASE_SECONDS,
) -> bool:
    """Extend lease expiration while verifying fencing token. Returns True on success, False if lost."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.lease_owner == worker_id,
            Job.lease_epoch == epoch,
            Job.status == JobStatus.RUNNING,
        )
        .values(
            lease_expires_at=now + timedelta(seconds=lease_duration_seconds),
            updated_at=now,
        )
    )
    res = await db.execute(stmt)
    return res.rowcount > 0


async def complete_job_fenced(
    db: AsyncSession,
    job_id: uuid.UUID,
    worker_id: str,
    epoch: int,
    success: bool,
    error_code: Optional[str] = None,
    allow_retry: bool = True,
) -> JobStatus:
    """Commit final job state with fencing guard.
    Invariant: Worker cũ KHÔNG ĐƯỢC commit sau khi lease mới đã được cấp.
    """
    now = datetime.now(timezone.utc)

    # First check if cancellation was requested
    stmt_check = select(Job).where(Job.id == job_id)
    job = (await db.execute(stmt_check)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.cancel_requested_at is not None:
        final_status = JobStatus.CANCELLED
    elif success:
        final_status = JobStatus.SUCCEEDED
    elif allow_retry and job.claim_count < DEFAULT_MAX_CLAIMS:
        final_status = JobStatus.RETRY_WAIT
        delay_idx = min(job.claim_count - 1, len(RETRY_DELAYS_SECONDS) - 1)
        delay_sec = RETRY_DELAYS_SECONDS[delay_idx]
        job.available_at = now + timedelta(seconds=delay_sec)
    else:
        final_status = JobStatus.FAILED

    # Fenced atomic update
    stmt = (
        update(Job)
        .where(
            Job.id == job_id,
            Job.lease_owner == worker_id,
            Job.lease_epoch == epoch,
        )
        .values(
            status=final_status,
            lease_owner=None if final_status != JobStatus.RETRY_WAIT else job.lease_owner,
            lease_expires_at=None,
            last_error_code=error_code,
            available_at=job.available_at if final_status == JobStatus.RETRY_WAIT else now,
            updated_at=now,
        )
    )
    res = await db.execute(stmt)
    if res.rowcount == 0:
        raise FencingViolationError(
            f"FENCING_VIOLATION: Job {job_id} epoch {epoch} by {worker_id} was superseded or stolen."
        )

    return final_status


async def cancel_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    reason: str,
    actor_id: Optional[uuid.UUID] = None,
) -> tuple[JobStatus, str]:
    """Request cooperative cancellation of a job."""
    now = datetime.now(timezone.utc)
    stmt = select(Job).where(Job.id == job_id).with_for_update()
    job = (await db.execute(stmt)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tác vụ không tồn tại.")

    # If already terminal
    if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.STALE}:
        return job.status, "Tác vụ đã kết thúc trước khi nhận được yêu cầu hủy."

    # If queued or retry_wait, cancel immediately
    if job.status in {JobStatus.QUEUED, JobStatus.RETRY_WAIT}:
        job.status = JobStatus.CANCELLED
        job.cancel_requested_at = now
        job.last_error_code = "CANCELLED_BY_USER"
        job.updated_at = now
        await db.flush()
        return JobStatus.CANCELLED, "Tác vụ trong hàng đợi đã được hủy thành công."

    # If running, request cancellation
    job.cancel_requested_at = now
    job.updated_at = now
    await db.flush()
    return JobStatus.RUNNING, "Đã gửi yêu cầu hủy tới worker đang xử lý."


async def sweep_stale_jobs(db: AsyncSession) -> int:
    """Recovery sweeper: Find dead/abandoned running jobs whose lease expired and max claims reached."""
    now = datetime.now(timezone.utc)
    stmt = (
        update(Job)
        .where(
            Job.status == JobStatus.RUNNING,
            Job.lease_expires_at < now,
            Job.claim_count >= DEFAULT_MAX_CLAIMS,
        )
        .values(
            status=JobStatus.FAILED,
            last_error_code="STALE_LEASE_ABANDONED",
            lease_expires_at=None,
            updated_at=now,
        )
    )
    res = await db.execute(stmt)
    return res.rowcount


# ---------------- Job Handler Dispatch ---------------- #


async def execute_job_handler(
    db: AsyncSession,
    job_id: uuid.UUID,
    job_type: JobType,
    target_id: uuid.UUID,
    payload_ref: dict[str, Any],
) -> None:
    """Dispatch job to its designated domain handler."""
    if job_type == JobType.INGEST_DOCUMENT:
        from app.services.provenance import ingest_and_parse_document
        await ingest_and_parse_document(db, target_id)
    elif job_type == JobType.ASSESS_APPLICATION:
        from app.services.assessment.service import execute_assessment_job
        await execute_assessment_job(db, job_id=job_id)
    elif job_type == JobType.DRAFT_INTERVIEW:
        from app.services.interview import execute_interview_job
        await execute_interview_job(db, job_id=job_id)
    else:
        logger.info(f"Handler for job type {job_type} executed (mock or pending).")


async def run_worker_once(
    db: AsyncSession,
    worker_id: Optional[str] = None,
) -> bool:
    """Execute one job lifecycle: Claim -> Separate execution -> Fenced commit.
    Returns True if a job was processed, False if queue was empty.
    """
    w_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"

    # 1. Claim in isolated transaction
    claim_res = await claim_next_job(db, w_id)
    if not claim_res:
        return False

    job_id, epoch, job_type, target_id, payload_ref = claim_res
    await db.commit()  # Release lock immediately, do not hold transaction across work!

    success = False
    error_code = None

    try:
        # 2. Execute handler in clean transaction
        await execute_job_handler(db, job_id, job_type, target_id, payload_ref)
        success = True
    except Exception as e:
        logger.exception(f"Job {job_id} handler failed: {e}")
        error_code = type(e).__name__
        success = False

    # 3. Fenced commit
    try:
        await complete_job_fenced(
            db,
            job_id=job_id,
            worker_id=w_id,
            epoch=epoch,
            success=success,
            error_code=error_code,
        )
        await db.commit()
    except FencingViolationError:
        logger.warning(f"Fencing violation on job {job_id}; discarding result.")
        await db.rollback()

    return True
