from decimal import Decimal
from pathlib import Path
import uuid
import pytest
from app.services.evaluation.benchmark.contracts import RunManifest,RunRecord,CriterionObservation
from app.services.evaluation.benchmark.dataset import load_inputs,load_references,select_runs
from app.services.evaluation.benchmark.preflight import plan_budget
from app.services.assessment.policy import benchmark_policy
from app.services.evaluation.benchmark.metrics import evaluate_records,paired_cluster_interval
from tests.test_ai_benchmark_budget import byte_bound
DATA=Path(__file__).resolve().parents[3]/'fixtures/ai_benchmark/v1'

def fixture_report(provider='deepseek'):
    inputs=load_inputs(DATA);refs=load_references(DATA,inputs)
    selection=select_runs(inputs,split=None,case_ids=('node-01',),profiles=('dense','hybrid'),seed=1)
    plan=plan_budget(inputs,selection,{p:benchmark_policy(p) for p in selection.profiles},model='mock',cap_usd=Decimal(5),bound=byte_bound())
    manifest=RunManifest(experiment_id=uuid.uuid4(),status='partial',mode='contract_only' if provider=='mock' else 'live_model',
        model_quality='unmeasured' if provider=='mock' else 'synthetic_reference_only',provider=provider,requested_model='mock',embedding_mode='scripted',
        selection=selection,dataset_hash=inputs.manifest_hash,dataset_files=inputs.hashes,policies={},provenance={},budget_plan=plan,
        budget_period_id=uuid.uuid4(),started_at='2026-10-09T00:00:00Z')
    criteria={c:CriterionObservation(status='insufficient_evidence',score=None,clarification_count=1) for c in refs['node-01'].criteria}
    criterion=next(iter(criteria));spans=[e.span_id for g in refs['node-01'].criteria[criterion].sufficient_evidence_groups for e in g]
    criteria[criterion]=CriterionObservation(status='assessed',score=0,evidence_ids=tuple(spans))
    rows=[RunRecord(case_id='node-01',profile='dense',status='accepted',policy_hash=benchmark_policy('dense').digest,criteria=criteria),
          RunRecord(case_id='node-01',profile='hybrid',status='failed',error_code='TEST_FAILURE',policy_hash=benchmark_policy('hybrid').digest)]
    return inputs,refs,manifest,rows,criterion,spans

def test_null_conflicts_and_failures_do_not_inflate_agreement():
    inputs,refs,manifest,rows,*_=fixture_report()
    report=evaluate_records(inputs,refs,manifest,rows)
    dense=report.profiles['dense']
    assert dense['quality']['numeric_pairs']==1
    assert dense['quality']['mae']==0 and dense['quality']['quadratic_kappa'] is None
    assert dense['quality']['status_agreement_accepted']==.2
    assert dense['quality']['status_agreement_all_planned']==.2
    assert report.profiles['hybrid']['counts']['failed']==1
    assert report.profiles['hybrid']['quality']['status_agreement_all_planned']==0
    assert report.profiles['hybrid']['quality']['mae'] is None
    mock=evaluate_records(inputs,refs,manifest.model_copy(update={'mode':'contract_only','model_quality':'unmeasured','provider':'mock'}),rows)
    assert mock.profiles['dense']['quality']['mae'] is None
    assert mock.profiles['dense']['quality']['measurement']=='unmeasured_mock'

def test_recall_uses_ranked_pool_not_top_four_pack():
    inputs,refs,manifest,rows,criterion,spans=fixture_report()
    distractors=['spn_'+f'{i:024x}' for i in range(5)]
    diag={'ranked_evidence':{criterion:[[s] for s in distractors+spans]},
          'initial_evidence':{criterion:distractors[:4]},'final_evidence':{criterion:spans},'counters':{}}
    rows[0]=rows[0].model_copy(update={'diagnostics':diag})
    report=evaluate_records(inputs,refs,manifest,rows)
    retrieval=report.profiles['dense']['retrieval']
    assert retrieval['span_recall_at_5']==0 and retrieval['span_recall_at_10']==1
    assert retrieval['initial_group_coverage']==0 and retrieval['final_group_coverage']==1
    assert retrieval['recovered_criteria']==1
    assert retrieval['ranked_criteria']==1

def test_sufficient_group_requires_every_span():
    inputs,refs,manifest,rows,c,spans=fixture_report()
    ref=refs['node-01'].criteria[c]
    from app.services.evaluation.benchmark.contracts import EvidenceReference
    second=EvidenceReference(span_id='spn_'+'f'*24,quote='reference-only')
    refs['node-01']=refs['node-01'].model_copy(update={'criteria':{**refs['node-01'].criteria,c:ref.model_copy(update={
        'sufficient_evidence_groups':((ref.sufficient_evidence_groups[0][0],second),)})}})
    rows[0]=rows[0].model_copy(update={'diagnostics':{'initial_evidence':{c:spans},'final_evidence':{c:spans}}})
    assert evaluate_records(inputs,refs,manifest,rows).profiles['dense']['retrieval']['initial_group_coverage']==0

def test_pairing_requires_same_case_and_cluster_bootstrap():
    pairs=[('a',0,1),('a',0,1),('b',1,0),('c',1,.5)]
    assert paired_cluster_interval(pairs,seed=7)==paired_cluster_interval(pairs,seed=7)
    assert paired_cluster_interval([('a',0,1)],seed=7) is None
    assert paired_cluster_interval([('a',0,0),('b',0,0)],seed=7) is None
    inputs,refs,manifest,rows,*_=fixture_report()
    report=evaluate_records(inputs,refs,manifest,rows)
    assert report.paired[0]['overlap_cases']==0 and report.paired[0]['ci95'] is None

@pytest.mark.parametrize('value',[True,'3',3.5])
def test_observations_reject_coerced_numeric_scores(value):
    with pytest.raises(ValueError):CriterionObservation(status='assessed',score=value)

def test_conflict_and_null_score_denominators_are_separate():
    inputs,refs,manifest,rows,*_=fixture_report()
    ids=list(refs['node-01'].criteria)
    a,b=ids[:2]
    from app.services.evaluation.benchmark.contracts import CriterionReference
    group=(refs['node-01'].criteria[a].sufficient_evidence_groups[0][0],refs['node-01'].criteria[b].sufficient_evidence_groups[0][0])
    refs['node-01']=refs['node-01'].model_copy(update={'criteria':{**refs['node-01'].criteria,
        a:CriterionReference(status='conflicting_evidence',score=None,sufficient_evidence_groups=(group,),clarification_expectation='clarify',explanation='design expected'),
        b:CriterionReference(status='insufficient_evidence',score=None,clarification_expectation='clarify',explanation='design expected')}})
    rows[0]=rows[0].model_copy(update={'criteria':{**rows[0].criteria,
        a:CriterionObservation(status='conflicting_evidence',score=None,evidence_ids=tuple(e.span_id for e in group),clarification_count=1),
        b:CriterionObservation(status='assessed',score=0,evidence_ids=(group[0].span_id,))}})
    q=evaluate_records(inputs,refs,manifest,rows).profiles['dense']['quality']
    assert q['numeric_pairs']==0 and q['mae'] is None
    assert q['null_reference_denominator']==2 and q['correct_abstention_rate']==.5
    assert q['false_zero_rate']==.5 and q['unsupported_score_rate']==.5
    assert q['conflict_denominator']==1 and q['conflict_agreement']==1



def test_valid_but_irrelevant_citations_fail_annotated_support():
    inputs,refs,manifest,rows,c,spans=fixture_report()
    irrelevant='spn_'+'e'*24
    rows[0]=rows[0].model_copy(update={'criteria':{**rows[0].criteria,c:CriterionObservation(status='assessed',score=0,evidence_ids=(irrelevant,))},
        'diagnostics':{'initial_evidence':{c:spans+[irrelevant]},'final_evidence':{c:spans+[irrelevant]}}})
    r=evaluate_records(inputs,refs,manifest,rows).profiles['dense']['retrieval']
    assert r['scope_violations']==0 and r['final_group_coverage']==1
    assert r['annotated_citation_denominator']==1 and r['annotated_citation_precision']==0
    assert r['cited_group_denominator']==1 and r['cited_group_coverage']==0
    refs['node-01']=refs['node-01'].model_copy(update={'criteria':{**refs['node-01'].criteria,
        c:refs['node-01'].criteria[c].model_copy(update={'annotation_complete':False})}})
    r=evaluate_records(inputs,refs,manifest,rows).profiles['dense']['retrieval']
    assert r['annotated_citation_precision'] is None and r['cited_group_coverage'] is None
    assert r['annotated_citation_denominator']==0 and r['cited_group_denominator']==0


def test_mock_semantic_citation_quality_remains_unmeasured():
    inputs,refs,manifest,rows,*_=fixture_report(provider='mock')
    r=evaluate_records(inputs,refs,manifest,rows).profiles['dense']['retrieval']
    assert r['annotated_citation_precision'] is None and r['cited_group_coverage'] is None


def test_unexecuted_retrieval_excluded_from_quality_denominators():
    from app.services.assessment.diagnostics import AssessmentDiagnostics
    inputs,refs,manifest,rows,*_=fixture_report()
    recorder=AssessmentDiagnostics(set(refs['node-01'].criteria))
    rows[1]=rows[1].model_copy(update={'diagnostics':recorder.snapshot()})
    r=evaluate_records(inputs,refs,manifest,rows).profiles['hybrid']['retrieval']
    assert r['group_denominator']==0 and r['initial_group_coverage'] is None and r['final_group_coverage'] is None
    assert r['ranked_criteria']==0
    assert evaluate_records(inputs,refs,manifest,rows).profiles['hybrid']['counts']['failed']==1
    # A real executed empty pack is measured zero, not unmeasured.
    recorder.record_initial_evidence({c:[] for c in refs['node-01'].criteria})
    recorder.record_final_evidence({c:[] for c in refs['node-01'].criteria})
    rows[1]=rows[1].model_copy(update={'diagnostics':recorder.snapshot()})
    r=evaluate_records(inputs,refs,manifest,rows).profiles['hybrid']['retrieval']
    assert r['group_denominator']==5 and r['initial_group_coverage']==0 and r['final_group_coverage']==0
