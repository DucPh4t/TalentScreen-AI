"""Explicit contracts for human review, preparation and round conclusions."""
from datetime import datetime
from typing import Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.decision import EffectiveResultRef
from app.domain.enums import DecisionOutcome

class ReviewProgressUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_hash: str = Field(min_length=64, max_length=64)
    expected_version: int = Field(ge=0)
    reviewed_criterion_ids: list[str] = Field(max_length=12)

class ScreeningDecisionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    effective_result: EffectiveResultRef
    reviewed_criterion_ids: list[str] = Field(min_length=2, max_length=12)
    acknowledged: Literal[True]
    outcome: DecisionOutcome
    reason: str = Field(min_length=20, max_length=2000)
    expected_previous_decision_id: uuid.UUID | None = None
    expected_rubric_version_id: uuid.UUID

class InterviewRoundUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=0)
    source_hash: str = Field(min_length=64, max_length=64)
    label: str = Field(min_length=3, max_length=120)
    focus_criterion_ids: list[str] = Field(min_length=1, max_length=12)
    interviewer_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    starts_at: datetime | None = None
    duration_minutes: int = Field(ge=15, le=180)
    channel: Literal['online', 'onsite', 'phone']
    meeting_location: str = Field(default='', max_length=500)

    @field_validator('starts_at')
    @classmethod
    def timezone_required(cls, value):
        if value and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError('Thời gian phỏng vấn cần có múi giờ.')
        return value

class InterviewConclusionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(ge=1)
    outcome: Literal['advance', 'request_information', 'not_advance', 'propose_hire']
    reason: str = Field(min_length=20, max_length=2000)
