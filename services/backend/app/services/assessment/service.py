"""Assessment execution, lifecycle management, and database persistence service."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.assessment import AssessmentRun, CriterionAssessment, CriterionEvidence
from app.db.models.candidate import Application
from app.db.models.document import Document, SanitizedVersion, SourceSpan
from app.db.models.ops import Job
from app.db.models import (
    Requisition,
    RequisitionMembership,
    RubricCriterion,
    RubricVersion,
)
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import (
    AccountRole,
    JobStatus,
    JobType,
    RequisitionStatus,
    RubricStatus,
    SanitizedVersionStatus,
)
from app.schemas.assessment import (
    AssessmentOutputSchema,
    AssessmentRunCreateRequest,
    AssessmentRunResponse,
    CriterionAssessmentResponse,
    CriterionEvidenceResponse,
)
from app.services.assessment.prompt import (
    build_assessment_system_prompt,
    build_assessment_user_prompt,
    build_repair_user_prompt,
)
from app.services.assessment.scoring import calculate_deterministic_scores
from app.services.assessment.validator import (
    AssessmentValidationError,
    validate_assessment_output,
)
from app.services.audit import record_audit_event
from app.services.llm.orchestrator import execute_bounded_llm_call
from app.services.llm.provider import BaseLLMProvider
from app.services.llm.types import CompletionRequest

logger = logging.getLogger(__name__)


async def create_assessment_run(
    db: AsyncSession,
    application_id: uuid.UUID,
    payload: AssessmentRunCreateRequest,
    ctx: AuthenticatedContext,
) -> AssessmentRunResponse:
    """Validate preconditions and enqueue an assessment run job.
    Preconditions:
      1. Application active and Requisition open.
      2. Caller is active member of Requisition.
      3. Sanitized version is APPROVED and matches current document.
      4. Rubric version is APPROVED.
    """
    stmt_app = (
        select(Application)
        .options(selectinload(Application.requisition))
        .where(Application.id == application_id)
    )
    app_obj = (await db.execute(stmt_app)).scalar_one_or_none()
    if not app_obj or app_obj.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Hồ sơ ứng viên không tồn tại.")

    # Membership check
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == app_obj.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập hồ sơ này.")

    # Requisition state check
    if app_obj.requisition.status == RequisitionStatus.CLOSED:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Đợt tuyển dụng đã đóng.")

    # Sanitized Version check: MUST BE APPROVED
    stmt_v = select(SanitizedVersion).where(SanitizedVersion.id == payload.sanitized_version_id)
    sanitized = (await db.execute(stmt_v)).scalar_one_or_none()
    if not sanitized or sanitized.application_id != application_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bản sanitized không tồn tại.")
    if sanitized.status != SanitizedVersionStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="CANNOT_EGRESS_UNAPPROVED_CV: Bản sanitized phải được HR phê duyệt (APPROVED) trước khi thực hiện đánh giá.",
        )

    # Rubric check: MUST BE APPROVED
    stmt_r = select(RubricVersion).where(RubricVersion.id == payload.rubric_version_id)
    rubric = (await db.execute(stmt_r)).scalar_one_or_none()
    if not rubric or rubric.status != RubricStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Rubric phải ở trạng thái APPROVED.",
        )

    # Next run number
    stmt_max = select(func.max(AssessmentRun.run_no)).where(AssessmentRun.application_id == application_id)
    max_run = (await db.execute(stmt_max)).scalar() or 0
    next_run = max_run + 1

    now = datetime.now(timezone.utc)
    snapshot = {
        "application_id": str(application_id),
        "document_id": str(sanitized.document_id),
        "sanitized_version_id": str(sanitized.id),
        "sanitized_sha256": sanitized.sha256,
        "rubric_version_id": str(rubric.id),
        "application_generation": app_obj.generation,
    }
    snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()

    # Enqueue Job
    job = Job(
        id=uuid.uuid4(),
        type=JobType.ASSESS_APPLICATION,
        status=JobStatus.QUEUED,
        target_type="application",
        target_id=application_id,
        input_snapshot_hash=snapshot_hash,
        payload_ref={"run_no": next_run},
        priority=10,
        available_at=now,
        created_at=now,
    )
    db.add(job)
    await db.flush()

    run = AssessmentRun(
        id=uuid.uuid4(),
        application_id=application_id,
        job_id=job.id,
        run_no=next_run,
        status="queued",
        snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        application_generation=app_obj.generation,
        document_id=sanitized.document_id,
        sanitized_version_id=sanitized.id,
        rubric_version_id=rubric.id,
        strategy="fulltext",
        output_schema_version="1.0",
        coverage=0.0,
        created_at=now,
    )
    db.add(run)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="assessment.queued",
        entity_type="assessment_run",
        entity_id=run.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={"run_no": next_run, "strategy": "fulltext"},
    )

    return AssessmentRunResponse(
        id=run.id,
        application_id=run.application_id,
        run_no=run.run_no,
        status=run.status,
        coverage=0.0,
    )


async def execute_assessment_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    provider_override: Optional[BaseLLMProvider] = None,
) -> None:
    """Background worker handler for executing full-text AI assessment with bounded repair."""
    now = datetime.now(timezone.utc)

    # 1. Load AssessmentRun
    stmt_run = (
        select(AssessmentRun)
        .options(selectinload(AssessmentRun.application))
        .where(AssessmentRun.job_id == job_id)
        .with_for_update()
    )
    run = (await db.execute(stmt_run)).scalar_one_or_none()
    if not run:
        raise ValueError(f"AssessmentRun with job_id {job_id} not found.")

    run.status = "running"
    run.started_at = now
    await db.flush()

    # SEC-10 Initial Tombstone / Deletion check
    stmt_app_check = select(Application.status, Application.generation).where(Application.id == run.application_id)
    app_check = (await db.execute(stmt_app_check)).first()
    if not app_check or app_check[0] == "deleted" or app_check[1] > run.application.generation:
        logger.warning(f"Application {run.application_id} is deleted or generation bumped. Aborting assessment.")
        run.status = "failed"
        run.failure_code = "APPLICATION_TOMBSTONED"
        run.completed_at = now
        await db.flush()
        return

    # 2. Load Rubric criteria and Sanitized Source Spans
    stmt_crit = (
        select(RubricCriterion)
        .where(RubricCriterion.rubric_version_id == run.rubric_version_id)
        .order_by(RubricCriterion.criterion_id.asc())
    )
    rubric_criteria = (await db.execute(stmt_crit)).scalars().all()
    weights_by_id = {c.criterion_id: c.weight for c in rubric_criteria}

    stmt_spans = (
        select(SourceSpan)
        .where(SourceSpan.sanitized_version_id == run.sanitized_version_id)
        .order_by(SourceSpan.start_cp.asc())
    )
    spans = (await db.execute(stmt_spans)).scalars().all()
    span_registry = {s.span_id: s for s in spans}

    # 3. Build Prompts
    system_prompt = build_assessment_system_prompt()
    user_prompt = build_assessment_user_prompt(rubric_criteria, spans)

    validated_output: Optional[AssessmentOutputSchema] = None
    last_error: Optional[str] = None

    # 4. Bounded Execution Loop (Attempt 1 + Max 1 Repair = 2 attempts total)
    for attempt in (1, 2):
        current_prompt = (
            user_prompt
            if attempt == 1
            else build_repair_user_prompt(user_prompt, [last_error or "Unknown validation error"])
        )

        req = CompletionRequest(
            task_kind="assessment",
            system_prompt=system_prompt,
            user_prompt=current_prompt,
            model="deepseek-chat",
            max_output_tokens=4096,
        )

        try:
            call_res = await execute_bounded_llm_call(
                db=db,
                job_id=job_id,
                request=req,
                logical_step=f"assessment_attempt_{attempt}",
                attempt_no=attempt,
                sanitized_version_id=run.sanitized_version_id,
                provider_override=provider_override,
            )
            validated_output = validate_assessment_output(call_res.content or "", span_registry)
            break  # Success!
        except (AssessmentValidationError, Exception) as e:
            logger.warning(f"Assessment run {run.id} attempt {attempt} failed: {e}")
            last_error = str(e)
            if attempt == 2:
                # Terminal failure
                run.status = "failed"
                run.failure_code = last_error[:100]
                run.completed_at = datetime.now(timezone.utc)
                await db.flush()
                return

    if not validated_output:
        run.status = "failed"
        run.failure_code = "OUTPUT_VALIDATION_FAILED"
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return

    # SEC-10 Late Arrival / Deletion Check
    stmt_app_check = select(Application.status, Application.generation).where(Application.id == run.application_id)
    app_check = (await db.execute(stmt_app_check)).first()
    if not app_check or app_check[0] == "deleted" or app_check[1] > run.application.generation:
        logger.warning(f"Application {run.application_id} was deleted or generation incremented during LLM call. Discarding output.")
        run.status = "failed"
        run.failure_code = "APPLICATION_TOMBSTONED"
        run.completed_at = datetime.now(timezone.utc)
        await db.flush()
        return

    # 5. Deterministic Scoring
    obs_score, coverage, comp_score, rec, reasons = calculate_deterministic_scores(
        evaluations=validated_output.criteria,
        rubric_weights=weights_by_id,
    )

    run.observed_score = float(obs_score) if obs_score is not None else None
    run.coverage = float(coverage)
    run.comparable_score = float(comp_score) if comp_score is not None else None
    run.recommendation = rec
    run.status = "succeeded"
    run.completed_at = datetime.now(timezone.utc)
    run.result_hash = hashlib.sha256(json.dumps(validated_output.model_dump(), sort_keys=True).encode("utf-8")).hexdigest()

    # 6. Persist Criteria & Evidence Records
    for c_dto in validated_output.criteria:
        c_model = CriterionAssessment(
            run_id=run.id,
            criterion_id=c_dto.criterion_id,
            status=c_dto.status,
            score=c_dto.score,
            rationale=c_dto.rationale,
            missing_information=c_dto.missing_information,
        )
        db.add(c_model)

        for ev_dto in c_dto.evidence:
            span = span_registry[ev_dto.span_id]
            ev_model = CriterionEvidence(
                run_id=run.id,
                criterion_id=c_dto.criterion_id,
                span_id=ev_dto.span_id,
                quote=ev_dto.quote,
                resolved_start_cp=span.start_cp,
                resolved_end_cp=span.end_cp,
            )
            db.add(ev_model)

    # Point application to current assessment run
    run.application.current_assessment_run_id = run.id
    run.application.updated_at = datetime.now(timezone.utc)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=None,
        action="assessment.completed",
        entity_type="assessment_run",
        entity_id=run.id,
        requisition_id=run.application.requisition_id,
        safe_metadata={
            "run_no": run.run_no,
            "coverage": float(coverage),
            "observed_score": float(obs_score) if obs_score else None,
            "recommendation": rec.value if rec else None,
        },
    )


async def get_assessment_run_detail(
    db: AsyncSession,
    run_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> AssessmentRunResponse:
    """Retrieve detailed assessment run with criteria evaluations and resolved evidence."""
    stmt = (
        select(AssessmentRun)
        .options(
            selectinload(AssessmentRun.application),
            selectinload(AssessmentRun.criteria),
            selectinload(AssessmentRun.evidence),
        )
        .where(AssessmentRun.id == run_id)
    )
    run = (await db.execute(stmt)).scalar_one_or_none()
    if not run or run.application.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kết quả đánh giá không tồn tại.")

    # Membership check
    is_admin = AccountRole.ADMIN in ctx.roles
    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == run.application.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    mem = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not is_admin and not mem:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập kết quả này.")

    # Group evidence by criterion_id
    evidence_by_crit: dict[str, list[CriterionEvidenceResponse]] = {}
    for ev in run.evidence:
        evidence_by_crit.setdefault(ev.criterion_id, []).append(
            CriterionEvidenceResponse(
                span_id=ev.span_id,
                quote=ev.quote,
                resolved_start_cp=ev.resolved_start_cp,
                resolved_end_cp=ev.resolved_end_cp,
            )
        )

    criteria_resp = []
    for c in run.criteria:
        criteria_resp.append(
            CriterionAssessmentResponse(
                criterion_id=c.criterion_id,
                status=c.status,
                score=c.score,
                rationale=c.rationale,
                missing_information=c.missing_information,
                evidence=evidence_by_crit.get(c.criterion_id, []),
            )
        )

    is_stale = run.application_generation != run.application.generation

    return AssessmentRunResponse(
        id=run.id,
        application_id=run.application_id,
        run_no=run.run_no,
        status=run.status,
        observed_score=float(run.observed_score) if run.observed_score is not None else None,
        coverage=float(run.coverage),
        comparable_score=float(run.comparable_score) if run.comparable_score is not None else None,
        recommendation=run.recommendation,
        started_at=run.started_at,
        completed_at=run.completed_at,
        failure_code=run.failure_code,
        criteria=criteria_resp,
        is_stale=is_stale,
    )
