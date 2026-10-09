"""Typed payload construction and fail-closed validation for Jev-primary scoring."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.domain.enums import CriterionOutcome
from app.schemas.assessment import EvidenceOnlyAssessmentSchema
from app.services.jev.provider import JevDecisionResponse


@dataclass(frozen=True)
class JevPrimaryScore:
    score: Decimal
    probabilities: dict[str, Decimal]
    confidence: Decimal
    disposition: str = "scored"


class JevNarrativeCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criterion_id: str
    explanation_vi: str = Field(min_length=1, max_length=800)
    basis_span_ids: list[str] = Field(max_length=6)
    followup_questions: list[str] = Field(max_length=2)

    @model_validator(mode="after")
    def unique_citations_and_questions(self) -> "JevNarrativeCriterion":
        if len(self.basis_span_ids) != len(set(self.basis_span_ids)):
            raise ValueError("duplicate basis span")
        if len(self.followup_questions) != len(set(self.followup_questions)):
            raise ValueError("duplicate follow-up question")
        return self


class JevNarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    criteria: list[JevNarrativeCriterion] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_criteria(self) -> "JevNarrativeOutput":
        ids = [item.criterion_id for item in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate criterion")
        return self


def _ordered_anchors(anchors: Any) -> list[str]:
    if isinstance(anchors, dict):
        values = [anchors.get(str(i), anchors.get(i)) for i in range(5)]
    elif isinstance(anchors, list):
        values = anchors
    else:
        values = []
    if len(values) != 5 or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError("JEV_PRIMARY_RUBRIC_ANCHORS_INVALID")
    return [value.strip() for value in values]


def build_jev_primary_payload(
    evidence: EvidenceOnlyAssessmentSchema,
    rubric_criteria: list[Any],
    spans_by_criterion: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], set[str]]:
    """Create per-criterion score questions using only validator-approved spans."""
    criteria_by_id = {criterion.criterion_id: criterion for criterion in rubric_criteria}
    if len(criteria_by_id) != len(rubric_criteria):
        raise ValueError("JEV_PRIMARY_RUBRIC_INVALID")
    evidence_ids = {criterion.criterion_id for criterion in evidence.criteria}
    if evidence_ids != set(criteria_by_id):
        raise ValueError("JEV_PRIMARY_CRITERION_SET_INVALID")

    questions: dict[str, dict[str, Any]] = {}
    state_criteria: dict[str, dict[str, Any]] = {}
    eligible: set[str] = set()
    for result in evidence.criteria:
        if result.status != CriterionOutcome.ASSESSED:
            continue
        allowed = spans_by_criterion.get(result.criterion_id, {})
        cited: list[dict[str, str]] = []
        for item in result.evidence:
            quote = allowed.get(item.span_id)
            if quote is None or quote != item.quote:
                raise ValueError("JEV_PRIMARY_EVIDENCE_PROVENANCE_INVALID")
            cited.append({"span_id": item.span_id, "quote": quote})
        if not cited:
            continue
        criterion = criteria_by_id[result.criterion_id]
        label = getattr(criterion, "label_vi", result.criterion_id)
        description = getattr(criterion, "description_vi", "")
        anchors = _ordered_anchors(criterion.anchors)
        state_criteria[result.criterion_id] = {
            "criterion_id": result.criterion_id,
            "label": label,
            "description": description,
            "source_spans": cited,
        }
        questions[result.criterion_id] = {
            "type": "score",
            "criteria": anchors,
            "instructions": (
                f"Đánh giá duy nhất năng lực {label} theo mô tả và 5 mức neo 0–4 đã cung cấp. "
                "Chỉ dùng source_spans gắn với criterion_id này; không suy diễn từ thông tin khác. "
                "Nếu câu trích chỉ nhắc tên kỹ năng mà không chứng minh năng lực, chọn mức thấp phù hợp với bằng chứng."
            ),
        }
        eligible.add(result.criterion_id)
    return {"state": {"criteria": state_criteria}, "questions": questions}, eligible


def validate_jev_primary_response(
    response: JevDecisionResponse,
    expected_criterion_ids: set[str],
    pinned_model: str,
) -> dict[str, JevPrimaryScore]:
    """Validate exact model and answer set, then derive expected score from probabilities."""
    served_model = response.model_version or response.model
    if response.model != pinned_model or served_model != pinned_model:
        raise ValueError("JEV_PRIMARY_MODEL_MISMATCH")
    if set(response.answers) != expected_criterion_ids:
        raise ValueError("JEV_PRIMARY_ANSWER_SET_INVALID")
    scores: dict[str, JevPrimaryScore] = {}
    expected_keys = {str(index) for index in range(5)}
    for criterion_id, answer in response.answers.items():
        if set(answer) != {"type", "score", "confidence", "probabilities"} or answer.get("type") != "score":
            raise ValueError("JEV_PRIMARY_ANSWER_SCHEMA_INVALID")
        try:
            raw_score = Decimal(str(answer["score"]))
            confidence = Decimal(str(answer["confidence"]))
            probabilities = {key: Decimal(str(value)) for key, value in answer["probabilities"].items()}
        except (InvalidOperation, TypeError, AttributeError) as exc:
            raise ValueError("JEV_PRIMARY_ANSWER_SCHEMA_INVALID") from exc
        probability_total = sum(probabilities.values())
        if (not raw_score.is_finite() or not Decimal("0") <= raw_score <= Decimal("4")
            or not confidence.is_finite() or not Decimal("0") <= confidence <= Decimal("1")
            or set(probabilities) != expected_keys
            or any(not value.is_finite() or not Decimal("0") <= value <= Decimal("1") for value in probabilities.values())
            or abs(probability_total - Decimal("1")) > Decimal("0.02")):
            raise ValueError("JEV_PRIMARY_ANSWER_SCHEMA_INVALID")
        # Jev returns rounded probabilities that may sum to 0.98..1.02.
        # Normalize before calculating/persisting the expected score so it
        # can never escape the rubric's 0..4 scale due only to rounding.
        normalized: dict[str, Decimal] = {}
        normalized_keys = sorted(probabilities, key=int)
        for key in normalized_keys[:-1]:
            normalized[key] = probabilities[key] / probability_total
        normalized[normalized_keys[-1]] = Decimal("1") - sum(normalized.values())
        probabilities = normalized
        expected = sum(Decimal(key) * value for key, value in probabilities.items())
        if abs(raw_score - expected) > Decimal("0.05"):
            raise ValueError("JEV_PRIMARY_SCORE_DISTRIBUTION_MISMATCH")
        scores[criterion_id] = JevPrimaryScore(
            score=expected,
            probabilities=probabilities,
            confidence=confidence,
        )
    return scores


def validate_jev_narrative(
    raw_content: str,
    evidence: EvidenceOnlyAssessmentSchema,
    expected_criterion_ids: set[str],
) -> JevNarrativeOutput:
    if not raw_content or not raw_content.strip():
        raise ValueError("JEV_NARRATIVE_INVALID")
    try:
        result = JevNarrativeOutput.model_validate_json(raw_content)
    except (ValueError, ValidationError) as exc:
        raise ValueError("JEV_NARRATIVE_INVALID") from exc
    if {item.criterion_id for item in result.criteria} != expected_criterion_ids:
        raise ValueError("JEV_NARRATIVE_CRITERION_SET_INVALID")
    allowed = {
        item.criterion_id: {source.span_id for source in item.evidence}
        for item in evidence.criteria
    }
    if any(set(item.basis_span_ids) - allowed.get(item.criterion_id, set()) for item in result.criteria):
        raise ValueError("JEV_NARRATIVE_UNSUPPORTED_CITATION")
    return result
