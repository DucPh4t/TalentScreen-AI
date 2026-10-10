"""Human screening and interview preparation; never an automatic hiring engine."""
from datetime import datetime, timezone
import hashlib
import json
import uuid
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.db.models import (Application, AssessmentRun, CriterionAssessment, Decision, HRRevision, InterviewRound, InterviewScorecard,
    RequisitionMembership, ReviewProgress, RubricCriterion, RubricVersion, SanitizedVersion, User)
from app.domain.enums import DecisionBasis, DecisionOutcome, RubricStatus, SanitizedVersionStatus
from app.domain.rubric_policy import scan_forbidden_criteria
from app.schemas.decision import AttestationAssessmentReviewRequest, DecisionCreateRequest
from app.services.audit import record_audit_event
from app.services.decision import (_verify_application_and_membership, create_review_attestation, create_decision,
    clarification_disposition_error, is_matching_information_request, resolve_required_criterion_ids)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

async def access(db, application_id, ctx, *, owner=False, write=False):
    application, membership = await _verify_application_and_membership(db, application_id, ctx, require_owner=owner, require_open=write)
    if application.status != 'active':
        raise HTTPException(404, 'Hồ sơ không còn hoạt động.')
    from app.api.v1.independent_review import enforce_shadow_blind
    await enforce_shadow_blind(db, application, ctx)
    if write:
        # Same Requisition -> Application order used by rubric approval.
        from app.db.models import Requisition
        await db.execute(select(Requisition.id).where(Requisition.id == application.requisition_id).with_for_update())
        await db.execute(select(Application.id).where(Application.id == application_id).with_for_update())
        await db.refresh(application)
        await db.refresh(application.requisition)
    return application, membership

def interview_source_hash(application, requisition=None):
    req = requisition or application.requisition
    return digest({'generation': application.generation, 'document': str(application.current_document_id),
        'sanitized': str(application.current_sanitized_version_id), 'rubric': str(req.current_rubric_version_id), 'jd': str(req.current_jd_version_id)})

async def source(db, application, *, assessment=False):
    req = application.requisition
    snapshot = {'generation': application.generation, 'document': str(application.current_document_id),
        'sanitized': str(application.current_sanitized_version_id), 'rubric': str(req.current_rubric_version_id), 'jd': str(req.current_jd_version_id)}
    if assessment:
        latest = (await db.execute(select(HRRevision.id).where(HRRevision.application_id == application.id,
            HRRevision.status == 'finalized', HRRevision.document_id == application.current_document_id,
            HRRevision.sanitized_version_id == application.current_sanitized_version_id,
            HRRevision.application_generation == application.generation,
            HRRevision.rubric_version_id == req.current_rubric_version_id).order_by(HRRevision.revision_no.desc()).limit(1))).scalar_one_or_none()
        snapshot.update(run=str(application.current_assessment_run_id), hr_revision=str(latest))
    ids = list((await db.execute(select(RubricCriterion.criterion_id).where(RubricCriterion.rubric_version_id == req.current_rubric_version_id).order_by(RubricCriterion.criterion_id))).scalars())
    return digest(snapshot), ids

async def current_sources(db, application):
    req = application.requisition
    rubric = await db.get(RubricVersion, req.current_rubric_version_id) if req.current_rubric_version_id else None
    version = await db.get(SanitizedVersion, application.current_sanitized_version_id) if application.current_sanitized_version_id else None
    if not rubric or rubric.status != RubricStatus.APPROVED or rubric.jd_version_id != req.current_jd_version_id:
        raise HTTPException(409, 'RUBRIC_STALE: Cần tiêu chí hiện hành đã duyệt theo JD.')
    if not version or version.status != SanitizedVersionStatus.APPROVED or version.document_id != application.current_document_id:
        raise HTTPException(409, 'SOURCE_STALE: Cần bản CV hiện hành đã che và được duyệt.')

async def review_progress(db, application_id, ctx, payload=None):
    application, _ = await access(db, application_id, ctx, owner=True, write=payload is not None)
    source_hash, ids = await source(db, application, assessment=True)
    row = (await db.execute(select(ReviewProgress).where(ReviewProgress.application_id == application_id, ReviewProgress.user_id == ctx.user.id).with_for_update())).scalar_one_or_none()
    if payload:
        if payload.source_hash != source_hash or payload.expected_version != (row.row_version if row else 0):
            raise HTTPException(409, 'REVIEW_PROGRESS_CONFLICT: Nguồn hoặc tiến độ đã đổi; tải lại trước khi lưu.')
        if len(payload.reviewed_criterion_ids) != len(set(payload.reviewed_criterion_ids)) or not set(payload.reviewed_criterion_ids).issubset(ids):
            raise HTTPException(422, 'INVALID_CRITERION: Tiêu chí rà soát không thuộc rubric hiện hành.')
        if not row:
            row = ReviewProgress(application_id=application_id, user_id=ctx.user.id, source_hash=source_hash, reviewed_criterion_ids=payload.reviewed_criterion_ids)
            db.add(row)
        else:
            row.source_hash = source_hash; row.reviewed_criterion_ids = payload.reviewed_criterion_ids; row.row_version += 1
        await db.flush()
        await record_audit_event(db, actor_id=ctx.user.id, action='review_progress.saved', entity_type='review_progress', entity_id=row.id,
            requisition_id=application.requisition_id, safe_metadata={'reviewed_count': len(payload.reviewed_criterion_ids)})
    return {'source_hash': source_hash, 'row_version': row.row_version if row else 0,
        'reviewed_criterion_ids': row.reviewed_criterion_ids if row and row.source_hash == source_hash else []}

async def screening_decision(db, application_id, ctx, payload):
    application, _ = await access(db, application_id, ctx, owner=True, write=True)
    await current_sources(db, application)
    req = application.requisition
    if payload.expected_previous_decision_id != application.current_decision_id or payload.expected_rubric_version_id != req.current_rubric_version_id:
        raise HTTPException(409, 'DECISION_CONFLICT: Quyết định hoặc tiêu chí đã đổi; tải lại hồ sơ.')
    effective = payload.effective_result
    model = AssessmentRun if effective.kind == 'assessment_run' else HRRevision
    result = await db.get(model, effective.id)
    if not result or result.application_id != application_id or result.application_generation != application.generation or result.rubric_version_id != req.current_rubric_version_id:
        raise HTTPException(409, 'RESULT_STALE: Căn cứ đánh giá không còn hiện hành.')
    if effective.kind == 'assessment_run' and result.id != application.current_assessment_run_id:
        raise HTTPException(409, 'RESULT_STALE: Chọn kết quả AI hiện hành.')
    attestation = await create_review_attestation(db, application_id, AttestationAssessmentReviewRequest(
        effective_result=effective, reviewed_criterion_ids=payload.reviewed_criterion_ids, acknowledged=True), ctx)
    recommendation = result.recommendation.value if hasattr(result.recommendation, "value") else result.recommendation
    has_clarification_gap = False
    has_conflicting_evidence = False
    if recommendation == "needs_clarification":
        if effective.kind == "assessment_run":
            criterion_rows = (await db.execute(
                select(CriterionAssessment).where(CriterionAssessment.run_id == result.id)
            )).scalars().all()
            criterion_statuses = {
                row.criterion_id: row.status.value if hasattr(row.status, "value") else str(row.status)
                for row in criterion_rows
            }
        else:
            criterion_items = ((result.criteria_payload or {}).get("criteria") or [])
            criterion_statuses = {
                item.get("criterion_id"): item.get("status")
                for item in criterion_items
                if item.get("criterion_id") and item.get("status")
            }
        policy_rubric = await db.get(RubricVersion, result.rubric_version_id)
        policy = (policy_rubric.threshold_config or {}) if policy_rubric else {}
        rubric_ids = set((await db.execute(
            select(RubricCriterion.criterion_id).where(
                RubricCriterion.rubric_version_id == result.rubric_version_id
            )
        )).scalars().all()) if result.rubric_version_id else set()
        required_ids = resolve_required_criterion_ids(policy, rubric_ids)
        previous = await db.get(Decision, application.current_decision_id) if (
            payload.outcome == DecisionOutcome.NOT_ADVANCE and application.current_decision_id
        ) else None
        previous_outcome = (
            DecisionOutcome.REQUEST_INFORMATION.value
            if is_matching_information_request(previous, application_id, attestation)
            else None
        )
        disposition_error = clarification_disposition_error(
            recommendation,
            payload.outcome.value if hasattr(payload.outcome, "value") else str(payload.outcome),
            criterion_statuses,
            required_ids,
            previous_outcome,
            payload.clarification_resolution,
        )
        if disposition_error == "MUST_HAVE_INFORMATION_REQUEST_REQUIRED":
            raise HTTPException(422, "MUST_HAVE_CLARIFICATION_REQUIRED: HR cần ghi nhận yêu cầu bổ sung trước khi cân nhắc từ chối.")
        if disposition_error == "CLARIFICATION_RESOLUTION_REQUIRED":
            raise HTTPException(422, "CLARIFICATION_RESOLUTION_REQUIRED: Ghi nhận xác nhận của ứng viên hoặc việc không phản hồi sau liên hệ.")
        if disposition_error == "NICE_TO_HAVE_INDEPENDENT_BASIS_REQUIRED":
            raise HTTPException(422, "NICE_TO_HAVE_INDEPENDENT_BASIS_REQUIRED: HR cần nêu căn cứ độc lập dựa trên evidence khác; thiếu nice-to-have không phải lý do từ chối.")
        has_clarification_gap = disposition_error is None and any(
            value == "insufficient_evidence" for value in criterion_statuses.values()
        )
        has_conflicting_evidence = any(value == "conflicting_evidence" for value in criterion_statuses.values())
    diverged = ((recommendation == "consider_next_round" and payload.outcome == DecisionOutcome.NOT_ADVANCE)
        or (recommendation == "review_required" and payload.outcome == DecisionOutcome.ADVANCE)
        or (recommendation == "needs_clarification" and (
            payload.outcome == DecisionOutcome.ADVANCE
            or (payload.outcome == DecisionOutcome.NOT_ADVANCE and (has_clarification_gap or has_conflicting_evidence))
        )))
    return await create_decision(db, application_id, DecisionCreateRequest(decision_basis=DecisionBasis.ASSESSMENT_REVIEW,
        outcome=payload.outcome, reason=payload.reason.strip(), override_reason=payload.reason.strip() if diverged else None,
        clarification_resolution=payload.clarification_resolution, attestation_id=attestation.id,
        expected_previous_decision_id=payload.expected_previous_decision_id, expected_rubric_version_id=payload.expected_rubric_version_id), ctx)

async def round_cards(db, application_id, round_no):
    return list((await db.execute(select(InterviewScorecard).options(selectinload(InterviewScorecard.interviewer)).where(InterviewScorecard.application_id == application_id,
        InterviewScorecard.round_no == round_no))).scalars())

async def interview_round(db, application_id, round_no, ctx, payload=None):
    if not 1 <= round_no <= 10: raise HTTPException(422, 'Lượt phỏng vấn phải từ 1 đến 10.')
    application, membership = await access(db, application_id, ctx, owner=payload is not None, write=payload is not None)
    source_hash, ids = await source(db, application)
    row = (await db.execute(select(InterviewRound).where(InterviewRound.application_id == application_id, InterviewRound.round_no == round_no).with_for_update())).scalar_one_or_none()
    cards = await round_cards(db, application_id, round_no)
    if payload:
        await current_sources(db, application)
        if payload.source_hash != source_hash or payload.expected_version != (row.row_version if row else 0):
            raise HTTPException(409, 'ROUND_VERSION_CONFLICT: Kế hoạch hoặc nguồn đã đổi; tải lại trước khi lưu.')
        if row and row.source_hash != source_hash and cards:
            raise HTTPException(409, 'ROUND_STALE: Giữ lượt cũ để kiểm toán và mở lượt mới theo nguồn hiện hành.')
        if len(set(payload.focus_criterion_ids)) != len(payload.focus_criterion_ids) or not set(payload.focus_criterion_ids).issubset(ids):
            raise HTTPException(422, 'INVALID_CRITERION: Tiêu chí trọng tâm không thuộc vị trí.')
        members = set((await db.execute(select(RequisitionMembership.user_id).where(RequisitionMembership.requisition_id == application.requisition_id, RequisitionMembership.active.is_(True)))).scalars())
        if len(set(payload.interviewer_ids)) != len(payload.interviewer_ids) or not set(payload.interviewer_ids).issubset(members):
            raise HTTPException(422, 'INVALID_INTERVIEWER: Người phỏng vấn cần là thành viên đang hoạt động của đợt.')
        if scan_forbidden_criteria(payload.label): raise HTTPException(422, 'Nhãn buổi phỏng vấn phải theo năng lực.')
        preparation = payload.model_dump(mode='json', exclude={'expected_version', 'source_hash'})
        if row and cards and any(preparation.get(key) != row.preparation.get(key) for key in ('focus_criterion_ids', 'interviewer_ids')):
            raise HTTPException(409, 'ROUND_STARTED: Không đổi trọng tâm hoặc hội đồng sau khi đã ghi phiếu.')
        if row:
            row.preparation = preparation; row.source_hash = source_hash; row.row_version += 1
        else:
            row = InterviewRound(application_id=application_id, round_no=round_no, source_hash=source_hash, preparation=preparation, conclusions=[])
            db.add(row)
        await db.flush()
        from app.services.email_draft import invalidate_email_drafts
        await invalidate_email_drafts(db, [application_id])
        await record_audit_event(db, actor_id=ctx.user.id, action='interview_round.saved', entity_type='interview_round', entity_id=row.id,
            requisition_id=application.requisition_id, safe_metadata={'round_no': round_no, 'row_version': row.row_version})
    users = (await db.execute(select(User.id, User.display_name).join(RequisitionMembership, RequisitionMembership.user_id == User.id)
        .where(RequisitionMembership.requisition_id == application.requisition_id, RequisitionMembership.active.is_(True)))).all()
    preparation = row.preparation if row else {'label': f'Phỏng vấn lượt {round_no}', 'focus_criterion_ids': ids,
        'interviewer_ids': [str(ctx.user.id)], 'starts_at': None, 'duration_minutes': 45, 'channel': 'online', 'meeting_location': ''}
    conclusions = row.conclusions if row else []
    assigned = str(ctx.user.id) in preparation.get('interviewer_ids', [])
    submitted = any(c.interviewer_id == ctx.user.id and c.status == 'finalized' for c in cards)
    can_view = membership.membership_role.value == 'owner' and (not assigned or submitted)
    current = conclusions[-1] if conclusions else None
    card_versions = {str(c.id): c.row_version for c in cards if c.status == 'finalized'}
    stale = bool(row and row.source_hash != source_hash)
    return {'id': row.id if row else None, 'round_no': round_no, 'row_version': row.row_version if row else 0,
        'source_hash': source_hash, 'is_stale': stale, 'preparation': preparation,
        'members': [{'id': str(u.id), 'display_name': u.display_name} for u in users],
        'conclusions': conclusions if can_view else [], 'can_view_summary': can_view,
        'conclusion_stale': bool(current and (stale or current.get('decision_id') != str(application.current_decision_id)
            or any(card_versions.get(ref['id']) != ref['row_version'] for ref in current['scorecards']))) if can_view else False}

async def conclude_round(db, application_id, round_no, ctx, payload):
    application, _ = await access(db, application_id, ctx, owner=True, write=True)
    await current_sources(db, application)
    state = await interview_round(db, application_id, round_no, ctx)
    row = await db.get(InterviewRound, state['id']) if state['id'] else None
    if not row or row.row_version != payload.expected_version or state['is_stale']:
        raise HTTPException(409, 'ROUND_STALE: Kế hoạch hoặc căn cứ đã đổi; tải lại để rà soát.')
    decision = await db.get(Decision, application.current_decision_id) if application.current_decision_id else None
    if not decision or decision.outcome != DecisionOutcome.ADVANCE or not decision_is_current(application, decision):
        raise HTTPException(409, 'ADVANCE_REQUIRED: Cần kết luận sàng lọc mời phỏng vấn hiện hành.')
    cards = await round_cards(db, application_id, round_no)
    from app.services.interview_scorecard import _scorecard_response
    complete = [c for c in cards if c.status == 'finalized' and not _scorecard_response(c, application, application.requisition).is_stale]
    assigned = set(row.preparation['interviewer_ids'])
    if not assigned.issubset({str(c.interviewer_id) for c in complete}):
        raise HTTPException(409, 'INTERVIEW_PENDING: Cần phiếu hiện hành của tất cả người được phân công.')
    complete = [c for c in complete if str(c.interviewer_id) in assigned]
    if scan_forbidden_criteria(payload.reason): raise HTTPException(422, 'Lý do kết luận phải dựa trên năng lực.')
    conclusion = {'id': str(uuid.uuid4()), 'outcome': payload.outcome, 'reason': payload.reason.strip(), 'decided_by': str(ctx.user.id),
        'created_at': datetime.now(timezone.utc).isoformat(), 'source_hash': row.source_hash, 'decision_id': str(decision.id),
        'scorecards': [{'id': str(c.id), 'row_version': c.row_version, 'snapshot_hash': c.snapshot_hash} for c in complete]}
    row.conclusions = [*row.conclusions, conclusion]; row.row_version += 1
    await db.flush()
    from app.services.email_draft import invalidate_email_drafts
    await invalidate_email_drafts(db, [application_id])
    await record_audit_event(db, actor_id=ctx.user.id, action='interview_round.concluded', entity_type='interview_round', entity_id=row.id,
        requisition_id=application.requisition_id, safe_metadata={'round_no': round_no, 'outcome': payload.outcome, 'scorecard_count': len(complete)})
    return await interview_round(db, application_id, round_no, ctx)


def decision_is_current(application, decision):
    req = application.requisition
    return bool(decision and decision.document_id == application.current_document_id
        and decision.source_snapshot.get('application_generation') == application.generation
        and decision.rubric_version_id == req.current_rubric_version_id)

async def validate_focus(db, application, round_no, interviewer_id, entries, *, require_complete=True):
    row = (await db.execute(select(InterviewRound).where(InterviewRound.application_id == application.id, InterviewRound.round_no == round_no))).scalar_one_or_none()
    if not row: return  # Legacy unplanned rounds retain their original API contract.
    source_hash, _ = await source(db, application)
    if row.source_hash != source_hash: raise HTTPException(409, 'ROUND_STALE: Kế hoạch dùng nguồn cũ.')
    if str(interviewer_id) not in row.preparation['interviewer_ids']: raise HTTPException(403, 'Bạn chưa được phân công phỏng vấn lượt này.')
    if not require_complete: return
    by_id = {e['criterion_id']: e for e in entries}
    for cid in row.preparation['focus_criterion_ids']:
        entry = by_id[cid]
        if entry['outcome'] != 'assessed' and len(entry.get('answer_summary', '').strip()) < 20:
            raise HTTPException(422, 'FOCUS_REVIEW_REQUIRED: Ghi nhận hoặc giải thích vì sao chưa quan sát được tiêu chí trọng tâm.')
