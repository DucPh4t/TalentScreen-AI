"""Pydantic schemas for Sanitization, HR approval, Raw Access Grants, and Source Viewer."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import SanitizedVersionStatus


class SanitizedVersionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    document_id: uuid.UUID
    version_no: int
    status: SanitizedVersionStatus
    sha256: str
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime


class SanitizedVersionDetailResponse(SanitizedVersionSummaryResponse):
    canonical_text: str
    normalizer_version: str
    sanitizer_version: str
    quality_flags: Optional[dict[str, Any]] = None


class SanitizedEditRequest(BaseModel):
    base_version_id: uuid.UUID
    canonical_text: str = Field(min_length=10, description="Văn bản đã chuẩn hóa và che PII mới")
    edit_reason: str = Field(min_length=5, max_length=500, description="Lý do chỉnh sửa bản nguồn")


class SanitizedApproveRequest(BaseModel):
    expected_application_version: int
    expected_sha256: str = Field(min_length=64, max_length=64, description="SHA256 của canonical_text để kiểm tra tính toàn vẹn")
    acknowledged: bool = Field(default=True, description="Xác nhận đã rà soát trước khi cho phép AI xử lý")


class SanitizedRevokeRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500, description="Lý do thu hồi bản sanitized")
    expected_application_version: int


class RawGrantCreateRequest(BaseModel):
    grantee_user_id: uuid.UUID
    scopes: list[str] = Field(default=["raw_cv"], description="Danh sách phạm vi quyền (ví dụ: raw_cv, identity)")
    expires_at: datetime
    reason: str = Field(min_length=5, max_length=500, description="Lý do cấp quyền đọc raw CV")


class RawGrantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    grantee_user_id: uuid.UUID
    scopes: list[str]
    granted_by: uuid.UUID
    reason: str
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime
