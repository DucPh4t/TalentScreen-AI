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
    elif isinstance(anchors, list) and all(isinstance(anchor, dict) for anchor in anchors):
        by_score = {}
        for anchor in anchors:
            score = anchor.get("score")
            if type(score) is not int or not 0 <= score <= 4 or score in by_score:
                raise ValueError("JEV_PRIMARY_RUBRIC_ANCHORS_INVALID")
            by_score[score] = anchor
        values = [by_score.get(i) for i in range(5)]
    elif isinstance(anchors, list):
        values = anchors
    else:
        values = []

    def anchor_text(value: Any) -> str | None:
        if isinstance(value, str):
            return value.strip()
        if not isinstance(value, dict):
            return None
        description = value.get("description")
        qualifying = value.get("qualifying_evidence", [])
        not_sufficient = value.get("not_sufficient", [])
        if (
            not isinstance(description, str)
            or not description.strip()
            or not isinstance(qualifying, list)
            or any(not isinstance(item, str) or not item.strip() for item in qualifying)
            or not isinstance(not_sufficient, list)
            or any(not isinstance(item, str) or not item.strip() for item in not_sufficient)
        ):
            return None
        parts = [description.strip()]
        if qualifying:
            parts.append("Bằng chứng đáp ứng: " + "; ".join(item.strip() for item in qualifying))
        if not_sufficient:
            parts.append("Chưa đủ bằng chứng: " + "; ".join(item.strip() for item in not_sufficient))
        return "\n".join(parts)

    ordered = [anchor_text(value) for value in values]
    if len(ordered) != 5 or any(not value for value in ordered):
        raise ValueError("JEV_PRIMARY_RUBRIC_ANCHORS_INVALID")
    return ordered


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
    expected_answer_keys = {"type", "score", "confidence", "probabilities"}
    for criterion_id, answer in response.answers.items():
        if not expected_answer_keys.issubset(answer):
            raise ValueError("JEV_PRIMARY_ANSWER_FIELDS_MISSING")
        if answer.get("type") != "score":
            raise ValueError("JEV_PRIMARY_ANSWER_TYPE_INVALID")
        try:
            raw_score = Decimal(str(answer["score"]))
            confidence = Decimal(str(answer["confidence"]))
            probabilities = {key: Decimal(str(value)) for key, value in answer["probabilities"].items()}
        except (InvalidOperation, TypeError, AttributeError) as exc:
            raise ValueError("JEV_PRIMARY_ANSWER_VALUES_INVALID") from exc
        if (not raw_score.is_finite() or not Decimal("0") <= raw_score <= Decimal("4")
            or not confidence.is_finite() or not Decimal("0") <= confidence <= Decimal("1")):
            raise ValueError("JEV_PRIMARY_ANSWER_VALUES_INVALID")
        if set(probabilities) != expected_keys:
            raise ValueError("JEV_PRIMARY_PROBABILITY_LEVELS_INVALID")
        if any(not value.is_finite() or not Decimal("0") <= value <= Decimal("1") for value in probabilities.values()):
            raise ValueError("JEV_PRIMARY_PROBABILITY_VALUES_INVALID")
        probability_total = sum(probabilities.values())
        if abs(probability_total - Decimal("1")) > Decimal("0.02"):
            raise ValueError("JEV_PRIMARY_PROBABILITY_MASS_INVALID")
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
