"""Pydantic schemas and DTOs for Application Intake and Document Upload."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ApplicationCreateRequest(BaseModel):
    candidate_id: Optional[uuid.UUID] = Field(default=None, description="Optional existing candidate UUID")


class ApplicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requisition_id: uuid.UUID
    candidate_id: uuid.UUID
    public_label: str
    status: str
    generation: int
    row_version: int
    current_document_id: Optional[uuid.UUID] = None
    current_sanitized_version_id: Optional[uuid.UUID] = None
    current_assessment_run_id: Optional[uuid.UUID] = None
    current_decision_id: Optional[uuid.UUID] = None
    received_at: datetime


class DocumentSummaryDTO(BaseModel):
    id: uuid.UUID
    version_no: int
    ingestion_status: str
    byte_size: int
    mime_verified: str
    created_at: datetime
    original_filename: Optional[str] = None  # Populated ONLY when caller has active raw grant


class ApplicationDetailResponse(ApplicationResponse):
    documents: list[DocumentSummaryDTO] = Field(default_factory=list)


class DocumentUploadedDTO(BaseModel):
    id: uuid.UUID
    version_no: int
    ingestion_status: str
    byte_size: int


class DocumentUploadResponse(BaseModel):
    document: DocumentUploadedDTO
    job_id: uuid.UUID
    application_row_version: int
    application_generation: int


class SourceSpanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    span_id: str
    sanitized_version_id: uuid.UUID
    source_hash: str
    coordinate_system: str = "unicode_codepoints_nfc_lf"
    start_cp: int
    end_cp: int
    page_number: Optional[int] = None
    section_label: Optional[str] = None
    text: str
    language: str = "vi"
