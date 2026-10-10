"""Explicit real-weight smoke; generic CI must neither download nor call LLMs."""
import json
import math
import os
from pathlib import Path
import pytest
from sqlalchemy import select
from app.config import get_settings
from app.db.models import SourceSpan
from app.services.evaluation.benchmark.dataset import load_inputs,select_runs
from app.services.evaluation.benchmark.seed import seed_cases
from app.services.evaluation.benchmark.preflight import embedding_cache_available,resolve_cached_embedding_revision
from tests.test_ai_benchmark_isolation import owned_context

DATA=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/golden_100'

@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('TALENTSCREEN_REAL_E5_SMOKE')!='1',reason='Real E5 smoke is opt-in; generic CI is offline.')
async def test_real_e5_smoke_is_explicit_and_uses_actual_device(test_session_factory,owned_context,monkeypatch):
    assert os.environ.get('HF_HUB_OFFLINE')=='1' and os.environ.get('TRANSFORMERS_OFFLINE')=='1'
    assert embedding_cache_available(),'Pinned E5 weights must be cached; missing cache is not a passing semantic test.'
    from app.services.embedding import _get_embedding_model,embed_texts,index_sanitized_version,EMBEDDING_CONFIG_ID
    from app.services.retrieval import hybrid_retrieve_for_criterion
    from app.services.llm.provider import DeepSeekHTTPXProvider
    async def forbidden(*a,**kw):raise AssertionError('No paid calls in real embedding smoke')
    monkeypatch.setattr(DeepSeekHTTPXProvider,'complete',forbidden)
    revision=resolve_cached_embedding_revision()
    monkeypatch.setattr(get_settings(),'EMBEDDING_MODEL_REVISION',revision)
    from app.services import embedding,retrieval
    pinned_config=f'{get_settings().EMBEDDING_MODEL}@{revision}:{embedding.CHUNK_FORMAT_VERSION}'
    monkeypatch.setattr(embedding,'EMBEDDING_CONFIG_ID',pinned_config)
    monkeypatch.setattr(retrieval,'EMBEDDING_CONFIG_ID',pinned_config)
    model=_get_embedding_model()
    assert type(model).__name__=='SentenceTransformer'
    device=str(model.device)
    vectors=embed_texts(['Thiết kế API và PostgreSQL','Machine learning inference','Android Kotlin'],prefix='query: ')
    assert len(vectors)==3
    assert all(len(v)==768 and abs(math.sqrt(sum(x*x for x in v))-1)<1e-6 for v in vectors)
    inputs=load_inputs(DATA);selection=select_runs(inputs,split=None,case_ids=('backend-008','backend-009','backend-011'),profiles=('dense',),seed=1)
    scopes=[]
    async with test_session_factory() as db:
        seeded=await seed_cases(db,inputs,selection,owned_context)
        for case_id,item in seeded.items():
            assert await index_sanitized_version(db,item.sanitized_version_id)>0
            role=next(c.role_family for c in inputs.cases if c.case_id==case_id)
            criterion=inputs.roles[role].criteria[0]
            found=await hybrid_retrieve_for_criterion(db,item.sanitized_version_id,criterion.label,criterion.description,top_k=10,channels=frozenset({'dense'}))
            assert found
            registry=set(await db.scalars(select(SourceSpan.span_id).where(SourceSpan.sanitized_version_id==item.sanitized_version_id)))
            assert all(set(row.span_ids)<=registry and row.lexical_rank is None for row in found)
            scopes.append({'role':role,'retrieved_chunks':len(found),'scope_ok':True})
    print('REAL_E5_SMOKE '+json.dumps({'device':device,'config':pinned_config,'dimension':768,'normalized':True,'scopes':scopes}))
