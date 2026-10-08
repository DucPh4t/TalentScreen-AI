"""Private review progress and versioned interview-round preparation."""
from typing import Any
import uuid
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, PrimaryKeyMixin, RowVersionMixin, TimestampMixin

class ReviewProgress(Base, PrimaryKeyMixin, RowVersionMixin, TimestampMixin):
    __tablename__ = 'review_progress'
    __table_args__ = (UniqueConstraint('application_id', 'user_id', name='uq_review_progress_actor'),)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'))
    source_hash: Mapped[str] = mapped_column(String(64))
    reviewed_criterion_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)

class InterviewRound(Base, PrimaryKeyMixin, RowVersionMixin, TimestampMixin):
    __tablename__ = 'interview_rounds'
    __table_args__ = (UniqueConstraint('application_id', 'round_no', name='uq_interview_round_application'),)
    application_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('applications.id', ondelete='CASCADE'), index=True)
    round_no: Mapped[int] = mapped_column(Integer)
    source_hash: Mapped[str] = mapped_column(String(64))
    preparation: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    conclusions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
