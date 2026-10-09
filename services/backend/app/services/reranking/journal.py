"""Bounded private, durable per-run judgments; no prompts, passages or query text."""
from pydantic import Field
from .contracts import Contract,RerankStageResult,PairJudgment,canonical


class RerankJournal(Contract):
    version: str='v1'
    policy_digest: str
    stages: tuple[RerankStageResult,...]=()
    successful_judgments: dict[str,PairJudgment]=Field(default_factory=dict)
    cumulative_calls:int=0
    cumulative_elapsed_ms:int=0
    admission_ids:tuple[str,...]=()
    pending_admission_ids:tuple[str,...]=()
    truncated_rows:int=0


async def load_rerank_journal(db,run)->RerankJournal:
    from .policy import load_rerank_policy
    p=load_rerank_policy(run.snapshot)
    journal=RerankJournal.model_validate(run.rerank_output) if run.rerank_output else RerankJournal(policy_digest=p.digest)
    if journal.policy_digest!=p.digest or len(journal.stages)>3 or len(journal.admission_ids)>9:
        raise ValueError('RERANK_POLICY_INVALID')
    return journal


async def persist_rerank_stage(db,run,stage:RerankStageResult,*,policy)->None:
    from sqlalchemy import select
    from app.db.models import LLMInvocation
    old=await load_rerank_journal(db,run)
    previous=next((s.elapsed_ms for s in old.stages if s.stage==stage.stage),0)
    stages=tuple(s for s in old.stages if s.stage!=stage.stage)+(stage,)
    rows=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==run.job_id,
        LLMInvocation.logical_step.like('jev_rerank_%')))).all()
    successful={**old.successful_judgments,**{j.pair_id:j for j in stage.judgments}}
    journal=RerankJournal(policy_digest=policy.digest,stages=stages,successful_judgments=successful,
        cumulative_calls=len(rows),cumulative_elapsed_ms=old.cumulative_elapsed_ms-previous+stage.elapsed_ms,
        admission_ids=tuple(str(i.id) for i in rows),pending_admission_ids=tuple(str(i.id) for i in rows if i.status.value in {'reserved','outcome_unknown'}),
        truncated_rows=old.truncated_rows)
    data=journal.model_dump(mode='json')
    # Reuse is an optimization: evict cache entries before compacting diagnostic rows.
    while len(canonical(data).encode())>262144 and data['successful_judgments']:
        del data['successful_judgments'][next(iter(data['successful_judgments']))];data['truncated_rows']+=1
    while len(canonical(data).encode())>262144:
        removed=False
        for s in data['stages']:
            if s['judgments']:
                s['judgments'].pop();data['truncated_rows']+=1;removed=True;break
        if not removed:raise ValueError('RERANK_JOURNAL_BOUND_EXCEEDED')
    run.rerank_output=data
    await db.commit()
