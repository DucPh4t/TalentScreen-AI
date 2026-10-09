"""V2 retrieval isolates claims and repetition without changing canonical spans."""
from pathlib import Path
import json
import uuid
import pytest
from app.db.models.document import SourceSpan
from app.services.evaluation.benchmark.runner import main


def spans_for(texts):
    offset=0;result=[];version=uuid.uuid4()
    for n,text in enumerate(texts):
        result.append(SourceSpan(span_id='spn_'+f'{n:024x}',full_hash='a'*64,sanitized_version_id=version,
            start_cp=offset,end_cp=offset+len(text),text=text,section_label=None,page_number=1,language='mixed'))
        offset+=len(text)+1
    return result


def test_v2_indexes_individual_claims_and_retains_contradictions():
    from app.services.embedding import build_evidence_chunks_from_spans
    spans=spans_for(['I built and tested an event processor.','Team plans listed an event processor.',
        'Team plans listed an event processor.','Correction: another developer implemented the event processor.'])
    chunks=build_evidence_chunks_from_spans(spans,lambda text:len(text.split()))
    assert len(chunks)==3
    assert [c['span_ids'] for c in chunks]==[[spans[0].span_id],[spans[1].span_id],[spans[3].span_id]]
    assert [c['text'] for c in chunks]==[spans[0].text,spans[1].text,spans[3].text]
    assert all(span.text==text for span,text in zip(spans,['I built and tested an event processor.',
        'Team plans listed an event processor.','Team plans listed an event processor.',
        'Correction: another developer implemented the event processor.']))


def test_v2_query_keeps_bilingual_skill_terms_before_long_rubric_prose():
    from app.services.retrieval import _build_evidence_query
    query,terms=_build_evidence_query('Machine learning','Generic explanation '*500,
        {'vi':['triển khai mô hình ML'],'en':['deployed ML inference']},['Generic anchors '*500])
    assert 'deployed ML inference' in query and 'triển khai mô hình ML' in query
    assert 'ml' in terms
    assert len(query)<=800


def test_pipeline_policies_keep_legacy_snapshot_and_pin_new_version():
    from app.services.assessment.policy import benchmark_policy,AssessmentExecutionPolicy
    old=benchmark_policy('hybrid')
    new=benchmark_policy('hybrid',retrieval_version='v2')
    assert 'retrieval_version' not in old.to_snapshot()
    assert new.to_snapshot()['retrieval_version']=='v2'
    assert old.digest!=new.digest
    assert AssessmentExecutionPolicy.from_snapshot(old.to_snapshot())==old
    assert AssessmentExecutionPolicy.from_snapshot(new.to_snapshot())==new


def test_cli_plan_declares_retrieval_version(capsys):
    data=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/v2'
    assert main(['plan','--dataset',str(data),'--provider','mock','--embedding-mode','scripted',
        '--cases','v2-node-10','--retrieval-version','v2'])==0
    payload=json.loads(capsys.readouterr().out)
    assert payload['retrieval_version']=='v2'

# These fixtures use deterministic vectors for SQL scoping, not model quality.
from tests.test_assessment_agent import agent_context
from tests.test_hybrid_retrieval import deterministic_embedding_model

@pytest.mark.asyncio
async def test_versions_coexist_and_retrieve_only_the_pinned_index(agent_context,test_session_factory,deterministic_embedding_model):
    from sqlalchemy import select
    from app.db.models import AssessmentRun,RetrievalChunk
    from app.services.embedding import index_sanitized_version,embedding_config_id
    from app.services.retrieval import hybrid_retrieve_for_criterion
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        for version in ('v1','v2'):
            assert await index_sanitized_version(db,run.sanitized_version_id,pipeline_version=version)==1
        chunks=list(await db.scalars(select(RetrievalChunk).where(RetrievalChunk.sanitized_version_id==run.sanitized_version_id)))
        assert len(chunks)==2
        before={c.id for c in chunks}
        assert await index_sanitized_version(db,run.sanitized_version_id,pipeline_version='v2')==1
        for version in ('v1','v2'):
            found=await hybrid_retrieve_for_criterion(db,run.sanitized_version_id,'Python','REST API',pipeline_version=version)
            assert {r.chunk_id for r in found}=={c.id for c in chunks if c.embedding_config_id==embedding_config_id(version)}
            assert not await hybrid_retrieve_for_criterion(db,uuid.uuid4(),'Python','REST API',pipeline_version=version)
        assert before==set(await db.scalars(select(RetrievalChunk.id).where(RetrievalChunk.sanitized_version_id==run.sanitized_version_id)))


def test_v2_chunk_splitting_preserves_exact_source_and_sections():
    from app.services.embedding import build_evidence_chunks_from_spans
    spans=spans_for([' '.join(f'token{i}' for i in range(1000)), 'Duplicate claim.', 'Duplicate claim.'])
    spans[1].section_label='Experience';spans[2].section_label='Projects'
    chunks=build_evidence_chunks_from_spans(spans,lambda text:len(text.split()))
    assert ''.join(c['text'] for c in chunks if c['span_ids']==[spans[0].span_id])==spans[0].text
    assert all(len(c['text'].split())<=480 for c in chunks)
    assert {c['section_label'] for c in chunks if c['text']=='Duplicate claim.'}=={'Experience','Projects'}

@pytest.mark.asyncio
async def test_unknown_packing_version_fails_before_egress(agent_context,test_session_factory,monkeypatch):
    from app.db.models import AssessmentRun
    from app.services.assessment.service import execute_assessment_job
    from tests.test_assessment_agent import ScriptedProvider
    from app.services import embedding
    def forbidden_load():raise AssertionError('No embedding/provider setup allowed before version validation')
    monkeypatch.setattr(embedding,'_get_embedding_model',forbidden_load)
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        run.snapshot={**run.snapshot,'request_packing_version':'unknown-future-packer'}
        provider=ScriptedProvider([])
        await execute_assessment_job(db,run.job_id,provider_override=provider)
        assert run.status=='failed' and run.failure_code=='ASSESSMENT_REQUEST_PACKING_VERSION_UNKNOWN'
        assert provider.requests==[]
