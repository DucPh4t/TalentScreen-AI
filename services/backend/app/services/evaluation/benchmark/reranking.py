"""Versioned two-provider experiments, separate references and conservative admission."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import math
from typing import Literal
from pydantic import Field
from .contracts import Contract,BudgetPlan,RunManifest
from .metrics import rate,mean,percentile,paired_cluster_interval
from app.services.reranking.contracts import PassagePair,RerankPolicy,canonical,OPTIONS
from app.services.llm.types import CompletionResult
from app.services.llm.provider import BaseLLMProvider


class PairReferenceDataset(Contract):
    input_pairs:tuple[PassagePair,...]
    design_labels:dict[str,str]
    independent_grades:dict[str,int]|None
    sufficient_groups:dict[str,tuple[tuple[str,...],...]]
    limiting_pair_ids:tuple[str,...]
    contradictory_pair_groups:tuple[tuple[str,str],...]
    hashes:dict[str,str]


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


def load_run_manifest(raw:str)->RunManifest:
    obj=json.loads(raw)
    return (RerankRunManifest if obj.get('schema_version')=='ai-benchmark-run.rerank.v1' else RunManifest).model_validate(obj)


def load_pair_references(root:Path)->PairReferenceDataset:
    manifest=json.loads((root/'manifest.json').read_text());hashes={}
    for name in ('pairs.json','references.json'):
        path=root/name
        if path.is_symlink():raise ValueError('RERANK_DATASET_HASH_INVALID')
        hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest['files'].get(name)!=hashes[name]:raise ValueError('RERANK_DATASET_HASH_MISMATCH')
    pairs=tuple(PassagePair.model_validate(p) for p in json.loads((root/'pairs.json').read_text()))
    refs=json.loads((root/'references.json').read_text())
    if set(refs['design_labels'])!={p.pair_id for p in pairs} or set(refs['design_labels'].values())-set(OPTIONS):
        raise ValueError('RERANK_REFERENCE_INVALID')
    return PairReferenceDataset(input_pairs=pairs,hashes=hashes,**refs)


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


def evaluate_rerank_records(dataset:PairReferenceDataset,records:list[dict],*,seed:int)->dict:
    # Records are evaluator-only: case_id, mode, status, ranked_pair_ids, selected_pair_ids,
    # unscored_pair_ids, predicted_categories, elapsed_ms and optional paired baseline coverage.
    complete=[r for r in records if r['status']=='ok'];keys={p.pair_id for p in dataset.input_pairs}
    for r in records:
        scope=set(r.get('input_pair_ids',keys))
        if (not scope or scope-keys or set(r.get('ranked_pair_ids',()))-scope
            or set(r.get('selected_pair_ids',()))-scope or set(r.get('unscored_pair_ids',()))-scope
            or set(r.get('predicted_categories',{}))-scope):
            raise ValueError('RERANK_RECORD_SCOPE_INVALID')
    exclusions=possible=negative_kept=negative_possible=conflict_kept=conflict_possible=0
    recall5=[];recall10=[];coverage=[];ndcg=[];pairs=[]
    for r in complete:
        selected=set(r['selected_pair_ids']);ranked=r['ranked_pair_ids']
        scope=set(r.get('input_pair_ids',keys))
        relevant={pid for pid,label in dataset.design_labels.items() if pid in scope and label in {'substantive_evidence','limiting_evidence'}}
        limiting=set(dataset.limiting_pair_ids)&scope
        conflicts=[g for g in dataset.contradictory_pair_groups if set(g)<=scope]
        sufficient={cid:tuple(g for g in groups if set(g)<=scope) for cid,groups in dataset.sufficient_groups.items()}
        sufficient={cid:groups for cid,groups in sufficient.items() if groups}
        possible+=len(relevant);exclusions+=len(relevant-set(ranked))
        negative_possible+=len(limiting);negative_kept+=len(limiting&selected)
        conflict_possible+=len(conflicts);conflict_kept+=sum(set(g)<=selected for g in conflicts)
        recall5.append(rate(len(relevant&set(ranked[:5])),len(relevant)));recall10.append(rate(len(relevant&set(ranked[:10])),len(relevant)))
        cv_covered=sum(any(set(g)<=selected for g in groups) for groups in sufficient.values())
        cv_rate=rate(cv_covered,len(sufficient));coverage.append(cv_rate)
        if cv_rate is not None and r.get('baseline_coverage') is not None:pairs.append((r['case_id'],r['baseline_coverage'],cv_rate))
        if dataset.independent_grades:
            grades={pid:g for pid,g in dataset.independent_grades.items() if pid in scope}
            dcg=sum((2**grades.get(pid,0)-1)/math.log2(i+2) for i,pid in enumerate(ranked[:4]))
            ideal=sum((2**g-1)/math.log2(i+2) for i,g in enumerate(sorted(grades.values(),reverse=True)[:4]))
            if ideal:ndcg.append(dcg/ideal)
    times=[r['elapsed_ms'] for r in complete if r.get('elapsed_ms') is not None]
    return {'origin':'synthetic_design_expected','planned_records':len(records),'completed_records':len(complete),
        'failed_records':len(records)-len(complete),'false_exclusion_rate':rate(exclusions,possible),
        'limiting_retention':rate(negative_kept,negative_possible),'contradictory_group_retention':rate(conflict_kept,conflict_possible),
        'recall_at_5':mean([v for v in recall5 if v is not None]),'recall_at_10':mean([v for v in recall10 if v is not None]),
        'sufficient_group_delivery':mean([v for v in coverage if v is not None]),'ndcg_at_4':mean(ndcg),
        'p50_ms':percentile(times,.5),'p95_ms':percentile(times,.95),'paired_coverage_ci':paired_cluster_interval(pairs,seed=seed)}
