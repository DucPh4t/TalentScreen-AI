"""Pydantic schemas and strict validators for Assessment outputs according to contracts/assessment-output.schema.json."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import CriterionOutcome, Recommendation


class EvidenceItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_id: str = Field(pattern=r"^spn_[0-9a-f]{24}$", description="Mã định danh source span dạng spn_ + 24 ký tự hex")
    quote: str = Field(min_length=1, max_length=1200, description="Toàn bộ nội dung chính xác của source span")


class CriterionAssessmentSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,49}$")
    status: CriterionOutcome
    score: Optional[int] = Field(default=None, ge=0, le=4)
    evidence: list[EvidenceItemSchema] = Field(default_factory=list, max_length=6)
    rationale: str = Field(min_length=1, max_length=1200)
    missing_information: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_conditional_invariants(self) -> CriterionAssessmentSchema:
        # Invariant checks for assessed status
        if self.status == CriterionOutcome.ASSESSED:
            if self.score is None:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái assessed bắt buộc phải có điểm (0..4).")
            if len(self.evidence) < 1:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái assessed bắt buộc phải có ít nhất 1 evidence.")
            if len(self.missing_information) > 0:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái assessed không được chứa missing_information.")

        # Invariant checks for insufficient_evidence status
        elif self.status == CriterionOutcome.INSUFFICIENT_EVIDENCE:
            if self.score is not None:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái insufficient_evidence bắt buộc điểm phải là null.")
            if len(self.missing_information) < 1:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái insufficient_evidence bắt buộc phải có ít nhất 1 mục cần làm rõ.")

        # Invariant checks for conflicting_evidence status
        elif self.status == CriterionOutcome.CONFLICTING_EVIDENCE:
            if self.score is not None:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái conflicting_evidence bắt buộc điểm phải là null.")
            if len(self.evidence) < 2:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái conflicting_evidence bắt buộc phải có ít nhất 2 evidence mâu thuẫn.")
            if len(self.missing_information) < 1:
                raise ValueError(f"Tiêu chí '{self.criterion_id}' ở trạng thái conflicting_evidence bắt buộc phải có ít nhất 1 mục cần xác minh.")

        # Disallow duplicate spans in the same criterion evidence list
        span_ids = [e.span_id for e in self.evidence]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError(f"Tiêu chí '{self.criterion_id}' chứa span_id trùng lặp trong evidence.")

        return self


class AssessmentOutputSchema(BaseModel):
    """Strictly validate a unique set of criteria from the approved role rubric."""
    model_config = ConfigDict(extra="forbid")

    criteria: list[CriterionAssessmentSchema] = Field(min_length=2, max_length=12)

    @model_validator(mode="after")
    def validate_unique_criteria(self) -> AssessmentOutputSchema:
        present_ids = [c.criterion_id for c in self.criteria]
        if len(present_ids) != len(set(present_ids)):
            raise ValueError("Đầu ra chứa criterion_id trùng lặp.")
        return self


class AssessmentRunCreateRequest(BaseModel):
    sanitized_version_id: uuid.UUID
    rubric_version_id: uuid.UUID


class CriterionEvidenceResponse(BaseModel):
    span_id: str
    quote: str
    resolved_start_cp: int
    resolved_end_cp: int


class CriterionAssessmentResponse(BaseModel):
    criterion_id: str
    status: CriterionOutcome
    score: Optional[int] = None
    rationale: str
    missing_information: Optional[list[str]] = None
    evidence: list[CriterionEvidenceResponse] = []


class AssessmentRunResponse(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    run_no: int
    status: str
    observed_score: Optional[float] = None
    coverage: float
    comparable_score: Optional[float] = None
    recommendation: Optional[Recommendation] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failure_code: Optional[str] = None
    secondary_model_output: Optional[dict[str, Any]] = None
    criteria: list[CriterionAssessmentResponse] = []
    is_stale: bool = False
