from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.config import Settings


def test_evidence_only_contract_rejects_scores_and_foreign_spans():
    from app.services.assessment.validator import AssessmentValidationError, validate_evidence_only_output

    span_id = "spn_" + "a" * 24
    spans = {span_id: type("Span", (), {"text": "Built a Python API"})()}
    raw = {
        "criteria": [
            {"criterion_id": "python_skill", "status": "assessed", "evidence": [{"span_id": span_id, "quote": "Built a Python API"}], "rationale": "Có bằng chứng triển khai."},
            {"criterion_id": "sql_skill", "status": "insufficient_evidence", "evidence": [], "rationale": "Chưa thấy bằng chứng.", "missing_information": ["Hỏi mức độ sử dụng SQL."]},
        ]
    }
    output = validate_evidence_only_output(json.dumps(raw, ensure_ascii=False), spans, {"python_skill", "sql_skill"}, allowed_span_ids_by_criterion={"python_skill": {span_id}, "sql_skill": set()})
    assert output.criteria[0].status == "assessed"
    assert not hasattr(output.criteria[0], "score")
    with pytest.raises(AssessmentValidationError, match="SCHEMA_VIOLATION"):
        validate_evidence_only_output(json.dumps({**raw, "criteria": [{**raw["criteria"][0], "score": 4}, raw["criteria"][1]]}), spans, {"python_skill", "sql_skill"}, allowed_span_ids_by_criterion={"python_skill": {span_id}, "sql_skill": set()})
    with pytest.raises(AssessmentValidationError, match="PROVENANCE_VIOLATION"):
        invalid = {**raw, "criteria": [{**raw["criteria"][0], "evidence": [{"span_id": "spn_" + "b" * 24, "quote": "other"}]}, raw["criteria"][1]]}
        validate_evidence_only_output(json.dumps(invalid), spans, {"python_skill", "sql_skill"}, allowed_span_ids_by_criterion={"python_skill": {span_id}, "sql_skill": set()})


def test_evidence_only_contract_requires_complete_unique_criterion_set():
    from app.services.assessment.validator import AssessmentValidationError, validate_evidence_only_output

    spans = {}
    base = {"criteria": [
        {"criterion_id": "python_skill", "status": "insufficient_evidence", "evidence": [], "rationale": "Chưa thấy bằng chứng.", "missing_information": ["Hỏi thêm."]},
        {"criterion_id": "sql_skill", "status": "insufficient_evidence", "evidence": [], "rationale": "Chưa thấy bằng chứng.", "missing_information": ["Hỏi thêm."]},
    ]}
    with pytest.raises(AssessmentValidationError, match="CRITERION_SET_MISMATCH"):
        validate_evidence_only_output(json.dumps({"criteria": base["criteria"][:1]}), spans, {"python_skill", "sql_skill"})
    with pytest.raises(AssessmentValidationError, match="SCHEMA_VIOLATION"):
        validate_evidence_only_output(json.dumps({"criteria": [base["criteria"][0], base["criteria"][0]]}), spans, {"python_skill", "sql_skill"})


def test_jev_fractional_score_overrides_are_not_rounded_before_threshold():
    from decimal import Decimal
    from app.schemas.assessment import AssessmentOutputSchema
    from app.services.assessment.scoring import calculate_deterministic_scores

    evaluations = AssessmentOutputSchema.model_validate({"criteria": [
        {"criterion_id": cid, "status": "assessed", "score": 3,
         "evidence": [{"span_id": f"spn_{letter * 24}", "quote": "evidence"}],
         "rationale": "grounded", "missing_information": []}
        for cid, letter in (("python_skill", "a"), ("sql_skill", "b"))
    ]}).criteria
    observed, _, comparable, _, _ = calculate_deterministic_scores(
        evaluations, {"python_skill": 50, "sql_skill": 50},
        threshold=Decimal("70"), core_minimum_scores={},
        score_overrides={"python_skill": Decimal("2.7999"), "sql_skill": Decimal("2.8000")},
    )
    assert observed == Decimal("69.9988")
    assert comparable == Decimal("69.9988")
    assert observed < Decimal("70")


def test_jev_question_builder_only_includes_evidence_supported_nonconflicting_criteria():
    from app.schemas.assessment import EvidenceOnlyAssessmentSchema
    from app.services.assessment.jev_scoring import build_jev_primary_payload

    span = "spn_" + "c" * 24
    evidence = EvidenceOnlyAssessmentSchema.model_validate({"criteria": [
        {"criterion_id": "python_skill", "status": "assessed", "evidence": [{"span_id": span, "quote": "Built API"}], "rationale": "Có bằng chứng.", "missing_information": []},
        {"criterion_id": "sql_skill", "status": "insufficient_evidence", "evidence": [], "rationale": "Thiếu.", "missing_information": ["Hỏi SQL."]},
    ]})
    class Criterion:
        criterion_id = "python_skill"
        label_vi = "Python"
        description_vi = "Xây dựng dịch vụ Python"
        anchors = {"0": "Không có", "1": "Cơ bản", "2": "Đạt", "3": "Tốt", "4": "Mạnh"}
    class MissingCriterion:
        criterion_id = "sql_skill"
        label_vi = "SQL"
        description_vi = "Dùng SQL"
        anchors = Criterion.anchors

    payload, eligible = build_jev_primary_payload(evidence, [Criterion(), MissingCriterion()], {"python_skill": {span: "Built API"}})
    assert eligible == {"python_skill"}
    assert set(payload["questions"]) == {"python_skill"}
    question = payload["questions"]["python_skill"]
    assert question["type"] == "score" and len(question["criteria"]) == 5
    assert payload["state"]["criteria"]["python_skill"]["source_spans"] == [{"span_id": span, "quote": "Built API"}]


def test_jev_response_validator_pins_model_and_probability_distribution():
    from app.services.assessment.jev_scoring import validate_jev_primary_response
    from app.services.jev.provider import JevDecisionResponse

    response = JevDecisionResponse.model_validate({
        "model": "jev-1.13.0", "answers": {"python_skill": {
            "type": "score", "score": 2.3, "confidence": 0.7,
            "probabilities": {"0": 0.1, "1": 0.1, "2": 0.3, "3": 0.4, "4": 0.1},
        }},
    })
    scores = validate_jev_primary_response(response, {"python_skill"}, "jev-1.13.0")
    assert scores["python_skill"].score == Decimal("2.3")
    assert scores["python_skill"].probabilities["2"] == Decimal("0.3")


def test_jev_response_validator_normalizes_rounded_probability_mass_at_score_boundary():
    from app.services.assessment.jev_scoring import validate_jev_primary_response
    from app.services.jev.provider import JevDecisionResponse

    response = JevDecisionResponse.model_validate({
        "model": "jev-1.13.0", "answers": {"python_skill": {
            "type": "score", "score": 4.0, "confidence": 0.9,
            "probabilities": {"0": 0.004, "1": 0.004, "2": 0.004, "3": 0.004, "4": 0.999},
        }},
    })
    score = validate_jev_primary_response(response, {"python_skill"}, "jev-1.13.0")["python_skill"]
    assert Decimal("0") <= score.score <= Decimal("4")
    assert score.score.quantize(Decimal("0.0001")) == Decimal("3.9606")
    assert sum(score.probabilities.values()) == Decimal("1")


def test_jev_request_limits_question_count_and_serialized_size():
    import uuid
    from app.services.llm.call_policy import JevReservationPolicy
    from app.services.llm.types import CompletionRequest

    policy = JevReservationPolicy(
        budget_period_id=uuid.uuid4(), cap_usd=Decimal("1"), max_input_tokens=65536,
        rate_per_million_usd=Decimal("0.042"), rate_verified_at=date.today().isoformat(),
        accepted_models=frozenset({"jev-1.13.0"}),
        provider_endpoint="https://api.typesafe.ai/v1/systemone",
    )
    request = CompletionRequest(
        task_kind="assessment", system_prompt="", user_prompt=json.dumps({
            "state": {"criteria": {}}, "questions": {f"c-{i}": {"type": "score"} for i in range(21)}
        }), model="jev-1.13.0", max_output_tokens=0, provider="jev", purpose="jev_primary",
        response_format=None,
    )
    with pytest.raises(ValueError, match="JEV_REQUEST_BOUND_EXCEEDED"):
        policy.input_reservation_tokens(request)


def test_jev_response_validator_rejects_unrequested_or_wrong_model():
    from app.services.assessment.jev_scoring import validate_jev_primary_response
    from app.services.jev.provider import JevDecisionResponse
    response = JevDecisionResponse.model_validate({
        "model": "jev-1.13.0", "answers": {"other": {"type": "score", "score": 2, "confidence": 0.8, "probabilities": {"0": 0, "1": 0, "2": 1, "3": 0, "4": 0}}},
    })
    with pytest.raises(ValueError, match="JEV_PRIMARY_ANSWER_SET_INVALID"):
        validate_jev_primary_response(response, {"python_skill"}, "jev-1.13.0")
    with pytest.raises(ValueError, match="JEV_PRIMARY_MODEL_MISMATCH"):
        validate_jev_primary_response(response, {"other"}, "jev-1.13.1")


def test_deepseek_explanation_validator_limits_ids_and_citations_to_validated_evidence():
    from app.schemas.assessment import EvidenceOnlyAssessmentSchema
    from app.services.assessment.jev_scoring import validate_jev_narrative

    span = "spn_" + "d" * 24
    evidence = EvidenceOnlyAssessmentSchema.model_validate({"criteria": [
        {"criterion_id": "python_skill", "status": "assessed", "evidence": [{"span_id": span, "quote": "Built API"}], "rationale": "Evidence.", "missing_information": []},
        {"criterion_id": "sql_skill", "status": "insufficient_evidence", "evidence": [], "rationale": "Missing.", "missing_information": ["Hỏi SQL."]},
    ]})
    valid = {"criteria": [
        {"criterion_id": "python_skill", "explanation_vi": "Có mô tả triển khai API.", "basis_span_ids": [span], "followup_questions": ["Bạn xử lý xác thực thế nào?"]},
        {"criterion_id": "sql_skill", "explanation_vi": "CV chưa nêu việc dùng SQL.", "basis_span_ids": [], "followup_questions": ["Bạn từng tối ưu truy vấn nào?"]},
    ]}
    parsed = validate_jev_narrative(json.dumps(valid, ensure_ascii=False), evidence, {"python_skill", "sql_skill"})
    assert parsed.criteria[0].basis_span_ids == [span]
    invalid = {**valid, "criteria": [{**valid["criteria"][0], "basis_span_ids": ["spn_" + "e" * 24]}, valid["criteria"][1]]}
    with pytest.raises(ValueError, match="JEV_NARRATIVE_UNSUPPORTED_CITATION"):
        validate_jev_narrative(json.dumps(invalid, ensure_ascii=False), evidence, {"python_skill", "sql_skill"})


import json


def _jev_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "APP_ENV": "sandbox",
        "LLM_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "synthetic-deepseek-key",
        "ASSESSMENT_SCORER_MODE": "jev",
        "JEV_API_KEY": "synthetic-typesafe-key",
        "JEV_BASE_URL": "https://api.typesafe.ai/v1/systemone",
        "JEV_MODEL": "jev-1.13.0",
        "JEV_DATA_PROCESSING_APPROVED": True,
        "JEV_INPUT_PRICE_PER_MILLION_USD": 0.042,
        "JEV_RATE_CARD_VERIFIED_AT": date.today().isoformat(),
    }
    values.update(overrides)
    return Settings(**values)


def test_assessment_scorer_defaults_to_deepseek():
    settings = Settings(_env_file=None, APP_ENV="sandbox", LLM_PROVIDER="mock")
    assert settings.ASSESSMENT_SCORER_MODE == "deepseek"


@pytest.mark.parametrize(
    "changes",
    [
        {"JEV_API_KEY": None},
        {"JEV_DATA_PROCESSING_APPROVED": False},
        {"JEV_INPUT_PRICE_PER_MILLION_USD": None},
        {"JEV_RATE_CARD_VERIFIED_AT": None},
        {"JEV_RATE_CARD_VERIFIED_AT": "yesterday"},
        {"JEV_BASE_URL": "https://openrouter.ai/api/v1/systemone"},
        {"JEV_MODEL": "jev-latest"},
        {"JEV_MODE": "shadow"},
        {"JEV_RERANK_MODE": "rerank"},
        {"LLM_PROVIDER": "mock", "DEEPSEEK_API_KEY": None},
    ],
)
def test_jev_primary_requires_direct_provider_approval_and_exclusive_mode(changes):
    with pytest.raises(ValueError):
        _jev_settings(**changes)


def test_scorer_snapshot_pins_provider_without_copying_secret():
    from app.services.assessment.service import _assessment_scorer_snapshot
    settings = _jev_settings()
    snapshot = _assessment_scorer_snapshot(settings)
    assert snapshot == {
        "scorer_mode": "jev",
        "scorer_provider": "typesafe_direct",
        "scorer_model": "jev-1.13.0",
        "evidence_agent_model": settings.DEEPSEEK_MODEL,
        "explanation_model": settings.DEEPSEEK_MODEL,
        "scorer_endpoint": "https://api.typesafe.ai/v1/systemone",
        "scorer_input_rate_per_million_usd": 0.042,
        "scorer_rate_verified_at": date.today().isoformat(),
        "evidence_agent_prompt_version": "assessment-agent-evidence.v1",
    }
    assert "JEV_API_KEY" not in snapshot
    assert "DEEPSEEK_API_KEY" not in snapshot


def test_deepseek_scorer_snapshot_is_explicit_and_keeps_model():
    from app.services.assessment.service import _assessment_scorer_snapshot
    settings = Settings(_env_file=None, APP_ENV="sandbox", LLM_PROVIDER="deepseek", DEEPSEEK_API_KEY="synthetic-deepseek-key", DEEPSEEK_MODEL="deepseek-flash")
    assert _assessment_scorer_snapshot(settings) == {
        "scorer_mode": "deepseek",
        "scorer_provider": "deepseek",
        "scorer_model": "deepseek-flash",
    }


@pytest.mark.asyncio
async def test_jev_primary_migration_adds_nullable_fields_and_keeps_legacy_score_type(test_session_factory):
    async with test_session_factory() as session:
        jev_score = await session.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'criterion_assessments' "
            "AND column_name = 'jev_score'"
        ))
        jev_probabilities = await session.execute(text(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'criterion_assessments' "
            "AND column_name = 'jev_probabilities'"
        ))
        legacy_score = await session.execute(text(
            "SELECT data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'criterion_assessments' "
            "AND column_name = 'score'"
        ))
        rows = jev_score.one()
        probabilities = jev_probabilities.one()
        legacy = legacy_score.scalar_one()
    assert rows == ("numeric", "YES")
    assert probabilities == ("jsonb", "YES")
    assert legacy == "smallint"
