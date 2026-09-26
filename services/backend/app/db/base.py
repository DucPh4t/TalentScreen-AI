"""Base declarative model and standard mixins for TalentScreen AI."""
from datetime import datetime, timezone
import uuid
from sqlalchemy import BigInteger, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class PrimaryKeyMixin:
    """Standard UUID v4 primary key for all entity tables."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Standard created_at and updated_at timestamps in UTC."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class RowVersionMixin:
    """Optimistic locking row_version for mutable business entities."""
    row_version: Mapped[int] = mapped_column(
        BigInteger,
        default=1,
        nullable=False,
    )
