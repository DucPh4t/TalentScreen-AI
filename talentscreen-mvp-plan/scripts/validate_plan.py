#!/usr/bin/env python3
"""Validate planning artifacts only; this is not a TalentScreen application test suite.
Run: python -m pip install -r scripts/requirements-validation.txt
     python scripts/validate_plan.py
"""
from __future__ import annotations
import copy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

try:
    from jsonschema import Draft202012Validator
except ImportError:
    raise SystemExit('Install scripts/requirements-validation.txt in an isolated Python environment first.')

ROOT = Path(__file__).resolve().parents[1]
CHECKS = []
IDS = ['python_backend', 'api_design', 'sql_data', 'testing_debugging', 'security_privacy', 'delivery_ops']

def check(name, test):
    try:
        result = test()
        assert result is not False, 'Assertion returned false'
        CHECKS.append({'name': name, 'status': 'pass'})
    except Exception as exc:
        CHECKS.append({'name': name, 'status': 'fail', 'detail': str(exc)})

def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))

def expect(condition, detail='Assertion failed'):
    if not condition:
        raise AssertionError(detail)


def check_json_files():
    files = sorted(ROOT.rglob('*.json'))
    expect(len([p for p in files if p.name != 'artifact-validation.json']) >= 9, 'Missing JSON artifacts')
    for path in files:
        if path.name != 'artifact-validation.json':
            json.loads(path.read_text(encoding='utf-8'))

check('all_json_artifacts_parse', check_json_files)
assessment_schema = read('contracts/assessment-output.schema.json')
assessment = read('contracts/assessment-output.valid-example.json')
interview_schema = read('contracts/interview-output.schema.json')
interview = read('contracts/interview-output.valid-example.json')
source = read('contracts/assessment-input.example.json')
rubric = read('examples/rubric-backend-python.v1.json')
expected = read('contracts/assessment-derived.expected.json')
bank = read('examples/interview-question-bank.v1.json')

for name, schema, example in [('assessment', assessment_schema, assessment), ('interview', interview_schema, interview)]:
    check(f'{name}_schema_draft202012_valid', lambda s=schema: Draft202012Validator.check_schema(s))
    check(f'{name}_example_matches_schema', lambda s=schema, x=example: Draft202012Validator(s).validate(x))

av = Draft202012Validator(assessment_schema)
iv = Draft202012Validator(interview_schema)

# Mutations exercise structural contracts, not semantic competence of a model.
def negative(name, mutate, example=assessment, validator=av):
    item = copy.deepcopy(example)
    mutate(item)
    check(name, lambda: expect(not validator.is_valid(item), 'Invalid mutation unexpectedly passed'))

negative('assessment_rejects_model_hiring_decision', lambda x: x.update(hiring_decision='advance'))
negative('assessment_rejects_unknown_criterion_field', lambda x: x['criteria'][0].update(confidence=0.99))
negative('assessment_rejects_missing_criterion', lambda x: x['criteria'].pop())
negative('assessment_rejects_duplicate_criterion_id', lambda x: x['criteria'][1].update(criterion_id='python_backend'))
negative('assessment_rejects_score_five', lambda x: x['criteria'][0].update(score=5))
negative('assessment_rejects_negative_score', lambda x: x['criteria'][0].update(score=-1))
negative('assessment_rejects_string_score', lambda x: x['criteria'][0].update(score='2'))
negative('assessment_rejects_boolean_score', lambda x: x['criteria'][0].update(score=True))
negative('assessment_rejects_fractional_score', lambda x: x['criteria'][0].update(score=2.5))
negative('assessment_rejects_assessed_without_evidence', lambda x: x['criteria'][0].update(evidence=[]))
negative('assessment_rejects_assessed_with_null', lambda x: x['criteria'][0].update(score=None))
negative('assessment_rejects_unknown_with_zero', lambda x: x['criteria'][3].update(score=0))
negative('assessment_rejects_unknown_without_question', lambda x: x['criteria'][3].update(missing_information=[]))
negative('assessment_rejects_conflict_with_one_evidence', lambda x: x['criteria'][5]['evidence'].pop())
negative('assessment_rejects_duplicate_evidence_object', lambda x: x['criteria'][0]['evidence'].append(copy.deepcopy(x['criteria'][0]['evidence'][0])))
negative('assessment_rejects_unknown_status', lambda x: x['criteria'][0].update(status='not_applicable'))
negative('assessment_rejects_malformed_span_id', lambda x: x['criteria'][0]['evidence'][0].update(span_id='wrong'))
negative('assessment_rejects_quote_over_limit', lambda x: x['criteria'][0]['evidence'][0].update(quote='x'*1201))
negative('interview_rejects_more_than_three_followups', lambda x: x.update(followups=x['followups']*4), interview, iv)
negative('interview_rejects_core_question_replacement', lambda x: x.update(core_questions=[]), interview, iv)
negative('interview_rejects_unknown_criterion', lambda x: x['followups'][0].update(criterion_id='school_prestige'), interview, iv)
negative('interview_rejects_duplicate_source_ids', lambda x: x['followups'][0].update(source_span_ids=['spn_'+'a'*24]*2), interview, iv)
check('interview_allows_no_followups', lambda: iv.validate({'followups': []}))


def validate_sources(payload):
    registry = {s['span_id']: s for s in source['source_spans']}
    for item in payload['criteria']:
        seen = set()
        for e in item['evidence']:
            expect(e['span_id'] in registry, 'Unknown span')
            expect(e['span_id'] not in seen, 'Duplicate span ID')
            expect(e['quote'] == registry[e['span_id']]['text'], 'Quote must equal full span')
            seen.add(e['span_id'])
    return True


def validate_registry():
    text = source['canonical_text']
    expect(hashlib.sha256(text.encode()).hexdigest() == source['sha256'], 'Document hash mismatch')
    expect(source['fixture_only'] is True)
    for span in source['source_spans']:
        start, end = span['start_cp'], span['end_cp']
        expect(text[start:end] == span['text'], 'Offset mismatch')
        expect(len(span['text']) <= 1200)
        seed = f"{source['sanitized_version_id']}:{start}:{end}"
        expect(span['span_id'] == 'spn_' + hashlib.sha256(seed.encode()).hexdigest()[:24], 'ID hash mismatch')
    return validate_sources(assessment)

check('synthetic_registry_hash_offsets_and_exact_quotes', validate_registry)

def semantic_boundary():
    bad = copy.deepcopy(assessment)
    bad['criteria'][0]['evidence'][0]['quote'] += ' Nội dung không nằm trong nguồn.'
    expect(av.is_valid(bad), 'Schema alone should not claim source fidelity')
    try:
        validate_sources(bad)
    except AssertionError:
        return True
    raise AssertionError('Source mismatch should fail the fixture-level source check')
check('schema_alone_does_not_validate_source_fidelity', semantic_boundary)


def strict_type_boundary():
    value = copy.deepcopy(assessment)
    value['criteria'][0]['score'] = 2.0
    # JSON Schema treats a mathematical integer as integer; runtime strict typing is separate.
    expect(av.is_valid(value))
    expect(type(value['criteria'][0]['score']) is not int)
check('jsonschema_integer_vs_runtime_strict_type_boundary_documented', strict_type_boundary)


def validate_rubric():
    expect(rubric['status'] == 'draft')
    expect(rubric['approval']['approved_by'] is None)
    expect([c['id'] for c in rubric['criteria']] == IDS)
    expect([c['weight'] for c in rubric['criteria']] == [20,25,20,15,10,10])
    expect(sum(c['weight'] for c in rubric['criteria']) == 100)
    jd = (ROOT / 'examples/jd-backend-python.vi.md').read_text()
    for item in rubric['criteria']:
        expect([a['score'] for a in item['scoring_anchors']] == list(range(5)))
        for ref in item['source_requirements']:
            expect(ref['quote'] in jd, f"JD quote missing: {item['id']}")
            expect(ref['requirement_id'] in jd)
    expect(rubric['recommendation_policy']['validation_status'] == 'unvalidated')
    expect(rubric['recommendation_policy']['automatic_hiring_decisions_allowed'] is False)
check('rubric_ids_weights_anchors_jd_quotes_and_draft_state', validate_rubric)


def score_fixture():
    weights = {c['id']: c['weight'] for c in rubric['criteria']}
    known = [c for c in assessment['criteria'] if c['status'] == 'assessed']
    w = sum(weights[c['criterion_id']] for c in known)
    total = sum(Fraction(weights[c['criterion_id']] * c['score'], 4) for c in known)
    observed = 100 * total / w
    expect(w == expected['assessed_weight'])
    expect(Fraction(w,100) == Fraction(expected['coverage']))
    expect(observed == Fraction(expected['observed_score_exact_fraction']))
    d = Decimal(observed.numerator) / Decimal(observed.denominator)
    expect(str(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) == expected['observed_score_api'])
    expect(str(d.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)) == expected['observed_score_ui'])
    expect(expected['comparable_score'] is None and expected['hiring_decision'] is None)
    expect(expected['recommendation'] == 'needs_clarification')
check('assessment_fixture_score_coverage_and_rounding', score_fixture)


def bank_check():
    expect(bank['status'] == 'draft_seed' and bank['approval']['approved_by'] is None)
    expect([q['criterion_id'] for q in bank['questions']] == IDS)
    expect(len({q['question_id'] for q in bank['questions']}) == 6)
    expect(all(q['question_vi'].strip() and q['purpose_vi'].strip() and q['answer_indicators'] for q in bank['questions']))
check('interview_bank_six_criteria_unapproved_seed', bank_check)


def source_registry_state():
    registry = read('examples/dataset-source-registry.json')
    expect(registry['status'] == 'planning_only_not_imported')
    for item in registry['sources']:
        expect(item['import_enabled'] is False)
        expect(item['external_processing_allowed'] is False)
        expect(item['revision'] is None, 'This plan did not download/pin a dataset; do not invent a revision')
check('external_datasets_not_imported_or_enabled', source_registry_state)


def check_links_and_fences():
    errors = []
    for path in sorted(ROOT.rglob('*.md')):
        content = path.read_text(encoding='utf-8')
        expect(sum(1 for line in content.splitlines() if line.startswith('```')) % 2 == 0, f'Unbalanced fence in {path.name}')
        # All local Markdown links in this bundle use simple targets, not title strings.
        for target in re.findall(r'\]\(([^\n)]+)\)', content):
            target = target.strip('<>')
            if urlsplit(target).scheme or target.startswith('#'):
                continue
            local = unquote(target.split('#')[0])
            if local and not (path.parent / local).exists():
                errors.append(f'{path.relative_to(ROOT)} -> {target}')
    expect(not errors, '; '.join(errors))
check('local_markdown_links_and_fence_balance', check_links_and_fences)


def check_table_columns():
    for path in ROOT.rglob('*.md'):
        expected_columns, fenced = None, False
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.startswith('```'): fenced = not fenced
            if not fenced and line.startswith('|'):
                columns = len(re.findall(r'(?<!\\)\|', line))
                if expected_columns is None: expected_columns = columns
                expect(columns == expected_columns, f'{path.name}:{number} has inconsistent table delimiters')
            else:
                expected_columns = None
check('markdown_tables_have_consistent_column_counts', check_table_columns)


def check_backlog():
    text = (ROOT/'09-implementation-backlog.md').read_text()
    blocks = re.split(r'^### (B\d\d) — ', text, flags=re.M)
    found = blocks[1::2]
    expect(found == [f'B{i:02}' for i in range(27)], 'Task list must contain B00..B26 once in order')
    graph = {}
    for task, body in zip(blocks[1::2], blocks[2::2]):
        dep_line = re.search(r'^- \*\*Depends:\*\* (.+)$', body, flags=re.M)
        expect(dep_line is not None, f'{task} needs dependencies')
        line = dep_line.group(1).split('**Spec:**')[0]
        for lo, hi in re.findall(r'B(\d\d)[–-]B(\d\d)', line):
            line += ' ' + ' '.join(f'B{i:02}' for i in range(int(lo),int(hi)+1))
        deps = set(re.findall(r'B\d\d', line))
        expect(deps <= set(found), f'{task} unknown dependency')
        expect(task not in deps, f'{task} depends on itself')
        graph[task] = deps
        expect('**AC:**' in body and '**Test:**' in body, f'{task} needs acceptance and tests')
    visiting, visited = set(), set()
    def visit(task):
        expect(task not in visiting, f'Dependency cycle at {task}')
        if task in visited: return
        visiting.add(task)
        for dep in graph[task]: visit(dep)
        visiting.remove(task); visited.add(task)
    for task in graph: visit(task)
check('backlog_27_tasks_acceptance_tests_and_acyclic_dependencies', check_backlog)


def check_canonical_tokens():
    docs = '\n'.join(p.read_text() for p in ROOT.glob('*.md'))
    expect('ASSESSMENT_MODE=' not in docs, 'Use canonical RAG_MODE instead')
    for name in ['00-scope-decisions.md','01-product-and-ux.md','03-data-api-state-machines.md']:
        text = (ROOT/name).read_text()
        for basis in ['assessment_review','manual_document_review','technical_information_request']:
            expect(basis in text, f'{name} missing decision basis {basis}')
    expect('embed_sanitized' in (ROOT/'03-data-api-state-machines.md').read_text())
check('canonical_rag_job_and_manual_decision_tokens_present', check_canonical_tokens)

files = [p for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name not in {'artifact-validation.json', '.DS_Store'} and '__pycache__' not in p.parts]
report = {
    'scope': 'planning_artifacts_only',
    'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'status': 'pass' if all(c['status']=='pass' for c in CHECKS) else 'fail',
    'summary': {'passed': sum(c['status']=='pass' for c in CHECKS), 'failed': sum(c['status']=='fail' for c in CHECKS)},
    'validator': {'python': sys.version.split()[0], 'jsonschema': importlib.metadata.version('jsonschema'), 'schema_dialect':'Draft 2020-12'},
    'checks': CHECKS,
    'not_validated': ['application code or runtime security', 'provider availability/model alias/pricing', 'AI output semantic accuracy', 'real HR labels or AI-HR agreement', 'fairness on actual applicants', 'operational SLA/latency/cost', 'dataset contents/license provenance beyond reviewed source cards', 'remote source availability after research date'],
    'app_implementation_status': 'not_implemented_in_this_task',
    'external_api_calls_made_for_cv_evaluation': 0,
    'dataset_imports_performed': 0,
    'files_sha256': {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
}
(ROOT/'artifact-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'scope':report['scope'],'status':report['status'],**report['summary'],'files_hashed':len(files)},ensure_ascii=False))
for item in CHECKS:
    if item['status']=='fail': print(json.dumps(item,ensure_ascii=False))
raise SystemExit(0 if report['status']=='pass' else 1)
