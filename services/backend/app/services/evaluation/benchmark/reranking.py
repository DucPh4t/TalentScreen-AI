"""Versioned reranking-provider experiments with conservative admission."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from pathlib import Path
import json
from typing import Literal
from .contracts import Contract,BudgetPlan,RunManifest,MetricsReport
from app.services.reranking.contracts import RerankPolicy,canonical,OPTIONS
from app.services.llm.types import CompletionResult
from app.services.llm.provider import BaseLLMProvider




class MultiProviderBudgetPlan(Contract):
    primary:BudgetPlan
    rerank_upper_by_combination:dict[str,Decimal]
    probe_upper_usd:Decimal
    total_upper_usd:Decimal
    cap_usd:Decimal
    admitted:bool


class RerankingManifestData(Contract):
    mode: Literal['shadow','rerank','gate_experiment']
    reranker_provider: Literal['scripted','jev']
    requested_model: str
    policy: RerankPolicy
    policy_hash: str
    model_quality: Literal['unmeasured','synthetic_retrieval_only']
    budget: MultiProviderBudgetPlan


class RerankRunManifest(RunManifest):
    schema_version:Literal['ai-benchmark-run.rerank.v1']='ai-benchmark-run.rerank.v1'
    reranking:RerankingManifestData


class RerankMetricsReport(MetricsReport):
    schema_version:Literal['ai-benchmark-metrics.rerank.v1']='ai-benchmark-metrics.rerank.v1'
    reranking:RerankingManifestData


def load_run_manifest(raw:str)->RunManifest:
    obj=json.loads(raw)
    return (RerankRunManifest if obj.get('schema_version')=='ai-benchmark-run.rerank.v1' else RunManifest).model_validate(obj)




def verify_provider_bounds(policy:RerankPolicy)->dict:
    root=Path(__file__).resolve().parents[6]
    path=root/'docs/evaluation/jev-provider-bounds.json'
    try:proof=json.loads(path.read_text())
    except (OSError,ValueError) as exc:raise ValueError('JEV_CONTEXT_PROOF_UNAVAILABLE') from exc
    age=(date.today()-date.fromisoformat(proof['verified_at'])).days
    if (proof['endpoint']!=policy.endpoint or proof['requested_model']!=policy.requested_model
        or Decimal(proof['input_price_per_million_usd'])!=Decimal(str(policy.rate_per_million_usd))
        or proof['output_price_per_million_usd']!='0' or proof['reservation_input_tokens']!=65536
        or not 0<proof['provider_max_context_tokens']<=65536 or not 0<=age<=7
        or proof['accepted_models']!=list(policy.accepted_models)):
        raise ValueError('JEV_CONTEXT_OR_RATE_UNVERIFIED')
    return proof


def experiment_policy(mode,reranker_provider,settings)->RerankPolicy:
    if mode=='off':return RerankPolicy()
    if reranker_provider=='scripted':
        return RerankPolicy(mode=mode,provider_kind='scripted',accepted_models=('scripted-jev-v1',),
            rate_per_million_usd=0,rate_verified_at=date.today().isoformat())
    from app.services.reranking.policy import freeze_rerank_policy
    values=settings.model_dump();values.update(JEV_RERANK_MODE=mode,RAG_MODE='hybrid',RAG_PIPELINE_VERSION='v2')
    from app.config import Settings
    policy=freeze_rerank_policy(Settings(_env_file=None,**values))
    verify_provider_bounds(policy)
    return policy


def plan_rerank_budget(primary_plan:BudgetPlan,selection,*,policy:RerankPolicy,reranker_provider:Literal['scripted','jev'],cap_usd:Decimal,probe_calls:int=0)->MultiProviderBudgetPlan:
    if not cap_usd.is_finite() or not 0<cap_usd<=1 or type(probe_calls) is not int or probe_calls<0:
        raise ValueError('RERANK_EXPERIMENT_CAP_INVALID')
    if set(selection.profiles)-{'hybrid','hybrid_agent'}:raise ValueError('RERANK_EXPERIMENT_PROFILE_INVALID')
    if reranker_provider=='jev':verify_provider_bounds(policy)
    price=Decimal(str(policy.rate_per_million_usd)) if reranker_provider=='jev' else Decimal(0)
    per_call=(Decimal(65536)/1000000*price).quantize(Decimal('.00000001'))
    per={canonical([c,p]):per_call*9 for c,p in selection.combinations}
    upper=primary_plan.total_upper_usd+sum(per.values(),Decimal(0))+per_call*probe_calls
    if upper>cap_usd:raise ValueError('RERANK_EXPERIMENT_BUDGET_REJECTED')
    return MultiProviderBudgetPlan(primary=primary_plan,rerank_upper_by_combination=per,probe_upper_usd=per_call*probe_calls,
        total_upper_usd=upper,cap_usd=cap_usd,admitted=True)


class ScriptedJevProvider(BaseLLMProvider):
    """Offline contract double, never used as model-quality evidence."""
    async def complete(self,request):
        payload=json.loads(request.user_prompt)
        answers={qid:{'type':'choice','choice':'unclear','confidence':1.0,'probabilities':{k:float(k=='unclear') for k in OPTIONS}} for qid in payload['questions']}
        return CompletionResult(content=canonical({'model':'scripted-jev-v1','answers':answers,'usage':{'input_tokens':0,'output_tokens':0}}),
            requested_model=request.model,reported_model='scripted-jev-v1',input_tokens=0,output_tokens=0,latency_ms=0)


