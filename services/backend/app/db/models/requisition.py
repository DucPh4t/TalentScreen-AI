"""Requisition, Membership, JD Version, Rubric Version and Rubric Criteria models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, RowVersionMixin, TimestampMixin, utc_now
from app.domain.enums import MembershipRole, RequisitionStatus, RubricStatus


class Requisition(Base, PrimaryKeyMixin, TimestampMixin, RowVersionMixin):
    __tablename__ = "requisitions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[RequisitionStatus] = mapped_column(
        SAEnum(RequisitionStatus, name="requisition_status"),
        default=RequisitionStatus.DRAFT,
        index=True,
        nullable=False,
    )
    current_jd_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    current_rubric_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization = relationship("Organization", back_populates="requisitions")
    memberships = relationship("RequisitionMembership", back_populates="requisition", cascade="all, delete-orphan")
    jd_versions = relationship("JDVersion", back_populates="requisition", cascade="all, delete-orphan")
    rubric_versions = relationship("RubricVersion", back_populates="requisition", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="requisition", cascade="all, delete-orphan")


class RequisitionMembership(Base):
    __tablename__ = "requisition_memberships"

    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requisitions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    membership_role: Mapped[MembershipRole] = mapped_column(
        SAEnum(MembershipRole, name="membership_role"),
        default=MembershipRole.REVIEWER,
        nullable=False,
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    requisition = relationship("Requisition", back_populates="memberships")
    user = relationship("User", back_populates="memberships")


class JDVersion(Base, PrimaryKeyMixin):
    __tablename__ = "jd_versions"
    __table_args__ = (
        UniqueConstraint("requisition_id", "version_no", name="uq_jd_version_requisition_no"),
    )

    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requisitions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_refs: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    egress_reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    egress_reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    requisition = relationship("Requisition", back_populates="jd_versions")
    rubric_versions = relationship("RubricVersion", back_populates="jd_version")


class RubricVersion(Base, PrimaryKeyMixin):
    __tablename__ = "rubric_versions"
    __table_args__ = (
        UniqueConstraint("requisition_id", "version_no", name="uq_rubric_version_requisition_no"),
    )

    requisition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("requisitions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    jd_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jd_versions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RubricStatus] = mapped_column(
        SAEnum(RubricStatus, name="rubric_status"),
        default=RubricStatus.DRAFT,
        index=True,
        nullable=False,
    )
    threshold_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    requisition = relationship("Requisition", back_populates="rubric_versions")
    jd_version = relationship("JDVersion", back_populates="rubric_versions")
    criteria = relationship("RubricCriterion", back_populates="rubric_version", cascade="all, delete-orphan")


class RubricCriterion(Base):
    __tablename__ = "rubric_criteria"

    rubric_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    criterion_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    label_vi: Mapped[str] = mapped_column(String(200), nullable=False)
    description_vi: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    anchors: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    jd_evidence_refs: Mapped[Optional[list[Any]]] = mapped_column(JSONB, nullable=True)
    bilingual_terms: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    rubric_version = relationship("RubricVersion", back_populates="criteria")
