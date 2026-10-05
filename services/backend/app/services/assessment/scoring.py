"""Deterministic scoring and recommendation engine for TalentScreen AI.
Invariants:
  1. AI NEVER computes or decides the final score or hiring recommendation.
  2. Pure, deterministic calculations using exact Decimal arithmetic.
  3. No premature rounding before threshold comparison.
  4. Incomplete profiles have no comparable_score and cannot be ranked.
  5. Core criteria floor (2) and threshold (70) strictly enforced from approved rubric.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

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
) -> tuple[Optional[Decimal], Decimal, Optional[Decimal], Recommendation, list[str]]:
    """Compute observed score, coverage, comparable score, recommendation, and reason codes.
    Returns:
        (observed_score, coverage, comparable_score, recommendation, reason_codes)
    """
    reason_codes: list[str] = []
    assessed_weights_sum = 0
    weighted_score_accum = Decimal("0")
    has_conflict = False
    has_insufficient = False

    scores_by_id: dict[str, int] = {}

    for c in evaluations:
        cid = c.criterion_id
        w = Decimal(rubric_weights.get(cid, 0))

        if c.status == CriterionOutcome.ASSESSED:
            assert c.score is not None
            assessed_weights_sum += int(w)
            scores_by_id[cid] = c.score
            # Contribution: w * (score / 4)
            weighted_score_accum += w * (Decimal(c.score) / Decimal("4"))
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

    # Comparable Score: valid ONLY when 100% of criteria are assessed without conflicts
    comparable_score: Optional[Decimal] = None
    if assessed_weights_sum == 100 and not has_conflict and not has_insufficient:
        comparable_score = observed_score

    # Recommendation determination
    if has_conflict or has_insufficient or assessed_weights_sum < 100:
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
