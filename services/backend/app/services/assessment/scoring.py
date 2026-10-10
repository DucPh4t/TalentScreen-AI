"""Deterministic scoring and recommendation engine for TalentScreen AI.
Invariants:
  1. AI NEVER computes or decides the final score or hiring recommendation.
  2. Pure, deterministic calculations using exact Decimal arithmetic.
  3. No premature rounding before threshold comparison.
  4. A comparable score requires evidence for every explicitly required criterion;
     missing optional criteria remain visible without suppressing the normalized score.
  5. Floors and threshold come from the approved rubric policy; they are guidance only.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Mapping

from app.domain.enums import CriterionId, CriterionOutcome, Recommendation
from app.schemas.assessment import CriterionAssessmentSchema

DEFAULT_THRESHOLD = Decimal("70.0")
DEFAULT_CORE_FLOOR = 2

CORE_CRITERIA_IDS = {
    CriterionId.PYTHON_BACKEND.value,
    CriterionId.API_DESIGN.value,
    CriterionId.SQL_DATA.value,
}


def calculate_deterministic_scores(
    evaluations: list[CriterionAssessmentSchema],
    rubric_weights: dict[str, int],
    threshold: Decimal = DEFAULT_THRESHOLD,
    core_floor: int = DEFAULT_CORE_FLOOR,
    core_criteria_ids: Optional[set[str]] = None,
    core_minimum_scores: Optional[dict[str, int]] = None,
    score_overrides: Mapping[str, Decimal] | None = None,
    required_criterion_ids: Optional[set[str]] = None,
) -> tuple[Optional[Decimal], Decimal, Optional[Decimal], Recommendation, list[str]]:
    """Compute observed score, coverage, comparable score, recommendation, and reason codes.
    Returns:
        (observed_score, coverage, comparable_score, recommendation, reason_codes)
    """
    reason_codes: list[str] = []
    if required_criterion_ids is None:
        # Preserve the legacy full-coverage contract for rubrics that do not
        # explicitly state which competencies are required.
        required_ids = set(rubric_weights)
    else:
        required_ids = set(required_criterion_ids)
        unknown_required = required_ids - set(rubric_weights)
        if unknown_required:
            raise ValueError(f"REQUIRED_CRITERION_NOT_IN_RUBRIC:{sorted(unknown_required)}")
    assessed_weights_sum = 0
    weighted_score_accum = Decimal("0")
    has_conflict = False
    has_insufficient = False

    scores_by_id: dict[str, Decimal] = {}

    for c in evaluations:
        cid = c.criterion_id
        w = Decimal(rubric_weights.get(cid, 0))

        if c.status == CriterionOutcome.ASSESSED:
            score_value = score_overrides.get(cid) if score_overrides is not None else (
                Decimal(c.score) if c.score is not None else None
            )
            if score_value is None and score_overrides is not None:
                has_insufficient = True
                reason_codes.append(f"SCORER_UNAVAILABLE:{cid}")
                continue
            if score_value is None or not score_value.is_finite() or not Decimal("0") <= score_value <= Decimal("4"):
                raise ValueError(f"ASSESSED_SCORE_INVALID:{cid}")
            assessed_weights_sum += int(w)
            scores_by_id[cid] = score_value
            # Contribution: w * (score / 4)
            weighted_score_accum += w * (score_value / Decimal("4"))
        elif c.status == CriterionOutcome.INSUFFICIENT_EVIDENCE:
            has_insufficient = True
            reason_codes.append(f"INSUFFICIENT_EVIDENCE:{cid}")
        elif c.status == CriterionOutcome.CONFLICTING_EVIDENCE:
            has_conflict = True
            reason_codes.append(f"CONFLICTING_EVIDENCE:{cid}")

    coverage = (Decimal(assessed_weights_sum) / Decimal("100")).quantize(Decimal("0.0001"))

    # Observed Score: normalized across assessed criteria only
    observed_score: Optional[Decimal] = None
    if assessed_weights_sum > 0:
        observed_score = (
            (weighted_score_accum / Decimal(assessed_weights_sum)) * Decimal("100")
        ).quantize(Decimal("0.0001"))

    missing_required = required_ids - set(scores_by_id)
    if missing_required:
        reason_codes.extend(f"REQUIRED_EVIDENCE_MISSING:{cid}" for cid in sorted(missing_required))

    # Normalize over criteria with evidence. A rubric may explicitly allow
    # optional competencies to be absent; their missing weight stays visible
    # through coverage and needs_clarification, but does not erase this score.
    comparable_score: Optional[Decimal] = None
    if assessed_weights_sum > 0 and not missing_required and not has_conflict:
        comparable_score = observed_score

    # Recommendation determination
    if has_conflict or has_insufficient or missing_required:
        recommendation = Recommendation.NEEDS_CLARIFICATION
    else:
        assert comparable_score is not None
        # Check core criteria floor dynamically
        core_floor_passed = True
        if core_minimum_scores is not None:
            for cid, floor_val in core_minimum_scores.items():
                if cid in rubric_weights or cid in scores_by_id:
                    s = scores_by_id.get(cid, 0)
                    if s < floor_val:
                        core_floor_passed = False
                        reason_codes.append(f"CORE_FLOOR_FAILED:{cid}({s}<{floor_val})")
        else:
            if core_criteria_ids is not None:
                active_core_ids = set(core_criteria_ids)
            else:
                active_core_ids = {cid for cid in CORE_CRITERIA_IDS if cid in rubric_weights or cid in scores_by_id}

            for core_id in active_core_ids:
                s = scores_by_id.get(core_id, 0)
                if s < core_floor:
                    core_floor_passed = False
                    reason_codes.append(f"CORE_FLOOR_FAILED:{core_id}({s}<{core_floor})")

        # Invariant: No premature rounding before threshold comparison (e.g. 69.9999 < 70)
        if comparable_score >= threshold and core_floor_passed:
            recommendation = Recommendation.CONSIDER_NEXT_ROUND
            reason_codes.append(f"THRESHOLD_MET:{comparable_score}>={threshold}")
        else:
            recommendation = Recommendation.REVIEW_REQUIRED
            if comparable_score < threshold:
                reason_codes.append(f"THRESHOLD_NOT_MET:{comparable_score}<{threshold}")

    return observed_score, coverage, comparable_score, recommendation, reason_codes
