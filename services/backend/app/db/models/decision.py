"""ReviewAttestation and Decision models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, utc_now
from app.domain.enums import DecisionBasis, DecisionOutcome


class ReviewAttestation(Base, PrimaryKeyMixin):
    __tablename__ = "review_attestations"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision_basis: Mapped[DecisionBasis] = mapped_column(
        SAEnum(DecisionBasis, name="decision_basis"),
        nullable=False,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    hr_revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rubric_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    application_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reviewed_criterion_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    manual_evidence_refs: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    technical_failure_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    failure_ref: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    raw_view_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    actor = relationship("User")
    application = relationship("Application")


class Decision(Base, PrimaryKeyMixin):
    __tablename__ = "decisions"
    __table_args__ = (
        UniqueConstraint("application_id", "sequence_no", name="uq_decision_app_sequence_no"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    decision_basis: Mapped[DecisionBasis] = mapped_column(
        SAEnum(DecisionBasis, name="decision_basis"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rubric_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    outcome: Mapped[DecisionOutcome] = mapped_column(
        SAEnum(DecisionOutcome, name="decision_outcome"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attestation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("review_attestations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    hr_revision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hr_revisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supersedes_decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application = relationship("Application", back_populates="decisions")
    decider = relationship("User", foreign_keys=[decided_by])
    attestation = relationship("ReviewAttestation")
