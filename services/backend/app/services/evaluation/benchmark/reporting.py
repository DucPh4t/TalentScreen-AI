"""Offline static reports. No CV, label explanations, network or scripts."""
import html
import json
from pathlib import Path
from .contracts import RunManifest
from .dataset import load_inputs,load_references
from .artifacts import read_records,read_events,atomic_json,atomic_text
from .metrics import evaluate_records

def write_reports(report,output):
    output=Path(output)
    if output.is_symlink() or any(p.is_symlink() for p in output.parents):raise ValueError('ARTIFACT_PATH_INVALID')
    output.mkdir(parents=True,exist_ok=True)
    atomic_json(output/'metrics.json',report)
    lines=['# TalentScreen AI — reproducible assessment benchmark','',f'Experiment: {report.experiment_id}',
        f'Status: {report.status}. Labels: synthetic design expectations. Model quality: {report.model_quality}.','',
        '| Profile | Planned | Accepted | Failed/skipped | Numeric n | MAE | Status agreement | Recall@10 | Calls |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    def cell(value):return 'unmeasured' if value is None else str(value).replace('|','\\|').replace('\n',' ')
    for name,data in report.profiles.items():
        c=data['counts'];q=data['quality'];r=data['retrieval']
        values=[name,c['planned'],c['accepted'],c['planned']-c['accepted'],q['numeric_pairs'],q['mae'],q['status_agreement_accepted'],r['span_recall_at_10'],data['model_calls']]
        lines.append('| '+' | '.join(cell(v) for v in values)+' |')
    lines+=['','## Limits','',*['- '+item for item in report.limitations],'','## Financial summary','',
        'Peak-rate usage estimates; invoice unavailable. Unresolved admissions remain uncertain.','',
        '```json',json.dumps(report.financial,indent=2),'```','','## Failures','']
    for row in report.failures:lines.append('- '+cell(row['case_id'])+' / '+cell(row['profile'])+': '+html.escape(cell(row['code'])))
    lines+=['','Full provenance, language/role slices, paired comparisons and timings are in metrics.json.','']
    atomic_text(output/'report.md','\n'.join(lines))
    # All source-derived strings are escaped, including JSON key/value content.
    payload=json.dumps(report.model_dump(mode='json'),ensure_ascii=False,indent=2)
    page='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    page+='<title>TalentScreen AI benchmark</title><style>body{font:15px system-ui;margin:24px auto;max-width:1000px;padding:0 16px;background:#fafaf8;color:#252620}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;border:1px solid #ddd;border-radius:8px}h1{font-size:24px}</style>'
    page+='<h1>TalentScreen AI benchmark</h1><p>Synthetic references. Exploratory comparisons. No autonomous hiring claim.</p><pre>'+html.escape(payload)+'</pre></html>'
    atomic_text(output/'report.html',page)

def generate_reports(source,output,dataset):
    source=Path(source)
    if source.is_symlink() or (source/'manifest.json').is_symlink():raise ValueError('ARTIFACT_PATH_INVALID')
    from .reranking import load_run_manifest
    manifest=load_run_manifest((source/'manifest.json').read_text())
    records=read_records(source/'runs.jsonl')
    events=read_events(source/'admissions.jsonl')
    inputs=load_inputs(Path(dataset));refs=load_references(inputs.root,inputs)
    report=evaluate_records(inputs,refs,manifest,records)
    all_ids=[str(i.invocation_id) for r in records for i in r.invocations]
    finalized={str(i.invocation_id) for r in records for i in r.invocations if i.status in {'succeeded','failed'}}
    admitted={e['invocation_id'] for e in events if e.get('event')=='admitted'}
    integrity=list(report.journal['integrity_errors'])
    if len(all_ids)!=len(set(all_ids)):integrity.append('DUPLICATE_INVOCATION_RECORD')
    if set(all_ids)-admitted:integrity.append('INVOCATION_ADMISSION_MISSING')
    if admitted-set(all_ids):integrity.append('ADMITTED_INVOCATION_NOT_FINALIZED')
    financial=manifest.financial
    from decimal import Decimal,InvalidOperation
    try:
        spent=Decimal(str(financial['spent_peak_estimate_usd']))
        held=Decimal(str(financial['held_usd']))
        unresolved=financial['unresolved_invocations']
        invocations=[i for r in records for i in r.invocations]
        recorded_spend=sum((i.estimated_peak_usd or Decimal(0) for i in invocations),Decimal(0))
        recorded_pending=sum(i.status in {'reserved','admitted','outcome_unknown'} for i in invocations)
        recorded_held=sum((i.reserved_usd for i in invocations if i.status in {'reserved','admitted','outcome_unknown'}),Decimal(0))
        # DB ledger amounts use eight decimals; compare at that precision.
        quantum=Decimal('0.00000001')
        if (not spent.is_finite() or not held.is_finite() or spent<0 or held<0 or type(unresolved) is not int
            or spent.quantize(quantum)!=recorded_spend.quantize(quantum)
            or held.quantize(quantum)!=recorded_held.quantize(quantum) or unresolved!=recorded_pending):
            integrity.append('FINANCIAL_RECORDS_MISMATCH')
    except (KeyError,ValueError,TypeError,InvalidOperation):
        integrity.append('FINANCIAL_EVIDENCE_MISSING')
    journal={**report.journal,'integrity_errors':integrity,'admitted_invocations':len(admitted),
        'unresolved_admissions':len(admitted-finalized),
        'financial_reconciled':manifest.status!='running' and report.journal['missing_records']==0 and not integrity
            and not (admitted-finalized) and not (set(all_ids)-admitted)}
    report=report.model_copy(update={'journal':journal,'status':'partial' if integrity and report.status=='complete' else report.status})
    write_reports(report,output)
    return report
