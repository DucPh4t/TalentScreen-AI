"""Document, SanitizedVersion, SourceSpan, and RetrievalChunk models."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, utc_now
from app.domain.enums import DocumentSafetyStatus, SanitizedVersionStatus


class Document(Base, PrimaryKeyMixin):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("application_id", "version_no", name="uq_document_application_version"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(50), default="cv", nullable=False)
    original_name_private: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_verified: Mapped[str] = mapped_column(String(100), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    blob_key: Mapped[str] = mapped_column(String(255), nullable=False)
    ingestion_status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    rendered_pdf_blob_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    safety_status: Mapped[DocumentSafetyStatus] = mapped_column(
        SAEnum(DocumentSafetyStatus, name="document_safety_status"),
        default=DocumentSafetyStatus.PENDING,
        nullable=False,
    )
    parser_manifest: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    quality_report: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    raw_text_blob_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    application = relationship("Application", back_populates="documents")
    sanitized_versions = relationship("SanitizedVersion", back_populates="document", cascade="all, delete-orphan")


class SanitizedVersion(Base, PrimaryKeyMixin):
    __tablename__ = "sanitized_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_sanitized_document_version"),
    )

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SanitizedVersionStatus] = mapped_column(
        SAEnum(SanitizedVersionStatus, name="sanitized_version_status"),
        default=SanitizedVersionStatus.DRAFT,
        index=True,
        nullable=False,
    )
    canonical_text: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalizer_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    sanitizer_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    mapping_blob_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quality_flags: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
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

    application = relationship("Application", back_populates="sanitized_versions")
    document = relationship("Document", back_populates="sanitized_versions")
    spans = relationship("SourceSpan", back_populates="sanitized_version", cascade="all, delete-orphan")
    chunks = relationship("RetrievalChunk", back_populates="sanitized_version", cascade="all, delete-orphan")


class SourceSpan(Base):
    __tablename__ = "source_spans"
    __table_args__ = (
        UniqueConstraint("sanitized_version_id", "start_cp", "end_cp", name="uq_source_span_coords"),
    )

    span_id: Mapped[str] = mapped_column(String(32), primary_key=True)  # Format: "spn_" + 24 hex
    full_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sanitized_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanitized_versions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    start_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    end_cp: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    section_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="vi", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    sanitized_version = relationship("SanitizedVersion", back_populates="spans")


class RetrievalChunk(Base, PrimaryKeyMixin):
    __tablename__ = "retrieval_chunks"
    __table_args__ = (
        UniqueConstraint("sanitized_version_id", "chunk_index", "embedding_config_id", name="uq_chunk_version_idx_config"),
    )

    sanitized_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sanitized_versions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    span_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(Vector(768), nullable=True)
    embedding_config_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    sanitized_version = relationship("SanitizedVersion", back_populates="chunks")
