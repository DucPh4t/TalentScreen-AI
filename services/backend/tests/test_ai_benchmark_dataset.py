from collections import Counter
from pathlib import Path
import hashlib
import json
import shutil
import unicodedata

import pytest
from pydantic import ValidationError

from app.services.evaluation.benchmark.contracts import CriterionReference
from app.services.evaluation.benchmark.dataset import canonical_case, load_inputs, load_references, select_runs

ROOT = Path(__file__).resolve().parents[3] / 'fixtures/ai_benchmark/golden_100'
CRITERIA = {'python_backend', 'api_design', 'sql_data', 'testing_debugging', 'security_privacy', 'delivery_ops'}
MULTI_ROLE_ROOT = Path(__file__).resolve().parents[3] / 'fixtures/ai_benchmark/synthetic_100_multi_role_v2'
ROLE_FAMILIES = (
    'senior_ai_engineer',
    'software_development_manager',
    'java_backend_developer',
    'mobile_web_qa',
    'agentic_engineer',
)


def test_dataset_shape_and_cluster_split():
    inputs = load_inputs(ROOT)
    assert len(inputs.cases) == 100
    assert set(inputs.roles) == {'backend_python'}
    assert Counter(c.role_family for c in inputs.cases) == {'backend_python': 100}
    assert Counter(c.split for c in inputs.cases) == {'development': 80, 'public_test': 20}
    assert Counter(c.language for c in inputs.cases) == {'vi': 34, 'en': 33, 'mixed': 33}
    assert all({c.language for c in inputs.cases if c.split == split} == {'vi', 'en', 'mixed'}
               for split in ('development', 'public_test'))
    assert len({c.cluster_id for c in inputs.cases}) == 100
    assert 'references' not in type(inputs).model_fields
    assert inputs.roles['backend_python'].policy['draft_status'] == 'draft_unapproved'


def test_all_600_expected_outputs_cover_every_anchor_and_nullable_state():
    inputs = load_inputs(ROOT)
    refs = load_references(ROOT, inputs)
    assert set(refs) == {c.case_id for c in inputs.cases}
    assert len(refs) == 100
    for case in inputs.cases:
        gold = refs[case.case_id]
        assert gold.origin == 'design_expected'
        assert set(gold.criteria) == CRITERIA
        _, canonical, spans = canonical_case(case)
        registry = {span.span_id: span for span in spans}
        for expected in gold.criteria.values():
            for group in expected.sufficient_evidence_groups:
                for evidence in group:
                    span = registry[evidence.span_id]
                    assert span.text == evidence.quote
                    assert canonical[span.start_cp:span.end_cp] == evidence.quote
            if expected.status == 'assessed':
                assert type(expected.score) is int and 0 <= expected.score <= 4
            else:
                assert expected.score is None
            if expected.status == 'conflicting_evidence':
                assert len(expected.sufficient_evidence_groups[0]) >= 2
    for criterion in CRITERIA:
        rows = [reference.criteria[criterion] for reference in refs.values()]
        assert {row.score for row in rows if row.status == 'assessed'} == {0, 1, 2, 3, 4}
        assert {row.status for row in rows} == {'assessed', 'insufficient_evidence', 'conflicting_evidence'}
    assert refs['backend-008'].criteria['python_backend'].score == 0
    assert refs['backend-006'].criteria['python_backend'].score is None
    assert refs['backend-007'].criteria['python_backend'].status == 'conflicting_evidence'
    assert refs['backend-001'].criteria['python_backend'].status == 'insufficient_evidence'


def test_unicode_canonicalization_and_skills_only_distractor_do_not_create_gold_evidence():
    inputs = load_inputs(ROOT)
    case = next(c for c in inputs.cases if c.case_id == 'backend-003')
    version, canonical, spans = canonical_case(case)
    changed = case.model_copy(update={'cv_text': unicodedata.normalize('NFD', case.cv_text).replace('\n', '\r\n')})
    version2, canonical2, spans2 = canonical_case(changed)
    assert version2 == version
    assert canonical2 == canonical
    assert [span.span_id for span in spans2] == [span.span_id for span in spans]
    skill_only_case = next(c for c in inputs.cases if c.case_id == 'backend-001')
    assert 'Skills: Python, FastAPI, HTTP API, PostgreSQL' in skill_only_case.cv_text
    refs = load_references(ROOT, inputs)
    assert refs['backend-001'].criteria['python_backend'].status == 'insufficient_evidence'
    assert refs['backend-001'].criteria['python_backend'].sufficient_evidence_groups == ()


def test_long_context_cases_preserve_exact_citations():
    inputs = load_inputs(ROOT)
    long_cases = [case for case in inputs.cases if 'long-context' in case.scenario_tags]
    assert len(long_cases) == 10
    for case in long_cases:
        _, canonical, spans = canonical_case(case)
        assert len(canonical) > 24000
        assert len(spans) > 10
        assert len({span.span_id for span in spans}) == len(spans)


@pytest.mark.parametrize('status,score', [('insufficient_evidence', 0), ('conflicting_evidence', 2), ('assessed', True), ('assessed', 5)])
def test_invalid_nullable_gold_scores_are_rejected(status, score):
    with pytest.raises(ValidationError):
        CriterionReference(status=status, score=score, sufficient_evidence_groups=[], explanation='Synthetic reference', clarification_expectation='Clarify contribution')


def _copy_and_rehash(tmp_path, filename, mutate):
    dest = tmp_path / 'dataset'
    shutil.copytree(ROOT, dest)
    path = dest / filename
    mutate(path)
    manifest = json.loads((dest / 'manifest.json').read_text())
    manifest['files'][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    (dest / 'manifest.json').write_text(json.dumps(manifest))
    return dest


def test_dangling_gold_reference_is_rejected(tmp_path):
    def mutate(path):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        span = next(
            span
            for row in rows
            for criterion in row['criteria'].values()
            for group in criterion['sufficient_evidence_groups']
            for span in group
        )
        span['span_id'] = 'spn_' + '0' * 24
        path.write_text('\n'.join(json.dumps(row, ensure_ascii=False) for row in rows) + '\n')
    dest = _copy_and_rehash(tmp_path, 'references.jsonl', mutate)
    with pytest.raises(ValueError, match='GOLD_SPAN_INVALID'):
        load_references(dest, load_inputs(dest))


def test_duplicate_cases_and_hash_changes_are_rejected(tmp_path):
    def mutate(path):
        lines = path.read_text().splitlines()
        lines[-1] = lines[0]
        path.write_text('\n'.join(lines) + '\n')
    dest = _copy_and_rehash(tmp_path, 'cases.jsonl', mutate)
    with pytest.raises(ValueError, match='DUPLICATE_CASE'):
        load_inputs(dest)
    (dest / 'roles.json').write_text('{}')
    with pytest.raises(ValueError, match='DATASET_HASH_MISMATCH'):
        load_inputs(dest)


def test_selection_is_reproducible_and_does_not_drop_profiles():
    inputs = load_inputs(ROOT)
    args = dict(split=None, case_ids=('backend-001', 'backend-002', 'backend-003'),
                profiles=('full_text', 'dense', 'hybrid', 'hybrid_agent'), seed=20261010)
    first, second = select_runs(inputs, **args), select_runs(inputs, **args)
    assert first == second
    assert len(first.combinations) == 12
    assert len(set(first.combinations)) == 12
    with pytest.raises(ValueError, match='UNKNOWN_CASE'):
        select_runs(inputs, **{**args, 'case_ids': ('does-not-exist',)})
def test_active_multirole_dataset_has_expected_roles_criteria_and_splits():
    inputs = load_inputs(MULTI_ROLE_ROOT)
    assert len(inputs.cases) == 100
    assert set(inputs.roles) == set(ROLE_FAMILIES)
    assert Counter(case.role_family for case in inputs.cases) == {role: 20 for role in ROLE_FAMILIES}
    assert Counter(case.language for case in inputs.cases) == {'vi': 35, 'en': 35, 'mixed': 30}
    assert Counter(case.split for case in inputs.cases) == {'development': 80, 'public_test': 20}
    assert len({case.cluster_id for case in inputs.cases}) == 95
    assert all(
        Counter(case.language for case in inputs.cases if case.role_family == role)
        == {'vi': 7, 'en': 7, 'mixed': 6}
        for role in ROLE_FAMILIES
    )
    for role in ROLE_FAMILIES:
        rubric = inputs.roles[role]
        assert len(rubric.criteria) == 6
        assert sum(criterion.weight for criterion in rubric.criteria) == 100
        assert rubric.policy['draft_status'] == 'draft_unapproved'
        assert {case.language for case in inputs.cases if case.role_family == role and case.split == 'public_test'} == {'vi', 'en', 'mixed'}


def test_active_multirole_references_pin_every_role_criterion_and_evidence_span():
    inputs = load_inputs(MULTI_ROLE_ROOT)
    refs = load_references(MULTI_ROLE_ROOT, inputs)
    assert len(refs) == 100
    assert sum(len(reference.criteria) for reference in refs.values()) == 600
    for role in ROLE_FAMILIES:
        criterion_ids = {criterion.id for criterion in inputs.roles[role].criteria}
        role_cases = [case for case in inputs.cases if case.role_family == role]
        for criterion_id in criterion_ids:
            labels = [refs[case.case_id].criteria[criterion_id] for case in role_cases]
            assert {label.status for label in labels} == {
                'assessed', 'insufficient_evidence', 'conflicting_evidence'
            }
            assert {label.score for label in labels if label.status == 'assessed'} == {0, 1, 2, 3, 4}
        for case in role_cases:
            _, canonical, spans = canonical_case(case)
            registry = {span.span_id: span for span in spans}
            assert set(refs[case.case_id].criteria) == criterion_ids
            for label in refs[case.case_id].criteria.values():
                if label.status == 'assessed':
                    assert label.score in {0, 1, 2, 3, 4}
                else:
                    assert label.score is None
                if label.status == 'conflicting_evidence':
                    assert len(label.sufficient_evidence_groups[0]) >= 2
                for group in label.sufficient_evidence_groups:
                    for evidence in group:
                        span = registry[evidence.span_id]
                        assert span.text == evidence.quote
                        assert canonical[span.start_cp:span.end_cp] == evidence.quote


def test_multirole_v2_distinguishes_nonpersonal_team_claims_from_direct_evidence():
    inputs = load_inputs(MULTI_ROLE_ROOT)
    references = load_references(MULTI_ROLE_ROOT, inputs)
    cases = {case.case_id: case for case in inputs.cases}

    for case_id, criterion_id in (
        ('software-development-manager-001', 'delivery_planning_risk'),
        ('java-backend-developer-001', 'relational_data'),
        ('mobile-web-qa-001', 'test_automation'),
        ('agentic-engineer-001', 'security_permissions'),
    ):
        reference = references[case_id].criteria[criterion_id]
        assert reference.status == 'insufficient_evidence'
        assert reference.score is None

    java_delivery = references['java-backend-developer-001'].criteria['delivery_reliability']
    assert java_delivery.status == 'assessed'
    assert java_delivery.score == 1
    evidence = java_delivery.sufficient_evidence_groups[0][0]
    assert evidence.quote == (
        'Dự án java-backend-developer-project-01: Tôi thiết lập quy tắc thay đổi contract giữa '
        'các dịch vụ và dẫn dắt rollout tương thích, theo dõi tỷ lệ lỗi client sau phát hành.'
    )
    assert evidence.quote in cases['java-backend-developer-001'].cv_text

def test_active_multirole_scenarios_include_counterfactuals_and_adversarial_text():
    inputs = load_inputs(MULTI_ROLE_ROOT)
    refs = load_references(MULTI_ROLE_ROOT, inputs)
    cases = {case.case_id: case for case in inputs.cases}
    assert len([case for case in cases.values() if 'long-context' in case.scenario_tags]) == 5
    assert len([case for case in cases.values() if 'prompt-injection' in case.scenario_tags]) == 5
    assert len([case for case in cases.values() if 'team-contribution-unclear' in case.scenario_tags]) == 10
    assert len([case for case in cases.values() if 'skills-only-distractor' in case.scenario_tags]) == 30
    for role in ROLE_FAMILIES:
        prefix = role.replace('_', '-')
        first, second = cases[f'{prefix}-017'], cases[f'{prefix}-018']
        assert first.split == second.split == 'public_test'
        assert first.cluster_id == second.cluster_id
        assert second.cv_text.replace('chị.', 'anh.') == first.cv_text
        for criterion_id in refs[first.case_id].criteria:
            left, right = refs[first.case_id].criteria[criterion_id], refs[second.case_id].criteria[criterion_id]
            assert (left.status, left.score) == (right.status, right.score)
            assert [[e.quote for e in group] for group in left.sufficient_evidence_groups] == [
                [e.quote for e in group] for group in right.sufficient_evidence_groups
            ]
        long_case = cases[f'{prefix}-015']
        assert len(canonical_case(long_case)[1]) > 24000
        injection_case = cases[f'{prefix}-010']
        assert any(text in injection_case.cv_text for text in ('Bỏ qua rubric', 'Ignore the rubric'))
        assert all(
            'Bỏ qua rubric' not in evidence.quote and 'Ignore the rubric' not in evidence.quote
            for label in refs[injection_case.case_id].criteria.values()
            for group in label.sufficient_evidence_groups for evidence in group
        )
