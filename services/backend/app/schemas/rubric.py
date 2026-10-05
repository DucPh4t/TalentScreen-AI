"""Pydantic schemas and DTOs for Rubric and Criteria management."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import RubricStatus


class ScoringAnchorDTO(BaseModel):
    score: int = Field(ge=0, le=4)
    description: str
    qualifying_evidence: list[str] = Field(default_factory=list)
    not_sufficient: list[str] = Field(default_factory=list)


class SourceRequirementRefDTO(BaseModel):
    requirement_id: str
    quote: str


class CriterionDTO(BaseModel):
    id: str
    label: str
    description: str
    weight: int = Field(gt=0, lt=100)
    core: bool = False
    source_requirements: list[SourceRequirementRefDTO] = Field(default_factory=list)
    scoring_anchors: list[ScoringAnchorDTO]
    bilingual_terms: Optional[dict[str, Any]] = None


class RecommendationPolicyDTO(BaseModel):
    threshold: int = Field(default=70, ge=1, le=100)
    core_minimum_scores: dict[str, int] = Field(default_factory=dict)
    require_full_coverage: bool = True


class RubricCreateRequest(BaseModel):
    jd_version_id: Optional[uuid.UUID] = None
    source: str = Field(default="seed", description="'seed' | 'clone' | 'manual'")
    clone_from_id: Optional[uuid.UUID] = None
    rubric: Optional[dict[str, Any]] = None


class RubricUpdateRequest(BaseModel):
    rubric: dict[str, Any]
    expected_rubric_version: Optional[int] = None


class RubricApproveRequest(BaseModel):
    expected_requisition_version: int
    expected_jd_version_id: uuid.UUID
    acknowledge_thresholds: bool = Field(
        default=True,
        description="Xác nhận đồng ý với ngưỡng điểm 70 và core floor 2",
    )


class RubricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    requisition_id: uuid.UUID
    jd_version_id: uuid.UUID
    version_no: int
    status: RubricStatus
    threshold_config: dict[str, Any]
    content_hash: str
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    criteria: list[CriterionDTO] = Field(default_factory=list)


class RubricApproveResponse(BaseModel):
    status: str = "approved"
    rubric: RubricResponse
    requisition_row_version: int
