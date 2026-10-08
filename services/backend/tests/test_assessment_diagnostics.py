"""Local diagnostics preserve rejected raw claims without exporting candidate text."""
import json
import pytest
from sqlalchemy import select
from app.db.models import AssessmentRun,RubricCriterion
from app.services.assessment.diagnostics import AssessmentDiagnostics
from app.services.agent.assessment_graph import run_assessment_agent
from app.services.llm.types import CompletionResult
from tests.test_assessment_agent import agent_context,ScriptedProvider,_score_output,SYNTHETIC_CANONICAL_TEXT


def span(i): return 'spn_'+f'{i:024x}'

def test_candidate_pool_and_delivered_pack_are_distinct():
    recorder=AssessmentDiagnostics({'api_design'})
    recorder.record_retrieval('api_design',[[span(i)] for i in range(10)],[span(i) for i in range(4)])
    snapshot=recorder.snapshot()
    assert len(snapshot['ranked_evidence']['api_design'])==10
    assert len(snapshot['initial_evidence']['api_design'])==4
    assert snapshot['stage_ms']['graph'] is None
    snapshot['initial_evidence']['api_design'].clear()
    assert len(recorder.snapshot()['initial_evidence']['api_design'])==4


def test_recorder_excludes_text_and_is_run_scoped():
    recorder=AssessmentDiagnostics({'api_design'})
    marker='CV_SECRET sk-or-v1-example@example.test'
    recorder.record_retrieval('api_design',[[span(1),marker]],[span(1),marker])
    recorder.record_retrieval(marker,[[span(1)]],[span(1)])
    recorder.record_stage(marker,42)
    recorder.record_stage('graph',float('nan'))
    recorder.record_stage('graph',12.5)
    recorder.record_validation(rejected_citations=1,normalized_criteria=2,schema_failures=0)
    recorder.record_final_evidence({'api_design':[span(1),marker],marker:[span(1)]})
    assert marker not in json.dumps(recorder.snapshot())
    assert recorder.snapshot()['stage_ms']['graph']==12.5
    assert AssessmentDiagnostics({'api_design'}).snapshot()['counters']['normalized_criteria']==0

@pytest.mark.asyncio
@pytest.mark.parametrize('empty_pack',[False,True])
async def test_validator_does_not_hide_raw_model_errors(empty_pack,agent_context,test_session_factory):
    span_id=agent_context['span_id']
    raw=_score_output(span_id,SYNTHETIC_CANONICAL_TEXT)
    responses=[CompletionResult(content=raw,requested_model='mock')]
    if not empty_pack:
        responses=[CompletionResult(content=raw.replace(SYNTHETIC_CANONICAL_TEXT,'CV_SECRET wrong quote'),requested_model='mock'),*responses]
    provider=ScriptedProvider(responses)
    recorder=AssessmentDiagnostics({'api_design','python_backend'})
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()
        pack={'source_span_ids':[] if empty_pack else [span_id],
              'criteria_retrieval_map':{c.criterion_id:[] if empty_pack else [{'span_ids':[span_id]}] for c in criteria}}
        result=await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,initial_pack=pack,provider_override=provider,diagnostics=recorder)
    metrics=recorder.snapshot()
    assert metrics['counters']['rejected_citations']>=2
    assert metrics['stage_ms']['graph'] is not None and metrics['stage_ms']['validation_scoring'] is not None
    if empty_pack:
        assert metrics['counters']['normalized_criteria']==2
        assert all(c.score is None for c in result.output.criteria)
    else:
        assert result.trace['repair_count']==1 and all(c.score==3 for c in result.output.criteria)
    assert 'CV_SECRET' not in json.dumps(metrics)

@pytest.mark.asyncio
async def test_recorder_failure_does_not_change_graph_result(agent_context,test_session_factory):
    class BrokenRecorder:
        def __getattr__(self,name):
            def fail(*args,**kwargs):raise RuntimeError('telemetry unavailable')
            return fail
    provider=ScriptedProvider([CompletionResult(content=_score_output(agent_context['span_id'],SYNTHETIC_CANONICAL_TEXT),requested_model='mock')])
    async with test_session_factory() as db:
        run=await db.get(AssessmentRun,agent_context['run_id'])
        criteria=(await db.scalars(select(RubricCriterion).where(RubricCriterion.rubric_version_id==run.rubric_version_id))).all()
        result=await run_assessment_agent(db=db,run=run,rubric_criteria=criteria,
            initial_pack={'source_span_ids':[agent_context['span_id']],
                'criteria_retrieval_map':{c.criterion_id:[{'span_ids':[agent_context['span_id']]}] for c in criteria}},
            provider_override=provider,diagnostics=BrokenRecorder())
        assert all(c.score==3 for c in result.output.criteria)
