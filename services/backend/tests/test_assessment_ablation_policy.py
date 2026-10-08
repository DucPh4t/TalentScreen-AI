"""Same assessment graph and prompts; only retrieval channels/tool permission vary."""
from dataclasses import FrozenInstanceError,replace
import hashlib
import json
from types import SimpleNamespace
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from app.db.models import AssessmentRun,RubricCriterion,SanitizedVersion,User
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole
from app.schemas.assessment import AssessmentRunCreateRequest
from app.services.assessment.policy import benchmark_policy,AssessmentExecutionPolicy
from app.services.assessment.prompt import get_assessment_prompt
from app.services.assessment.service import create_assessment_run
from app.services.agent.assessment_graph import run_assessment_agent,AgentExecutionError
from app.services.llm.types import CompletionResult,ToolCall
from app.services.retrieval import hybrid_retrieve_for_criterion,RetrievedChunkScore
from tests.test_assessment_agent import agent_context,ScriptedProvider,_insufficient_output,_score_output,SYNTHETIC_CANONICAL_TEXT

PROFILES=('full_text','dense','hybrid','hybrid_agent')

def freeze_policy(run,profile):
    policy=benchmark_policy(profile)
    run.snapshot={**run.snapshot,'assessment_execution_policy':policy.to_snapshot(),
        'assessment_execution_policy_hash':policy.digest,'assessment_prompt_version':policy.assessment_prompt_version,
        'retrieval_strategy':policy.retrieval_strategy}
    return policy

@pytest.mark.asyncio
async def test_four_profiles_share_prompt_and_source_snapshot(agent_context,test_session_factory):
    hashes=[]
    async with test_session_factory() as db:
        original=await db.get(AssessmentRun,agent_context['run_id'])
        version=await db.get(SanitizedVersion,original.sanitized_version_id)
        owner=await db.get(User,version.approved_by)
        ctx=AuthenticatedContext(owner,[AccountRole.ADMIN],None)
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==original.rubric_version_id))).all()
        payload=AssessmentRunCreateRequest(sanitized_version_id=original.sanitized_version_id,rubric_version_id=original.rubric_version_id)
        for profile in PROFILES:
            policy=benchmark_policy(profile)
            response=await create_assessment_run(db,original.application_id,payload,ctx,execution_policy=policy)
            run=await db.get(AssessmentRun,response.id)
            assert run.sanitized_version_id==original.sanitized_version_id and run.rubric_version_id==original.rubric_version_id
            assert run.snapshot['assessment_execution_policy_hash']==policy.digest
            provider=ScriptedProvider([CompletionResult(content=_insufficient_output(),requested_model='mock')])
            await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
                initial_pack={'source_span_ids':[agent_context['span_id']],
                    'criteria_retrieval_map':{c.criterion_id:[{'span_ids':[agent_context['span_id']]}] for c in criteria}},
                provider_override=provider,execution_policy=policy)
            request=provider.requests[0]
            assert bool(request.tools)==(profile=='hybrid_agent')
            assert request.max_output_tokens==4096 and request.temperature==0 and request.thinking_mode=='disabled'
            hashes.append((hashlib.sha256(request.messages[0]['content'].encode()).hexdigest(),request.model,
                           hashlib.sha256(json.dumps(request.messages[1],sort_keys=True).encode()).hexdigest()))
    assert len(set(hashes))==1

@pytest.mark.asyncio
@pytest.mark.parametrize('profile',PROFILES[:3])
async def test_disabled_tools_cannot_execute(profile,agent_context,test_session_factory):
    provider=ScriptedProvider([CompletionResult(content=None,requested_model='mock',tool_calls=[
        ToolCall(id='call_bad',name='retrieve_more_evidence',arguments={'criterion_ids':['python_backend'],'query_hint':'Python'})])])
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        policy=freeze_policy(run,profile)
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()
        with pytest.raises(AgentExecutionError,match='AGENT_UNAUTHORIZED_TOOL_CALL'):
            await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
                initial_pack={'source_span_ids':[],'criteria_retrieval_map':{}},provider_override=provider,execution_policy=policy)
        assert provider.requests[0].tools is None

@pytest.mark.asyncio
async def test_dense_does_not_execute_lexical_query(monkeypatch):
    import app.services.retrieval as retrieval
    monkeypatch.setattr(retrieval,'embed_texts',lambda *a,**k:[[1.0]+[0.0]*767])
    statements=[]
    version=uuid.uuid4()
    chunk=SimpleNamespace(id=uuid.uuid4(),chunk_index=0,text='REST API',span_ids=['spn_'+'a'*24])
    class DB:
        async def execute(self,stmt):
            statements.append(stmt)
            return SimpleNamespace(scalars=lambda:SimpleNamespace(all=lambda:[chunk]))
    dense=await hybrid_retrieve_for_criterion(DB(),version,'REST API','REST API',channels=frozenset({'dense'}))
    assert len(statements)==1 and dense[0].lexical_rank is None
    sql=str(statements[0].compile(dialect=postgresql.dialect()))
    assert 'to_tsquery' not in sql and 'sanitized_version_id' in sql and 'embedding_config_id' in sql
    assert version in statements[0].compile().params.values()
    statements.clear()
    hybrid=await hybrid_retrieve_for_criterion(DB(),version,'REST API','REST API')
    assert len(statements)==2 and hybrid[0].rrf_score==pytest.approx(2/61)
    assert 'to_tsquery' in str(statements[1].compile(dialect=postgresql.dialect()))


def test_old_snapshots_and_public_api_ignore_experimental_profiles():
    assert hashlib.sha256(get_assessment_prompt('assessment-v1.4.0').encode()).hexdigest()=='e12febda5b46049db5c7b09b2ba943e3ce343a624011ac214c526b975ffa12cc'
    assert hashlib.sha256(get_assessment_prompt('assessment-v1.5.0').encode()).hexdigest()=='a841ea21e60d71f628f5e223b26148fe5189fb41ea691a072f08594fe404e1f4'
    payload=AssessmentRunCreateRequest(sanitized_version_id=uuid.uuid4(),rubric_version_id=uuid.uuid4(),
        assessment_execution_policy={'profile':'hybrid_agent'})
    assert 'assessment_execution_policy' not in payload.model_dump()
    policy=benchmark_policy('dense')
    with pytest.raises(FrozenInstanceError): policy.tools_enabled=True
    with pytest.raises(ValueError): replace(policy,tools_enabled=True)
    with pytest.raises(ValueError): AssessmentExecutionPolicy.from_snapshot({**policy.to_snapshot(),'max_output_tokens':9000})

@pytest.mark.asyncio
async def test_agent_empty_pack_recovers_then_repairs_with_four_outbound_calls(agent_context,test_session_factory,monkeypatch):
    import app.services.agent.assessment_graph as graph
    span_id=agent_context['span_id']
    async def retrieve(**kwargs):
        return [RetrievedChunkScore(uuid.uuid4(),0,SYNTHETIC_CANONICAL_TEXT,[span_id],1,1,2/61)]
    monkeypatch.setattr(graph,'retrieve_more_evidence',retrieve)
    provider=ScriptedProvider([
        CompletionResult(content=None,requested_model='mock',tool_calls=[ToolCall(id='call_one',name='retrieve_more_evidence',arguments={
            'criterion_ids':['python_backend','api_design'],'query_hint':'Python REST'})]),
        CompletionResult(content=None,requested_model='mock',tool_calls=[ToolCall(id='call_two',name='get_source_spans',arguments={'span_ids':[span_id]})]),
        CompletionResult(content='{}',requested_model='mock'),
        CompletionResult(content=_score_output(span_id,SYNTHETIC_CANONICAL_TEXT),requested_model='mock')])
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        policy=freeze_policy(run,'hybrid_agent')
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()
        result=await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
            initial_pack={'source_span_ids':[],'criteria_retrieval_map':{}},provider_override=provider,execution_policy=policy)
        assert all(c.score==3 for c in result.output.criteria)
        assert len(provider.requests)==4 and result.trace['repair_count']==1 and result.trace['tool_execution_count']==2
        assert provider.requests[-1].tools is None

@pytest.mark.asyncio
async def test_repair_exhaustion_fails_after_two_calls(agent_context,test_session_factory):
    provider=ScriptedProvider([CompletionResult(content='{}',requested_model='mock') for _ in range(2)])
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        policy=freeze_policy(run,'dense')
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()
        with pytest.raises(AgentExecutionError,match='ASSESSMENT_OUTPUT_INVALID'):
            await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
                initial_pack={'source_span_ids':[],'criteria_retrieval_map':{}},provider_override=provider,execution_policy=policy)
        assert len(provider.requests)==2

@pytest.mark.asyncio
async def test_profile_rejects_oversized_initial_evidence_before_call(agent_context,test_session_factory):
    from app.db.models import SourceSpan
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        policy=freeze_policy(run,'hybrid_agent')
        span=await db.get(SourceSpan,agent_context['span_id'])
        span.text='a'*24001
        await db.flush()
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()
        provider=ScriptedProvider([CompletionResult(content=_insufficient_output(),requested_model='mock')])
        with pytest.raises(ValueError,match='ASSESSMENT_CONTEXT_LIMIT'):
            await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
                initial_pack={'source_span_ids':[span.span_id],
                    'criteria_retrieval_map':{c.criterion_id:[{'span_ids':[span.span_id]}] for c in criteria}},
                provider_override=provider,execution_policy=policy)
        assert not provider.requests
