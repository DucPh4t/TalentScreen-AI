"""Deterministic passage utility and protected, diverse selections."""
from .contracts import PassagePair,PairJudgment,RerankPolicy,RerankStageResult,Stage


def utility(j: PairJudgment)->float:
    p=j.probabilities
    return p['substantive_evidence']+p['limiting_evidence']+.35*p['mention_only']+.15*p['unclear']


def diverse(pairs,limit,selected=()):
    result=list(selected)
    seen={p.section or f'unknown:{p.chunk_id}' for p in result}
    ids={p.chunk_id for p in result}
    for distinct_only in (True,False):
        for p in pairs:
            if len(result)>=limit:return result
            section=p.section or f'unknown:{p.chunk_id}'
            if p.chunk_id in ids or (distinct_only and section in seen):continue
            result.append(p);ids.add(p.chunk_id);seen.add(section)
    return result


from app.services.observability import trace_span


def rank_and_select(*args, **kwargs)->RerankStageResult:
    policy = args[2] if len(args)>2 else kwargs["policy"]
    with trace_span("jev_gate", metadata={"rerank_mode":policy.mode,"rerank_policy_version":policy.policy_version}) as span:
        result = _rank_and_select(*args, **kwargs)
        span.record({"result_count":sum(len(ids) for ids in result.selected_pair_ids_by_criterion.values()),
            "omitted_count":result.omitted_limiting_count})
        return result


def _rank_and_select(pairs: tuple[PassagePair,...],judgments: tuple[PairJudgment,...],policy: RerankPolicy,*,stage: Stage,elapsed_ms: int=0)->RerankStageResult:
    by_id={p.pair_id:p for p in pairs};js={j.pair_id:j for j in judgments}
    if len(js)!=len(judgments) or set(js)-set(by_id):raise ValueError('JEV_JUDGMENT_INVALID')
    ordered={};selected={};omitted=0
    for c in dict.fromkeys(p.criterion.criterion_id for p in pairs):
        ps=[p for p in pairs if p.criterion.criterion_id==c]
        rrf=sorted(ps,key=lambda p:(-p.rrf_score,p.chunk_index,p.chunk_id))
        unscored=[p for p in rrf if p.pair_id not in js]
        scored=sorted((p for p in ps if p.pair_id in js),key=lambda p:(-utility(js[p.pair_id]),-p.rrf_score,p.chunk_index,p.chunk_id))
        eligible=[p for p in scored if not (policy.mode=='gate_experiment' and js[p.pair_id].choice=='unrelated'
            and js[p.pair_id].probabilities['unrelated']>=policy.gate_probability and js[p.pair_id].confidence>=policy.gate_confidence)]
        limiting=[p for p in eligible if js[p.pair_id].probabilities['limiting_evidence']>=policy.limiting_probability]
        if not scored:
            picked=diverse(rrf,policy.selection_limit);ordered[c]=tuple(p.pair_id for p in rrf)
        else:
            protected=limiting[:1]+unscored[:1]
            picked=diverse(eligible,policy.selection_limit,protected)
            picked=diverse(unscored,policy.selection_limit,picked)
            ordered[c]=tuple(p.pair_id for p in eligible+unscored)
        selected[c]=tuple(p.pair_id for p in picked)
        omitted+=sum(p.pair_id not in selected[c] for p in limiting)
    return RerankStageResult(stage=stage,mode=policy.mode,ordered_pair_ids_by_criterion=ordered,
        selected_pair_ids_by_criterion=selected,judgments=judgments,unscored_pair_ids=tuple(p.pair_id for p in pairs if p.pair_id not in js),
        omitted_limiting_count=omitted,status='ok' if judgments else 'not_scored_bound',elapsed_ms=elapsed_ms)
