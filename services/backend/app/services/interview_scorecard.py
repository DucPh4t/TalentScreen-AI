"""Human-authored interview scorecards, separate from AI CV assessments."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Application,
    InterviewDraft,
    InterviewScorecard,
    Requisition,
    RubricCriterion,
    RubricVersion,
    SanitizedVersion,
)
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import MembershipRole, RubricStatus, SanitizedVersionStatus
from app.domain.rubric_policy import scan_forbidden_criteria
from app.schemas.interview import (
    InterviewScorecardFinalizeRequest,
    InterviewScorecardResponse,
    InterviewScorecardUpsertRequest,
)
from app.services.audit import record_audit_event
from app.services.sanitizer import residual_contact_types


async def _membership_and_application(
    db: AsyncSession, application_id: uuid.UUID, ctx: AuthenticatedContext, *, require_open: bool = False
):
    from app.services.decision import _verify_application_and_membership

    application, membership = await _verify_application_and_membership(
        db, application_id, ctx, require_open=require_open
    )
    from app.api.v1.independent_review import enforce_shadow_blind
    await enforce_shadow_blind(db, application, ctx)
    return application, membership


def _scorecard_response(
    card: InterviewScorecard,
    application: Application,
    requisition: Requisition,
    interviewer_name: str | None = None,
):
    snapshot = card.source_snapshot
    stale = (
        snapshot.get("application_generation") != application.generation
        or snapshot.get("document_id") != str(application.current_document_id)
        or snapshot.get("sanitized_version_id") != str(application.current_sanitized_version_id)
        or snapshot.get("rubric_version_id") != str(requisition.current_rubric_version_id)
    )
    return InterviewScorecardResponse(
        id=card.id,
        application_id=card.application_id,
        interviewer_id=card.interviewer_id,
        interviewer_name=interviewer_name or getattr(getattr(card, "interviewer", None), "display_name", None),
        rubric_version_id=card.rubric_version_id,
        interview_draft_id=card.interview_draft_id,
        round_no=card.round_no,
        status=card.status,
        criteria=card.criteria_payload,
        row_version=card.row_version,
        snapshot_hash=card.snapshot_hash,
        is_stale=stale,
        created_at=card.created_at,
        updated_at=card.updated_at,
        finalized_at=card.finalized_at,
    )


async def list_interview_scorecards(
    db: AsyncSession, application_id: uuid.UUID, ctx: AuthenticatedContext
) -> list[InterviewScorecardResponse]:
    application, membership = await _membership_and_application(db, application_id, ctx)
    requisition = await db.get(Requisition, application.requisition_id)
    if requisition is None:
        raise HTTPException(404, "Không tìm thấy đợt tuyển dụng.")
    stmt = select(InterviewScorecard).options(selectinload(InterviewScorecard.interviewer)).where(
        InterviewScorecard.application_id == application_id
    )
    # Interviewer notes stay private to their author while the score is a
    # draft. The owner can review their own draft and other interviewers'
    # finalized scorecards, preserving independent scoring during the round.
    if membership.membership_role == MembershipRole.OWNER:
        stmt = stmt.where(or_(
            InterviewScorecard.interviewer_id == ctx.user.id,
            InterviewScorecard.status == "finalized",
        ))
    else:
        stmt = stmt.where(InterviewScorecard.interviewer_id == ctx.user.id)
    cards = (await db.execute(stmt.order_by(InterviewScorecard.round_no, InterviewScorecard.created_at))).scalars().all()
    return [_scorecard_response(card, application, requisition) for card in cards]


async def _validate_current_sources(
    db: AsyncSession,
    application: Application,
    interview_draft_id: uuid.UUID | None,
):
    requisition = await db.get(Requisition, application.requisition_id)
    if not requisition or not requisition.current_rubric_version_id:
        raise HTTPException(409, "Cần có rubric hiện hành đã duyệt trước khi ghi nhận phỏng vấn.")
    rubric = await db.get(RubricVersion, requisition.current_rubric_version_id)
    if not rubric or rubric.status != RubricStatus.APPROVED:
        raise HTTPException(409, "Rubric hiện hành chưa được duyệt.")
    sanitized = await db.get(SanitizedVersion, application.current_sanitized_version_id) if application.current_sanitized_version_id else None
    if (
        not sanitized
        or sanitized.status != SanitizedVersionStatus.APPROVED
        or sanitized.document_id != application.current_document_id
        or residual_contact_types(sanitized.canonical_text)
    ):
        raise HTTPException(409, "Cần CV hiện hành đã khử định danh và được HR duyệt trước khi ghi nhận phỏng vấn.")

    interview_draft = None
    if interview_draft_id:
        interview_draft = await db.get(InterviewDraft, interview_draft_id)
        if not interview_draft or interview_draft.application_id != application.id:
            raise HTTPException(404, "Không tìm thấy hướng dẫn phỏng vấn của hồ sơ này.")
        if interview_draft.status != "succeeded":
            raise HTTPException(409, "Chỉ có thể gắn scorecard với hướng dẫn phỏng vấn đã tạo thành công.")
        source = interview_draft.source_snapshot
        if (
            source.get("application_generation") != application.generation
            or source.get("document_id") != str(application.current_document_id)
            or source.get("sanitized_version_id") != str(application.current_sanitized_version_id)
            or source.get("rubric_version_id") != str(rubric.id)
        ):
            raise HTTPException(409, "Hướng dẫn phỏng vấn đã cũ; hãy tạo lại theo hồ sơ và rubric hiện hành.")
    criteria = (await db.execute(
        select(RubricCriterion)
        .where(RubricCriterion.rubric_version_id == rubric.id)
        .order_by(RubricCriterion.criterion_id)
    )).scalars().all()
    return requisition, rubric, sanitized, criteria, interview_draft


def _validate_entries(entries, criterion_ids: set[str], *, require_complete: bool) -> list[dict]:
    if len({entry.criterion_id for entry in entries}) != len(entries) or {entry.criterion_id for entry in entries} != criterion_ids:
        raise HTTPException(422, "Scorecard phải có đúng một dòng cho mỗi tiêu chí trong rubric hiện hành.")
    result = []
    for entry in entries:
        outcome = entry.outcome
        score = entry.score
        answer = entry.answer_summary.strip()
        note = entry.interviewer_note.strip()
        if outcome == "assessed":
            if type(score) is not int or not 0 <= score <= 4:
                raise HTTPException(422, f"Tiêu chí {entry.criterion_id}: chọn điểm 0–4 hoặc đánh dấu chưa quan sát.")
            if len(answer) < 20:
                raise HTTPException(422, f"Tiêu chí {entry.criterion_id}: cần ghi tóm tắt câu trả lời làm căn cứ cho điểm.")
        elif score is not None:
            raise HTTPException(422, f"Tiêu chí {entry.criterion_id}: chưa có bằng chứng phù hợp thì điểm phải để trống.")
        if require_complete and outcome == "conflicting_evidence" and len(answer) < 20:
            raise HTTPException(422, f"Tiêu chí {entry.criterion_id}: ghi lại điểm mâu thuẫn cần HR rà soát.")
        for field, content in (("answer", answer), ("note", note)):
            forbidden = scan_forbidden_criteria(content) if content else None
            if forbidden:
                raise HTTPException(422, f"Không ghi thuộc tính cá nhân nhạy cảm vào {field} phỏng vấn ({entry.criterion_id}).")
        result.append({
            "criterion_id": entry.criterion_id,
            "outcome": outcome,
            "score": score,
            "answer_summary": answer,
            "interviewer_note": note,
        })
    return result


async def upsert_interview_scorecard(
    db: AsyncSession,
    application_id: uuid.UUID,
    payload: InterviewScorecardUpsertRequest,
    ctx: AuthenticatedContext,
) -> InterviewScorecardResponse:
    application, _ = await _membership_and_application(db, application_id, ctx, require_open=True)
    await db.execute(select(Application.id).where(Application.id == application_id).with_for_update())
    await db.refresh(application)
    requisition, rubric, sanitized, criteria, interview_draft = await _validate_current_sources(
        db, application, payload.interview_draft_id
    )
    if len(criteria) < 2:
        raise HTTPException(409, "Rubric cần ít nhất hai tiêu chí để mở scorecard.")
    entries = _validate_entries(payload.criteria, {criterion.criterion_id for criterion in criteria}, require_complete=False)
    stmt = select(InterviewScorecard).where(
        InterviewScorecard.application_id == application_id,
        InterviewScorecard.interviewer_id == ctx.user.id,
        InterviewScorecard.rubric_version_id == rubric.id,
        InterviewScorecard.round_no == payload.round_no,
    ).with_for_update()
    card = (await db.execute(stmt)).scalar_one_or_none()
    if card is None and payload.expected_version != 0:
        raise HTTPException(409, "Scorecard chưa tồn tại hoặc phiên bản đã thay đổi. Tải lại để tiếp tục.")
    if card is not None:
        if card.status != "draft":
            raise HTTPException(409, "Scorecard đã khóa sau khi nộp.")
        if payload.expected_version != card.row_version:
            raise HTTPException(409, "SCORECARD_VERSION_CONFLICT: Bản nháp đã đổi ở cửa sổ khác. Tải lại trước khi lưu.")
        old_snapshot = card.source_snapshot
        if (
            old_snapshot.get("application_generation") != application.generation
            or old_snapshot.get("document_id") != str(application.current_document_id)
            or old_snapshot.get("sanitized_version_id") != str(application.current_sanitized_version_id)
        ):
            raise HTTPException(409, "SCORECARD_STALE: CV đã đổi. Giữ phiếu cũ và mở lượt phỏng vấn mới.")

    snapshot = {
        "application_generation": application.generation,
        "document_id": str(application.current_document_id),
        "sanitized_version_id": str(sanitized.id),
        "rubric_version_id": str(rubric.id),
        "interview_draft_id": str(interview_draft.id) if interview_draft else None,
        "round_no": payload.round_no,
        "interviewer_id": str(ctx.user.id),
    }
    snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc)
    before = card.row_version if card else 0
    if card is None:
        card = InterviewScorecard(
            application_id=application_id,
            interviewer_id=ctx.user.id,
            rubric_version_id=rubric.id,
            interview_draft_id=interview_draft.id if interview_draft else None,
            round_no=payload.round_no,
            status="draft",
            criteria_payload=entries,
            source_snapshot=snapshot,
            snapshot_hash=snapshot_hash,
            row_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(card)
    else:
        card.criteria_payload = entries
        card.interview_draft_id = interview_draft.id if interview_draft else None
        card.source_snapshot = snapshot
        card.snapshot_hash = snapshot_hash
        card.row_version += 1
        card.updated_at = now
    await db.flush()
    await record_audit_event(
        db, actor_id=ctx.user.id, action="interview_scorecard.saved",
        entity_type="interview_scorecard", entity_id=card.id,
        requisition_id=application.requisition_id,
        before_version=before, after_version=card.row_version,
        safe_metadata={"round_no": card.round_no, "criteria_count": len(entries),
                       "scored_count": sum(entry["outcome"] == "assessed" for entry in entries)},
    )
    return _scorecard_response(card, application, requisition, ctx.user.display_name)


async def finalize_interview_scorecard(
    db: AsyncSession,
    scorecard_id: uuid.UUID,
    payload: InterviewScorecardFinalizeRequest,
    ctx: AuthenticatedContext,
) -> InterviewScorecardResponse:
    card = (await db.execute(
        select(InterviewScorecard).where(InterviewScorecard.id == scorecard_id).with_for_update()
    )).scalar_one_or_none()
    if card is None:
        raise HTTPException(404, "Không tìm thấy phiếu phỏng vấn.")
    if card.interviewer_id != ctx.user.id:
        raise HTTPException(403, "Chỉ người phỏng vấn tạo phiếu mới được nộp và khóa phiếu.")
    application, _ = await _membership_and_application(db, card.application_id, ctx, require_open=True)
    requisition, rubric, _, criteria, _ = await _validate_current_sources(db, application, card.interview_draft_id)
    if card.status != "draft":
        raise HTTPException(409, "Phiếu phỏng vấn đã được nộp và khóa.")
    if payload.expected_version != card.row_version:
        raise HTTPException(409, "SCORECARD_VERSION_CONFLICT: Phiếu đã đổi. Tải lại trước khi nộp.")
    if rubric.id != card.rubric_version_id:
        raise HTTPException(409, "RUBRIC_CHANGED: Rubric đã đổi; tạo phiếu mới theo rubric hiện hành.")
    if _scorecard_response(card, application, requisition).is_stale:
        raise HTTPException(409, "SCORECARD_STALE: CV hoặc rubric đã đổi; không thể nộp phiếu cũ.")
    from app.schemas.interview import InterviewScorecardCriterionSchema
    complete_entries = [InterviewScorecardCriterionSchema.model_validate(entry) for entry in card.criteria_payload]
    _validate_entries(complete_entries, {criterion.criterion_id for criterion in criteria}, require_complete=True)
    if not any(entry.outcome == "assessed" for entry in complete_entries):
        raise HTTPException(422, "Cần đánh giá ít nhất một tiêu chí trước khi nộp phiếu.")
    before = card.row_version
    card.status = "finalized"
    card.finalized_at = datetime.now(timezone.utc)
    card.updated_at = card.finalized_at
    card.row_version += 1
    await db.flush()
    await record_audit_event(
        db, actor_id=ctx.user.id, action="interview_scorecard.finalized",
        entity_type="interview_scorecard", entity_id=card.id,
        requisition_id=application.requisition_id,
        before_version=before, after_version=card.row_version,
        safe_metadata={"round_no": card.round_no, "criteria_count": len(complete_entries),
                       "scored_count": sum(entry.outcome == "assessed" for entry in complete_entries)},
    )
    return _scorecard_response(card, application, requisition, ctx.user.display_name)
