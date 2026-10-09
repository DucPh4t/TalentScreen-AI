"""Stable round-robin allocation under serialized byte and physical-call ceilings."""
from collections import deque
from .contracts import BatchPlan,PlannedBatch,PassagePair,RerankPolicy,canonical
from .prompt import build_jev_payload


def plan_batches(pairs_by_criterion: dict[str,tuple[PassagePair,...]],policy: RerankPolicy,*,remaining_calls: int,focus_ids: tuple[str,...])->BatchPlan:
    ordered=[k for k in focus_ids if k in pairs_by_criterion]+[k for k in sorted(pairs_by_criterion) if k not in focus_ids]
    queues={k:deque(pairs_by_criterion[k][:policy.max_pairs_per_criterion]) for k in ordered}
    scheduled=[]
    while any(queues.values()):
        for k in ordered:
            if queues[k]:scheduled.append(queues[k].popleft())
    def fit(ps):
        body=build_jev_payload(tuple(ps),policy)
        return (len(ps)<=policy.max_questions and len(canonical(body['state']).encode())<=policy.max_state_bytes
            and len(canonical(body).encode())<=policy.max_body_bytes)
    batches=[];current=[];cap=max(0,min(remaining_calls,policy.max_rerank_calls))
    for p in scheduled:
        if not fit([p]):continue
        if not fit(current+[p]):
            batches.append(PlannedBatch(payload=build_jev_payload(tuple(current),policy),pairs=tuple(current)))
            current=[]
        if len(batches)>=cap:break
        current.append(p)
    if current and len(batches)<cap:
        batches.append(PlannedBatch(payload=build_jev_payload(tuple(current),policy),pairs=tuple(current)))
    # Zero allowance must never create a first physical batch.
    batches=batches[:cap]
    sent={p.pair_id for b in batches for p in b.pairs}
    return BatchPlan(batches=tuple(batches),unscored_pair_ids=tuple(p.pair_id for ps in pairs_by_criterion.values() for p in ps if p.pair_id not in sent))
