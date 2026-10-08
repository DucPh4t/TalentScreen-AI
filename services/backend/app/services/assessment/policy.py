"""Internal, immutable experimental policies; never accepted by public APIs."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib
import json
from typing import Any

BENCHMARK_PROMPT_VERSION='assessment-v1.6.0'
CHANNELS={'full_text':frozenset(), 'dense':frozenset({'dense'}),
          'hybrid':frozenset({'dense','lexical'}), 'hybrid_agent':frozenset({'dense','lexical'})}

@dataclass(frozen=True)
class AssessmentExecutionPolicy:
    profile: str
    channels: frozenset[str]
    tools_enabled: bool
    max_evidence_chars: int=24000
    assessment_prompt_version: str=BENCHMARK_PROMPT_VERSION
    agent_prompt_version: str='assessment-agent.v1'
    temperature: float=0.0
    thinking_mode: str='disabled'
    max_output_tokens: int=4096

    def __post_init__(self):
        if (self.profile not in CHANNELS or self.channels!=CHANNELS[self.profile]
            or type(self.tools_enabled) is not bool or self.tools_enabled!=(self.profile=='hybrid_agent')
            or type(self.max_evidence_chars) is not int or self.max_evidence_chars!=24000
            or self.assessment_prompt_version!=BENCHMARK_PROMPT_VERSION
            or self.agent_prompt_version!='assessment-agent.v1'
            or isinstance(self.temperature,bool) or self.temperature!=0
            or self.thinking_mode!='disabled' or type(self.max_output_tokens) is not int or self.max_output_tokens!=4096):
            raise ValueError('ASSESSMENT_EXECUTION_POLICY_INVALID')

    @property
    def retrieval_strategy(self):
        return 'full_text_baseline' if self.profile=='full_text' else 'hybrid'

    def to_snapshot(self) -> dict[str,Any]:
        result=asdict(self)
        result['channels']=sorted(self.channels)
        return result

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(self.to_snapshot(),sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @classmethod
    def from_snapshot(cls,value):
        try:
            if not isinstance(value,dict) or not isinstance(value.get('channels'),list):
                raise ValueError('ASSESSMENT_EXECUTION_POLICY_INVALID')
            return cls(**{**value,'channels':frozenset(value['channels'])})
        except (TypeError,KeyError) as exc:
            raise ValueError('ASSESSMENT_EXECUTION_POLICY_INVALID') from exc


def benchmark_policy(profile: str) -> AssessmentExecutionPolicy:
    if profile not in CHANNELS: raise ValueError('ASSESSMENT_EXECUTION_POLICY_INVALID')
    return AssessmentExecutionPolicy(profile,CHANNELS[profile],profile=='hybrid_agent')


def load_execution_policy(snapshot: dict) -> AssessmentExecutionPolicy | None:
    raw=snapshot.get('assessment_execution_policy')
    if raw is None:
        if snapshot.get('assessment_execution_policy_hash') is not None:
            raise ValueError('ASSESSMENT_EXECUTION_POLICY_INVALID')
        return None
    policy=AssessmentExecutionPolicy.from_snapshot(raw)
    if (snapshot.get('assessment_execution_policy_hash')!=policy.digest
        or snapshot.get('assessment_prompt_version')!=policy.assessment_prompt_version
        or snapshot.get('agent_prompt_version')!=policy.agent_prompt_version
        or snapshot.get('retrieval_strategy')!=policy.retrieval_strategy):
        raise ValueError('ASSESSMENT_EXECUTION_POLICY_INVALID')
    return policy
