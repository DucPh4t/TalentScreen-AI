from datetime import date
import json
import uuid
import pytest
from sqlalchemy import select,update
from app.db.models import AssessmentRun,LLMInvocation,RetrievalChunk,SourceSpan,SanitizedVersion
from app.config import get_settings
from app.services.llm.provider import BaseLLMProvider
from app.services.llm.types import CompletionResult
from tests.test_assessment_agent import agent_context
from tests.test_ai_benchmark_budget import fresh_period
from tests.test_rerank_kernel import policy


class ChoiceProvider(BaseLLMProvider):
    def __init__(self,callback=None):self.calls=0;self.callback=callback
    async def complete(self,request):
        self.calls+=1
        if self.callback:await self.callback()
        body=json.loads(request.user_prompt)
        answers={qid:{'type':'choice','choice':'substantive_evidence','confidence':1.0,
            'probabilities':{k:float(k=='substantive_evidence') for k in q['criteria']}} for qid,q in body['questions'].items()}
        content=json.dumps({'model':'typesafe/jev-1.13-20260917','answers':answers,'usage':{'input_tokens':20,'output_tokens':0}})
        return CompletionResult(content=content,requested_model=request.model,reported_model='typesafe/jev-1.13-20260917',input_tokens=20,output_tokens=0)


async def rerank_context(db,context):
    from app.services.reranking.prompt import pairs_from_candidates
    from app.services.reranking.contracts import ApprovedCriterion
    from app.services.retrieval import RetrievedChunkScore
    run=await db.get(AssessmentRun,context['run_id']);p=policy()
    run.snapshot={**run.snapshot,'reranking_policy':p.model_dump(mode='json'),'reranking_policy_hash':p.digest,'rag_pipeline_version':'v2'}
    span=await db.get(SourceSpan,context['span_id'])
    from app.services.embedding import embedding_config_id
    chunk=RetrievalChunk(id=uuid.uuid4(),sanitized_version_id=run.sanitized_version_id,chunk_index=0,
        text=span.text,span_ids=[span.span_id],embedding_config_id=embedding_config_id('v2'))
    db.add(chunk);await db.commit()
    c=ApprovedCriterion(criterion_id='api_design',label='Thiết kế API',description='Thiết kế REST API phù hợp yêu cầu.',anchors=('None','Basic','Good','Strong','Expert'))
    match=RetrievedChunkScore(chunk_id=chunk.id,chunk_index=0,text=span.text,span_ids=[span.span_id],dense_rank=1,lexical_rank=1,rrf_score=.03)
    pairs=pairs_from_candidates([c],{'api_design':[match]},sanitized_version_id=run.sanitized_version_id,rubric_version_id=run.rubric_version_id)
    return run,p,pairs


@pytest.mark.asyncio
async def test_exact_success_reuse_and_private_journal(test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.services.reranking.service import rerank_candidates
    from app.services.llm.call_policy import JevReservationPolicy
    from decimal import Decimal
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pairs=await rerank_context(db,agent_context);provider=ChoiceProvider()
        financial=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        a=await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pairs,provider_override=provider,financial_policy=financial)
        b=await rerank_candidates(db=db,run=run,policy=p,stage='tool_1',candidates_by_criterion=pairs,provider_override=provider,financial_policy=financial)
        assert a.selected_pair_ids_by_criterion==b.selected_pair_ids_by_criterion
        assert provider.calls==1
        journal=json.dumps(run.rerank_output)
        assert 'Kinh nghiem' not in journal and 'Thực hiện' not in journal and len(journal.encode())<=262144
        assert len((await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==run.job_id))).all())==1


@pytest.mark.asyncio
async def test_revoked_input_after_network_discards_selection(test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.services.reranking.service import rerank_candidates,RerankError
    from app.services.llm.call_policy import JevReservationPolicy
    from app.domain.enums import SanitizedVersionStatus
    from decimal import Decimal
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pairs=await rerank_context(db,agent_context)
        async def revoke():
            async with test_session_factory() as other:
                await other.execute(update(SanitizedVersion).where(SanitizedVersion.id==run.sanitized_version_id).values(status=SanitizedVersionStatus.DRAFT));await other.commit()
        f=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        with pytest.raises(RerankError,match='ASSESSMENT_INPUT_STALE'):
            await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pairs,provider_override=ChoiceProvider(revoke),financial_policy=f)
        assert not (run.rerank_output or {}).get('successful_judgments')

@pytest.mark.asyncio
async def test_crash_after_settlement_before_journal_cannot_replay(test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.services.reranking.service import rerank_candidates,RerankError
    from app.services.llm.call_policy import JevReservationPolicy
    from decimal import Decimal
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pairs=await rerank_context(db,agent_context);provider=ChoiceProvider()
        f=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pairs,provider_override=provider,financial_policy=f)
        run.rerank_output=None;await db.commit()
        with pytest.raises(RerankError,match='RECONCILIATION_REQUIRED'):
            await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pairs,provider_override=provider,financial_policy=f)
        assert provider.calls==1

@pytest.mark.asyncio
async def test_invalid_paid_judgment_fails_safely_without_expired_orm_access(test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.services.reranking.service import rerank_candidates,RerankError
    from app.services.llm.call_policy import JevReservationPolicy
    from decimal import Decimal
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    class BadProvider(ChoiceProvider):
        async def complete(self,request):
            good=await super().complete(request)
            body=json.loads(good.content)
            for answer in body['answers'].values():answer['confidence']='unsafe'
            good.content=json.dumps(body)
            return good
    async with test_session_factory() as db:
        run,p,pairs=await rerank_context(db,agent_context)
        f=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        with pytest.raises(RerankError,match='JEV_RERANK_FAILED'):
            await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pairs,provider_override=BadProvider(),financial_policy=f)

@pytest.mark.asyncio
async def test_restarted_partial_stage_uses_next_physical_ordinal(test_session_factory,agent_context,fresh_period,monkeypatch):
    from app.services.reranking.service import rerank_candidates
    from app.services.llm.call_policy import JevReservationPolicy
    from app.services.reranking.prompt import pair_id_for
    from decimal import Decimal
    monkeypatch.setattr(get_settings(),'JEV_DATA_PROCESSING_APPROVED',True)
    async with test_session_factory() as db:
        run,p,pairs=await rerank_context(db,agent_context);provider=ChoiceProvider()
        f=JevReservationPolicy(fresh_period,Decimal('5'),65536,Decimal('.042'),date.today().isoformat(),frozenset(p.accepted_models),p.endpoint)
        await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion=pairs,provider_override=provider,financial_policy=f)
        first=pairs['api_design'][0];chunk=await db.get(RetrievalChunk,uuid.UUID(first.chunk_id))
        second=RetrievalChunk(id=uuid.uuid4(),sanitized_version_id=chunk.sanitized_version_id,chunk_index=1,
            text=chunk.text,span_ids=chunk.span_ids,embedding_config_id=chunk.embedding_config_id)
        db.add(second);await db.commit()
        pair2=first.model_copy(update={'chunk_id':str(second.id),'chunk_index':1,
            'pair_id':pair_id_for(first.criterion,str(second.id),first.text,first.span_ids,sanitized_version_id=run.sanitized_version_id,rubric_version_id=run.rubric_version_id)})
        result=await rerank_candidates(db=db,run=run,policy=p,stage='initial',candidates_by_criterion={'api_design':(first,pair2)},provider_override=provider,financial_policy=f)
        assert provider.calls==2 and len(result.judgments)==2
        rows=(await db.scalars(select(LLMInvocation).where(LLMInvocation.job_id==run.job_id).order_by(LLMInvocation.logical_step))).all()
        assert [r.logical_step for r in rows]==['jev_rerank_initial_1','jev_rerank_initial_2']
