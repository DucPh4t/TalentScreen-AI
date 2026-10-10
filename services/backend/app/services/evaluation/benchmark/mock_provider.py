"""Pipeline contract double; intentionally not an AI quality evaluator."""
import json
from app import config
from contextlib import contextmanager
from app.services.llm.provider import BaseLLMProvider
from app.services.llm.types import CompletionResult

class BenchmarkMockProvider(BaseLLMProvider):
    def __init__(self):self.requests=[]
    async def complete(self,request):
        self.requests.append(request)
        messages=request.messages or [{'role':'user','content':request.user_prompt}]
        payload=next(json.loads(m['content']) for m in messages if m['role']=='user' and m['content'].lstrip().startswith('{'))
        if request.purpose=='jev_primary_explanation':
            result={'criteria':[{
                'criterion_id':criterion['criterion_id'],
                'explanation_vi':'Contract-only mock; quality unmeasured.',
                'basis_span_ids':[item['span_id'] for item in criterion.get('evidence',[])],
                'followup_questions':[],
            } for criterion in payload['state']]}
        elif config.get_settings().ASSESSMENT_SCORER_MODE=='jev':
            source_by_id={span['span_id']:span['quote'] for span in payload['source_spans']}
            retrieved=payload.get('retrieved_evidence_by_criterion',{})
            criteria=[]
            for criterion in payload['rubric']:
                criterion_id=criterion['criterion_id']
                evidence=[{'span_id':span_id,'quote':source_by_id[span_id]}
                    for span_id in retrieved.get(criterion_id,[]) if span_id in source_by_id][:1]
                criteria.append({
                    'criterion_id':criterion_id,
                    'status':'assessed' if evidence else 'insufficient_evidence',
                    'evidence':evidence,
                    'rationale':'Contract-only mock; quality unmeasured.',
                    'missing_information':[] if evidence else ['Please clarify individual evidence.'],
                })
            result={'criteria':criteria}
        else:
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
