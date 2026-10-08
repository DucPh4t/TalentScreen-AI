"""Candidate One-Page Executive Summary Generator (Quick Win 1).
Provides high-density, 5-sentence structured synthesis for rapid HR decision-making.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.assessment import AssessmentRun, CriterionAssessment
from app.db.models.candidate import Application, Candidate
from app.db.models.requisition import Requisition, RequisitionMembership, RubricCriterion, RubricVersion
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import AccountRole, CriterionOutcome, Recommendation

logger = logging.getLogger(__name__)
SUMMARY_VERSION = 2


async def generate_candidate_summary(
    db: AsyncSession,
    application_id: uuid.UUID,
    ctx: AuthenticatedContext,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Synthesize or retrieve a cached 5-sentence executive summary for an application."""
    stmt_app = (
        select(Application)
        .options(
            selectinload(Application.requisition),
            selectinload(Application.candidate),
        )
        .where(Application.id == application_id)
    )
    app_obj = (await db.execute(stmt_app)).scalar_one_or_none()
    if not app_obj or app_obj.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hồ sơ ứng viên không tồn tại.")

    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == app_obj.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập hồ sơ này.")

    if not app_obj.current_assessment_run_id:
        return {
            "application_id": str(application_id),
            "status": "not_assessed",
            "headline": "Hồ sơ chưa có kết quả đánh giá AI",
            "summary_paragraph": "Hồ sơ ứng viên đang chờ phê duyệt bản che (Sanitization) hoặc đang xếp hàng xử lý đánh giá.",
            "key_strengths": [],
            "gaps_or_questions": [],
            "recommended_interview_focus": [],
            "recommendation_label": "Chờ đánh giá",
            "cached": False,
        }

    stmt_run = (
        select(AssessmentRun)
        .options(
            selectinload(AssessmentRun.criteria),
            selectinload(AssessmentRun.evidence),
        )
        .where(AssessmentRun.id == app_obj.current_assessment_run_id)
    )
    run = (await db.execute(stmt_run)).scalar_one_or_none()
    if not run or run.status != "succeeded":
        return {
            "application_id": str(application_id),
            "status": run.status if run else "pending",
            "headline": "Tiến trình đánh giá chưa hoàn tất",
            "summary_paragraph": "AI đang phân tích đối chiếu bằng chứng với Rubric đợt tuyển dụng. Vui lòng quay lại sau ít phút.",
            "key_strengths": [],
            "gaps_or_questions": [],
            "recommended_interview_focus": [],
            "recommendation_label": "Đang xử lý",
            "cached": False,
        }

    trace = run.execution_trace or {}
    cached_data = trace.get("executive_summary")
    if not force_refresh and isinstance(cached_data, dict) and cached_data.get("summary_version") == SUMMARY_VERSION:
        return {**cached_data, "cached": True}

    # Load Rubric Criteria labels
    stmt_rubric = (
        select(RubricCriterion)
        .where(RubricCriterion.rubric_version_id == run.rubric_version_id)
    )
    rubric_criteria = {c.criterion_id: c.label_vi for c in (await db.execute(stmt_rubric)).scalars().all()}

    # Extract high signals
    strengths: list[str] = []
    gaps: list[str] = []
    interview_questions: list[str] = []

    for c in run.criteria:
        label = rubric_criteria.get(c.criterion_id, c.criterion_id)
        if c.status == CriterionOutcome.ASSESSED and c.score is not None:
            if c.score >= 3:
                strengths.append(f"{label} ({c.score}/4): {c.rationale[:120]}")
            elif c.score <= 1:
                gaps.append(f"{label} ({c.score}/4): Điểm thấp, bằng chứng còn hạn chế.")
        elif c.status == CriterionOutcome.INSUFFICIENT_EVIDENCE:
            gaps.append(f"{label}: Chưa tìm thấy bằng chứng rõ ràng trong CV.")

        if c.missing_information:
            for q in c.missing_information[:2]:
                interview_questions.append(f"[{label}] {q}")

    cand_label = app_obj.candidate.public_label
    req_title = app_obj.requisition.title
    comp_score = float(run.comparable_score) if run.comparable_score is not None else None
    score_label = f"{comp_score:.1f}/100" if comp_score is not None else "Chưa có điểm so sánh"
    score_description = f"có điểm so sánh {score_label}" if comp_score is not None else "chưa có điểm so sánh hợp lệ"
    coverage_pct = round(float(run.coverage) * 100)

    # Build concise 5-sentence narrative
    s1 = f"Ứng viên {cand_label} ứng tuyển vị trí {req_title} {score_description}, với độ phủ bằng chứng {coverage_pct}%."
    if strengths:
        s2 = f"Thế mạnh nổi bật nhất thể hiện ở các kỹ năng: {', '.join(s.split(':')[0] for s in strengths[:3])}."
    else:
        s2 = "Chưa ghi nhận tiêu chí nào đạt ngưỡng điểm mạnh trong kết quả đánh giá hiện tại."

    if gaps:
        s3 = f"Các khía cạnh cần làm rõ thêm gồm: {', '.join(g.split(':')[0] for g in gaps[:2])}."
    else:
        s3 = "Tất cả các tiêu chí trọng tâm của vị trí đều có bằng chứng đối chiếu đầy đủ."

    if interview_questions:
        s4 = f"Khuyến nghị phỏng vấn: Tập trung kiểm chứng chuyên sâu về {interview_questions[0]}."
    else:
        s4 = "Khuyến nghị phỏng vấn: Đào sâu trải nghiệm xử lý tình huống thực tế và quy trình phối hợp dự án."

    rec = run.recommendation
    if rec == Recommendation.CONSIDER_NEXT_ROUND:
        rec_label = "Khuyến nghị Mời Phỏng Vấn (Consider Next Round)"
        s5 = "Đánh giá chung: Hồ sơ đáp ứng tốt kỳ vọng vị trí; HR nên ưu tiên sắp xếp phỏng vấn chuyên môn sớm."
    elif rec == Recommendation.NEEDS_CLARIFICATION:
        rec_label = "Cần Làm Rõ Thông Tin (Needs Clarification)"
        s5 = "Đánh giá chung: Hồ sơ có tiềm năng nhưng thiếu bằng chứng quan trọng; nên gửi email đề nghị bổ sung thông tin hoặc phỏng vấn sàng lọc ngắn."
    else:
        rec_label = "Cần Hội Đồng Rà Soát (Review Required)"
        s5 = "Đánh giá chung: Hồ sơ ở vùng ranh giới hoặc có tín hiệu xung đột bằng chứng; HR cần xem xét kỹ trước khi ra quyết định."

    full_narrative = f"{s1} {s2} {s3} {s4} {s5}"

    summary_result = {
        "application_id": str(application_id),
        "status": "ready",
        "summary_version": SUMMARY_VERSION,
        "headline": f"{cand_label} — {rec_label} ({score_label})",
        "summary_paragraph": full_narrative,
        "key_strengths": strengths[:4],
        "gaps_or_questions": gaps[:4],
        "recommended_interview_focus": interview_questions[:3] if interview_questions else ["Phỏng vấn chuyên sâu theo câu hỏi chuẩn trong rubric"],
        "recommendation_label": rec_label,
        "comparable_score": comp_score,
        "coverage": float(run.coverage),
        "cached": False,
    }

    # Cache into execution_trace
    new_trace = dict(trace)
    new_trace["executive_summary"] = summary_result
    run.execution_trace = new_trace
    await db.commit()

    return summary_result
