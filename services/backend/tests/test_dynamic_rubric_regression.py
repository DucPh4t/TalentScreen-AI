"""Regression tests for role-specific rubric IDs across validation and scoring."""
from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain.enums import CriterionOutcome, Recommendation
from app.domain.rubric_policy import RubricValidationError, validate_canonical_rubric
from app.schemas.assessment import AssessmentOutputSchema
from app.services.assessment.scoring import calculate_deterministic_scores
from app.services.assessment.validator import AssessmentValidationError, validate_assessment_output


def _criterion(criterion_id: str, weight: int, *, core: bool = False) -> dict:
    return {
        "id": criterion_id,
        "label": f"Năng lực {criterion_id}",
        "description": f"Đánh giá năng lực {criterion_id} theo yêu cầu công việc.",
        "weight": weight,
        "core": core,
        "scoring_anchors": [
            {"score": score, "description": f"Mức {score} thể hiện năng lực {criterion_id}."}
            for score in range(5)
        ],
    }


def _rubric(criteria: list[dict], core_minimum_scores: dict | None = None) -> dict:
    return {
        "criteria": criteria,
        "recommendation_policy": {
            "threshold": 70,
            "core_minimum_scores": core_minimum_scores or {},
        },
    }


@pytest.mark.parametrize(
    "criteria",
    [
        [_criterion("react_ui", 60), _criterion("typescript", 40)],
        [_criterion(f"skill_{index}", 11 if index < 4 else 7) for index in range(12)],
    ],
)
def test_dynamic_rubric_accepts_two_to_twelve_criteria(criteria: list[dict]) -> None:
    validate_canonical_rubric(_rubric(criteria))


def test_dynamic_rubric_rejects_duplicate_ids_bad_weight_and_unknown_core() -> None:
    duplicate = [_criterion("react_ui", 50), _criterion("react_ui", 50)]
    with pytest.raises(RubricValidationError, match="Trùng lặp"):
        validate_canonical_rubric(_rubric(duplicate))

    with pytest.raises(RubricValidationError, match="Tổng trọng số"):
        validate_canonical_rubric(_rubric([_criterion("react_ui", 40), _criterion("typescript", 40)]))

    valid = [_criterion("react_ui", 60), _criterion("typescript", 40)]
    with pytest.raises(RubricValidationError, match="Core minimum tham chiếu"):
        validate_canonical_rubric(_rubric(valid, {"python_backend": 2}))


def test_dynamic_assessment_schema_and_exact_rubric_set_validation() -> None:
    span_id = "spn_" + "a" * 24
    payload = {
        "criteria": [
            {
                "criterion_id": criterion_id,
                "status": "assessed",
                "score": 3,
                "evidence": [{"span_id": span_id, "quote": "Implemented a React dashboard."}],
                "rationale": "Có ví dụ trực tiếp trong CV.",
                "missing_information": [],
            }
            for criterion_id in ("react_ui", "typescript")
        ]
    }
    parsed = AssessmentOutputSchema.model_validate(payload)
    assert {criterion.criterion_id for criterion in parsed.criteria} == {"react_ui", "typescript"}

    registry = {span_id: SimpleNamespace(text="Implemented a React dashboard.")}
    accepted = validate_assessment_output(json.dumps(payload), registry, {"react_ui", "typescript"})
    assert len(accepted.criteria) == 2

    with pytest.raises(AssessmentValidationError, match="CRITERION_SET_MISMATCH"):
        validate_assessment_output(json.dumps(payload), registry, {"react_ui", "typescript", "accessibility"})


def test_dynamic_scoring_uses_configured_core_floor_and_not_legacy_ids() -> None:
    evaluations = AssessmentOutputSchema.model_validate(
        {
            "criteria": [
                {
                    "criterion_id": "react_ui",
                    "status": "assessed",
                    "score": 4,
                    "evidence": [{"span_id": "spn_" + "b" * 24, "quote": "React"}],
                    "rationale": "Có bằng chứng cụ thể.",
                },
                {
                    "criterion_id": "typescript",
                    "status": "assessed",
                    "score": 3,
                    "evidence": [{"span_id": "spn_" + "c" * 24, "quote": "TypeScript"}],
                    "rationale": "Có bằng chứng cụ thể.",
                },
            ]
        }
    ).criteria

    score, coverage, comparable, recommendation, _ = calculate_deterministic_scores(
        evaluations,
        {"react_ui": 60, "typescript": 40},
        threshold=Decimal("70"),
        core_minimum_scores={},
    )
    assert score == Decimal("90.0000")
    assert coverage == Decimal("1.0000")
    assert comparable == Decimal("90.0000")
    assert recommendation == Recommendation.CONSIDER_NEXT_ROUND

    _, _, _, below_core, reasons = calculate_deterministic_scores(
        [evaluations[0].model_copy(update={"score": 1}), evaluations[1]],
        {"react_ui": 60, "typescript": 40},
        threshold=Decimal("0"),
        core_minimum_scores={"react_ui": 2},
    )
    assert below_core == Recommendation.REVIEW_REQUIRED
    assert any(reason.startswith("CORE_FLOOR_FAILED:react_ui") for reason in reasons)


def test_dynamic_assessment_schema_keeps_missing_evidence_unscored() -> None:
    output = AssessmentOutputSchema.model_validate(
        {
            "criteria": [
                {
                    "criterion_id": "react_ui",
                    "status": "insufficient_evidence",
                    "score": None,
                    "evidence": [],
                    "rationale": "CV chưa nêu rõ.",
                    "missing_information": ["Cần hỏi về khả năng accessibility."],
                },
                {
                    "criterion_id": "typescript",
                    "status": "insufficient_evidence",
                    "score": None,
                    "evidence": [],
                    "rationale": "CV chưa nêu rõ.",
                    "missing_information": ["Cần hỏi về typing."],
                },
            ]
        }
    )
    assert all(item.status == CriterionOutcome.INSUFFICIENT_EVIDENCE and item.score is None for item in output.criteria)
