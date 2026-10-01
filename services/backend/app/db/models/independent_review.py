"""Human labels recorded before AI results are revealed in shadow mode."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, utc_now


class IndependentReview(Base, PrimaryKeyMixin):
    __tablename__ = "independent_reviews"
    __table_args__ = (
        UniqueConstraint("application_id", "reviewer_id", "application_generation", "rubric_version_id", name="uq_independent_review_snapshot_reviewer"),
        Index("ix_independent_reviews_reviewer", "reviewer_id", "submitted_at"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    review_kind: Mapped[str] = mapped_column(String(10), nullable=False)  # hr | it; role declared by reviewer
    blind_enforced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    application_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    sanitized_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sanitized_versions.id", ondelete="CASCADE"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rubric_versions.id", ondelete="CASCADE"), nullable=False)
    criterion_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    criterion_statuses: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    criterion_quotes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    criterion_notes: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IndependentReviewDraft(Base, PrimaryKeyMixin):
    __tablename__ = "independent_review_drafts"
    __table_args__ = (UniqueConstraint("application_id", "reviewer_id", name="uq_review_draft_actor"),)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sanitized_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sanitized_versions.id", ondelete="CASCADE"), nullable=False)
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rubric_versions.id", ondelete="CASCADE"), nullable=False)
    application_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
