from collections import Counter
from pathlib import Path
import hashlib
import json
import shutil
import unicodedata

import pytest
from pydantic import ValidationError

from app.services.evaluation.benchmark.contracts import CaseReference, CriterionReference
from app.services.evaluation.benchmark.dataset import canonical_case, load_inputs, load_references, select_runs

ROOT = Path(__file__).resolve().parents[3] / 'fixtures/ai_benchmark/v1'


def test_dataset_shape_and_cluster_split():
    inputs = load_inputs(ROOT)
    assert len(inputs.cases) == 60
    assert Counter(c.role_family for c in inputs.cases) == {'backend_node': 20, 'ai_ml': 20, 'android': 20}
    assert Counter(c.split for c in inputs.cases) == {'development': 36, 'public_test': 24}
    for role in inputs.roles:
        cases = [c for c in inputs.cases if c.role_family == role]
        assert Counter(c.language for c in cases) == {'vi': 7, 'en': 7, 'mixed': 6}
        assert Counter(c.split for c in cases) == {'development': 12, 'public_test': 8}
        for split in ('development', 'public_test'):
            assert {c.language for c in cases if c.split == split} == {'vi', 'en', 'mixed'}
    clusters = {}
    for case in inputs.cases:
        clusters.setdefault(case.cluster_id, set()).add(case.split)
    assert all(len(splits) == 1 for splits in clusters.values())
    assert 'references' not in type(inputs).model_fields


def test_gold_references_are_exact_and_dynamic():
    inputs = load_inputs(ROOT)
    refs = load_references(ROOT, inputs)
    assert set(refs) == {c.case_id for c in inputs.cases}
    for case in inputs.cases:
        _, canonical, spans = canonical_case(case)
        registry = {s.span_id: s for s in spans}
        gold = refs[case.case_id]
        assert gold.origin == 'design_expected'
        assert set(gold.criteria) == {c.id for c in inputs.roles[case.role_family].criteria}
        for expected in gold.criteria.values():
            for group in expected.sufficient_evidence_groups:
                for evidence in group:
                    assert registry[evidence.span_id].text == evidence.quote
                    span = registry[evidence.span_id]
                    assert canonical[span.start_cp:span.end_cp] == evidence.quote
            if expected.status == 'assessed':
                assert type(expected.score) is int and 0 <= expected.score <= 4
            else:
                assert expected.score is None
            if expected.status == 'conflicting_evidence':
                assert len(expected.sufficient_evidence_groups[0]) >= 2
    assert refs['node-01'].criteria['backend_implementation'].score == 0
    assert refs['node-06'].criteria['backend_implementation'].score is None
    assert refs['node-10'].criteria['backend_implementation'].status == 'conflicting_evidence'


def test_unicode_canonicalization_and_duplicate_bilingual_claim():
    inputs = load_inputs(ROOT)
    case = next(c for c in inputs.cases if c.case_id == 'node-09')
    version, canonical, spans = canonical_case(case)
    changed = case.model_copy(update={'cv_text': unicodedata.normalize('NFD', case.cv_text).replace('\n', '\r\n')})
    version2, canonical2, spans2 = canonical_case(changed)
    assert version2 == version
    assert canonical2 == canonical
    assert [s.span_id for s in spans2] == [s.span_id for s in spans]
    refs = load_references(ROOT, inputs)
    pair = [next(c for c in inputs.cases if c.case_id == f'node-{i}') for i in ('11', '12')]
    assert pair[0].cluster_id == pair[1].cluster_id
    assert canonical_case(pair[0])[1] == canonical_case(pair[1])[1]
    # Repeated bilingual wording is annotated as alternative evidence, not additive achievement.
    assert refs['node-09'].criteria['backend_implementation'].score == 2


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
        rows[0]['criteria']['backend_implementation']['sufficient_evidence_groups'][0][0]['span_id'] = 'spn_' + '0' * 24
        path.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n')
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
    args = dict(split=None, case_ids=('node-01', 'ai-01', 'android-01'), profiles=('full_text', 'dense', 'hybrid', 'hybrid_agent'), seed=20261008)
    a, b = select_runs(inputs, **args), select_runs(inputs, **args)
    assert a == b
    assert len(a.combinations) == 12
    assert len(set(a.combinations)) == 12
    with pytest.raises(ValueError, match='UNKNOWN_CASE'):
        select_runs(inputs, **{**args, 'case_ids': ('does-not-exist',)})
