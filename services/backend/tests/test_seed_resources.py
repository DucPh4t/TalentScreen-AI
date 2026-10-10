"""Runtime seed imports must not depend on the retired planning bundle."""
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import interview, rubric
from app.services.assessment.service import create_assessment_run
from app.domain.enums import AccountRole, RequisitionStatus, RubricStatus, SanitizedVersionStatus
from app.domain.rubric_policy import validate_canonical_rubric
from app.schemas.assessment import AssessmentRunCreateRequest


@pytest.fixture(scope="session", autouse=True)
def test_engine():
    """Seed-resource and guard tests use filesystem/fake-DB behavior only."""
    return None


@pytest.mark.parametrize(
    'service,filename,loader,payload',
    [
        (rubric, 'rubric-backend-python.v3.json', rubric.load_seed_rubric_dict,
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


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeAssessmentDB:
    def __init__(self, results):
        self.results = iter(results)

    async def execute(self, _statement):
        return _FakeResult(next(self.results))


@pytest.mark.asyncio
async def test_draft_rubric_seed_cannot_enqueue_a_real_assessment():
    application_id = uuid.uuid4()
    requisition_id = uuid.uuid4()
    document_id = uuid.uuid4()
    sanitized_id = uuid.uuid4()
    rubric_id = uuid.uuid4()
    user_id = uuid.uuid4()
    app_row = SimpleNamespace(
        id=application_id,
        status="active",
        requisition_id=requisition_id,
        requisition=SimpleNamespace(
            status=RequisitionStatus.OPEN,
            current_rubric_version_id=rubric_id,
        ),
        current_document_id=document_id,
        current_sanitized_version_id=sanitized_id,
    )
    sanitized_row = SimpleNamespace(
        id=sanitized_id,
        application_id=application_id,
        status=SanitizedVersionStatus.APPROVED,
        document_id=document_id,
    )
    draft_rubric = SimpleNamespace(id=rubric_id, status=RubricStatus.DRAFT)
    ctx = SimpleNamespace(roles={AccountRole.ADMIN}, user=SimpleNamespace(id=user_id))
    db = _FakeAssessmentDB([app_row, None, sanitized_row, draft_rubric])

    with pytest.raises(HTTPException) as exc:
        await create_assessment_run(
            db,
            application_id,
            AssessmentRunCreateRequest(
                sanitized_version_id=sanitized_id,
                rubric_version_id=rubric_id,
            ),
            ctx,
        )

    assert exc.value.status_code == 422
    assert exc.value.detail == "Rubric phải ở trạng thái APPROVED."


def test_v3_rubric_seed_keeps_provisional_policy_and_stays_unapproved():
    seed = rubric.load_seed_rubric_dict()
    validate_canonical_rubric({
        "criteria": seed["criteria"],
        "recommendation_policy": seed["recommendation_policy"],
    })
    seed_dir = rubric.get_seed_rubric_path().parent
    v1 = json.loads((seed_dir / "rubric-backend-python.v1.json").read_text(encoding="utf-8"))
    v2 = json.loads((seed_dir / "rubric-backend-python.v2.json").read_text(encoding="utf-8"))
    assert seed["version"] == 3
    assert seed["status"] == "draft"
    assert seed["approval"]["approved_by"] is None
    assert seed["approval"]["approved_at"] is None
    assert seed["approval"]["approved_content_hash"] is None
    assert seed["recommendation_policy"]["validation_status"] == "unvalidated"
    policy = seed["recommendation_policy"]
    assert policy["threshold"] == 50
    assert policy["required_criterion_ids"] == ["python_backend", "api_design", "sql_data"]
    assert policy["core_minimum_scores"] == {cid: 2 for cid in policy["required_criterion_ids"]}
    assert policy["optional_criterion_ids"] == ["testing_debugging", "security_privacy", "delivery_ops"]
    assert sum(c["weight"] for c in seed["criteria"]) == 100
    assert [(c["id"], c["weight"], c["classification"]) for c in seed["criteria"]] == [
        ("python_backend", 25, "must_have"),
        ("api_design", 25, "must_have"),
        ("sql_data", 20, "must_have"),
        ("testing_debugging", 15, "nice_to_have"),
        ("security_privacy", 10, "nice_to_have"),
        ("delivery_ops", 5, "nice_to_have"),
    ]
    assert policy["require_full_coverage"] is False
    assert "Không tìm thấy biên bản quyết định chung HR–IT" in policy["decision_source"]
    assert "đề xuất AI chưa xác nhận" in policy["note"]
    assert "Biên bản họp HR–IT" not in seed["purpose"]
    assert seed["publication_gate"]["can_publish_or_assess_real_applicants"] is False
    assert seed["status"] == "draft" and v1["version"] == 1 and v2["version"] == 2
    jd_text = (seed_dir / "jd-backend-python.v3.vi.md").read_text(encoding="utf-8")
    from app.services.requisition import extract_jd_source_refs
    source_refs = extract_jd_source_refs(jd_text)["requirements"]
    for criterion in seed["criteria"]:
        assert len(criterion["source_requirements"]) == 1
        quote = criterion["source_requirements"][0]["quote"]
        assert quote in jd_text
        matches = [
            ref for ref in source_refs
            if ref["criterion_id"] == criterion["id"]
            and ref["weight"] == criterion["weight"]
            and ref["quote"] == quote
        ]
        assert len(matches) == 1
    assert all(
        anchor["qualifying_evidence"] and anchor["not_sufficient"]
        for criterion in seed["criteria"]
        for anchor in criterion["scoring_anchors"]
    )


def test_seed_rubric_loader_uses_v3_without_mutating_previous_versions():
    assert rubric.get_seed_rubric_path().name == "rubric-backend-python.v3.json"
    seed_dir = rubric.get_seed_rubric_path().parent
    assert (seed_dir / "rubric-backend-python.v1.json").is_file()
    assert (seed_dir / "rubric-backend-python.v2.json").is_file()
