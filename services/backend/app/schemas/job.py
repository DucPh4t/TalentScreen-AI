"""Pydantic schemas and DTOs for Job monitoring and cancellation."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import JobStatus, JobType


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: JobType
    status: JobStatus
    target_type: str
    target_id: uuid.UUID
    priority: int
    available_at: datetime
    lease_owner: Optional[str] = None
    lease_epoch: int
    lease_expires_at: Optional[datetime] = None
    claim_count: int
    cancel_requested_at: Optional[datetime] = None
    last_error_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class JobCancelRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500, description="Lý do hủy tác vụ")


class JobCancelResponse(BaseModel):
    id: uuid.UUID
    status: str
    message: str
