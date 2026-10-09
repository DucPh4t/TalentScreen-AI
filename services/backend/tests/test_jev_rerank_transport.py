from datetime import date
import hashlib
import json
import httpx
import pytest
from app.services.jev.provider import JevHTTPXProvider
from app.services.llm.types import CompletionRequest
from app.services.llm.orchestrator import _serialized_request_payload
from tests.test_rerank_kernel import pair,policy
from app.services.reranking.prompt import build_jev_payload


@pytest.mark.asyncio
async def test_rerank_transport_matches_wire_hash_and_frozen_model(monkeypatch):
    from app.services.reranking.contracts import canonical
    from tests.test_rerank_policy import valid_settings
    monkeypatch.setattr('app.services.jev.provider.get_settings',lambda:valid_settings())
    p=policy();payload=build_jev_payload((pair(1),),p);sent=[]
    def handler(request):
        sent.append(request.content)
        return httpx.Response(200,json={'model':p.accepted_models[0],'answers':{'c-1':{'type':'choice','choice':'unrelated',
            'confidence':1.0,'probabilities':{k:float(k=='unrelated') for k in payload['questions']['c-1']['criteria']}}},'usage':{'input_tokens':0,'output_tokens':0}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider=JevHTTPXProvider(api_key='synthetic',model='incorrect-default',api_url=p.endpoint,client=client,policy=p)
        request=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt=canonical(payload),model=p.requested_model,
            max_output_tokens=0,provider='jev',purpose='jev_rerank')
        result=await provider.complete(request)
    assert len(sent)==1
    assert hashlib.sha256(sent[0]).hexdigest()==hashlib.sha256(_serialized_request_payload(request).encode()).hexdigest()
    assert json.loads(sent[0])['model']=='typesafe/jev-1.13'
    assert result.input_tokens==0


def test_request_byte_cap_rejected_before_egress():
    from app.services.llm.call_policy import JevReservationPolicy
    import uuid
    from decimal import Decimal
    p=JevReservationPolicy(uuid.uuid4(),Decimal('1'),65536,Decimal('.042'),date.today().isoformat(),frozenset({'typesafe/jev-1.13-20260917'}),'https://openrouter.ai/api/alpha/decisions')
    r=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt=json.dumps({'model':'typesafe/jev-1.13','state':'x'*16385,'questions':{'q':{}}}),provider='jev',model='typesafe/jev-1.13')
    with pytest.raises(ValueError):p.input_reservation_tokens(r)

@pytest.mark.asyncio
@pytest.mark.parametrize('drift',['endpoint','model'])
async def test_transport_cannot_drift_from_frozen_policy(monkeypatch,drift):
    from tests.test_rerank_policy import valid_settings
    from app.services.llm.exceptions import LLMProviderError
    from app.services.reranking.contracts import canonical
    monkeypatch.setattr('app.services.jev.provider.get_settings',lambda:valid_settings())
    p=policy();payload=build_jev_payload((pair(1),),p)
    def no_http(request):raise AssertionError('drift must fail before HTTP')
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_http)) as client:
        provider=JevHTTPXProvider(api_key='synthetic',api_url='https://unapproved.example/test' if drift=='endpoint' else p.endpoint,client=client,policy=p)
        request=CompletionRequest(task_kind='assessment',system_prompt='',user_prompt=canonical(payload),model='unapproved/model' if drift=='model' else p.requested_model,
            max_output_tokens=0,provider='jev',purpose='jev_rerank')
        with pytest.raises(LLMProviderError):await provider.complete(request)
