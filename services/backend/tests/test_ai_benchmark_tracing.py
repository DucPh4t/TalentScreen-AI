import hashlib
import json
import uuid
import pytest
from app.services.observability import safe_metadata
from app.services.evaluation.benchmark.runner import run_experiment
from app.services.evaluation.benchmark.mock_provider import BenchmarkMockProvider
from app.services.evaluation.benchmark.artifacts import read_records
from tests.test_ai_benchmark_runner import experiment
from tests.test_ai_benchmark_isolation import owned_context
from tests.test_ai_benchmark_budget import fresh_period
from tests.test_langsmith_observability import enable_recording

def test_trace_allowlist_rejects_sensitive_and_secret_shaped_values():
    experiment_id=str(uuid.uuid4());case_hash=hashlib.sha256(b'node-01').hexdigest()
    values={'experiment_id':experiment_id,'benchmark_profile':'hybrid_agent','case_id_sha256':case_hash,
        'cached_input_tokens':3,'rejected_citations':1,'normalized_criteria':2,
        'cv_text':'RAW_SECRET_CV','prompt':'RAW_SECRET_CV','case_id':'Linh Nguyen','gold':'GOLD_NOT_FOR_MODEL'}
    filtered=safe_metadata(values)
    assert filtered=={k:v for k,v in values.items() if k not in {'cv_text','prompt','case_id','gold'}}
    assert not safe_metadata({'case_id_sha256':'sk-secret','benchmark_profile':'candidate-name','experiment_id':'lsv2_key','cached_input_tokens':True})

@pytest.mark.asyncio
@pytest.mark.parametrize('outage',[False,True])
async def test_langsmith_outage_does_not_change_assessment(outage,experiment,test_session_factory,monkeypatch):
    client=enable_recording(monkeypatch,fail=outage)
    inputs,selection,plan,context,output=experiment
    async with test_session_factory() as db:
        manifest=await run_experiment(db,inputs,selection,context,provider=BenchmarkMockProvider(),budget_plan=plan,output=output,embedding_mode='scripted')
    records=read_records(output/'runs.jsonl')
    assert manifest.status=='complete'
    assert all(r.status=='accepted' and all(c.score is None for c in r.criteria.values()) for r in records)
    assert manifest.provenance['embedding_device']=='scripted_test_double'
    payload=json.dumps([client.posts,client.patches])
    assert all(s not in payload for s in ('GOLD_NOT_FOR_MODEL','Linh Nguyen','example.test','source_spans','rubric"','sk-secret'))
    if not outage:
        roots=[p for p in client.posts if p['name']=='benchmark_combination']
        assert len(roots)==4
        assert all(p['extra']['metadata']['experiment_id']==str(context.experiment_id) for p in roots)
        assert all(p['extra']['metadata']['case_id_sha256']==hashlib.sha256(b'node-01').hexdigest() for p in roots)
        assert len({r.trace_id for r in records})==4
        assert all(not p.get('inputs') and not p.get('outputs') for p in client.posts+client.patches)

def test_real_benchmark_resolves_an_immutable_cached_revision(monkeypatch,tmp_path):
    import re
    from app.services.evaluation.benchmark.preflight import resolve_cached_embedding_revision
    from types import SimpleNamespace
    import sys
    snapshot=tmp_path/'snapshots'/('a'*40);snapshot.mkdir(parents=True)
    for name in ('config.json','tokenizer_config.json','tokenizer.json','model.safetensors'):(snapshot/name).write_text('test')
    def cached(model,name,revision):return str(snapshot/name) if (snapshot/name).exists() else None
    monkeypatch.setitem(sys.modules,'huggingface_hub',SimpleNamespace(try_to_load_from_cache=cached))
    revision=resolve_cached_embedding_revision()
    assert re.fullmatch('[0-9a-f]{40}',revision)
