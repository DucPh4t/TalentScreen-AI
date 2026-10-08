"""Pydantic schemas for Task B14: Interview Question Bank, Interview Draft, and Revisions."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.decision import EffectiveResultRef


# ---------------- Core Question Bank Schemas ---------------- #


class CoreQuestionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=1, max_length=50)
    criterion_id: str
    question_vi: str = Field(min_length=10, max_length=1000)
    purpose_vi: str = Field(min_length=5, max_length=500)
    answer_indicators: list[str] = Field(min_length=1, max_length=10)


class QuestionBankCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["seed", "clone"] = "seed"
    clone_from_id: Optional[uuid.UUID] = None


class QuestionBankUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[CoreQuestionSchema] = Field(min_length=1, max_length=120)
    change_reason: str = Field(min_length=10, max_length=1000)


class QuestionBankApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_rubric_version_id: uuid.UUID
    acknowledged: Literal[True]


class QuestionBankResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rubric_version_id: uuid.UUID
    version_no: int
    status: str  # draft | approved | superseded
    questions: list[CoreQuestionSchema]
    content_hash: str
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    created_at: datetime


# ---------------- Candidate-Specific Follow-Up Schemas ---------------- #


class FollowupQuestionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    question_vi: str = Field(min_length=1, max_length=600)
    purpose_vi: str = Field(min_length=1, max_length=400)
    source_span_ids: list[str] = Field(default_factory=list, max_length=6)
    answer_indicators: list[str] = Field(min_length=1, max_length=4)


class InterviewOutputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    followups: list[FollowupQuestionSchema] = Field(default_factory=list, max_length=3)


# ---------------- Interview Draft & Revision Schemas ---------------- #


class InterviewDraftCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_result: EffectiveResultRef
    expected_question_bank_id: Optional[uuid.UUID] = None


class InterviewRevisionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_previous_revision_id: Optional[uuid.UUID] = None
    followups: list[FollowupQuestionSchema] = Field(default_factory=list, max_length=6)
    change_reason: str = Field(min_length=10, max_length=1000)


class InterviewRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    interview_draft_id: uuid.UUID
    revision_no: int
    followups: list[FollowupQuestionSchema]
    change_reason: str
    created_by: uuid.UUID
    created_at: datetime


class InterviewDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    question_bank_id: Optional[uuid.UUID] = None
    job_id: uuid.UUID
    status: str  # queued | running | succeeded | failed
    core_questions: list[CoreQuestionSchema]
    ai_followups: list[FollowupQuestionSchema] = Field(default_factory=list)
    latest_revision: Optional[InterviewRevisionResponse] = None
    is_stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)
    created_at: datetime


class InterviewScorecardCriterionSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=80)
    outcome: Literal["assessed", "not_observed", "conflicting_evidence"]
    score: Optional[int] = Field(default=None, ge=0, le=4)
    answer_summary: str = Field(default="", max_length=2000)
    interviewer_note: str = Field(default="", max_length=2000)


class InterviewScorecardUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_no: int = Field(ge=1, le=10)
    expected_version: int = Field(ge=0)
    submit: bool = False
    interview_draft_id: Optional[uuid.UUID] = None
    criteria: list[InterviewScorecardCriterionSchema] = Field(min_length=2, max_length=12)


class InterviewScorecardFinalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class InterviewScorecardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    interviewer_id: uuid.UUID
    interviewer_name: Optional[str] = None
    rubric_version_id: uuid.UUID
    interview_draft_id: Optional[uuid.UUID] = None
    round_no: int
    status: Literal["draft", "finalized"]
    criteria: list[InterviewScorecardCriterionSchema]
    row_version: int
    snapshot_hash: str
    is_stale: bool
    created_at: datetime
    updated_at: datetime
    finalized_at: Optional[datetime] = None
    amendment_history: list[dict] = Field(default_factory=list)


class InterviewScorecardAmendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    criteria: list[InterviewScorecardCriterionSchema] = Field(min_length=2, max_length=12)
    change_reason: str = Field(min_length=20, max_length=1000)
