"""Pipeline contract double; intentionally not an AI quality evaluator."""
import json
from contextlib import contextmanager
from app.services.llm.provider import BaseLLMProvider
from app.services.llm.types import CompletionResult

class BenchmarkMockProvider(BaseLLMProvider):
    def __init__(self):self.requests=[]
    async def complete(self,request):
        self.requests.append(request)
        messages=request.messages or [{'role':'user','content':request.user_prompt}]
        payload=next(json.loads(m['content']) for m in messages if m['role']=='user' and m['content'].lstrip().startswith('{'))
        result={'criteria':[{'criterion_id':c['criterion_id'],'status':'insufficient_evidence','score':None,
            'evidence':[],'rationale':'Contract-only mock; quality unmeasured.',
            'missing_information':['Please clarify individual evidence.']} for c in payload['rubric']]}
        return CompletionResult(content=json.dumps(result),requested_model=request.model,reported_model='mock',
            input_tokens=0,output_tokens=0,cached_input_tokens=0,latency_ms=0)

@contextmanager
def scripted_embeddings(enabled: bool):
    if not enabled:
        yield
        return
    from app.services import embedding
    class Tokenizer:
        def encode(self,text,**kwargs):return text.split()
    class Encoder:
        tokenizer=Tokenizer()
        def encode(self,texts,**kwargs):return [embedding._deterministic_mock_embed(t) for t in texts]
    original=embedding._get_embedding_model
    embedding._get_embedding_model=lambda:Encoder()
    try:yield
    finally:embedding._get_embedding_model=original
