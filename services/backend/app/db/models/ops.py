"""Operations, Jobs, Queue, LLM Invocations, Budget, Idempotency, Audit and Deletion models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, TimestampMixin, utc_now
from app.domain.enums import BudgetScope, DeletionScope, DeletionStatus, JobStatus, JobType, LLMInvocationStatus


class Job(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_claimable", "priority", "available_at", "created_at"),
    )

    type: Mapped[JobType] = mapped_column(
        SAEnum(JobType, name="job_type"),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"),
        default=JobStatus.QUEUED,
        index=True,
        nullable=False,
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    input_snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_ref: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    lease_owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    lease_epoch: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancel_requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    llm_invocations = relationship("LLMInvocation", back_populates="job", cascade="all, delete-orphan")


class LLMInvocation(Base, PrimaryKeyMixin):
    __tablename__ = "llm_invocations"
    __table_args__ = (
        UniqueConstraint("job_id", "logical_step", "attempt_no", name="uq_llm_invocation_step_attempt"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    logical_step: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[LLMInvocationStatus] = mapped_column(
        SAEnum(LLMInvocationStatus, name="llm_invocation_status"),
        default=LLMInvocationStatus.RESERVED,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_resolved: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_blob_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    response_blob_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_reserved: Mapped[float] = mapped_column(Numeric(18, 8), default=0.0, nullable=False)
    cost_actual: Mapped[Optional[float]] = mapped_column(Numeric(18, 8), nullable=True)
    rate_card_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    admitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    job = relationship("Job", back_populates="llm_invocations")


class BudgetPeriod(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "budget_periods"
    __table_args__ = (
        UniqueConstraint("scope", "period_start", "period_end", name="uq_budget_period_scope_window"),
    )

    scope: Mapped[BudgetScope] = mapped_column(
        SAEnum(BudgetScope, name="budget_scope"),
        nullable=False,
    )
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    limit_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    reserved_usd: Mapped[float] = mapped_column(Numeric(18, 8), default=0.0, nullable=False)
    spent_usd: Mapped[float] = mapped_column(Numeric(18, 8), default=0.0, nullable=False)
    rate_card_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)


class BudgetReservation(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "budget_reservations"

    budget_period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("budget_periods.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    amount_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    settled_usd: Mapped[float] = mapped_column(Numeric(18, 8), default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="reserved", nullable=False)


class IdempotencyRecord(Base, PrimaryKeyMixin):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("actor_id", "method", "route_scope", "key", name="uq_idempotency_actor_method_route_key"),
    )

    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    route_scope: Mapped[str] = mapped_column(String(100), nullable=False)
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="processing", nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resource_ref: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AuditEvent(Base, PrimaryKeyMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_action", "occurred_at", "action"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)  # user | worker | system
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    before_version: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    after_version: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    outcome: Mapped[str] = mapped_column(String(50), default="success", nullable=False)
    safe_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class DeletionRequest(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "deletion_requests"

    scope: Mapped[DeletionScope] = mapped_column(
        SAEnum(DeletionScope, name="deletion_scope"),
        nullable=False,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    status: Mapped[DeletionStatus] = mapped_column(
        SAEnum(DeletionStatus, name="deletion_status"),
        default=DeletionStatus.REQUESTED,
        index=True,
        nullable=False,
    )
    local_purge_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_purge_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    backup_status: Mapped[str] = mapped_column(String(50), default="pending_expiry", nullable=False)
    backup_expiry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    external_retention_status: Mapped[str] = mapped_column(String(50), default="not_applicable", nullable=False)
    reason_category: Mapped[str] = mapped_column(String(100), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    inventory: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    verification_report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
