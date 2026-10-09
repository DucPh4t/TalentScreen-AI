"""Runtime seed imports must not depend on the retired planning bundle."""
import json

import pytest

from app.services import interview, rubric


@pytest.mark.parametrize(
    'service,filename,loader,payload',
    [
        (rubric, 'rubric-backend-python.v1.json', rubric.load_seed_rubric_dict,
         {'status': 'draft', 'criteria': [{'id': 'api_design', 'weight': 100}]}),
        (interview, 'interview-question-bank.v1.json', interview.load_seed_question_bank_dict,
         {'status': 'draft_seed', 'questions': [{'question_id': 'q1', 'question_vi': 'Thiết kế API như thế nào?'}]}),
    ],
    ids=['rubric', 'interview-question-bank'],
)
def test_seed_import_from_runtime_layout_without_planning_bundle(
    service, filename, loader, payload, monkeypatch, tmp_path,
):
    # Model a clean Docker checkout: only source + seeds, no handoff documents.
    runtime = tmp_path / 'runtime'
    seed_dir = runtime / 'fixtures' / 'seeds'
    seed_dir.mkdir(parents=True)
    (seed_dir / filename).write_text(json.dumps(payload), encoding='utf-8')
    module_file = runtime / 'services' / 'backend' / 'app' / 'services' / 'service.py'
    module_file.parent.mkdir(parents=True)
    monkeypatch.setattr(service, '__file__', str(module_file))
    # Workers may start outside the checkout; source-relative resolution must work.
    elsewhere = tmp_path / 'worker-cwd'
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert loader() == payload
