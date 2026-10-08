"""Versioned, strict contracts for synthetic inputs and reference annotations."""
from __future__ import annotations
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from app.schemas.rubric import CriterionDTO

ProfileName = Literal['full_text', 'dense', 'hybrid', 'hybrid_agent']
PROFILES: tuple[ProfileName, ...] = ('full_text', 'dense', 'hybrid', 'hybrid_agent')

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)

class CaseInput(Contract):
    case_id: str = Field(pattern=r'^[a-z][a-z0-9-]{1,49}$')
    cluster_id: str = Field(pattern=r'^[a-z][a-z0-9-]{1,49}$')
    role_family: str
    language: Literal['vi', 'en', 'mixed']
    scenario_tags: tuple[str, ...]
    split: Literal['development', 'public_test']
    cv_text: str = Field(min_length=1, max_length=100000)
    jd_ref: str
    rubric_ref: str

class RoleInput(Contract):
    title: str
    jd_text: str = Field(min_length=50)
    criteria: tuple[CriterionDTO, ...] = Field(min_length=2, max_length=12)
    policy: dict = Field(default_factory=lambda: {'threshold': 70, 'core_minimum_scores': {}, 'require_full_coverage': True})

    @model_validator(mode='after')
    def valid_rubric(self):
        ids = [c.id for c in self.criteria]
        if len(ids) != len(set(ids)) or sum(c.weight for c in self.criteria) != 100:
            raise ValueError('INVALID_RUBRIC')
        for c in self.criteria:
            if {a.score for a in c.scoring_anchors} != {0, 1, 2, 3, 4}:
                raise ValueError('INVALID_ANCHORS')
            if not c.source_requirements or any(r.quote not in self.jd_text for r in c.source_requirements):
                raise ValueError('INVALID_JD_REFERENCE')
        return self

class EvidenceReference(Contract):
    span_id: str = Field(pattern=r'^spn_[0-9a-f]{24}$')
    quote: str = Field(min_length=1, max_length=1200)

class CriterionReference(Contract):
    status: Literal['assessed', 'insufficient_evidence', 'conflicting_evidence']
    score: StrictInt | None
    sufficient_evidence_groups: tuple[tuple[EvidenceReference, ...], ...] = ()
    clarification_expectation: str = ''
    explanation: str = Field(min_length=1)
    annotation_complete: bool = True

    @model_validator(mode='after')
    def valid_status(self):
        if self.status == 'assessed':
            if self.score is None or not 0 <= self.score <= 4 or not self.sufficient_evidence_groups:
                raise ValueError('INVALID_ASSESSED_REFERENCE')
        elif self.score is not None or not self.clarification_expectation:
            raise ValueError('INVALID_NULLABLE_REFERENCE')
        if self.status == 'conflicting_evidence' and (not self.sufficient_evidence_groups or any(len(g) < 2 for g in self.sufficient_evidence_groups)):
            raise ValueError('INVALID_CONFLICT_REFERENCE')
        if any(not g or len({e.span_id for e in g}) != len(g) for g in self.sufficient_evidence_groups):
            raise ValueError('INVALID_EVIDENCE_GROUP')
        return self

class CaseReference(Contract):
    case_id: str
    origin: Literal['design_expected'] = 'design_expected'
    criteria: dict[str, CriterionReference]

class DatasetInputs(Contract):
    root: Path
    cases: tuple[CaseInput, ...]
    roles: dict[str, RoleInput]
    hashes: dict[str, str]
    manifest_hash: str

class RunSelection(Contract):
    case_ids: tuple[str, ...]
    profiles: tuple[ProfileName, ...]
    combinations: tuple[tuple[str, ProfileName], ...]
    seed: int
    concurrency: Literal[1] = 1
    repetitions: Literal[1] = 1

from decimal import Decimal

class InputBound(Contract):
    strategy: Literal['verified_utf8','model_context']
    max_input_tokens: StrictInt = Field(gt=0)
    max_serialized_bytes: StrictInt | None = None
    framing_allowance: StrictInt | None = None
    tokenizer_artifact_sha256: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')
    proof_reference: str = Field(min_length=1)
    rate_card_version: str

    @model_validator(mode='after')
    def valid_bound(self):
        if self.strategy=='verified_utf8':
            if (self.max_serialized_bytes!=65536 or self.framing_allowance!=4096
                or self.max_input_tokens!=69632 or self.tokenizer_artifact_sha256 is None):
                raise ValueError('INPUT_BOUND_INVALID')
        elif any(v is not None for v in (self.max_serialized_bytes,self.framing_allowance,self.tokenizer_artifact_sha256)):
            raise ValueError('INPUT_BOUND_INVALID')
        return self

class BudgetCombination(Contract):
    case_id: str
    profile: ProfileName
    max_calls: Literal[4] = 4
    max_output_tokens: Literal[4096] = 4096
    upper_usd: Decimal = Field(ge=0)

class BudgetPlan(Contract):
    model: str
    bound: InputBound
    combinations: tuple[BudgetCombination,...]
    total_upper_usd: Decimal = Field(ge=0)
    cap_usd: Decimal = Field(gt=0,le=5)
    admitted: bool
