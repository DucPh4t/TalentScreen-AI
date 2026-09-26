"""Pydantic schemas for data deletion, retention policy, and verification reports (Task B17)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DeletionScope, DeletionStatus


class DeletionRequestCreate(BaseModel):
    """Payload to request deletion of an application or candidate."""
    scope: DeletionScope
    target_id: uuid.UUID
    reason_category: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Reason for deletion: candidate_request, gdpr_erasure, retention_policy, data_cleanup",
    )


class DeletionRequestResponse(BaseModel):
    """Response representing a DeletionRequest record and its verification status."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope: DeletionScope
    target_id: uuid.UUID
    status: DeletionStatus
    local_purge_complete: bool
    local_purge_completed_at: Optional[datetime] = None
    backup_status: str
    backup_expiry_at: Optional[datetime] = None
    external_retention_status: str
    reason_category: str
    requested_by: uuid.UUID
    requested_at: datetime
    completed_at: Optional[datetime] = None
    inventory: Optional[dict[str, Any]] = None
    verification_report: Optional[dict[str, Any]] = None
    job_id: Optional[uuid.UUID] = None


class RetentionPolicyResponse(BaseModel):
    """Organization retention policy configuration and TTL metadata."""
    sandbox_ttl_days: int = 30
    temp_file_ttl_hours: int = 24
    backup_retention_days: int = 7
    active_policy_name: str = "TalentScreen Baseline Retention Policy v1"
    responsible_role: str = "Data Protection Officer / Requisition Owner"
    description: str = (
        "Active candidates retained during open requisition. "
        "Deleted applications purged from active storage immediately. "
        "Rolling backups expire in 7 days. "
        "External LLM retention governed by non-training agreement."
    )


class RetentionSweepResponse(BaseModel):
    """Result of a retention sweep operation."""
    swept_temp_files_count: int
    swept_expired_backups_count: int
    executed_at: datetime
