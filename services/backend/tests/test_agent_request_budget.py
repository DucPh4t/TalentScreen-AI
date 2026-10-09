"""Request size must fail/fit before egress without changing canonical evidence."""
import json
import hashlib
import uuid
import pytest
from sqlalchemy import select
from app.db.models import AssessmentRun, RubricCriterion, SourceSpan, SanitizedVersion
from app.services.llm.types import CompletionRequest, CompletionResult
from app.services.llm.orchestrator import _serialized_request_payload
from tests.test_assessment_agent import agent_context, ScriptedProvider, _insufficient_output


def request_with_quotes(quotes):
    return CompletionRequest(task_kind='assessment',system_prompt='',user_prompt='',model='mock',thinking_mode='disabled',messages=[
        {'role':'system','content':'Use only supplied evidence.'},
        {'role':'user','content':json.dumps({'source_spans':[{'span_id':k,'quote':v} for k,v in quotes.items()],
            'retrieved_evidence_by_criterion':{'skill_a':list(quotes)},'rubric':[]},ensure_ascii=False,indent=2)}])


def test_request_fitter_preserves_whole_quotes_and_removes_stale_scope():
    from app.services.agent.request_budget import fit_evidence_request
    quotes={'spn_'+'a'*24:'Kỹ năng "API"\nđã kiểm thử.','spn_'+'b'*24:'漢字'*400}
    request=request_with_quotes(quotes)
    original=json.loads(request.messages[1]['content'])
    fitted,removed,metadata=fit_evidence_request(request,list(quotes),byte_limit=900)
    assert removed==['spn_'+'b'*24]
    payload=json.loads(fitted.messages[1]['content'])
    assert payload['source_spans']==[{'span_id':'spn_'+'a'*24,'quote':'Kỹ năng "API"\nđã kiểm thử.'}]
    assert payload['retrieved_evidence_by_criterion']=={'skill_a':['spn_'+'a'*24]}
    assert len(_serialized_request_payload(fitted).encode())<=900
    assert metadata['excluded_span_count']==1
    assert json.loads(request.messages[1]['content'])==original


def test_tool_history_quote_is_removed_together_with_initial_quote():
    from app.services.agent.request_budget import fit_evidence_request
    a,b='spn_'+'a'*24,'spn_'+'b'*24
    request=request_with_quotes({a:'Python validation.',b:'語'*1200})
    request.messages.extend([
        {'role':'assistant','content':None,'tool_calls':[{'id':'call_read','type':'function','function':{'name':'get_source_spans','arguments':json.dumps({'span_ids':[b]})}}]},
        {'role':'tool','tool_call_id':'call_read','content':json.dumps({'source_spans':[{'span_id':b,'quote':'語'*1200}]},ensure_ascii=False)}])
    fitted,removed,metadata=fit_evidence_request(request,[a,b],byte_limit=1200)
    assert removed==[b]
    assert json.loads(fitted.messages[-1]['content'])['source_spans']==[]
    assert fitted.messages[-2]['tool_calls'][0]['id']=='call_read'
    assert len(_serialized_request_payload(fitted).encode())<=1200
    assert '語' not in fitted.messages[-1]['content']


def test_fixed_overhead_cannot_be_silently_truncated():
    from app.services.agent.request_budget import fit_evidence_request, RequestBudgetError
    request=request_with_quotes({})
    request.messages[0]['content']='Required policy '*500
    with pytest.raises(RequestBudgetError,match='ASSESSMENT_REQUEST_OVERHEAD_LIMIT'):
        fit_evidence_request(request,[],byte_limit=900)


@pytest.mark.asyncio
async def test_actual_agent_drops_oversized_whole_span_before_provider(agent_context,test_session_factory):
    from app.services.agent.assessment_graph import run_assessment_agent
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        span=await db.scalar(select(SourceSpan).where(SourceSpan.span_id==agent_context['span_id']))
        # Controlled synthetic fixture authored before executing this run.
        span.text='ữ'*23500;span.end_cp=23500
        span.full_hash=hashlib.sha256(span.text.encode()).hexdigest()
        sanitized=await db.get(SanitizedVersion,run.sanitized_version_id)
        sanitized.canonical_text=span.text;sanitized.sha256=span.full_hash
        criteria=list(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id)))
        await db.flush()
        provider=ScriptedProvider([CompletionResult(content=_insufficient_output(),requested_model='mock')])
        from app.config import get_settings
        old=get_settings().DEEPSEEK_MODEL;get_settings().DEEPSEEK_MODEL='mock'
        try:
            result=await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
                initial_pack={'strategy':'hybrid','source_span_ids':[span.span_id],'criteria_retrieval_map':{c.criterion_id:[{'span_ids':[span.span_id]}] for c in criteria}},
                provider_override=provider)
        finally:get_settings().DEEPSEEK_MODEL=old
        assert provider.requests and all(len(_serialized_request_payload(r).encode())<=65536 for r in provider.requests)
        assert result.source_spans=={}
        assert all(c.score is None for c in result.output.criteria)


def test_expanded_evidence_evicts_old_whole_spans_to_fit_character_cap():
    from app.services.agent.request_budget import fit_evidence_request
    old,new='spn_'+'a'*24,'spn_'+'b'*24
    request=request_with_quotes({old:'x'*600,new:'y'*600})
    fitted,removed,metadata=fit_evidence_request(request,[new,old],byte_limit=3000,max_evidence_chars=1000)
    assert removed==[old]
    assert json.loads(fitted.messages[1]['content'])['source_spans']==[{'span_id':new,'quote':'y'*600}]

@pytest.mark.asyncio
async def test_invalid_model_output_is_not_replayed_into_repair_request(agent_context,test_session_factory,monkeypatch):
    from app.services.agent.assessment_graph import run_assessment_agent
    from app.config import get_settings
    monkeypatch.setattr(get_settings(),'DEEPSEEK_MODEL','mock')
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        criteria=list(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id)))
        provider=ScriptedProvider([CompletionResult(content='INVALID_PRIVATE_MARKER'+'語'*70000,requested_model='mock'),
            CompletionResult(content=_insufficient_output(),requested_model='mock')])
        result=await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
            initial_pack={'strategy':'hybrid','source_span_ids':[agent_context['span_id']],
                'criteria_retrieval_map':{c.criterion_id:[{'span_ids':[agent_context['span_id']]}] for c in criteria}},provider_override=provider)
        assert result.trace['repair_count']==1 and len(provider.requests)==2
        assert all(len(_serialized_request_payload(r).encode())<=65536 for r in provider.requests)
        assert 'INVALID_PRIVATE_MARKER' not in _serialized_request_payload(provider.requests[-1])

@pytest.mark.asyncio
async def test_canonical_accounting_bounds_actual_http_transport_bytes():
    import httpx
    from app.services.llm.provider import DeepSeekHTTPXProvider
    from app.services.agent.request_budget import fit_evidence_request,serialized_bytes
    captured=[]
    def receive(request):
        captured.append(request.content)
        return httpx.Response(200,json={'model':'mock','choices':[{'message':{'content':'{}'}}],'usage':{'prompt_tokens':1,'completion_tokens':1}})
    req,_,_=fit_evidence_request(request_with_quotes({'spn_'+'a'*24:'Tiếng Việt: "ữ"\n漢字.'}),['spn_'+'a'*24])
    async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
        await DeepSeekHTTPXProvider(api_key='synthetic-test-key',api_url='https://unit.invalid/chat/completions',client=client).complete(req)
    assert captured and len(captured[0])<=serialized_bytes(req)<=65536

@pytest.mark.asyncio
async def test_actual_tool_expansion_fits_by_evicting_old_context(agent_context,test_session_factory,monkeypatch):
    from app.services.agent import assessment_graph
    from app.services.llm.types import ToolCall
    from app.services.retrieval import RetrievedChunkScore
    from app.config import get_settings
    monkeypatch.setattr(get_settings(),'DEEPSEEK_MODEL','mock')
    new_id='spn_'+uuid.uuid4().hex[:24]
    async def retrieve(**kwargs):
        return [RetrievedChunkScore(uuid.uuid4(),1,'y'*16000,[new_id],1,1,.03)]
    monkeypatch.setattr(assessment_graph,'retrieve_more_evidence',retrieve)
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        old=await db.scalar(select(SourceSpan).where(SourceSpan.span_id==agent_context['span_id']))
        old.text='x'*16000;old.end_cp=16000;old.full_hash=hashlib.sha256(old.text.encode()).hexdigest()
        sanitized=await db.get(SanitizedVersion,run.sanitized_version_id)
        sanitized.canonical_text=old.text+'\n'+'y'*16000
        sanitized.sha256=hashlib.sha256(sanitized.canonical_text.encode()).hexdigest()
        db.add(SourceSpan(span_id=new_id,full_hash=hashlib.sha256(('y'*16000).encode()).hexdigest(),
            sanitized_version_id=run.sanitized_version_id,start_cp=16001,end_cp=32001,text='y'*16000,
            section_label='experience',page_number=1,language='en'))
        criteria=list(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id)))
        await db.flush()
        provider=ScriptedProvider([
            CompletionResult(content=None,requested_model='mock',tool_calls=[ToolCall(id='call_retrieve1',name='retrieve_more_evidence',arguments={'criterion_ids':['python_backend'],'query_hint':'Python'})]),
            CompletionResult(content='ECHO_PRIVATE_OLD'+old.text,requested_model='mock',tool_calls=[ToolCall(id='call_read1',name='get_source_spans',arguments={'span_ids':[new_id]})]),
            CompletionResult(content=_insufficient_output(),requested_model='mock')])
        result=await assessment_graph.run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
            initial_pack={'strategy':'hybrid','source_span_ids':[old.span_id],
                'criteria_retrieval_map':{c.criterion_id:[{'span_ids':[old.span_id]}] for c in criteria}},provider_override=provider)
        assert result.trace['tool_execution_count']==2 and len(provider.requests)==3
        assert set(result.source_spans)=={new_id}
        assert 'ECHO_PRIVATE_OLD' not in _serialized_request_payload(provider.requests[-1])
        for request in provider.requests:
            assert len(_serialized_request_payload(request).encode())<=65536
            quotes={}
            for message in request.messages:
                if message.get('role') in {'user','tool'}:
                    try: payload=json.loads(message['content'])
                    except ValueError: continue
                    quotes.update({s['span_id']:s['quote'] for s in payload.get('source_spans',[])})
            assert sum(map(len,quotes.values()))<=24000
        assert json.loads(provider.requests[-1].messages[1]['content'])['source_spans']==[]
        assert provider.requests[-1].messages[-1]['tool_call_id']=='call_read1'

@pytest.mark.asyncio
async def test_partial_optional_context_does_not_crash_assessment(agent_context,test_session_factory,monkeypatch):
    from app.services.agent.assessment_graph import run_assessment_agent
    from app.services.assessment.diagnostics import AssessmentDiagnostics
    from app.config import get_settings
    monkeypatch.setattr(get_settings(),'DEEPSEEK_MODEL','mock')
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        criteria=list(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id)))
        diag=AssessmentDiagnostics({c.criterion_id for c in criteria});diag.record_context(character_limit=24000)
        result=await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
            initial_pack={'strategy':'hybrid','source_span_ids':[agent_context['span_id']],
                'criteria_retrieval_map':{c.criterion_id:[{'span_ids':[agent_context['span_id']]}] for c in criteria}},
            diagnostics=diag,provider_override=ScriptedProvider([CompletionResult(content=_insufficient_output(),requested_model='mock')]))
        assert result.trace['outcome']=='validated'
