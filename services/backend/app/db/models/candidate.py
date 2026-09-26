"""Candidate, CandidateIdentity, Application and RawAccessGrant models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, RowVersionMixin, TimestampMixin, utc_now


class CandidateStatus(str):
    ACTIVE = "active"
    DELETION_PENDING = "deletion_pending"
    DELETED = "deleted"


class ApplicationStatus(str):
    ACTIVE = "active"
    DELETION_PENDING = "deletion_pending"
    DELETED = "deleted"


class Candidate(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "candidates"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Pseudonymized public label e.g. "CAND-001" (does NOT contain personal info)
    public_label: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)

    organization = relationship("Organization", back_populates="candidates")
    identity = relationship("CandidateIdentity", back_populates="candidate", uselist=False, cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="candidate", cascade="all, delete-orphan")


class CandidateIdentity(Base):
    __tablename__ = "candidate_identities"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    provided_by: Mapped[str] = mapped_column(String(100), default="direct_cv", nullable=False)
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    candidate = relationship("Candidate", back_populates="identity")


class Application(Base, PrimaryKeyMixin, TimestampMixin, RowVersionMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("requisition_id", "candidate_id", name="uq_application_requisition_candidate"),
        Index("ix_applications_req_received", "requisition_id", "received_at", "id"),
    )

    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requisitions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)
    current_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_sanitized_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_assessment_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    current_decision_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    requisition = relationship("Requisition", back_populates="applications")
    candidate = relationship("Candidate", back_populates="applications")
    documents = relationship("Document", back_populates="application", cascade="all, delete-orphan")
    sanitized_versions = relationship("SanitizedVersion", back_populates="application", cascade="all, delete-orphan")
    assessment_runs = relationship("AssessmentRun", back_populates="application", cascade="all, delete-orphan")
    hr_revisions = relationship("HRRevision", back_populates="application", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="application", cascade="all, delete-orphan")
    raw_grants = relationship("RawAccessGrant", back_populates="application", cascade="all, delete-orphan")


class RawAccessGrant(Base, PrimaryKeyMixin):
    __tablename__ = "raw_access_grants"

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    grantee_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    scopes: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application = relationship("Application", back_populates="raw_grants")
    grantee = relationship("User", foreign_keys=[grantee_user_id])
    granter = relationship("User", foreign_keys=[granted_by])
