"""Strict immutable contracts for evidence ranking, separate from competency scores."""
from __future__ import annotations
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Mode=Literal['off','shadow','rerank','gate_experiment']
Stage=Literal['initial','tool_1','tool_2']
Choice=Literal['substantive_evidence','mention_only','limiting_evidence','unrelated','unclear']
OPTIONS=('substantive_evidence','mention_only','limiting_evidence','unrelated','unclear')


def canonical(value: object) -> str:
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,allow_inf_nan=False,hide_input_in_errors=True)


class RerankPolicy(Contract):
    mode: Mode='off'
    policy_version: Literal['jev-evidence-ranking.v1']='jev-evidence-ranking.v1'
    prompt_version: Literal['jev-passage-choice.v1']='jev-passage-choice.v1'
    requested_model: str='typesafe/jev-1.13'
    accepted_models: tuple[str,...]=()
    endpoint: str='https://openrouter.ai/api/alpha/decisions'
    rate_per_million_usd: float=Field(default=0,ge=0)
    rate_verified_at: str|None=None
    max_pairs_per_criterion: Literal[8]=8
    max_questions: Literal[20]=20
    max_state_bytes: Literal[16384]=16384
    max_body_bytes: Literal[32768]=32768
    max_rerank_calls: Literal[9]=9
    max_primary_calls: Literal[4]=4
    max_total_calls: Literal[13]=13
    request_timeout_seconds: Literal[15]=15
    aggregate_timeout_seconds: Literal[60]=60
    input_reservation_tokens: Literal[65536]=65536
    selection_limit: Literal[4]=4
    mention_weight: Literal[0.35]=0.35
    unclear_weight: Literal[0.15]=0.15
    limiting_probability: Literal[0.50]=0.50
    gate_probability: Literal[0.95]=0.95
    gate_confidence: Literal[0.80]=0.80

    @model_validator(mode='before')
    @classmethod
    def reject_booleans(cls,value):
        if isinstance(value,dict) and any(isinstance(v,bool) for v in value.values()):
            raise ValueError('RERANK_POLICY_INVALID')
        return value

    @property
    def enabled(self)->bool:return self.mode!='off'

    @property
    def digest(self)->str:return hashlib.sha256(canonical(self.model_dump(mode='json')).encode()).hexdigest()


class ApprovedCriterion(Contract):
    criterion_id: str
    label: str
    description: str
    anchors: tuple[str,...]=()
    bilingual_terms: dict=Field(default_factory=dict)


class PassagePair(Contract):
    pair_id: str
    criterion: ApprovedCriterion
    chunk_id: str
    chunk_index: int
    text: str
    span_ids: tuple[str,...]
    section: str|None=None
    rrf_score: float


class PairJudgment(Contract):
    pair_id: str
    choice: Choice
    probabilities: dict[str,float]
    confidence: float=Field(ge=0,le=1)
    reported_model: str

    @model_validator(mode='before')
    @classmethod
    def check_numeric_input(cls,value):
        if isinstance(value,dict):
            numbers=[value.get('confidence'),*(value.get('probabilities') or {}).values()]
            if any(type(v) not in (float,int) for v in numbers):raise ValueError('JEV_JUDGMENT_INVALID')
        return value

    @model_validator(mode='after')
    def check_distribution(self):
        ps=self.probabilities
        if (set(ps)!=set(OPTIONS) or any(not 0<=v<=1 for v in ps.values())
            or abs(sum(ps.values())-1)>.02 or ps[self.choice]<max(ps.values())):
            raise ValueError('JEV_JUDGMENT_INVALID')
        return self


class RerankStageResult(Contract):
    stage: Stage
    mode: Mode
    ordered_pair_ids_by_criterion: dict[str,tuple[str,...]]
    selected_pair_ids_by_criterion: dict[str,tuple[str,...]]
    judgments: tuple[PairJudgment,...]=()
    unscored_pair_ids: tuple[str,...]=()
    omitted_limiting_count: int=0
    status: str='ok'
    elapsed_ms: int=0


class PlannedBatch(Contract):
    payload: dict
    pairs: tuple[PassagePair,...]
    @property
    def pair_ids(self)->tuple[str,...]:return tuple(p.pair_id for p in self.pairs)


class BatchPlan(Contract):
    batches: tuple[PlannedBatch,...]
    unscored_pair_ids: tuple[str,...]
