"""Authorized initial/tool reranking through durable invocation admission."""
from __future__ import annotations
import json
import time
from decimal import Decimal
from uuid import UUID
from sqlalchemy import select
from app.config import get_settings
from app.db.models import LLMInvocation,RetrievalChunk,SourceSpan,RubricCriterion,RubricVersion
from app.domain.enums import BudgetScope,RubricStatus
from app.services.observability import observed,record_trace_metadata
from app.services.agent.tools import snapshot_failure_code,_anchor_query_terms
from app.services.llm.orchestrator import execute_bounded_llm_call,PreconditionViolationError
from app.services.llm.exceptions import LLMProviderError
from app.services.llm.types import CompletionRequest
from app.services.llm.call_policy import JevReservationPolicy
from app.services.llm.ledger import get_or_create_active_budget_period
from app.services.jev.provider import get_jev_provider
from app.services.sanitizer import residual_contact_types
from .contracts import ApprovedCriterion,canonical
from .policy import load_rerank_policy
from .journal import load_rerank_journal,persist_rerank_stage
from .planner import plan_batches
from .selection import rank_and_select
from .prompt import validate_pair_judgments,pair_id_for


class RerankError(ValueError):
    def __init__(self,code):super().__init__(code);self.error_code=code


def criterion_from_row(row)->ApprovedCriterion:
    return ApprovedCriterion(criterion_id=row.criterion_id,label=row.label_vi,description=row.description_vi,
        anchors=tuple(_anchor_query_terms(row.anchors)),bilingual_terms=row.bilingual_terms or {})


async def require_scope(db,run,policy,pairs):
    code=await snapshot_failure_code(db,run)
    if code:raise RerankError(code)
    if load_rerank_policy(run.snapshot)!=policy:raise RerankError('RERANK_POLICY_INVALID')
    rubric=await db.scalar(select(RubricVersion).where(RubricVersion.id==run.rubric_version_id))
    if rubric is None or rubric.status!=RubricStatus.APPROVED:raise RerankError('ASSESSMENT_INPUT_STALE')
    if policy.mode=='gate_experiment' and (get_settings().APP_ENV!='sandbox' or not run.snapshot.get('assessment_execution_policy')):
        raise RerankError('JEV_GATE_SANDBOX_ONLY')
    approved={c.criterion_id:criterion_from_row(c) for c in (await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()}
    from app.services.embedding import embedding_config_id
    chunks={str(c.id):c for c in (await db.scalars(select(RetrievalChunk).where(RetrievalChunk.sanitized_version_id==run.sanitized_version_id,
        RetrievalChunk.embedding_config_id==embedding_config_id('v2')))).all()}
    spans={s.span_id:s for s in (await db.scalars(select(SourceSpan).where(SourceSpan.sanitized_version_id==run.sanitized_version_id))).all()}
    for p in pairs:
        c=chunks.get(p.chunk_id)
        if (approved.get(p.criterion.criterion_id)!=p.criterion or c is None or c.text!=p.text
            or tuple(c.span_ids)!=p.span_ids or not p.span_ids or any(s not in spans for s in p.span_ids)
            or p.pair_id!=pair_id_for(p.criterion,p.chunk_id,p.text,p.span_ids,sanitized_version_id=run.sanitized_version_id,rubric_version_id=run.rubric_version_id)):
            raise RerankError('HYBRID_RETRIEVAL_PROVENANCE_INVALID')
        if residual_contact_types(canonical(p.criterion.model_dump(mode='json'))) or residual_contact_types(p.text):
            raise RerankError('RESIDUAL_CONTACT_DATA')


@observed('jev_rerank',input_metadata=lambda args:{'rerank_mode':args['policy'].mode},
    result_metadata=lambda result:{'result_count':len(result.judgments),'rerank_elapsed_ms':result.elapsed_ms})
async def rerank_candidates(*,db,run,policy,stage,candidates_by_criterion,focus_ids=(),provider_override=None,financial_policy=None):
    pairs=tuple(p for ps in candidates_by_criterion.values() for p in ps)
    if len(pairs)>360 or len({p.pair_id for p in pairs})!=len(pairs):raise RerankError('RERANK_POLICY_INVALID')
    if not policy.enabled:return rank_and_select(pairs,(),policy,stage=stage)
    await require_scope(db,run,policy,pairs)
    journal=await load_rerank_journal(db,run)
    existing=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==run.job_id,LLMInvocation.logical_step.like('jev_rerank_%')))).all()
    if any(str(i.id) not in journal.admission_ids or i.status.value in {'reserved','outcome_unknown'} for i in existing):
        raise RerankError('RERANK_RECONCILIATION_REQUIRED')
    cached=tuple(journal.successful_judgments[p.pair_id] for p in pairs if p.pair_id in journal.successful_judgments)
    unsent={k:tuple(p for p in ps if p.pair_id not in journal.successful_judgments) for k,ps in candidates_by_criterion.items()}
    plan=plan_batches(unsent,policy,remaining_calls=policy.max_rerank_calls-len(existing),focus_ids=tuple(focus_ids))
    if financial_policy is None and plan.batches:
        scope=BudgetScope.DEVELOPMENT if get_settings().APP_ENV=='sandbox' else BudgetScope.PILOT
        period=await get_or_create_active_budget_period(db,scope)
        financial_policy=JevReservationPolicy(period.id,Decimal(str(period.limit_usd)),policy.input_reservation_tokens,
            Decimal(str(policy.rate_per_million_usd)),policy.rate_verified_at,frozenset(policy.accepted_models),policy.endpoint)
        await db.commit()
    provider=provider_override or get_jev_provider(policy=policy)
    started=time.monotonic();judgments=list(cached);status=None
    previous_ms=next((s.elapsed_ms for s in journal.stages if s.stage==stage),0)
    for n,batch in enumerate(plan.batches,1):
        remaining=policy.aggregate_timeout_seconds-journal.cumulative_elapsed_ms/1000-(time.monotonic()-started)
        if remaining<=0:break
        await require_scope(db,run,policy,pairs)
        request=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt=canonical(batch.payload),model=policy.requested_model,
            provider='jev',purpose='jev_rerank',max_output_tokens=0,timeout_seconds=min(policy.request_timeout_seconds,remaining),jev_reservation_policy=financial_policy)
        try:
            result=await execute_bounded_llm_call(db,run.job_id,request,f'jev_rerank_{stage}_{n}',1,
                sanitized_version_id=run.sanitized_version_id,provider_override=provider)
            await require_scope(db,run,policy,pairs)
            parsed=validate_pair_judgments(json.loads(result.content),batch.pairs,policy)
        except RerankError:raise
        except (ValueError,LLMProviderError,PreconditionViolationError) as exc:
            await db.rollback()
            code=await snapshot_failure_code(db,run)
            if code:raise RerankError(code) from exc
            unresolved=await db.scalar(select(LLMInvocation.id).where(LLMInvocation.job_id==run.job_id,
                LLMInvocation.status.in_(('reserved','outcome_unknown'))).limit(1))
            if policy.mode!='shadow' or unresolved:raise RerankError('JEV_RERANK_FAILED') from exc
            status='JEV_RERANK_FAILED';break
        judgments.extend(parsed)
        partial=rank_and_select(pairs,tuple(judgments),policy,stage=stage,elapsed_ms=previous_ms+int((time.monotonic()-started)*1000))
        await persist_rerank_stage(db,run,partial,policy=policy)
    result=rank_and_select(pairs,tuple(judgments),policy,stage=stage,elapsed_ms=previous_ms+int((time.monotonic()-started)*1000))
    if status:result=result.model_copy(update={'status':status})
    await require_scope(db,run,policy,pairs)
    await persist_rerank_stage(db,run,result,policy=policy)
    record_trace_metadata({'rerank_mode':policy.mode,'result_count':len(result.judgments),'rerank_elapsed_ms':result.elapsed_ms})
    return result


async def rerank_retrieval_pool(*,db,run,criteria,candidates,stage,focus_ids=(),provider_override=None,financial_policy=None):
    from .prompt import pairs_from_candidates
    policy=load_rerank_policy(run.snapshot)
    pairs=pairs_from_candidates([criterion_from_row(c) for c in criteria],candidates,
        sanitized_version_id=run.sanitized_version_id,rubric_version_id=run.rubric_version_id)
    spans={s.span_id:s.section_label for s in (await db.scalars(select(SourceSpan).where(SourceSpan.sanitized_version_id==run.sanitized_version_id))).all()}
    for c,ps in pairs.items():
        updated=[]
        for p in ps:
            labels={spans[s] for s in p.span_ids if s in spans and spans[s]}
            if len(labels)>1 or any(s not in spans for s in p.span_ids):raise RerankError('HYBRID_RETRIEVAL_PROVENANCE_INVALID')
            updated.append(p.model_copy(update={'section':next(iter(labels)) if labels else None}))
        pairs[c]=tuple(updated)
    result=await rerank_candidates(db=db,run=run,policy=policy,stage=stage,candidates_by_criterion=pairs,
        focus_ids=tuple(focus_ids),provider_override=provider_override,financial_policy=financial_policy)
    return result,pairs
