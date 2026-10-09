"""Frozen provider-aware admission limits and independent Jev financial bounds."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID
from app.services.reranking.policy import load_rerank_policy
from app.services.reranking.contracts import canonical


@dataclass(frozen=True)
class InvocationBudgetPolicy:
    primary_limit:int
    rerank_limit:int
    total_limit:int
    @classmethod
    def from_snapshot(cls,snapshot:dict):
        p=load_rerank_policy(snapshot)
        return cls(p.max_primary_calls,p.max_rerank_calls,p.max_total_calls) if p.enabled else cls(4,0,4)


@dataclass(frozen=True)
class JevReservationPolicy:
    budget_period_id:UUID
    cap_usd:Decimal
    max_input_tokens:int
    rate_per_million_usd:Decimal
    rate_verified_at:str
    accepted_models:frozenset[str]
    provider_endpoint:str
    def __post_init__(self):
        age=(date.today()-date.fromisoformat(self.rate_verified_at)).days
        url=urlsplit(self.provider_endpoint)
        allowed={('api.typesafe.ai','/v1/systemone')}
        if (not isinstance(self.budget_period_id,UUID) or not self.cap_usd.is_finite() or not 0<self.cap_usd
            or type(self.max_input_tokens) is not int or self.max_input_tokens!=65536
            or not self.rate_per_million_usd.is_finite() or (self.rate_per_million_usd<0 or (self.rate_per_million_usd==0 and self.accepted_models!=frozenset({'scripted-jev-v1'})))
            or not 0<=age<=7 or not self.accepted_models or url.scheme!='https'
            or (url.hostname,url.path) not in allowed or url.port not in (None,443) or url.query or url.fragment or url.username):
            raise ValueError('JEV_RESERVATION_POLICY_INVALID')
    def input_reservation_tokens(self,request)->int:
        import json
        body=json.loads(request.user_prompt)
        if not isinstance(body,dict) or set(body)-{'model','state','questions'} or not {'state','questions'}<=set(body):
            raise ValueError('JEV_REQUEST_INVALID')
        body={**body,'model':request.model}
        if (request.provider!='jev' or request.max_output_tokens!=0 or request.strict_reservation_policy is not None
            or len(canonical(body).encode())>32768 or len(canonical(body['state']).encode())>16384
            or not isinstance(body['questions'],dict) or not 1<=len(body['questions'])<=20):
            raise ValueError('JEV_REQUEST_BOUND_EXCEEDED')
        return self.max_input_tokens


@dataclass(frozen=True)
class AdmittedInvocation:
    invocation_id:UUID
    reservation_id:UUID
    reserved_usd:Decimal
    input_upper_tokens:int
    input_rate_per_million_usd:Decimal
    output_rate_per_million_usd:Decimal
    accepted_models:frozenset[str]
