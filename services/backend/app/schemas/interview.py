"""Pydantic schemas for Task B14: Interview Question Bank, Interview Draft, and Revisions."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
import uuid
from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CriterionId
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

    questions: list[CoreQuestionSchema] = Field(min_length=6, max_length=6)
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
    expected_question_bank_id: uuid.UUID


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
    question_bank_id: uuid.UUID
    job_id: uuid.UUID
    status: str  # queued | running | succeeded | failed
    core_questions: list[CoreQuestionSchema]
    ai_followups: list[FollowupQuestionSchema] = Field(default_factory=list)
    latest_revision: Optional[InterviewRevisionResponse] = None
    is_stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list)
    created_at: datetime
