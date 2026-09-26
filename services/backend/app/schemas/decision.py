"""Pydantic schemas for Task B13: HR Revisions, Attestation, and Decision Flow."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional, Union
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    CriterionId,
    CriterionOutcome,
    DecisionBasis,
    DecisionOutcome,
    Recommendation,
)
from app.schemas.assessment import CriterionAssessmentSchema


# ---------------- HR Revision Schemas ---------------- #


class SourceSnapshotRefSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    sanitized_version_id: uuid.UUID
    rubric_version_id: uuid.UUID
    application_generation: int = Field(ge=1)


class ChangeReasonItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_code: Literal["missed_evidence", "misinterpreted_role", "wrong_anchor", "source_error", "other"]
    note: str = Field(min_length=20, max_length=2000)


class HRRevisionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_application_version: int = Field(ge=1)
    base_run_id: Optional[uuid.UUID] = None
    source_snapshot_ref: SourceSnapshotRefSchema
    criteria: list[CriterionAssessmentSchema] = Field(min_length=6, max_length=6)
    change_reasons: dict[str, ChangeReasonItemSchema] = Field(default_factory=dict)
    summary_reason: str = Field(min_length=10, max_length=2000)
    proposed_decision: Optional[Literal["advance", "request_information", "not_advance"]] = None


class HRRevisionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision_version: int = Field(default=1, ge=1)
    criteria: list[CriterionAssessmentSchema] = Field(min_length=6, max_length=6)
    change_reasons: dict[str, ChangeReasonItemSchema] = Field(default_factory=dict)
    summary_reason: str = Field(min_length=10, max_length=2000)
    proposed_decision: Optional[Literal["advance", "request_information", "not_advance"]] = None


class HRRevisionFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_application_version: int = Field(ge=1)
    expected_rubric_version_id: uuid.UUID


class HRRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    base_run_id: Optional[uuid.UUID] = None
    document_id: uuid.UUID
    sanitized_version_id: uuid.UUID
    rubric_version_id: uuid.UUID
    application_generation: int
    revision_no: int
    status: str  # draft | finalized
    criteria_payload: dict[str, Any]
    change_reasons: dict[str, Any]
    proposed_decision: Optional[str] = None
    summary_reason: str
    observed_score: Optional[Decimal] = None
    coverage: Optional[Decimal] = None
    comparable_score: Optional[Decimal] = None
    recommendation: Optional[str] = None
    content_hash: Optional[str] = None
    created_by: uuid.UUID
    finalized_by: Optional[uuid.UUID] = None
    finalized_at: Optional[datetime] = None
    created_at: datetime
    is_stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)


# ---------------- Review Attestation Schemas ---------------- #


class EffectiveResultRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["assessment_run", "hr_revision"]
    id: uuid.UUID


class ManualEvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    document_id: uuid.UUID
    page_number: int = Field(ge=1)
    section_label: Optional[str] = None
    note: str = Field(min_length=10, max_length=1000)


class FailureRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["document", "job"]
    id: uuid.UUID


class AttestationAssessmentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_basis: Literal[DecisionBasis.ASSESSMENT_REVIEW] = DecisionBasis.ASSESSMENT_REVIEW
    effective_result: EffectiveResultRef
    reviewed_criterion_ids: list[str] = Field(min_length=6, max_length=6)
    acknowledged: Literal[True]


class AttestationManualDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_basis: Literal[DecisionBasis.MANUAL_DOCUMENT_REVIEW] = DecisionBasis.MANUAL_DOCUMENT_REVIEW
    document_id: uuid.UUID
    expected_document_sha256: str = Field(min_length=64, max_length=64)
    expected_rubric_version_id: uuid.UUID
    reviewed_criterion_ids: list[str] = Field(min_length=6, max_length=6)
    manual_evidence_refs: list[ManualEvidenceRef] = Field(min_length=1)
    acknowledged: Literal[True]


class AttestationTechnicalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_basis: Literal[DecisionBasis.TECHNICAL_INFORMATION_REQUEST] = DecisionBasis.TECHNICAL_INFORMATION_REQUEST
    document_id: uuid.UUID
    expected_document_sha256: str = Field(min_length=64, max_length=64)
    failure_ref: FailureRef
    technical_failure_code: str = Field(min_length=3, max_length=100)
    reviewed_criterion_ids: list[str] = Field(default_factory=list)
    acknowledged: Literal[True]


AttestationCreateRequest = Union[
    AttestationAssessmentReviewRequest,
    AttestationManualDocumentRequest,
    AttestationTechnicalRequest,
]


class ReviewAttestationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    actor_id: uuid.UUID
    decision_basis: DecisionBasis
    run_id: Optional[uuid.UUID] = None
    hr_revision_id: Optional[uuid.UUID] = None
    document_id: uuid.UUID
    document_sha256: str
    rubric_version_id: Optional[uuid.UUID] = None
    snapshot_hash: str
    application_generation: int
    reviewed_criterion_ids: list[str]
    acknowledged_at: datetime
    created_at: datetime


# ---------------- Final Decision Schemas ---------------- #


class DecisionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_basis: DecisionBasis
    outcome: DecisionOutcome
    reason: str = Field(min_length=20, max_length=2000)
    override_reason: Optional[str] = Field(default=None, max_length=2000)
    attestation_id: uuid.UUID
    expected_previous_decision_id: Optional[uuid.UUID] = None
    expected_rubric_version_id: Optional[uuid.UUID] = None


class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    sequence_no: int
    decision_basis: DecisionBasis
    outcome: DecisionOutcome
    reason: str
    override_reason: Optional[str] = None
    attestation_id: uuid.UUID
    run_id: Optional[uuid.UUID] = None
    hr_revision_id: Optional[uuid.UUID] = None
    document_id: uuid.UUID
    rubric_version_id: Optional[uuid.UUID] = None
    decided_by: uuid.UUID
    source_hash: str
    supersedes_decision_id: Optional[uuid.UUID] = None
    created_at: datetime
