"""Requisition-level review queue and safe, same-rubric comparison."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import (
    Application, AssessmentRun, Candidate, CriterionAssessment, Document,
    Requisition, RequisitionMembership, RubricCriterion, SanitizedVersion, Job, Decision, InterviewRound, InterviewScorecard, RubricVersion,
)
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.domain.enums import AccountRole, MembershipRole, SanitizedVersionStatus, JobStatus, JobType
from app.services.sanitizer import residual_contact_types
from app.services.duplicates import duplicate_signals

router = APIRouter(tags=["Review workflow"])


async def _authorized_requisition(db: AsyncSession, requisition_id: uuid.UUID, ctx: AuthenticatedContext, owner_only: bool = False) -> Requisition:
    requisition = await db.get(Requisition, requisition_id)
    if requisition is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đợt tuyển dụng.")
    # Admin can already inspect intake metadata across requisitions. Queue
    # metadata follows the same policy; comparison still requires an Owner.
    if not owner_only and ctx.has_role(AccountRole.ADMIN):
        return requisition
    membership = (await db.execute(select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    ))).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy đợt tuyển dụng.")
    if owner_only and membership.membership_role != MembershipRole.OWNER:
        raise HTTPException(status_code=403, detail="Chỉ Owner được xem ma trận so sánh.")
    return requisition


@router.get("/requisitions/{id}/review-queue")
async def review_queue(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Metadata only: no raw/sanitized CV text or AI scores are returned."""
    requisition = await _authorized_requisition(db, id, ctx)
    rows = (await db.execute(
        select(Application, Candidate.public_label, Document, SanitizedVersion)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .outerjoin(Document, Document.id == Application.current_document_id)
        .outerjoin(SanitizedVersion, SanitizedVersion.id == Application.current_sanitized_version_id)
        .where(Application.requisition_id == id, Application.status == "active")
        .order_by(Application.received_at.asc(), Application.id.asc())
    )).all()
    run_ids = [application.current_assessment_run_id for application, _, _, _ in rows if application.current_assessment_run_id]
    runs = {run.id: run for run in (await db.execute(select(AssessmentRun).where(AssessmentRun.id.in_(run_ids)))).scalars().all()} if run_ids else {}
    target_ids = [application.id for application, _, _, _ in rows] + [document.id for _, _, document, _ in rows if document]
    jobs = (await db.execute(select(Job).where(Job.target_id.in_(target_ids), Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY_WAIT]), Job.type.in_([JobType.INGEST_DOCUMENT, JobType.ASSESS_APPLICATION])))).scalars().all() if target_ids else []
    reading_ids = {job.target_id for job in jobs if job.type == JobType.INGEST_DOCUMENT}
    analyzing_ids = {job.target_id for job in jobs if job.type == JobType.ASSESS_APPLICATION}
    duplicates = await duplicate_signals(db, requisition, ctx)
    decision_ids = [a.current_decision_id for a, _, _, _ in rows if a.current_decision_id]
    decisions = {d.id: d for d in (await db.execute(select(Decision).where(Decision.id.in_(decision_ids)))).scalars()} if decision_ids else {}

    current_rubric = await db.get(RubricVersion,requisition.current_rubric_version_id) if requisition.current_rubric_version_id else None
    rubric_current = bool(current_rubric and current_rubric.jd_version_id == requisition.current_jd_version_id)
    application_ids = [a.id for a, _, _, _ in rows]
    rounds = (await db.execute(select(InterviewRound).where(InterviewRound.application_id.in_(application_ids)).order_by(InterviewRound.round_no))).scalars().all() if application_ids else []
    latest_rounds = {row.application_id: row for row in rounds if row.conclusions}
    cards = (await db.execute(select(InterviewScorecard.id,InterviewScorecard.row_version).where(InterviewScorecard.application_id.in_(application_ids),InterviewScorecard.status == "finalized"))).all() if application_ids else []
    card_versions = dict(cards)
    now = datetime.now(timezone.utc)
    result = []
    for application, label, document, version in rows:
        flags = []
        if document and document.quality_report and document.quality_report.get("quality_status") not in (None, "ok", "ok_ocr_recovered"):
            flags.append("parse_quality")
        if version and residual_contact_types(version.canonical_text):
            flags.append("contact_data")

        app_count, duplicate_reasons = duplicates.get(application.id, (1, []))
        if app_count > 1:
            flags.append("duplicate_candidate")

        run = runs.get(application.current_assessment_run_id)
        current_stage = _stage(
            application,
            document,
            version,
            run,
            requisition.current_rubric_version_id,
            bool(document and document.id in reading_ids),
            application.id in analyzing_ids,
            decisions.get(application.current_decision_id),
            rubric_current,
        )
        current_stage = _interview_stage(current_stage,application,requisition,latest_rounds.get(application.id),card_versions)

        # SLA Alert (QW4): Check if application is awaiting HR decision for more than 72 hours
        hours_in_stage = 0.0
        sla_breached = False
        if current_stage == "awaiting_decision" and run:
            ref_time = run.completed_at or run.created_at or application.received_at
            hours_in_stage = round((now - ref_time).total_seconds() / 3600.0, 1)
            sla_breached = hours_in_stage > 72.0

        result.append({
            "application_id": application.id,
            "public_label": label,
            "received_at": application.received_at,
            "document_status": document.ingestion_status if document else "missing",
            "sanitized_status": version.status.value if version else "missing",
            "risk_flags": flags,
            "assessment_available": bool(application.current_assessment_run_id),
            "workflow_stage": current_stage,
            "sla_breached": sla_breached,
            "hours_in_stage": hours_in_stage,
            "application_history_count": app_count,
            "is_duplicate": app_count > 1,
            "duplicate_reasons": duplicate_reasons,
        })
    return result


@router.get("/requisitions/{id}/shortlist")
async def get_requisition_shortlist_endpoint(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Return HR review groups from the threshold and floors in the current approved rubric."""
    from app.services.shortlist import compute_requisition_shortlist
    return await compute_requisition_shortlist(db, requisition_id=id, ctx=ctx)


@router.get("/requisitions/{id}/comparison")
async def candidate_comparison(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Owner-only matrix; incomplete/stale cases never receive a comparable score."""
    requisition = await _authorized_requisition(db, id, ctx, owner_only=True)
    rubric_id = requisition.current_rubric_version_id
    if rubric_id is None:
        return {"rubric_version_id": None, "criteria": [], "candidates": []}
    criteria = (await db.execute(select(RubricCriterion).where(
        RubricCriterion.rubric_version_id == rubric_id
    ).order_by(RubricCriterion.criterion_id))).scalars().all()
    rows = (await db.execute(
        select(Application, Candidate.public_label, AssessmentRun)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .outerjoin(AssessmentRun, AssessmentRun.id == Application.current_assessment_run_id)
        .where(Application.requisition_id == id, Application.status == "active")
        .order_by(Application.received_at.asc(), Application.id.asc())
    )).all()
    run_ids = [run.id for _, _, run in rows if run is not None]
    scores_by_run: dict[uuid.UUID, dict[str, dict]] = {}
    if run_ids:
        for criterion in (await db.execute(select(CriterionAssessment).where(
            CriterionAssessment.run_id.in_(run_ids)
        ))).scalars().all():
            scores_by_run.setdefault(criterion.run_id, {})[criterion.criterion_id] = {
                "status": criterion.status.value,
                "score": criterion.score,
            }
    candidates = []
    for application, label, run in rows:
        valid = bool(
            run and run.status == "succeeded"
            and run.application_generation == application.generation
            and run.document_id == application.current_document_id
            and run.sanitized_version_id == application.current_sanitized_version_id
            and run.rubric_version_id == rubric_id
        )
        if valid:
            version = await db.get(SanitizedVersion, application.current_sanitized_version_id)
            valid = bool(version and version.status == SanitizedVersionStatus.APPROVED)
        candidates.append({
            "application_id": application.id,
            "public_label": label,
            "assessment_status": run.status if valid else "missing_or_stale",
            "coverage": float(run.coverage) if valid else None,
            "observed_score": float(run.observed_score) if valid and run.observed_score is not None else None,
            "comparable_score": float(run.comparable_score) if valid and run.comparable_score is not None else None,
            "recommendation": run.recommendation.value if valid and run.recommendation else None,
            "criteria": scores_by_run.get(run.id, {}) if valid else {},
        })
    return {
        "rubric_version_id": rubric_id,
        "criteria": [{"id": criterion.criterion_id, "label": criterion.label_vi} for criterion in criteria],
        "candidates": candidates,
    }


def _fresh(application, run, rubric_id):
    return bool(run and run.application_generation == application.generation and run.document_id == application.current_document_id
                and run.sanitized_version_id == application.current_sanitized_version_id and run.rubric_version_id == rubric_id)

def _stage(application, document, version, run, rubric_id, reading=False, analyzing=False, decision=None, rubric_current=True):
    if not rubric_current and document: return "needs_rubric"
    if decision and decision.document_id == application.current_document_id and decision.source_snapshot.get("application_generation") == application.generation and decision.rubric_version_id == rubric_id:
        outcome = decision.outcome.value
        return {"request_information": "waiting_information", "advance": "awaiting_interview", "not_advance": "not_advanced"}[outcome]
    if not document: return "awaiting_upload"
    if reading: return "reading"
    if document.ingestion_status == "failed": return "error"
    if document.ingestion_status != "parsed": return "reading"
    if not version or version.status != SanitizedVersionStatus.APPROVED: return "needs_review"
    if analyzing: return "analyzing"
    if _fresh(application, run, rubric_id):
        if run.status in ("queued", "running"): return "analyzing"
        if run.status == "succeeded": return "awaiting_decision"
        if run.status == "failed": return "error"
    return "ready_for_ai"

def _interview_stage(stage, application, requisition, plan, card_versions):
    if stage != "awaiting_interview" or not plan or not plan.conclusions: return stage
    from app.services.hr_workflow import interview_source_hash
    conclusion = plan.conclusions[-1]
    if plan.source_hash != interview_source_hash(application,requisition) or conclusion.get("decision_id") != str(application.current_decision_id): return stage
    if any(card_versions.get(uuid.UUID(ref["id"])) != ref["row_version"] for ref in conclusion["scorecards"]): return "interview_review"
    return {"advance":"awaiting_interview","request_information":"waiting_information","not_advance":"not_advanced","propose_hire":"interview_completed"}[conclusion["outcome"]]

@router.get("/applications/{id}/progress")
async def application_progress(id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    application = await db.get(Application, id)
    if application is None or application.status != "active": raise HTTPException(404, "Không tìm thấy hồ sơ đang hoạt động.")
    requisition = await _authorized_requisition(db, application.requisition_id, ctx)
    document = await db.get(Document, application.current_document_id) if application.current_document_id else None
    version = await db.get(SanitizedVersion, application.current_sanitized_version_id) if application.current_sanitized_version_id else None
    run = await db.get(AssessmentRun, application.current_assessment_run_id) if application.current_assessment_run_id else None
    fresh = _fresh(application, run, requisition.current_rubric_version_id)
    pending = (await db.execute(select(Job).where(Job.target_id.in_([application.id] + ([document.id] if document else [])),
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY_WAIT]), Job.type.in_([JobType.INGEST_DOCUMENT, JobType.ASSESS_APPLICATION])))).scalars().all()
    analyzing = any(job.type == JobType.ASSESS_APPLICATION for job in pending)
    decision = await db.get(Decision, application.current_decision_id) if application.current_decision_id else None
    rubric = await db.get(RubricVersion,requisition.current_rubric_version_id) if requisition.current_rubric_version_id else None
    stage = _stage(application, document, version, run, requisition.current_rubric_version_id,
                   any(job.type == JobType.INGEST_DOCUMENT for job in pending), analyzing, decision,
                   bool(rubric and rubric.jd_version_id == requisition.current_jd_version_id))
    plan = (await db.execute(select(InterviewRound).where(InterviewRound.application_id == application.id, InterviewRound.conclusions != []).order_by(InterviewRound.round_no.desc()).limit(1))).scalar_one_or_none()
    card_versions = dict((await db.execute(select(InterviewScorecard.id,InterviewScorecard.row_version).where(InterviewScorecard.application_id == application.id,InterviewScorecard.status == "finalized"))).all()) if plan and plan.conclusions else {}
    stage = _interview_stage(stage,application,requisition,plan,card_versions)

    history_count, duplicate_reasons = (await duplicate_signals(db, requisition, ctx)).get(application.id, (1, []))

    return {"application_id": application.id, "stage": stage, "pending": bool(pending),
            "document_status": document.ingestion_status if document else "missing",
            "assessment_status": "running" if analyzing else run.status if fresh else "missing_or_stale",
            "failure_code": run.failure_code if fresh and run.status == "failed" else None,
            "application_history_count": history_count,
            "is_duplicate": history_count > 1, "duplicate_reasons": duplicate_reasons}



@router.get("/applications/{id}/approved-spans")
async def approved_spans(id: uuid.UUID, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    from app.db.models import SourceSpan
    application = await db.get(Application, id)
    if not application or application.status != "active": raise HTTPException(404, "Không tìm thấy hồ sơ.")
    await _authorized_requisition(db, application.requisition_id, ctx, owner_only=True)
    version = await db.get(SanitizedVersion, application.current_sanitized_version_id) if application.current_sanitized_version_id else None
    if not version or version.status != SanitizedVersionStatus.APPROVED or residual_contact_types(version.canonical_text):
        raise HTTPException(409, "Cần CV đã che được duyệt.")
    spans = (await db.execute(select(SourceSpan).where(SourceSpan.sanitized_version_id == version.id).order_by(SourceSpan.start_cp))).scalars().all()
    return [{"span_id": span.span_id, "quote": span.text} for span in spans]
