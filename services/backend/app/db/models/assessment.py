"""AssessmentRun, CriterionAssessment, CriterionEvidence, and HRRevision models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, utc_now
from app.domain.enums import CriterionOutcome, Recommendation


class AssessmentRun(Base, PrimaryKeyMixin):
    __tablename__ = "assessment_runs"
    __table_args__ = (
        UniqueConstraint("application_id", "run_no", name="uq_assessment_run_app_no"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, index=True, nullable=False)
    run_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued", index=True, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    application_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sanitized_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanitized_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    strategy: Mapped[str] = mapped_column(String(50), default="fulltext", nullable=False)
    output_schema_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    observed_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    coverage: Mapped[float] = mapped_column(Numeric(5, 2), default=0.0, nullable=False)
    comparable_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    recommendation: Mapped[Optional[Recommendation]] = mapped_column(
        SAEnum(Recommendation, name="recommendation_status"),
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    result_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    secondary_model_output: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    jev_explanation: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    rerank_output: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    execution_trace: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application = relationship("Application", back_populates="assessment_runs")
    criteria = relationship("CriterionAssessment", back_populates="assessment_run", cascade="all, delete-orphan")
    evidence = relationship("CriterionEvidence", back_populates="assessment_run", cascade="all, delete-orphan")


class CriterionAssessment(Base):
    __tablename__ = "criterion_assessments"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    criterion_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    status: Mapped[CriterionOutcome] = mapped_column(
        SAEnum(CriterionOutcome, name="criterion_outcome"),
        nullable=False,
    )
    score: Mapped[Optional[int]] = mapped_column(SmallInteger, nullable=True)
    jev_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    jev_probabilities: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    jev_confidence: Mapped[Optional[float]] = mapped_column(Numeric(5, 4), nullable=True)
    score_disposition: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    missing_information: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)

    assessment_run = relationship("AssessmentRun", back_populates="criteria")


class CriterionEvidence(Base):
    __tablename__ = "criterion_evidence"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    criterion_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    span_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("source_spans.span_id", ondelete="RESTRICT"),
        primary_key=True,
    )
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_start_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_end_cp: Mapped[int] = mapped_column(Integer, nullable=False)

    assessment_run = relationship("AssessmentRun", back_populates="evidence")
    span = relationship("SourceSpan")


class HRRevision(Base, PrimaryKeyMixin):
    __tablename__ = "hr_revisions"
    __table_args__ = (
        UniqueConstraint("application_id", "revision_no", name="uq_hr_revision_app_no"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    base_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sanitized_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanitized_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)  # draft | finalized
    criteria_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    change_reasons: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    proposed_decision: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    summary_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    finalized_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    finalized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    observed_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    coverage: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    comparable_score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    recommendation: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application = relationship("Application", back_populates="hr_revisions")
    author = relationship("User", foreign_keys=[created_by])
    finalizer = relationship("User", foreign_keys=[finalized_by])
