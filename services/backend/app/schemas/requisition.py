"""Pydantic schemas and DTOs for Requisition, Membership, and JD Version."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import MembershipRole, RequisitionStatus


class RequisitionCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=200, description="Tên vị trí hoặc mã yêu cầu tuyển dụng")
    owner_user_id: Optional[uuid.UUID] = Field(default=None, description="User ID sở hữu requisition (dành cho Admin)")
    organization_id: Optional[uuid.UUID] = Field(default=None, description="ID tổ chức (mặc định lấy theo context)")


class RequisitionUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    status: Optional[RequisitionStatus] = None
    reason: Optional[str] = Field(default=None, max_length=500, description="Lý do chuyển trạng thái (bắt buộc khi đóng/tạm dừng/mở lại)")
    expected_version: Optional[int] = Field(default=None, description="Row version cho optimistic locking")


class RequisitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    title: str
    status: RequisitionStatus
    current_jd_version_id: Optional[uuid.UUID] = None
    current_rubric_version_id: Optional[uuid.UUID] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    row_version: int
    created_at: datetime
    updated_at: datetime
    my_role: Optional[str] = None


class RequisitionDetailResponse(RequisitionResponse):
    counts: dict[str, int] = Field(default_factory=dict)
    current_jd: Optional[dict[str, Any]] = None
    current_rubric: Optional[dict[str, Any]] = None


class MemberAddUpdateRequest(BaseModel):
    membership_role: MembershipRole = MembershipRole.REVIEWER
    expected_requisition_version: Optional[int] = Field(default=None, description="Expected requisition row_version")


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    login_name: str
    display_name: str
    membership_role: MembershipRole
    active: bool
    assigned_at: datetime


class JDVersionCreateRequest(BaseModel):
    source_text: str = Field(min_length=50, description="Nội dung JD Markdown đầy đủ")
    change_reason: str = Field(min_length=3, max_length=500, description="Lý do cập nhật hoặc mô tả phiên bản JD")
    expected_requisition_version: Optional[int] = Field(default=None, description="Expected requisition row_version")


class JDVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requisition_id: uuid.UUID
    version_no: int
    text_hash: str
    source_refs: Optional[dict[str, Any]] = None
    egress_reviewed_by: Optional[uuid.UUID] = None
    egress_reviewed_at: Optional[datetime] = None
    created_by: uuid.UUID
    created_at: datetime


class JDVersionDetailResponse(JDVersionResponse):
    source_text: str


class JDEgressApproveRequest(BaseModel):
    expected_text_hash: str = Field(description="Mã hash SHA-256 của JD dự kiến phê duyệt")
    acknowledged: bool = Field(description="Xác nhận kiểm tra nội dung JD trước khi gửi LLM")
