"""Independent human labels collected before AI reveal during shadow pilots."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    Application, Candidate, Document, IndependentReview, IndependentReviewDraft, Requisition,
    RequisitionMembership, RubricCriterion, RubricVersion, SanitizedVersion,
)
from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.domain.enums import MembershipRole, RubricStatus, SanitizedVersionStatus
from app.services.audit import record_audit_event
from app.services.sanitizer import residual_contact_types

router = APIRouter(tags=["Independent human review"])


class HumanLabelRequest(BaseModel):
    review_kind: Literal["hr", "it"]
    expected_generation: int
    expected_document_id: uuid.UUID
    expected_sanitized_version_id: uuid.UUID
    expected_rubric_version_id: uuid.UUID
    criterion_scores: dict[str, int | None]
    criterion_statuses: dict[str, Literal["assessed", "insufficient_evidence", "conflicting_evidence"]]
    criterion_quotes: dict[str, str | None]
    criterion_notes: dict[str, str]
    recommendation: Literal["consider_next_round", "needs_clarification", "review_required"]


@router.get("/requisitions/{id}/independent-reviews")
async def export_independent_reviews(
    id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Owner-only label export for offline agreement analysis; no CV text or AI score."""
    requisition = await db.get(Requisition, id)
    if requisition is None:
        raise HTTPException(404, "Không tìm thấy đợt tuyển dụng.")
    membership = (await db.execute(select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
        RequisitionMembership.membership_role == MembershipRole.OWNER,
    ))).scalar_one_or_none()
    if membership is None:
        raise HTTPException(403, "Chỉ Owner được xuất nhãn đánh giá độc lập.")
    rows = (await db.execute(select(IndependentReview, Application, Candidate.public_label)
        .join(Application, Application.id == IndependentReview.application_id)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .where(Application.requisition_id == id)
        .order_by(IndependentReview.submitted_at.asc(), IndependentReview.id.asc()))).all()
    return [{
        "id": review.id, "application_id": application.id, "public_label": label,
        "reviewer_id": review.reviewer_id, "review_kind": review.review_kind,
        "blind_enforced": review.blind_enforced,
        "application_generation": review.application_generation,
        "document_id": review.document_id, "sanitized_version_id": review.sanitized_version_id,
        "rubric_version_id": review.rubric_version_id,
        "criterion_scores": review.criterion_scores,
        "criterion_statuses": review.criterion_statuses,
        "criterion_quotes": review.criterion_quotes,
        "criterion_notes": review.criterion_notes,
        "recommendation": review.recommendation,
        "snapshot_hash": review.snapshot_hash, "submitted_at": review.submitted_at,
        "current_snapshot": bool(application.status == "active"
                                 and application.generation == review.application_generation
                                 and application.current_document_id == review.document_id
                                 and application.current_sanitized_version_id == review.sanitized_version_id
                                 and requisition.current_rubric_version_id == review.rubric_version_id),
    } for review, application, label in rows]


async def _reviewer_application(db: AsyncSession, app_id: uuid.UUID, ctx: AuthenticatedContext):
    application = await db.get(Application, app_id)
    if application is None or application.status != "active":
        raise HTTPException(404, "Không tìm thấy hồ sơ.")
    membership = (await db.execute(select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == application.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    ))).scalar_one_or_none()
    if membership is None or membership.membership_role != MembershipRole.REVIEWER:
        raise HTTPException(403, "Chỉ reviewer được giao cho đợt tuyển dụng mới chấm độc lập.")
    requisition = await db.get(Requisition, application.requisition_id)
    version = await db.get(SanitizedVersion, application.current_sanitized_version_id) if application.current_sanitized_version_id else None
    rubric = await db.get(RubricVersion, requisition.current_rubric_version_id) if requisition.current_rubric_version_id else None
    if (version is None or version.status != SanitizedVersionStatus.APPROVED or
        version.document_id != application.current_document_id or
        rubric is None or rubric.status != RubricStatus.APPROVED):
        raise HTTPException(409, "Cần CV đã che và rubric hiện hành được duyệt trước khi chấm độc lập.")
    if residual_contact_types(version.canonical_text):
        raise HTTPException(409, "CV đã che còn dấu hiệu thông tin liên hệ; cần rà soát lại trước khi chấm.")
    return application, requisition, version, rubric


@router.get("/requisitions/{id}/independent-reviews/mine")
async def my_review_worklist(
    id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context),
):
    membership = (await db.execute(select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
        RequisitionMembership.membership_role == MembershipRole.REVIEWER,
    ))).scalar_one_or_none()
    if membership is None:
        raise HTTPException(403, "Chỉ reviewer của đợt tuyển dụng được xem danh sách chấm độc lập.")
    rows = (await db.execute(select(Application, Candidate.public_label, SanitizedVersion)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .outerjoin(SanitizedVersion, SanitizedVersion.id == Application.current_sanitized_version_id)
        .where(Application.requisition_id == id, Application.status == "active")
        .order_by(Application.received_at.asc(), Application.id.asc()))).all()
    submitted = (await db.execute(select(IndependentReview).where(
        IndependentReview.application_id.in_([app.id for app, _, _ in rows]),
        IndependentReview.reviewer_id == ctx.user.id,
    ))).scalars().all() if rows else []
    requisition = await db.get(Requisition, id)
    rubric = await db.get(RubricVersion, requisition.current_rubric_version_id) if requisition.current_rubric_version_id else None
    submitted_keys = {(review.application_id, review.application_generation, review.rubric_version_id) for review in submitted}
    return [{"application_id": app.id, "public_label": label, "received_at": app.received_at,
             "ready": bool(version and version.status == SanitizedVersionStatus.APPROVED
                           and version.document_id == app.current_document_id
                           and not residual_contact_types(version.canonical_text)
                           and rubric and rubric.status == RubricStatus.APPROVED),
             "submitted": (app.id, app.generation, requisition.current_rubric_version_id) in submitted_keys} for app, label, version in rows]


@router.get("/applications/{id}/independent-review/context")
async def independent_review_context(
    id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context),
):
    application, requisition, version, rubric = await _reviewer_application(db, id, ctx)
    criteria = (await db.execute(select(RubricCriterion).where(
        RubricCriterion.rubric_version_id == rubric.id
    ).order_by(RubricCriterion.criterion_id))).scalars().all()
    submitted = (await db.execute(select(IndependentReview.id).where(
        IndependentReview.application_id == id,
        IndependentReview.reviewer_id == ctx.user.id,
        IndependentReview.application_generation == application.generation,
        IndependentReview.rubric_version_id == rubric.id,
    ))).scalar_one_or_none()
    label = (await db.execute(select(Candidate.public_label).where(Candidate.id == application.candidate_id))).scalar_one()
    return {
        "application_id": id, "public_label": label, "requisition_id": requisition.id,
        "application_generation": application.generation,
        "document_id": application.current_document_id,
        "sanitized_version_id": version.id,
        "rubric_version_id": rubric.id,
        "sanitized_text": version.canonical_text,
        "criteria": [{"id": c.criterion_id, "label": c.label_vi,
                      "description": c.description_vi, "anchors": c.anchors} for c in criteria],
        "already_submitted": submitted is not None,
        "enforced_blind": get_settings().APP_ENV == "pilot" and get_settings().PILOT_STAGE == "shadow",
    }


@router.post("/applications/{id}/independent-review", status_code=201)
async def submit_independent_review(
    id: uuid.UUID, payload: HumanLabelRequest,
    db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context),
):
    # Lock before reading snapshot pointers and checking duplicate submissions.
    await db.execute(select(Application.id).where(Application.id == id).with_for_update())
    application, requisition, version, rubric = await _reviewer_application(db, id, ctx)
    await db.refresh(application)
    await db.execute(select(Requisition.id).where(Requisition.id == requisition.id).with_for_update())
    await db.refresh(requisition)
    if (version.id != application.current_sanitized_version_id or
        rubric.id != requisition.current_rubric_version_id):
        raise HTTPException(409, "REVIEW_SNAPSHOT_STALE: CV hoặc rubric đã thay đổi; tải lại trước khi nộp nhãn.")
    if (payload.expected_generation != application.generation or
        payload.expected_document_id != application.current_document_id or
        payload.expected_sanitized_version_id != version.id or
        payload.expected_rubric_version_id != rubric.id):
        raise HTTPException(409, "REVIEW_SNAPSHOT_STALE: CV hoặc rubric đã thay đổi; tải lại trước khi nộp nhãn.")
    criteria = (await db.execute(select(RubricCriterion.criterion_id).where(
        RubricCriterion.rubric_version_id == rubric.id
    ))).scalars().all()
    expected = set(criteria)
    if any(set(values) != expected for values in (
        payload.criterion_scores, payload.criterion_statuses, payload.criterion_quotes, payload.criterion_notes
    )):
        raise HTTPException(422, "Nhãn phải bao gồm đúng mọi tiêu chí của rubric hiện hành.")
    for criterion_id in expected:
        score = payload.criterion_scores[criterion_id]
        outcome = payload.criterion_statuses[criterion_id]
        quote = (payload.criterion_quotes[criterion_id] or "").strip()
        note = payload.criterion_notes[criterion_id].strip()
        if outcome == "assessed" and (type(score) is not int or not 0 <= score <= 4):
            raise HTTPException(422, f"Tiêu chí {criterion_id} cần điểm 0–4 khi có bằng chứng.")
        if outcome != "assessed" and score is not None:
            raise HTTPException(422, f"Tiêu chí {criterion_id} chưa đánh giá được thì điểm phải là null.")
        if outcome != "insufficient_evidence" and (len(quote) < 10 or quote not in version.canonical_text):
            raise HTTPException(422, f"Trích dẫn của {criterion_id} phải có ít nhất 10 ký tự và khớp nguyên văn CV đã che.")
        if outcome == "insufficient_evidence" and quote:
            raise HTTPException(422, f"Không gán trích dẫn cho {criterion_id} khi chưa có bằng chứng.")
        if len(note) < 10:
            raise HTTPException(422, f"Cần ghi căn cứ hoặc thông tin còn thiếu cho {criterion_id}.")
    existing = (await db.execute(select(IndependentReview.id).where(
        IndependentReview.application_id == id,
        IndependentReview.reviewer_id == ctx.user.id,
        IndependentReview.application_generation == application.generation,
        IndependentReview.rubric_version_id == rubric.id,
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Nhãn độc lập đã nộp và được khóa; không thể ghi đè.")
    document = await db.get(Document, application.current_document_id)
    snapshot = {"generation": application.generation, "document_sha256": document.sha256,
                "sanitized_sha256": version.sha256, "rubric_hash": rubric.content_hash}
    review = IndependentReview(
        id=uuid.uuid4(), application_id=id, reviewer_id=ctx.user.id,
        review_kind=payload.review_kind, application_generation=application.generation,
        blind_enforced=get_settings().APP_ENV == "pilot" and get_settings().PILOT_STAGE == "shadow",
        document_id=document.id, sanitized_version_id=version.id, rubric_version_id=rubric.id,
        criterion_scores=payload.criterion_scores,
        criterion_statuses=payload.criterion_statuses,
        criterion_quotes={key: value.strip() if value else None for key, value in payload.criterion_quotes.items()},
        criterion_notes={key: value.strip() for key, value in payload.criterion_notes.items()},
        recommendation=payload.recommendation,
        snapshot_hash=hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest(),
        created_at=datetime.now(timezone.utc), submitted_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.flush()
    await record_audit_event(db, actor_id=ctx.user.id, action="independent_review.submitted",
                             entity_type="independent_review", entity_id=review.id,
                             requisition_id=requisition.id,
                             safe_metadata={"application_id": str(id), "review_kind": review.review_kind,
                                            "rubric_version_id": str(rubric.id), "snapshot_hash": review.snapshot_hash})
    await db.execute(delete(IndependentReviewDraft).where(IndependentReviewDraft.application_id == id, IndependentReviewDraft.reviewer_id == ctx.user.id))
    await db.commit()
    return {"id": review.id, "submitted_at": review.submitted_at, "snapshot_hash": review.snapshot_hash}


async def enforce_shadow_blind(db: AsyncSession, application: Application, ctx: AuthenticatedContext) -> None:
    """Prevent a shadow reviewer from viewing AI-derived output before own locked label."""
    settings = get_settings()
    if settings.APP_ENV != "pilot" or settings.PILOT_STAGE != "shadow":
        return
    membership = (await db.execute(select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == application.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    ))).scalar_one_or_none()
    if membership is None or membership.membership_role != MembershipRole.REVIEWER:
        return
    review_id = (await db.execute(select(IndependentReview.id).where(
        IndependentReview.application_id == application.id,
        IndependentReview.reviewer_id == ctx.user.id,
        IndependentReview.application_generation == application.generation,
        IndependentReview.document_id == application.current_document_id,
        IndependentReview.sanitized_version_id == application.current_sanitized_version_id,
        IndependentReview.rubric_version_id == select(Requisition.current_rubric_version_id).where(
            Requisition.id == application.requisition_id
        ).scalar_subquery(),
    ))).scalar_one_or_none()
    if review_id is None:
        raise HTTPException(403, "BLIND_REVIEW_PENDING: Nộp nhãn độc lập trước khi xem đánh giá AI.")


class DraftRequest(HumanLabelRequest):
    model_config = ConfigDict(extra="forbid")
    expected_draft_version: int = Field(ge=0)

async def _draft_source(db, id, ctx):
    application, requisition, version, rubric = await _reviewer_application(db, id, ctx)
    locked = (await db.execute(select(IndependentReview.id).where(IndependentReview.application_id == id,
        IndependentReview.reviewer_id == ctx.user.id, IndependentReview.application_generation == application.generation,
        IndependentReview.rubric_version_id == rubric.id))).scalar_one_or_none()
    if locked: raise HTTPException(409, "Nhãn đã nộp và khóa; không sửa bản nháp.")
    return application, requisition, version, rubric

@router.get("/applications/{id}/independent-review/draft")
async def get_draft(id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    application, _, version, rubric = await _draft_source(db, id, ctx)
    draft = (await db.execute(select(IndependentReviewDraft).where(IndependentReviewDraft.application_id == id,
        IndependentReviewDraft.reviewer_id == ctx.user.id))).scalar_one_or_none()
    if not draft: return None
    if draft.expires_at <= datetime.now(timezone.utc) or draft.application_generation != application.generation or draft.sanitized_version_id != version.id or draft.rubric_version_id != rubric.id:
        await db.delete(draft); return None
    return {"version": draft.version, "payload": draft.payload, "expires_at": draft.expires_at}

@router.put("/applications/{id}/independent-review/draft")
async def save_draft(id: uuid.UUID, payload: DraftRequest, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    await db.execute(select(Application.id).where(Application.id == id).with_for_update())
    application, requisition, version, rubric = await _draft_source(db, id, ctx)
    if (payload.expected_generation, payload.expected_document_id, payload.expected_sanitized_version_id, payload.expected_rubric_version_id) != (application.generation, application.current_document_id, version.id, rubric.id):
        raise HTTPException(409, "Nguồn đã thay đổi; tải lại trước khi lưu nhãn.")
    expected_ids = set((await db.execute(select(RubricCriterion.criterion_id).where(RubricCriterion.rubric_version_id == rubric.id))).scalars())
    for values in (payload.criterion_scores, payload.criterion_statuses, payload.criterion_quotes, payload.criterion_notes):
        if set(values) != expected_ids: raise HTTPException(422, "Bản nháp phải dùng đúng tiêu chí hiện hành.")
    if any(value is not None and not 0 <= value <= 4 for value in payload.criterion_scores.values()): raise HTTPException(422, "Điểm phải trong 0–4 hoặc trống.")
    if any(len(value or "") > 1200 for value in payload.criterion_quotes.values()) or any(len(value) > 2000 for value in payload.criterion_notes.values()):
        raise HTTPException(422, "Nội dung bản nháp vượt giới hạn.")
    draft = (await db.execute(select(IndependentReviewDraft).where(IndependentReviewDraft.application_id == id,
        IndependentReviewDraft.reviewer_id == ctx.user.id).with_for_update())).scalar_one_or_none()
    if draft and (draft.application_generation != application.generation or draft.sanitized_version_id != version.id or draft.rubric_version_id != rubric.id or draft.expires_at <= datetime.now(timezone.utc)):
        await db.delete(draft); await db.flush(); draft = None
    if payload.expected_draft_version != (draft.version if draft else 0):
        raise HTTPException(409, "Bản nháp đã thay đổi ở phiên khác. Tải lại để tránh ghi đè.")
    data = payload.model_dump(mode="json", exclude={"expected_draft_version"})
    if draft: draft.payload = data; draft.version += 1; draft.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    else:
        draft = IndependentReviewDraft(application_id=id, reviewer_id=ctx.user.id, sanitized_version_id=version.id,
            rubric_version_id=rubric.id, application_generation=application.generation, version=1, payload=data,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
        db.add(draft)
    await db.flush()
    await record_audit_event(db, actor_id=ctx.user.id, action="independent_review.draft_saved", entity_type="application", entity_id=id,
        requisition_id=requisition.id, safe_metadata={"draft_version": draft.version})
    return {"version": draft.version, "expires_at": draft.expires_at}
