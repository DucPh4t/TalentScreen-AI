"""Organization, User, Role, Session and Onboarding models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, Enum as SAEnum, ForeignKey, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, RowVersionMixin, TimestampMixin, utc_now
from app.domain.enums import AccountRole, EnvironmentMode, PilotStage, UserStatus


class Organization(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[EnvironmentMode] = mapped_column(
        SAEnum(EnvironmentMode, name="environment_mode"),
        default=EnvironmentMode.SANDBOX,
        nullable=False,
    )
    pilot_stage: Mapped[Optional[PilotStage]] = mapped_column(
        SAEnum(PilotStage, name="pilot_stage"),
        nullable=True,
    )
    stage_gate_report_refs: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    policy_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    policy_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)

    # Relationships
    requisitions = relationship("Requisition", back_populates="organization", cascade="all, delete-orphan")
    candidates = relationship("Candidate", back_populates="organization", cascade="all, delete-orphan")


class User(Base, PrimaryKeyMixin, TimestampMixin, RowVersionMixin):
    __tablename__ = "users"

    login_name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"),
        default=UserStatus.ACTIVE,
        nullable=False,
    )
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    session_generation: Mapped[int] = mapped_column(BigInteger, default=1, nullable=False)

    # Relationships
    account_roles = relationship("UserAccountRole", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("SessionRecord", back_populates="user", cascade="all, delete-orphan")
    memberships = relationship("RequisitionMembership", back_populates="user", cascade="all, delete-orphan")


class UserAccountRole(Base):
    __tablename__ = "user_account_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[AccountRole] = mapped_column(
        SAEnum(AccountRole, name="account_role"),
        primary_key=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    user = relationship("User", back_populates="account_roles")


class SessionRecord(Base, PrimaryKeyMixin):
    __tablename__ = "sessions"

    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    csrf_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    user_session_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user = relationship("User", back_populates="sessions")


class OnboardingProgress(Base):
    __tablename__ = "onboarding_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    walkthrough_version: Mapped[str] = mapped_column(String(50), primary_key=True)
    completed_steps: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sandbox_exercise_result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    user = relationship("User")
