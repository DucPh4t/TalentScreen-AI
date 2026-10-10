"""AI Shortlist Engine for TalentScreen AI.
Ranks candidates within a requisition based on deterministic rubric scores,
core competency thresholds, coverage, and evidence completeness.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.assessment import AssessmentRun, CriterionAssessment
from app.db.models.candidate import Application, Candidate
from app.db.models.document import SanitizedVersion
from app.db.models.requisition import Requisition, RequisitionMembership, RubricCriterion, RubricVersion
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole, CriterionOutcome, Recommendation, SanitizedVersionStatus
from app.services.assessment.scoring import DEFAULT_THRESHOLD

logger = logging.getLogger(__name__)


class ShortlistTier(str, Enum):
    RECOMMEND = "recommend"
    BELOW_THRESHOLD = "below_threshold"
    CORE_FAIL = "core_fail"
    NEEDS_CLARIFICATION = "needs_clarification"
    REVIEW_REQUIRED = "review_required"
    NOT_ASSESSED = "not_assessed"


TIER_DISPLAY_NAMES = {
    ShortlistTier.RECOMMEND.value: "Đạt ngưỡng tham khảo — HR/IT cân nhắc",
    ShortlistTier.BELOW_THRESHOLD.value: "Dưới ngưỡng tham khảo — HR/IT xem xét",
    ShortlistTier.CORE_FAIL.value: "Must-have dưới floor — cần HR/IT xem xét",
    ShortlistTier.NEEDS_CLARIFICATION.value: "Cần HR làm rõ evidence",
    ShortlistTier.REVIEW_REQUIRED.value: "Cần HR/IT đối chiếu trực tiếp",
    ShortlistTier.NOT_ASSESSED.value: "Chưa có đánh giá hiện hành (Not Assessed)",
}


def classify_shortlist_tier(
    *, has_current_assessment: bool, comparable_score: Optional[float],
    core_failed: bool, threshold: float, recommendation: Optional[str] = None,
) -> ShortlistTier:
    """Group for human review; a tier is never an automatic hiring decision."""
    if not has_current_assessment:
        return ShortlistTier.NOT_ASSESSED
    if comparable_score is None:
        return (
            ShortlistTier.NEEDS_CLARIFICATION
            if recommendation == Recommendation.NEEDS_CLARIFICATION.value
            else ShortlistTier.REVIEW_REQUIRED
        )
    if core_failed:
        return ShortlistTier.CORE_FAIL
    return ShortlistTier.RECOMMEND if comparable_score >= threshold else ShortlistTier.BELOW_THRESHOLD


async def compute_requisition_shortlist(
    db: AsyncSession,
    requisition_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> dict[str, Any]:
    """Compute ranked shortlist for a requisition.
    Guarantees:
      - Strictly scoped to requisition membership or Admin role.
      - Missing must-have evidence is shown for HR clarification, never as automatic rejection.
      - Transparent breakdown of core criteria status, missing evidence, and top strengths.
    """
    # 1. Access verification
    stmt_req = select(Requisition).where(Requisition.id == requisition_id)
    req = (await db.execute(stmt_req)).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Đợt tuyển dụng không tồn tại.")

    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập đợt tuyển dụng này.")

    rubric_id = req.current_rubric_version_id
    if not rubric_id:
        return {
            "requisition_id": str(requisition_id),
            "requisition_title": req.title,
            "rubric_version_id": None,
            "threshold": float(DEFAULT_THRESHOLD),
            "total_candidates": 0,
            "assessed_candidates": 0,
            "tier_summary": {tier.value: 0 for tier in ShortlistTier},
            "criteria": [],
            "candidates": [],
        }

    stmt_rubric = (
        select(RubricVersion)
        .where(RubricVersion.id == rubric_id)
        .options(selectinload(RubricVersion.criteria))
    )
    rubric = (await db.execute(stmt_rubric)).scalar_one_or_none()
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric hiện hành không tồn tại.")

    criteria_list = sorted(rubric.criteria, key=lambda c: c.criterion_id)
    threshold_config = rubric.threshold_config or {}
    base_threshold = float(threshold_config.get("threshold", DEFAULT_THRESHOLD))
    core_mins = threshold_config.get("core_minimum_scores", {})
    if not isinstance(core_mins, dict):
        core_mins = {}

    # Core floors come exclusively from the HR-approved policy, never weights.
    core_mins = dict(core_mins)
    core_criterion_ids = set(core_mins)

    # 2. Load active applications joined with candidate and current assessment
    stmt_apps = (
        select(Application, Candidate.public_label, AssessmentRun)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .outerjoin(AssessmentRun, AssessmentRun.id == Application.current_assessment_run_id)
        .where(Application.requisition_id == requisition_id, Application.status == "active")
        .order_by(Application.received_at.asc())
    )
    rows = (await db.execute(stmt_apps)).all()

    # Load criterion scores for active assessment runs
    run_ids = [run.id for _, _, run in rows if run is not None]
    criteria_by_run: dict[uuid.UUID, dict[str, CriterionAssessment]] = {}
    if run_ids:
        stmt_crits = (
            select(CriterionAssessment)
            .where(CriterionAssessment.run_id.in_(run_ids))
        )
        for ca in (await db.execute(stmt_crits)).scalars().all():
            criteria_by_run.setdefault(ca.run_id, {})[ca.criterion_id] = ca

    candidate_records = []
    tier_counts = {tier.value: 0 for tier in ShortlistTier}

    for app, label, run in rows:
        # Check freshness & validity
        valid = bool(
            run and run.status == "succeeded"
            and run.application_generation == app.generation
            and run.document_id == app.current_document_id
            and run.sanitized_version_id == app.current_sanitized_version_id
            and run.rubric_version_id == rubric_id
        )
        if valid:
            sv = await db.get(SanitizedVersion, app.current_sanitized_version_id)
            valid = bool(sv and sv.status == SanitizedVersionStatus.APPROVED)

        if not valid or run is None:
            tier = ShortlistTier.NOT_ASSESSED
            tier_counts[tier.value] += 1
            candidate_records.append({
                "application_id": str(app.id),
                "candidate_id": str(app.candidate_id),
                "public_label": label,
                "tier": tier.value,
                "tier_display": TIER_DISPLAY_NAMES[tier.value],
                "rank": None,
                "comparable_score": None,
                "observed_score": None,
                "coverage": None,
                "recommendation": None,
                "strengths": [],
                "missing_criteria": [],
                "core_failed_criteria": [],
                "criteria_scores": {},
                "has_decision": bool(app.current_decision_id),
                "received_at": app.received_at.isoformat() if app.received_at else None,
                "raw_comp_score": -1.0,
                "raw_coverage": 0.0,
            })
            continue

        comp_score = float(run.comparable_score) if run.comparable_score is not None else None
        coverage = float(run.coverage)
        obs_score = float(run.observed_score) if run.observed_score is not None else None
        rec_val = run.recommendation.value if run.recommendation else None

        crit_map = criteria_by_run.get(run.id, {})
        scores_payload: dict[str, Any] = {}
        strengths: list[str] = []
        missing_criteria: list[str] = []
        core_failed_criteria: list[str] = []

        for c in criteria_list:
            ca = crit_map.get(c.criterion_id)
            if ca:
                score = ca.score
                c_status = ca.status.value if hasattr(ca.status, "value") else str(ca.status)
                scores_payload[c.criterion_id] = {
                    "label": c.label_vi,
                    "score": score,
                    "status": c_status,
                    "core": c.criterion_id in core_criterion_ids,
                }
                if c_status == CriterionOutcome.ASSESSED.value and score is not None and score >= 3:
                    strengths.append(c.label_vi)
                elif c_status == CriterionOutcome.INSUFFICIENT_EVIDENCE.value:
                    missing_criteria.append(c.label_vi)

                # Core check
                if c.criterion_id in core_criterion_ids:
                    min_floor = core_mins.get(c.criterion_id, 2)
                    if c_status != CriterionOutcome.ASSESSED.value or score is None or score < min_floor:
                        core_failed_criteria.append(c.label_vi)
            else:
                scores_payload[c.criterion_id] = {
                    "label": c.label_vi,
                    "score": None,
                    "status": "missing",
                    "core": c.criterion_id in core_criterion_ids,
                }
                missing_criteria.append(c.label_vi)
                if c.criterion_id in core_criterion_ids:
                    core_failed_criteria.append(c.label_vi)

        # Determine Tier
        tier = classify_shortlist_tier(
            has_current_assessment=True,
            comparable_score=comp_score,
            core_failed=bool(core_failed_criteria),
            threshold=base_threshold,
            recommendation=rec_val,
        )

        tier_counts[tier.value] += 1
        candidate_records.append({
            "application_id": str(app.id),
            "candidate_id": str(app.candidate_id),
            "public_label": label,
            "tier": tier.value,
            "tier_display": TIER_DISPLAY_NAMES[tier.value],
            "rank": None,
            "comparable_score": comp_score,
            "observed_score": obs_score,
            "coverage": coverage,
            "recommendation": rec_val,
            "strengths": strengths,
            "missing_criteria": missing_criteria,
            "core_failed_criteria": core_failed_criteria,
            "criteria_scores": scores_payload,
            "has_decision": bool(app.current_decision_id),
            "received_at": app.received_at.isoformat() if app.received_at else None,
            "raw_comp_score": comp_score if comp_score is not None else -1.0,
            "raw_coverage": coverage,
        })

    # Sort & Rank
    # Tier sort order
    tier_order = {
        ShortlistTier.RECOMMEND.value: 1,
        ShortlistTier.BELOW_THRESHOLD.value: 2,
        ShortlistTier.CORE_FAIL.value: 3,
        ShortlistTier.NEEDS_CLARIFICATION.value: 4,
        ShortlistTier.REVIEW_REQUIRED.value: 5,
        ShortlistTier.NOT_ASSESSED.value: 6,
    }

    assessed_candidates = [c for c in candidate_records if c["tier"] not in {ShortlistTier.NOT_ASSESSED.value, ShortlistTier.NEEDS_CLARIFICATION.value, ShortlistTier.REVIEW_REQUIRED.value}]
    unranked_candidates = [c for c in candidate_records if c["tier"] in {ShortlistTier.NOT_ASSESSED.value, ShortlistTier.NEEDS_CLARIFICATION.value, ShortlistTier.REVIEW_REQUIRED.value}]

    # Sort assessed by: Tier priority (asc), Comparable Score (desc), Coverage (desc)
    assessed_candidates.sort(
        key=lambda c: (tier_order.get(c["tier"], 99), -c["raw_comp_score"], -c["raw_coverage"])
    )

    # Assign rank 1..N
    current_rank = 1
    for c in assessed_candidates:
        c["rank"] = current_rank
        current_rank += 1
        # clean temporary sorting keys
        del c["raw_comp_score"]
        del c["raw_coverage"]

    for c in unranked_candidates:
        del c["raw_comp_score"]
        del c["raw_coverage"]

    final_candidates = assessed_candidates + unranked_candidates

    assessed_scores = [c["comparable_score"] for c in assessed_candidates if c["comparable_score"] is not None]
    avg_score = round(sum(assessed_scores) / len(assessed_scores), 1) if assessed_scores else None
    clarification_count = sum(
        1 for candidate in candidate_records
        if candidate.get("recommendation") == Recommendation.NEEDS_CLARIFICATION.value
    )

    return {
        "requisition_id": str(requisition_id),
        "requisition_title": req.title,
        "rubric_version_id": str(rubric.id),
        "threshold": base_threshold,
        "total_candidates": len(candidate_records),
        "assessed_candidates": len(candidate_records) - tier_counts[ShortlistTier.NOT_ASSESSED.value],
        "shortlisted_candidates": tier_counts[ShortlistTier.RECOMMEND.value],
        "clarification_candidates": clarification_count,
        "average_score": avg_score,
        "tier_summary": tier_counts,
        "criteria": [
            {
                "id": c.criterion_id,
                "label": c.label_vi,
                "weight": c.weight,
                "core": c.criterion_id in core_criterion_ids,
            }
            for c in criteria_list
        ],
        "candidates": final_candidates,
    }
