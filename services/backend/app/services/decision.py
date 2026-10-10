"""Domain services for Task B13: HR Revisions, Attestation, and Decision Flow."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Application,
    AssessmentRun,
    CriterionAssessment,
    Decision,
    Document,
    HRRevision,
    Job,
    RawAccessGrant,
    Requisition,
    RequisitionMembership,
    ReviewAttestation,
    RubricCriterion,
    RubricVersion,
    SanitizedVersion,
    SourceSpan,
)
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import (
    AccountRole,
    CriterionOutcome,
    DecisionBasis,
    DecisionOutcome,
    DocumentSafetyStatus,
    JobStatus,
    JobType,
    MembershipRole,
    Recommendation,
    RequisitionStatus,
    RubricStatus,
    SanitizedVersionStatus,
)
from app.domain.rubric_policy import scan_forbidden_criteria
from app.schemas.decision import (
    AttestationAssessmentReviewRequest,
    AttestationCreateRequest,
    AttestationManualDocumentRequest,
    AttestationTechnicalRequest,
    DecisionCreateRequest,
    DecisionResponse,
    HRRevisionCreateRequest,
    HRRevisionFinalizeRequest,
    HRRevisionResponse,
    HRRevisionUpdateRequest,
    ReviewAttestationResponse,
)
from app.services.assessment.scoring import DEFAULT_THRESHOLD, calculate_deterministic_scores
from app.services.audit import record_audit_event

logger = logging.getLogger(__name__)


def requires_information_request_before_rejection(
    recommendation: str | None,
    criterion_statuses: dict[str, str],
    required_criterion_ids: set[str],
) -> bool:
    """Official v3 flow requires contact first when must-have evidence is absent."""
    if recommendation != Recommendation.NEEDS_CLARIFICATION.value:
        return False
    return any(criterion_statuses.get(criterion_id) == CriterionOutcome.INSUFFICIENT_EVIDENCE.value
               for criterion_id in required_criterion_ids)


def clarification_disposition_error(
    recommendation: str | None,
    outcome: str,
    criterion_statuses: dict[str, str],
    required_criterion_ids: set[str],
    previous_outcome: str | None,
    clarification_resolution: str | None,
) -> str | None:
    """Require an auditable HR disposition before rejecting an unclear assessment.

    Missing must-have evidence needs a recorded contact step and candidate
    confirmation/non-response. Missing nice-to-have evidence alone cannot be
    the reason for rejection; HR must attest to an independent evidence-based
    reason. Conflicts retain their separate existing HR-review path.
    """
    if recommendation != Recommendation.NEEDS_CLARIFICATION.value or outcome != DecisionOutcome.NOT_ADVANCE.value:
        return None

    missing_required = any(
        criterion_statuses.get(criterion_id) == CriterionOutcome.INSUFFICIENT_EVIDENCE.value
        for criterion_id in required_criterion_ids
    )
    if missing_required:
        if previous_outcome != DecisionOutcome.REQUEST_INFORMATION.value:
            return "MUST_HAVE_INFORMATION_REQUEST_REQUIRED"
        if clarification_resolution not in {"candidate_confirmed_no_experience", "no_response_after_contact"}:
            return "CLARIFICATION_RESOLUTION_REQUIRED"

    missing_optional = any(
        status_value == CriterionOutcome.INSUFFICIENT_EVIDENCE.value
        and criterion_id not in required_criterion_ids
        for criterion_id, status_value in criterion_statuses.items()
    )
    if not missing_required and missing_optional and clarification_resolution != "independent_evidence_based_reason":
        return "NICE_TO_HAVE_INDEPENDENT_BASIS_REQUIRED"
    return None


def is_matching_information_request(previous: Any, application_id: uuid.UUID, attestation: Any) -> bool:
    """A contact decision only unlocks the same application source and rubric generation."""
    if not previous or previous.outcome != DecisionOutcome.REQUEST_INFORMATION:
        return False
    snapshot = previous.source_snapshot or {}
    return (
        previous.application_id == application_id
        and previous.document_id == attestation.document_id
        and previous.rubric_version_id == attestation.rubric_version_id
        and snapshot.get("application_generation") == attestation.application_generation
    )


def resolve_required_criterion_ids(policy: dict[str, Any], rubric_criterion_ids: set[str]) -> set[str]:
    """Resolve explicit policy, preserving legacy full-coverage rubrics."""
    explicit = policy.get("required_criterion_ids")
    if isinstance(explicit, list):
        return set(explicit)
    floors = policy.get("core_minimum_scores")
    if isinstance(floors, dict) and floors:
        return set(floors)
    return set(rubric_criterion_ids) if policy.get("require_full_coverage", True) else set()


async def _verify_application_and_membership(
    db: AsyncSession,
    application_id: uuid.UUID,
    ctx: AuthenticatedContext,
    require_owner: bool = False,
    require_open: bool = True,
) -> tuple[Application, RequisitionMembership]:
    """Verify access; closed requisitions remain readable for audit history."""
    stmt_app = (
        select(Application)
        .options(
            selectinload(Application.requisition),
        )
        .where(Application.id == application_id)
    )
    app_obj = (await db.execute(stmt_app)).scalar_one_or_none()
    if not app_obj or app_obj.status == "deleted":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Đơn ứng tuyển không tồn tại.")

    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == app_obj.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    membership = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không có quyền truy cập đợt tuyển dụng này.",
        )

    if require_owner and membership.membership_role != MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner của Requisition mới có quyền thực hiện hành động này.",
        )

    if require_open and app_obj.requisition.status == RequisitionStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="REQUISITION_CLOSED: Requisition đã đóng, không thể thực hiện thao tác.",
        )

    return app_obj, membership


async def _validate_revision_sources(db, app_obj, document_id, sanitized_id, generation, criteria):
    if (document_id != app_obj.current_document_id or sanitized_id != app_obj.current_sanitized_version_id
            or generation != app_obj.generation):
        raise HTTPException(409, "SNAPSHOT_MISMATCH: Hồ sơ đã thay đổi; tải lại trước khi sửa đánh giá.")
    version = await db.get(SanitizedVersion, sanitized_id)
    if not version or version.status != SanitizedVersionStatus.APPROVED:
        raise HTTPException(409, "Cần bản CV đã che được duyệt.")
    spans = {span.span_id: span for span in (await db.execute(select(SourceSpan).where(SourceSpan.sanitized_version_id == sanitized_id))).scalars().all()}
    for criterion in criteria:
        for evidence in criterion.evidence:
            span = spans.get(evidence.span_id)
            if not span or evidence.quote != span.text or span.text not in version.canonical_text:
                raise HTTPException(422, "INVALID_EVIDENCE: Đoạn trích không khớp CV hiện hành.")


# ---------------- HR Revision Domain Methods ---------------- #


async def create_hr_revision(
    db: AsyncSession,
    application_id: uuid.UUID,
    payload: HRRevisionCreateRequest,
    ctx: AuthenticatedContext,
) -> HRRevisionResponse:
    """Create a draft HR Revision with server-side deterministic scoring and anti-discrimination checks."""
    app_obj, _ = await _verify_application_and_membership(db, application_id, ctx)

    # Invariant: Concurrency check
    if app_obj.row_version != payload.expected_application_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VERSION_CONFLICT: Hồ sơ ứng viên đã thay đổi (hiện tại v{app_obj.row_version}, kỳ vọng v{payload.expected_application_version}). Vui lòng tải lại trang.",
        )

    # Invariant: Must target current document and sanitized version
    ref = payload.source_snapshot_ref
    if ref.document_id != app_obj.current_document_id or ref.sanitized_version_id != app_obj.current_sanitized_version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SNAPSHOT_MISMATCH: Nguồn tài liệu hoặc phiên bản sanitized đã thay đổi.",
        )

    # Invariant: Active approved rubric
    stmt_rubric = select(RubricVersion).where(
        RubricVersion.id == ref.rubric_version_id,
        RubricVersion.requisition_id == app_obj.requisition_id,
        RubricVersion.status == RubricStatus.APPROVED,
    )
    rubric = (await db.execute(stmt_rubric)).scalar_one_or_none()
    if not rubric:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RUBRIC_NOT_APPROVED: Rubric được tham chiếu chưa được duyệt hoặc không tồn tại.",
        )

    # Anti-discrimination check on summary reason
    forbidden = scan_forbidden_criteria(payload.summary_reason)
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Lý do tổng hợp nhắc đến thuộc tính cấm: '{forbidden}'.",
        )

    # Validate criteria and change reasons
    stmt_crit = select(RubricCriterion).where(RubricCriterion.rubric_version_id == rubric.id)
    criteria_defs = (await db.execute(stmt_crit)).scalars().all()
    weights_by_id = {c.criterion_id: c.weight for c in criteria_defs}

    # The HR revision must match this exact approved rubric version.
    crit_dict = {c.criterion_id: c for c in payload.criteria}
    expected_ids = set(weights_by_id)
    if len(payload.criteria) != len(crit_dict) or set(crit_dict) != expected_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"CRITERION_SET_MISMATCH: Bản HR phải chứa đúng các tiêu chí của rubric hiện hành.",
        )
    for cid, criterion in crit_dict.items():
        # Scan rationale for forbidden attributes
        f_rat = scan_forbidden_criteria(criterion.rationale)
        if f_rat:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Giải trình tiêu chí '{cid}' nhắc đến thuộc tính cấm: '{f_rat}'.",
            )

    # Check change reasons
    for c_id, cr in payload.change_reasons.items():
        f_cr = scan_forbidden_criteria(cr.note)
        if f_cr:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Ghi chú thay đổi cho tiêu chí '{c_id}' nhắc đến thuộc tính cấm: '{f_cr}'.",
            )

    await _validate_revision_sources(db, app_obj, ref.document_id, ref.sanitized_version_id, ref.application_generation, payload.criteria)

    # Compute deterministic scores server-side with dynamic rubric policy
    policy = rubric.threshold_config or {}
    t_val = Decimal(str(policy.get("threshold", DEFAULT_THRESHOLD)))
    core_mins = policy.get("core_minimum_scores") if isinstance(policy.get("core_minimum_scores"), dict) else None
    required_ids = set(policy["required_criterion_ids"]) if isinstance(policy.get("required_criterion_ids"), list) else None

    obs, cov, comp, rec, _ = calculate_deterministic_scores(
        payload.criteria,
        weights_by_id,
        threshold=t_val,
        core_minimum_scores=core_mins,
        required_criterion_ids=required_ids,
    )

    # Determine revision sequence number
    stmt_max = select(func.max(HRRevision.revision_no)).where(HRRevision.application_id == application_id)
    max_rev = (await db.execute(stmt_max)).scalar() or 0
    next_rev = max_rev + 1

    revision = HRRevision(
        id=uuid.uuid4(),
        application_id=application_id,
        base_run_id=payload.base_run_id,
        document_id=ref.document_id,
        sanitized_version_id=ref.sanitized_version_id,
        rubric_version_id=ref.rubric_version_id,
        application_generation=app_obj.generation,
        revision_no=next_rev,
        status="draft",
        criteria_payload={"criteria": [c.model_dump() for c in payload.criteria]},
        change_reasons={k: v.model_dump() for k, v in payload.change_reasons.items()},
        proposed_decision=payload.proposed_decision,
        summary_reason=payload.summary_reason,
        observed_score=obs,
        coverage=cov,
        comparable_score=comp,
        recommendation=rec.value if rec else None,
        created_by=ctx.user.id,
    )
    db.add(revision)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="hr_revision.created",
        entity_type="hr_revision",
        entity_id=revision.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "application_id": str(application_id),
            "revision_no": next_rev,
            "status": "draft",
            "comparable_score": str(comp),
        },
    )

    return HRRevisionResponse.model_validate(revision)


async def get_hr_revision_detail(
    db: AsyncSession,
    revision_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> HRRevisionResponse:
    """Fetch HR revision details and calculate staleness against current application state."""
    stmt = (
        select(HRRevision)
        .options(selectinload(HRRevision.application))
        .where(HRRevision.id == revision_id)
    )
    rev = (await db.execute(stmt)).scalar_one_or_none()
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bản chỉnh sửa HR không tồn tại.")

    await _verify_application_and_membership(db, rev.application_id, ctx, require_open=False)
    from app.api.v1.independent_review import enforce_shadow_blind
    await enforce_shadow_blind(db, rev.application, ctx)

    version_status = (await db.execute(
        select(SanitizedVersion.status).where(SanitizedVersion.id == rev.sanitized_version_id)
    )).scalar_one_or_none()
    if version_status == SanitizedVersionStatus.REVOKED:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="REVISION_QUARANTINED: Bản rà soát dùng CV đã che bị thu hồi.",
        )

    # Check staleness
    app_obj = rev.application
    is_stale = False
    stale_reasons = []

    if rev.document_id != app_obj.current_document_id:
        is_stale = True
        stale_reasons.append("DOCUMENT_CHANGED: Ứng viên đã nộp tài liệu CV mới.")
    if rev.sanitized_version_id != app_obj.current_sanitized_version_id:
        is_stale = True
        stale_reasons.append("SANITIZED_VERSION_CHANGED: Phiên bản sanitized mới đã được tạo.")

    res = HRRevisionResponse.model_validate(rev)
    res.is_stale = is_stale
    res.stale_reasons = stale_reasons
    return res


async def update_hr_revision(
    db: AsyncSession,
    revision_id: uuid.UUID,
    payload: HRRevisionUpdateRequest,
    ctx: AuthenticatedContext,
) -> HRRevisionResponse:
    """Update a draft HR revision. Finalized revisions are immutable."""
    stmt = (
        select(HRRevision)
        .options(selectinload(HRRevision.application))
        .where(HRRevision.id == revision_id)
        .with_for_update()
    )
    rev = (await db.execute(stmt)).scalar_one_or_none()
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bản chỉnh sửa HR không tồn tại.")

    app_obj, membership = await _verify_application_and_membership(db, rev.application_id, ctx)

    # Only author or Owner can edit draft
    if rev.created_by != ctx.user.id and membership.membership_role != MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ tác giả bản nháp hoặc Owner mới có quyền chỉnh sửa.",
        )

    if rev.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="REVISION_FINALIZED: Bản chỉnh sửa này đã hoàn tất, không thể thay đổi.",
        )

    # Scan for forbidden attributes
    forbidden = scan_forbidden_criteria(payload.summary_reason)
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Lý do tổng hợp nhắc đến thuộc tính cấm: '{forbidden}'.",
        )

    for c in payload.criteria:
        f_rat = scan_forbidden_criteria(c.rationale)
        if f_rat:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Giải trình tiêu chí '{c.criterion_id}' nhắc đến thuộc tính cấm: '{f_rat}'.",
            )

    for c_id, cr in payload.change_reasons.items():
        f_cr = scan_forbidden_criteria(cr.note)
        if f_cr:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Ghi chú thay đổi cho tiêu chí '{c_id}' nhắc đến thuộc tính cấm: '{f_cr}'.",
            )

    await _validate_revision_sources(db, app_obj, rev.document_id, rev.sanitized_version_id, rev.application_generation, payload.criteria)

    stmt_crit = select(RubricCriterion).where(RubricCriterion.rubric_version_id == rev.rubric_version_id)
    criteria_defs = (await db.execute(stmt_crit)).scalars().all()
    weights_by_id = {c.criterion_id: c.weight for c in criteria_defs}
    if len({c.criterion_id for c in payload.criteria}) != len(payload.criteria) or {c.criterion_id for c in payload.criteria} != set(weights_by_id):
        raise HTTPException(status_code=422, detail="CRITERION_SET_MISMATCH: Bản HR phải khớp với rubric đã duyệt.")

    stmt_rubric = select(RubricVersion).where(RubricVersion.id == rev.rubric_version_id)
    rubric_obj = (await db.execute(stmt_rubric)).scalar_one_or_none()
    policy = (rubric_obj.threshold_config or {}) if rubric_obj else {}
    t_val = Decimal(str(policy.get("threshold", DEFAULT_THRESHOLD)))
    core_mins = policy.get("core_minimum_scores") if isinstance(policy.get("core_minimum_scores"), dict) else None
    required_ids = set(policy["required_criterion_ids"]) if isinstance(policy.get("required_criterion_ids"), list) else None

    obs, cov, comp, rec, _ = calculate_deterministic_scores(
        payload.criteria,
        weights_by_id,
        threshold=t_val,
        core_minimum_scores=core_mins,
        required_criterion_ids=required_ids,
    )

    rev.criteria_payload = {"criteria": [c.model_dump() for c in payload.criteria]}
    rev.change_reasons = {k: v.model_dump() for k, v in payload.change_reasons.items()}
    rev.summary_reason = payload.summary_reason
    rev.proposed_decision = payload.proposed_decision
    rev.observed_score = obs
    rev.coverage = cov
    rev.comparable_score = comp
    rev.recommendation = rec.value if rec else None

    await db.flush()
    return HRRevisionResponse.model_validate(rev)


async def finalize_hr_revision(
    db: AsyncSession,
    revision_id: uuid.UUID,
    payload: HRRevisionFinalizeRequest,
    ctx: AuthenticatedContext,
) -> HRRevisionResponse:
    """Finalize an HR revision, freezing it into an immutable baseline."""
    stmt = (
        select(HRRevision)
        .options(selectinload(HRRevision.application))
        .where(HRRevision.id == revision_id)
        .with_for_update()
    )
    rev = (await db.execute(stmt)).scalar_one_or_none()
    if not rev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bản chỉnh sửa HR không tồn tại.")

    app_obj, membership = await _verify_application_and_membership(db, rev.application_id, ctx)

    if rev.created_by != ctx.user.id and membership.membership_role != MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ tác giả hoặc Owner mới có quyền hoàn tất bản đánh giá HR.",
        )

    if rev.status == "finalized":
        return HRRevisionResponse.model_validate(rev)

    if app_obj.row_version != payload.expected_application_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"VERSION_CONFLICT: Hồ sơ ứng viên đã thay đổi (hiện tại v{app_obj.row_version}, kỳ vọng v{payload.expected_application_version}).",
        )

    if rev.rubric_version_id != payload.expected_rubric_version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RUBRIC_MISMATCH: Phiên bản Rubric không khớp với phiên bản dự kiến.",
        )

    from app.schemas.assessment import AssessmentOutputSchema
    validated = AssessmentOutputSchema.model_validate(rev.criteria_payload)
    current_rubric_ids = set((await db.execute(
        select(RubricCriterion.criterion_id).where(RubricCriterion.rubric_version_id == rev.rubric_version_id)
    )).scalars().all())
    if {criterion.criterion_id for criterion in validated.criteria} != current_rubric_ids:
        raise HTTPException(422, "CRITERION_SET_MISMATCH: Bản HR không còn khớp đầy đủ rubric đã duyệt.")
    await _validate_revision_sources(db, app_obj, rev.document_id, rev.sanitized_version_id, rev.application_generation, validated.criteria)
    if app_obj.requisition.current_rubric_version_id and app_obj.requisition.current_rubric_version_id != rev.rubric_version_id:
        raise HTTPException(409, "RUBRIC_MISMATCH: Tiêu chí hiện hành đã thay đổi.")

    # Compute deterministic content hash of finalized payload
    serialized = json.dumps(rev.criteria_payload, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    now = datetime.now(timezone.utc)
    rev.status = "finalized"
    rev.finalized_by = ctx.user.id
    rev.finalized_at = now
    rev.content_hash = content_hash
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="hr_revision.finalized",
        entity_type="hr_revision",
        entity_id=rev.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "application_id": str(rev.application_id),
            "revision_no": rev.revision_no,
            "content_hash": content_hash,
            "comparable_score": str(rev.comparable_score),
        },
    )

    return HRRevisionResponse.model_validate(rev)


async def list_hr_revisions(
    db: AsyncSession,
    application_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[HRRevisionResponse]:
    """List all HR revisions for an application ordered by revision_no desc."""
    application, _ = await _verify_application_and_membership(db, application_id, ctx, require_open=False)
    from app.api.v1.independent_review import enforce_shadow_blind
    await enforce_shadow_blind(db, application, ctx)
    stmt = (
        select(HRRevision)
        .join(SanitizedVersion, HRRevision.sanitized_version_id == SanitizedVersion.id)
        .where(HRRevision.application_id == application_id)
        .where(SanitizedVersion.status != SanitizedVersionStatus.REVOKED)
        .order_by(HRRevision.revision_no.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [HRRevisionResponse.model_validate(r) for r in rows]


# ---------------- Review Attestation Domain Methods ---------------- #


async def create_review_attestation(
    db: AsyncSession,
    application_id: uuid.UUID,
    payload: AttestationCreateRequest,
    ctx: AuthenticatedContext,
) -> ReviewAttestationResponse:
    """Create a signed ReviewAttestation bound to actor, basis, and snapshot hash."""
    app_obj, membership = await _verify_application_and_membership(db, application_id, ctx)

    now = datetime.now(timezone.utc)
    run_id: Optional[uuid.UUID] = None
    hr_rev_id: Optional[uuid.UUID] = None
    doc_id: uuid.UUID = app_obj.current_document_id
    doc_sha256: str = ""
    rubric_id: Optional[uuid.UUID] = None
    manual_refs: Optional[dict[str, Any]] = None
    tech_code: Optional[str] = None
    tech_failure_ref: Optional[dict[str, Any]] = None

    # Load current document
    stmt_doc = select(Document).where(Document.id == doc_id)
    doc = (await db.execute(stmt_doc)).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tài liệu CV hiện tại không tồn tại.")
    doc_sha256 = doc.sha256

    if isinstance(payload, AttestationAssessmentReviewRequest):
        # Validate effective result
        if payload.effective_result.kind == "assessment_run":
            run_id = payload.effective_result.id
            stmt_run = select(AssessmentRun).where(
                AssessmentRun.id == run_id,
                AssessmentRun.application_id == application_id,
                AssessmentRun.status == "succeeded",
            )
            run = (await db.execute(stmt_run)).scalar_one_or_none()
            if not run:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="RUN_INVALID: Kết quả đánh giá không hợp lệ hoặc chưa hoàn tất.",
                )
            # Verify not stale
            if run.document_id != app_obj.current_document_id or run.sanitized_version_id != app_obj.current_sanitized_version_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="RUN_STALE: Đánh giá này dựa trên tài liệu cũ hoặc phiên bản sanitized cũ.",
                )
            rubric_id = run.rubric_version_id
        else:
            hr_rev_id = payload.effective_result.id
            stmt_rev = select(HRRevision).where(
                HRRevision.id == hr_rev_id,
                HRRevision.application_id == application_id,
                HRRevision.status == "finalized",
            )
            rev = (await db.execute(stmt_rev)).scalar_one_or_none()
            if not rev:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="REVISION_NOT_FINALIZED: Bản chỉnh sửa HR chưa được hoàn tất.",
                )
            rubric_id = rev.rubric_version_id

        rubric_criteria_ids = set((await db.execute(
            select(RubricCriterion.criterion_id).where(RubricCriterion.rubric_version_id == rubric_id)
        )).scalars().all())
        if (
            len(payload.reviewed_criterion_ids) != len(set(payload.reviewed_criterion_ids))
            or set(payload.reviewed_criterion_ids) != rubric_criteria_ids
        ):
            raise HTTPException(status_code=422, detail="CRITERION_REVIEW_MISMATCH: HR phải xác nhận đã rà soát toàn bộ tiêu chí của rubric.")

    elif isinstance(payload, AttestationManualDocumentRequest):
        # Requires active raw_cv grant
        stmt_grant = select(RawAccessGrant).where(
            RawAccessGrant.application_id == application_id,
            RawAccessGrant.grantee_user_id == ctx.user.id,
            RawAccessGrant.expires_at > now,
            RawAccessGrant.revoked_at.is_(None),
        )
        grant = (await db.execute(stmt_grant)).scalar_one_or_none()
        if not grant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="MANUAL_REVIEW_REQUIRES_RAW_GRANT: Đánh giá thủ công tài liệu gốc yêu cầu quyền raw_cv còn hiệu lực.",
            )

        if doc.safety_status != DocumentSafetyStatus.PASSED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="DOCUMENT_NOT_SAFE: Tài liệu chưa qua kiểm tra an toàn hoặc bị lỗi.",
            )

        if payload.expected_document_sha256 != doc.sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="DOCUMENT_HASH_MISMATCH: SHA256 tài liệu không khớp.",
            )

        rubric_id = payload.expected_rubric_version_id
        manual_rubric_ids = set((await db.execute(
            select(RubricCriterion.criterion_id).where(RubricCriterion.rubric_version_id == rubric_id)
        )).scalars().all())
        if (
            len(payload.reviewed_criterion_ids) != len(set(payload.reviewed_criterion_ids))
            or set(payload.reviewed_criterion_ids) != manual_rubric_ids
        ):
            raise HTTPException(status_code=422, detail="CRITERION_REVIEW_MISMATCH: HR phải xác nhận đã rà soát toàn bộ tiêu chí của rubric.")
        manual_refs = {"evidence_refs": [ref.model_dump(mode="json") for ref in payload.manual_evidence_refs]}

    elif isinstance(payload, AttestationTechnicalRequest):
        if payload.expected_document_sha256 != doc.sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="DOCUMENT_HASH_MISMATCH: SHA256 tài liệu không khớp.",
            )
        tech_code = payload.technical_failure_code
        tech_failure_ref = payload.failure_ref.model_dump(mode="json")

    if rubric_id is not None:
        attested_rubric = await db.get(RubricVersion, rubric_id)
        if (
            not attested_rubric
            or attested_rubric.requisition_id != app_obj.requisition_id
            or attested_rubric.status != RubricStatus.APPROVED
            or app_obj.requisition.current_rubric_version_id != rubric_id
        ):
            raise HTTPException(409, "RUBRIC_MISMATCH: Chỉ được xác nhận theo rubric hiện hành đã duyệt của requisition.")
        expected_ids = set((await db.execute(
            select(RubricCriterion.criterion_id).where(RubricCriterion.rubric_version_id == rubric_id)
        )).scalars().all())
        reviewed_ids = set(payload.reviewed_criterion_ids)
        if (
            len(payload.reviewed_criterion_ids) != len(reviewed_ids)
            or reviewed_ids != expected_ids
        ):
            raise HTTPException(422, "CRITERION_REVIEW_MISMATCH: HR phải rà soát từng criterion của rubric hiện hành.")

    # Build canonical snapshot hash
    snapshot_raw = {
        "actor_id": str(ctx.user.id),
        "decision_basis": payload.decision_basis.value,
        "application_id": str(application_id),
        "application_generation": app_obj.generation,
        "document_sha256": doc_sha256,
        "rubric_version_id": str(rubric_id) if rubric_id else None,
        "run_id": str(run_id) if run_id else None,
        "hr_revision_id": str(hr_rev_id) if hr_rev_id else None,
        "technical_failure_code": tech_code,
    }
    snapshot_hash = hashlib.sha256(json.dumps(snapshot_raw, sort_keys=True).encode("utf-8")).hexdigest()

    attestation = ReviewAttestation(
        id=uuid.uuid4(),
        application_id=application_id,
        actor_id=ctx.user.id,
        decision_basis=payload.decision_basis,
        run_id=run_id,
        hr_revision_id=hr_rev_id,
        document_id=doc_id,
        document_sha256=doc_sha256,
        rubric_version_id=rubric_id,
        snapshot_hash=snapshot_hash,
        application_generation=app_obj.generation,
        reviewed_criterion_ids=payload.reviewed_criterion_ids,
        manual_evidence_refs=manual_refs,
        technical_failure_code=tech_code,
        failure_ref=tech_failure_ref,
        acknowledged_at=now,
    )
    db.add(attestation)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="attestation.created",
        entity_type="review_attestation",
        entity_id=attestation.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "application_id": str(application_id),
            "decision_basis": payload.decision_basis.value,
            "snapshot_hash": snapshot_hash,
        },
    )

    return ReviewAttestationResponse.model_validate(attestation)


# ---------------- Final Decision Domain Methods ---------------- #


async def create_decision(
    db: AsyncSession,
    application_id: uuid.UUID,
    payload: DecisionCreateRequest,
    ctx: AuthenticatedContext,
) -> DecisionResponse:
    """Record an attested, immutable hiring decision. Owner role ONLY."""
    # Enforce Owner role
    app_obj, _ = await _verify_application_and_membership(
        db, application_id, ctx, require_owner=True
    )

    now = datetime.now(timezone.utc)

    # 1. Concurrency & active jobs guard
    # Check if there are active analysis jobs running for this application
    stmt_job = select(Job).where(
        Job.target_id == application_id,
        Job.type == JobType.ASSESS_APPLICATION,
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
    )
    active_job = (await db.execute(stmt_job)).scalar_one_or_none()
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ANALYSIS_IN_PROGRESS: Có tiến trình đánh giá đang chạy. Vui lòng chờ hoàn tất hoặc hủy tiến trình trước khi ra quyết định.",
        )

    # Check previous decision optimistic concurrency
    if payload.expected_previous_decision_id != app_obj.current_decision_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="DECISION_CONFLICT: Quyết định trước đó của hồ sơ đã thay đổi. Vui lòng tải lại trang.",
        )

    # 2. Verify Attestation
    stmt_att = select(ReviewAttestation).where(
        ReviewAttestation.id == payload.attestation_id,
        ReviewAttestation.application_id == application_id,
    )
    attestation = (await db.execute(stmt_att)).scalar_one_or_none()
    if not attestation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ATTESTATION_NOT_FOUND: Giấy chứng nhận rà soát (Attestation) không tồn tại.",
        )

    # Invariant: Owner caller MUST be the one who signed the attestation
    if attestation.actor_id != ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ATTESTATION_ACTOR_MISMATCH: Quyết định phải do chính Owner đã thực hiện rà soát và ký attestation ban hành.",
        )

    if (
        attestation.application_generation != app_obj.generation
        or attestation.document_id != app_obj.current_document_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="ATTESTATION_STALE: Hồ sơ đã thay đổi sau khi ký rà soát; cần rà soát và ký lại.",
        )
    if attestation.run_id:
        attested_run = (await db.execute(
            select(AssessmentRun).where(AssessmentRun.id == attestation.run_id)
        )).scalar_one_or_none()
        if not attested_run or attested_run.sanitized_version_id != app_obj.current_sanitized_version_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="ASSESSMENT_QUARANTINED: Kết quả AI không còn dựa trên bản CV đã che hiện hành.",
            )

    # Invariant: Matching decision basis
    if attestation.decision_basis != payload.decision_basis:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="BASIS_MISMATCH: Căn cứ quyết định không khớp với căn cứ trên attestation.",
        )

    # 3. Decision-basis specific validations
    if payload.decision_basis == DecisionBasis.TECHNICAL_INFORMATION_REQUEST:
        if payload.outcome != DecisionOutcome.REQUEST_INFORMATION:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="INVALID_OUTCOME_FOR_TECHNICAL_REQUEST: Căn cứ lỗi kỹ thuật chỉ được chọn kết quả 'request_information'.",
            )

    elif payload.decision_basis == DecisionBasis.MANUAL_DOCUMENT_REVIEW:
        if not payload.override_reason or len(payload.override_reason.strip()) < 20:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="OVERRIDE_REASON_REQUIRED: Đánh giá tài liệu thủ công bắt buộc phải có lý do điều chỉnh (override_reason) tối thiểu 20 ký tự.",
            )

    elif payload.decision_basis == DecisionBasis.ASSESSMENT_REVIEW:
        # Check if outcome diverges from recommendation
        rec_status = None
        if attestation.run_id:
            stmt_r = select(AssessmentRun).where(AssessmentRun.id == attestation.run_id)
            r_obj = (await db.execute(stmt_r)).scalar_one()
            rec_status = r_obj.recommendation
        elif attestation.hr_revision_id:
            stmt_hr = select(HRRevision).where(HRRevision.id == attestation.hr_revision_id)
            hr_obj = (await db.execute(stmt_hr)).scalar_one()
            rec_status = hr_obj.recommendation

        rec_val = rec_status.value if hasattr(rec_status, "value") else str(rec_status) if rec_status else None

        clarification_statuses: dict[str, str] = {}
        if attestation.run_id:
            stmt_criteria = select(CriterionAssessment).where(CriterionAssessment.run_id == attestation.run_id)
            for criterion in (await db.execute(stmt_criteria)).scalars().all():
                clarification_statuses[criterion.criterion_id] = criterion.status.value if hasattr(criterion.status, "value") else str(criterion.status)
        elif attestation.hr_revision_id:
            revision = await db.get(HRRevision, attestation.hr_revision_id)
            revision_criteria = ((revision.criteria_payload or {}).get("criteria") or []) if revision else []
            clarification_statuses = {
                item.get("criterion_id"): item.get("status")
                for item in revision_criteria
                if item.get("criterion_id") and item.get("status")
            }

        policy_rubric = await db.get(RubricVersion, attestation.rubric_version_id) if attestation.rubric_version_id else None
        policy = (policy_rubric.threshold_config or {}) if policy_rubric else {}
        rubric_ids = set((await db.execute(
            select(RubricCriterion.criterion_id).where(
                RubricCriterion.rubric_version_id == attestation.rubric_version_id
            )
        )).scalars().all()) if attestation.rubric_version_id else set()
        required_ids = resolve_required_criterion_ids(policy, rubric_ids)
        has_conflicting_evidence = any(
            value == CriterionOutcome.CONFLICTING_EVIDENCE.value
            for value in clarification_statuses.values()
        )
        previous = await db.get(Decision, app_obj.current_decision_id) if (
            payload.outcome == DecisionOutcome.NOT_ADVANCE
            and rec_val == Recommendation.NEEDS_CLARIFICATION.value
            and app_obj.current_decision_id
        ) else None
        previous_outcome = (
            DecisionOutcome.REQUEST_INFORMATION.value
            if is_matching_information_request(previous, application_id, attestation)
            else None
        )
        disposition_error = clarification_disposition_error(
            rec_val,
            payload.outcome.value if hasattr(payload.outcome, "value") else str(payload.outcome),
            clarification_statuses,
            required_ids,
            previous_outcome,
            payload.clarification_resolution,
        )
        if disposition_error == "MUST_HAVE_INFORMATION_REQUEST_REQUIRED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="MUST_HAVE_CLARIFICATION_REQUIRED: HR phải ghi nhận yêu cầu bổ sung thông tin trước khi cân nhắc từ chối.",
            )
        if disposition_error == "CLARIFICATION_RESOLUTION_REQUIRED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="CLARIFICATION_RESOLUTION_REQUIRED: Ghi nhận ứng viên xác nhận chưa có năng lực hoặc không phản hồi sau khi được liên hệ.",
            )
        if disposition_error == "NICE_TO_HAVE_INDEPENDENT_BASIS_REQUIRED":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="NICE_TO_HAVE_INDEPENDENT_BASIS_REQUIRED: Thiếu nice-to-have không phải căn cứ từ chối; HR phải ghi nhận căn cứ độc lập dựa trên evidence khác.",
            )

        diverged = False
        if rec_val == Recommendation.CONSIDER_NEXT_ROUND.value and payload.outcome == DecisionOutcome.NOT_ADVANCE:
            diverged = True
        elif rec_val == Recommendation.REVIEW_REQUIRED.value and payload.outcome == DecisionOutcome.ADVANCE:
            diverged = True
        elif rec_val == Recommendation.NEEDS_CLARIFICATION.value and payload.outcome in [DecisionOutcome.ADVANCE, DecisionOutcome.NOT_ADVANCE]:
            diverged = True

        if diverged and (not payload.override_reason or len(payload.override_reason.strip()) < 20):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="OVERRIDE_REASON_REQUIRED: Quyết định khác với khuyến nghị hệ thống bắt buộc phải giải trình lý do (override_reason) tối thiểu 20 ký tự.",
            )

    # 4. Anti-discrimination scan
    forbidden_reason = scan_forbidden_criteria(payload.reason)
    if forbidden_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Lý do quyết định nhắc đến thuộc tính cấm: '{forbidden_reason}'.",
        )

    if payload.override_reason:
        forbidden_override = scan_forbidden_criteria(payload.override_reason)
        if forbidden_override:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Lý do ghi đè nhắc đến thuộc tính cấm: '{forbidden_override}'.",
            )

    # 5. Lock and determine sequence number
    stmt_seq = select(func.max(Decision.sequence_no)).where(Decision.application_id == application_id)
    max_seq = (await db.execute(stmt_seq)).scalar() or 0
    next_seq = max_seq + 1

    source_snapshot = {
        "attestation_id": str(attestation.id),
        "snapshot_hash": attestation.snapshot_hash,
        "decision_basis": attestation.decision_basis.value,
        "document_sha256": attestation.document_sha256,
        "application_generation": attestation.application_generation,
    }

    decision = Decision(
        id=uuid.uuid4(),
        application_id=application_id,
        decision_basis=payload.decision_basis,
        document_id=attestation.document_id,
        rubric_version_id=attestation.rubric_version_id,
        outcome=payload.outcome,
        reason=payload.reason,
        override_reason=(
            f"clarification_resolution={payload.clarification_resolution}; {payload.override_reason or payload.reason}"
            if payload.clarification_resolution else payload.override_reason
        ),
        attestation_id=attestation.id,
        run_id=attestation.run_id,
        hr_revision_id=attestation.hr_revision_id,
        source_snapshot=source_snapshot,
        source_hash=attestation.snapshot_hash,
        decided_by=ctx.user.id,
        supersedes_decision_id=app_obj.current_decision_id,
        sequence_no=next_seq,
    )
    db.add(decision)
    await db.flush()

    # Update application pointer & row version
    from app.services.email_draft import invalidate_email_drafts
    await invalidate_email_drafts(db, [app_obj.id])
    app_obj.current_decision_id = decision.id
    app_obj.row_version += 1
    app_obj.updated_at = now
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="decision.recorded",
        entity_type="decision",
        entity_id=decision.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={
            "application_id": str(application_id),
            "sequence_no": next_seq,
            "outcome": payload.outcome.value,
            "decision_basis": payload.decision_basis.value,
        },
    )

    return DecisionResponse.model_validate(decision)


async def list_decisions(
    db: AsyncSession,
    application_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[DecisionResponse]:
    """List historical decisions for an application ordered by sequence_no desc."""
    application, _ = await _verify_application_and_membership(db, application_id, ctx, require_open=False)
    from app.api.v1.independent_review import enforce_shadow_blind
    await enforce_shadow_blind(db, application, ctx)
    stmt = (
        select(Decision)
        .where(Decision.application_id == application_id)
        .order_by(Decision.sequence_no.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [DecisionResponse.model_validate(d) for d in rows]
