"""Admin Observability, Metrics, SLI monitoring, and System Readiness (Task B23)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
import uuid
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Application, BudgetPeriod, Decision, Job, LLMInvocation
from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, require_role
from app.domain.enums import AccountRole, BudgetScope, JobStatus
from app.services.storage import get_storage_base_dir

router = APIRouter(prefix="/admin", tags=["Admin & Observability"])


class SLIReportDTO(BaseModel):
    queue_latency_ok: bool
    worker_health_ok: bool
    budget_cap_ok: bool
    error_rate_ok: bool
    reason_codes: list[str]


class AdminMetricsResponse(BaseModel):
    timestamp_utc: str
    app_env: str
    pilot_stage: Optional[str] = None
    jobs_summary: dict[str, int]
    latencies: dict[str, Optional[float]]
    human_review_metrics: dict[str, Any]
    budget_summary: dict[str, Any]
    worker_health: dict[str, Any]
    sli_report: SLIReportDTO


@router.get(
    "/metrics",
    response_model=AdminMetricsResponse,
    dependencies=[Depends(require_role(AccountRole.ADMIN))],
)
async def get_admin_metrics(
    db: AsyncSession = Depends(get_db),
):
    """Aggregate system telemetry: job queue SLIs, latencies, budget usage, worker health.
    Strict Invariant: Log & metrics contain ZERO candidate PII.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)

    # 1. Job counts by status
    stmt_jobs = select(Job.status, func.count(Job.id)).group_by(Job.status)
    res_jobs = (await db.execute(stmt_jobs)).all()
    jobs_summary = {st.value if hasattr(st, "value") else str(st): count for st, count in res_jobs}
    recent_jobs = (await db.execute(select(Job.status, func.count(Job.id))
        .where(Job.created_at >= now - timedelta(days=1)).group_by(Job.status))).all()
    recent_counts = {st.value: count for st, count in recent_jobs}
    terminal_jobs = recent_counts.get(JobStatus.SUCCEEDED.value, 0) + recent_counts.get(JobStatus.FAILED.value, 0)

    # 2. Worker Leases & Active Workers
    stmt_workers = select(func.count(func.distinct(Job.lease_owner))).where(
        Job.lease_expires_at > now,
        Job.status == JobStatus.RUNNING,
    )
    active_workers_count = (await db.execute(stmt_workers)).scalar() or 0

    # 3. Budget & Invocations metrics
    stmt_budget = select(
        func.coalesce(func.sum(LLMInvocation.cost_actual), 0.0),
        func.count(LLMInvocation.id),
    ).where(LLMInvocation.created_at >= now - timedelta(days=1))
    daily_spent_usd, calls_count = (await db.execute(stmt_budget)).one()

    daily_spent_cents = int(float(daily_spent_usd) * 100)
    scope = BudgetScope.DEVELOPMENT if settings.APP_ENV == "sandbox" else BudgetScope.PILOT
    periods = (await db.execute(select(BudgetPeriod).where(
        BudgetPeriod.scope == scope, BudgetPeriod.period_start <= now,
        BudgetPeriod.period_end > now))).scalars().all()
    budget_cap_ok = len(periods) <= 1 and all(
        period.spent_usd + period.reserved_usd <= period.limit_usd for period in periods)

    # 4. Latencies for completed jobs
    stmt_latencies = (
        select(
            func.avg(func.extract("epoch", Job.updated_at - Job.created_at)),
        )
        .where(Job.status == JobStatus.SUCCEEDED)
    )
    avg_exec_sec = (await db.execute(stmt_latencies)).scalar()

    # 5. Human review latency (application received_at to attested decision)
    stmt_decisions = (
        select(
            func.count(Decision.id),
            func.avg(func.extract("epoch", Decision.created_at - Application.received_at)),
        )
        .join(Application, Decision.application_id == Application.id)
    )
    total_decisions, avg_decision_wait_sec = (await db.execute(stmt_decisions)).one()

    # Queue age is measured; the schema has no separate first-start timestamp,
    # so execution time and average queue wait must not be fabricated.
    oldest_queued = (await db.execute(select(func.min(Job.created_at)).where(
        Job.status.in_([JobStatus.QUEUED, JobStatus.RETRY_WAIT]),
        Job.available_at <= now))).scalar()
    oldest_queue_age = max(0.0, (now - oldest_queued).total_seconds()) if oldest_queued else 0.0
    expired_running = (await db.execute(select(func.count(Job.id)).where(
        Job.status == JobStatus.RUNNING, Job.lease_expires_at <= now))).scalar() or 0
    # 6. SLI Assessment & Reason Codes
    reason_codes = []
    queue_ok = oldest_queue_age <= 60.0
    if not queue_ok:
        reason_codes.append("ALARM_QUEUE_LATENCY_EXCEEDED: Hàng đợi xử lý vượt quá 60 giây.")

    worker_ok = expired_running == 0 and (active_workers_count > 0 or queue_ok)
    if not worker_ok:
        reason_codes.append("ALARM_WORKER_HEARTBEAT_LOST: Có job trong hàng đợi nhưng không có worker active.")

    if not budget_cap_ok:
        reason_codes.append("ALARM_BUDGET_CAP_EXCEEDED: Vượt hạn mức kỳ ngân sách hoặc có nhiều kỳ đang hoạt động.")

    failed_count = recent_counts.get(JobStatus.FAILED.value, 0)
    error_rate = (failed_count / terminal_jobs) if terminal_jobs > 0 else 0.0
    error_rate_ok = error_rate <= 0.05
    if not error_rate_ok:
        reason_codes.append(f"ALARM_ERROR_RATE_HIGH: Tỷ lệ lỗi job {error_rate * 100:.1f}% vượt ngưỡng 5%.")

    return AdminMetricsResponse(
        timestamp_utc=now.isoformat(),
        app_env=settings.APP_ENV,
        pilot_stage=settings.PILOT_STAGE,
        jobs_summary=jobs_summary,
        latencies={
            "avg_queue_wait_seconds": None,
            "avg_worker_exec_seconds": None,
            "oldest_ready_queue_age_seconds": round(oldest_queue_age, 2),
            "avg_job_turnaround_seconds": round(float(avg_exec_sec), 2) if avg_exec_sec is not None else None,
        },
        human_review_metrics={
            "total_final_decisions": total_decisions or 0,
            "avg_human_review_hours": round(float(avg_decision_wait_sec) / 3600.0, 2) if avg_decision_wait_sec is not None else None,
        },
        budget_summary={
            "daily_spent_cents": daily_spent_cents,
            "active_periods": [{"id": str(p.id), "limit_usd": float(p.limit_usd),
                                "spent_usd": float(p.spent_usd), "reserved_usd": float(p.reserved_usd)} for p in periods],
            "daily_api_calls": calls_count,
            "rate_card_verified": bool(settings.RATE_CARD_VERIFIED_AT),
        },
        worker_health={
            "active_workers_count": active_workers_count,
            "heartbeat_healthy": worker_ok,
            "expired_running_leases": expired_running,
            "signal": "job_leases_only",
        },
        sli_report=SLIReportDTO(
            queue_latency_ok=queue_ok,
            worker_health_ok=worker_ok,
            budget_cap_ok=budget_cap_ok,
            error_rate_ok=error_rate_ok,
            reason_codes=reason_codes,
        ),
    )


@router.get("/readiness")
async def get_system_readiness(
    db: AsyncSession = Depends(get_db),
):
    """Readiness probe for container orchestration: verifies DB and storage health."""
    # 1. Check DB
    try:
        await db.execute(select(1))
        db_healthy = True
    except Exception:
        db_healthy = False
        await db.rollback()

    # 2. Check Storage
    try:
        base_dir = get_storage_base_dir()
        with tempfile.NamedTemporaryFile(dir=base_dir, prefix=".readiness-") as probe:
            probe.write(b"ready")
            probe.flush()
            os.fsync(probe.fileno())
            probe.seek(0)
            storage_healthy = probe.read() == b"ready"
    except Exception:
        storage_healthy = False

    schema_healthy = False
    if db_healthy:
        try:
            config_path = Path(__file__).resolve().parents[5] / "alembic.ini"
            heads = set(ScriptDirectory.from_config(Config(str(config_path))).get_heads())
            revisions = set((await db.execute(text("SELECT version_num FROM alembic_version"))).scalars().all())
            schema_healthy = revisions == heads
        except Exception:
            await db.rollback()
    is_ready = db_healthy and storage_healthy and schema_healthy
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    if not is_ready:
        raise HTTPException(
            status_code=status_code,
            detail={
                "status": "not_ready",
                "database": db_healthy,
                "storage": storage_healthy,
                "schema": schema_healthy,
            },
        )

    return {
        "status": "ready",
        "database": db_healthy,
        "storage": storage_healthy,
        "schema": schema_healthy,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
