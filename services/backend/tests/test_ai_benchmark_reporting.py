import json
from pathlib import Path
import pytest
from app.services.evaluation.benchmark.artifacts import atomic_json,append_record
from app.services.evaluation.benchmark.reporting import generate_reports,write_reports
from app.services.evaluation.benchmark.metrics import evaluate_records
from tests.test_ai_benchmark_metrics import fixture_report,DATA

def test_report_rejects_duplicate_or_torn_records(tmp_path):
    inputs,refs,manifest,rows,*_=fixture_report()
    source=tmp_path/'source';source.mkdir()
    atomic_json(source/'manifest.json',manifest)
    append_record(source/'runs.jsonl',rows[0])
    with (source/'runs.jsonl').open('a') as f:f.write(rows[0].model_dump_json()+'\n')
    with pytest.raises(ValueError,match='DUPLICATE'):generate_reports(source,tmp_path/'reports',DATA)
    (source/'runs.jsonl').write_text('{')
    with pytest.raises(ValueError,match='INCOMPLETE'):generate_reports(source,tmp_path/'reports',DATA)

def test_html_escapes_error_strings_and_report_regenerates(tmp_path,monkeypatch):
    inputs,refs,manifest,rows,*_=fixture_report()
    marker='<script>alert("CV")</script>'
    rows[1]=rows[1].model_copy(update={'error_code':marker})
    report=evaluate_records(inputs,refs,manifest,rows)
    write_reports(report,tmp_path)
    html=(tmp_path/'report.html').read_text()
    assert marker not in html and '&lt;script&gt;' in html
    assert '<script' not in html and 'https://' not in html
    assert 'GOLD_NOT_FOR_MODEL' not in html
    source=tmp_path/'source';source.mkdir()
    atomic_json(source/'manifest.json',manifest)
    for row in rows:append_record(source/'runs.jsonl',row)
    a=generate_reports(source,tmp_path/'a',DATA)
    b=generate_reports(source,tmp_path/'b',DATA)
    assert a==b
    from app.services.evaluation.benchmark.runner import main
    assert main(['report','--input',str(source),'--output',str(tmp_path/'cli'),'--dataset',str(DATA)])==0
    assert json.loads((tmp_path/'cli/metrics.json').read_text())['schema_version']=='ai-benchmark-metrics.v1'

def test_hard_kill_admission_is_uncertain_even_without_final_records(tmp_path):
    from app.services.evaluation.benchmark.artifacts import append_event
    inputs,refs,manifest,*_=fixture_report()
    atomic_json(tmp_path/'manifest.json',manifest.model_copy(update={'status':'running'}))
    append_event(tmp_path/'admissions.jsonl',{'event':'admitted','invocation_id':'opaque-synthetic-id'})
    report=generate_reports(tmp_path,tmp_path/'report',DATA)
    assert report.journal['missing_records']==2
    assert report.journal['unresolved_admissions']==1 and not report.journal['financial_reconciled']


@pytest.mark.parametrize('missing',['both','runs','admissions'])
def test_complete_manifest_requires_complete_journal_evidence(tmp_path,missing):
    from app.services.evaluation.benchmark.contracts import InvocationRecord
    import uuid
    inputs,refs,manifest,rows,*_=fixture_report()
    manifest=manifest.model_copy(update={'status':'complete','counts':{'planned':2,'accepted':2},
        'financial':{'spent_peak_estimate_usd':'0','held_usd':'0','unresolved_invocations':0}})
    rows[1]=rows[0].model_copy(update={'profile':'hybrid'})
    rows[0]=rows[0].model_copy(update={'invocations':(InvocationRecord(invocation_id=uuid.uuid4(),logical_step='test',attempt_no=1,status='succeeded',
        requested_model='mock',input_tokens=0,output_tokens=0,reserved_usd=0,estimated_peak_usd=0),)})
    atomic_json(tmp_path/'manifest.json',manifest)
    if missing=='admissions':
        for row in rows:append_record(tmp_path/'runs.jsonl',row)
    elif missing=='runs':
        from app.services.evaluation.benchmark.artifacts import append_event
        append_event(tmp_path/'admissions.jsonl',{'event':'admitted','invocation_id':str(rows[0].invocations[0].invocation_id)})
    report=generate_reports(tmp_path,tmp_path/'report',DATA)
    assert report.status=='partial'
    assert not report.journal['financial_reconciled']
    assert report.journal['manifest_status']=='complete'
    assert report.journal['integrity_errors']
