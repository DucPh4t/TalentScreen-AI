"""Domain services for Interview Question Banks and Interview Agent (Task B14)."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    Application,
    AssessmentRun,
    Document,
    HRRevision,
    InterviewDraft,
    InterviewQuestionBank,
    InterviewRevision,
    Job,
    Requisition,
    RequisitionMembership,
    RubricCriterion,
    RubricVersion,
    SanitizedVersion,
    SourceSpan,
)
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import (
    AccountRole,
    CriterionId,
    JobStatus,
    JobType,
    MembershipRole,
    RequisitionStatus,
    RubricStatus,
)
from app.domain.rubric_policy import scan_forbidden_criteria
from app.schemas.decision import EffectiveResultRef
from app.schemas.interview import (
    CoreQuestionSchema,
    FollowupQuestionSchema,
    InterviewDraftCreateRequest,
    InterviewDraftResponse,
    InterviewRevisionCreateRequest,
    InterviewRevisionResponse,
    QuestionBankApproveRequest,
    QuestionBankCreateRequest,
    QuestionBankResponse,
    QuestionBankUpdateRequest,
)
from app.services.audit import record_audit_event
from app.services.interview_prompts import (
    InterviewValidationError,
    build_interview_repair_prompt,
    build_interview_system_prompt,
    build_interview_user_prompt,
    validate_interview_output,
)
from app.services.llm.provider import BaseLLMProvider, get_llm_provider
from app.services.llm.types import CompletionRequest

logger = logging.getLogger(__name__)


def get_seed_question_bank_path() -> Path:
    """Find path to seed question bank JSON."""
    candidates = [
        Path("talentscreen-mvp-plan/examples/interview-question-bank.v1.json"),
        Path("../talentscreen-mvp-plan/examples/interview-question-bank.v1.json"),
        Path(__file__).parents[4] / "talentscreen-mvp-plan" / "examples" / "interview-question-bank.v1.json",
    ]
    for p in candidates:
        if p.exists():
            return p.resolve()
    raise FileNotFoundError("Không tìm thấy file interview-question-bank.v1.json")


def load_seed_question_bank_dict() -> dict[str, Any]:
    with open(get_seed_question_bank_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def compute_bank_hash(questions_list: list[dict[str, Any]]) -> str:
    canonical = sorted(questions_list, key=lambda q: q.get("question_id", ""))
    serialized = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def _verify_rubric_and_owner(
    db: AsyncSession,
    rubric_id: uuid.UUID,
    ctx: AuthenticatedContext,
    require_owner: bool = True,
) -> tuple[RubricVersion, RequisitionMembership]:
    stmt_r = (
        select(RubricVersion)
        .options(selectinload(RubricVersion.requisition))
        .where(RubricVersion.id == rubric_id)
    )
    rubric = (await db.execute(stmt_r)).scalar_one_or_none()
    if not rubric:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rubric không tồn tại.")

    stmt_mem = select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == rubric.requisition_id,
        RequisitionMembership.user_id == ctx.user.id,
        RequisitionMembership.active.is_(True),
    )
    membership = (await db.execute(stmt_mem)).scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Không có quyền truy cập đợt tuyển dụng này.")

    if require_owner and membership.membership_role != MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ Owner của Requisition mới có quyền quản lý ngân hàng câu hỏi.",
        )

    return rubric, membership


# ---------------- Question Bank Domain Methods ---------------- #


async def create_question_bank(
    db: AsyncSession,
    rubric_id: uuid.UUID,
    payload: QuestionBankCreateRequest,
    ctx: AuthenticatedContext,
) -> QuestionBankResponse:
    """Create a new Question Bank in DRAFT status for a rubric version. Owner only."""
    rubric, _ = await _verify_rubric_and_owner(db, rubric_id, ctx, require_owner=True)

    stmt_max = select(func.max(InterviewQuestionBank.version_no)).where(
        InterviewQuestionBank.rubric_version_id == rubric_id
    )
    max_v = (await db.execute(stmt_max)).scalar() or 0
    next_v = max_v + 1

    questions_list = []
    if payload.source == "seed":
        seed_data = load_seed_question_bank_dict()
        questions_list = seed_data.get("questions", [])
    elif payload.source == "clone":
        if not payload.clone_from_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Thiếu clone_from_id khi clone ngân hàng câu hỏi.")
        stmt_clone = select(InterviewQuestionBank).where(InterviewQuestionBank.id == payload.clone_from_id)
        source_bank = (await db.execute(stmt_clone)).scalar_one_or_none()
        if not source_bank:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ngân hàng câu hỏi nguồn không tồn tại.")
        questions_list = source_bank.questions_payload.get("questions", [])

    # Validate all 6 core criteria
    c_ids = {q.get("criterion_id") for q in questions_list}
    for cid in CriterionId:
        if cid.value not in c_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"INVALID_BANK: Ngân hàng câu hỏi bắt buộc phải có câu hỏi cho tiêu chí '{cid.value}'.",
            )

    content_hash = compute_bank_hash(questions_list)

    bank = InterviewQuestionBank(
        id=uuid.uuid4(),
        rubric_version_id=rubric_id,
        version_no=next_v,
        status="draft",
        questions_payload={"questions": questions_list},
        content_hash=content_hash,
        created_by=ctx.user.id,
    )
    db.add(bank)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="question_bank.created",
        entity_type="interview_question_bank",
        entity_id=bank.id,
        requisition_id=rubric.requisition_id,
        safe_metadata={"rubric_version_id": str(rubric_id), "version_no": next_v, "status": "draft"},
    )

    return QuestionBankResponse(
        id=bank.id,
        rubric_version_id=bank.rubric_version_id,
        version_no=bank.version_no,
        status=bank.status,
        questions=[CoreQuestionSchema.model_validate(q) for q in questions_list],
        content_hash=bank.content_hash,
        approved_by=bank.approved_by,
        approved_at=bank.approved_at,
        created_at=bank.created_at,
    )


async def list_question_banks(
    db: AsyncSession,
    rubric_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[QuestionBankResponse]:
    """List all question banks for a rubric version. Members can view."""
    await _verify_rubric_and_owner(db, rubric_id, ctx, require_owner=False)

    stmt = (
        select(InterviewQuestionBank)
        .where(InterviewQuestionBank.rubric_version_id == rubric_id)
        .order_by(InterviewQuestionBank.version_no.desc())
    )
    banks = (await db.execute(stmt)).scalars().all()
    results = []
    for b in banks:
        q_list = b.questions_payload.get("questions", [])
        results.append(
            QuestionBankResponse(
                id=b.id,
                rubric_version_id=b.rubric_version_id,
                version_no=b.version_no,
                status=b.status,
                questions=[CoreQuestionSchema.model_validate(q) for q in q_list],
                content_hash=b.content_hash,
                approved_by=b.approved_by,
                approved_at=b.approved_at,
                created_at=b.created_at,
            )
        )
    return results


async def update_question_bank(
    db: AsyncSession,
    bank_id: uuid.UUID,
    payload: QuestionBankUpdateRequest,
    ctx: AuthenticatedContext,
) -> QuestionBankResponse:
    """Update a draft question bank. Invariant: Only DRAFT banks can be edited. Owner only."""
    stmt_bank = select(InterviewQuestionBank).where(InterviewQuestionBank.id == bank_id).with_for_update()
    bank = (await db.execute(stmt_bank)).scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ngân hàng câu hỏi không tồn tại.")

    rubric, _ = await _verify_rubric_and_owner(db, bank.rubric_version_id, ctx, require_owner=True)

    if bank.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="BANK_ALREADY_APPROVED: Ngân hàng câu hỏi đã được duyệt không thể chỉnh sửa trực tiếp. Vui lòng tạo phiên bản mới.",
        )

    # Anti-discrimination check on change reason and questions
    f_reason = scan_forbidden_criteria(payload.change_reason)
    if f_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Lý do thay đổi nhắc đến thuộc tính cấm: '{f_reason}'.",
        )

    q_dicts = []
    c_ids = set()
    for q in payload.questions:
        c_ids.add(q.criterion_id)
        f_q = scan_forbidden_criteria(q.question_vi)
        if f_q:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Câu hỏi cho '{q.criterion_id}' nhắc đến thuộc tính cấm: '{f_q}'.",
            )
        f_p = scan_forbidden_criteria(q.purpose_vi)
        if f_p:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Mục đích câu hỏi '{q.criterion_id}' nhắc đến thuộc tính cấm: '{f_p}'.",
            )
        q_dicts.append(q.model_dump())

    for cid in CriterionId:
        if cid.value not in c_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"MISSING_CRITERION: Thiếu câu hỏi cho tiêu chí '{cid.value}'.",
            )

    content_hash = compute_bank_hash(q_dicts)
    bank.questions_payload = {"questions": q_dicts, "change_reason": payload.change_reason}
    bank.content_hash = content_hash
    await db.flush()

    return QuestionBankResponse(
        id=bank.id,
        rubric_version_id=bank.rubric_version_id,
        version_no=bank.version_no,
        status=bank.status,
        questions=payload.questions,
        content_hash=content_hash,
        approved_by=bank.approved_by,
        approved_at=bank.approved_at,
        created_at=bank.created_at,
    )


async def approve_question_bank(
    db: AsyncSession,
    bank_id: uuid.UUID,
    payload: QuestionBankApproveRequest,
    ctx: AuthenticatedContext,
) -> QuestionBankResponse:
    """Approve a question bank, atomically superseding any previously approved bank for this rubric."""
    stmt_bank = select(InterviewQuestionBank).where(InterviewQuestionBank.id == bank_id).with_for_update()
    bank = (await db.execute(stmt_bank)).scalar_one_or_none()
    if not bank:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ngân hàng câu hỏi không tồn tại.")

    rubric, _ = await _verify_rubric_and_owner(db, bank.rubric_version_id, ctx, require_owner=True)

    if bank.rubric_version_id != payload.expected_rubric_version_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RUBRIC_MISMATCH: Phiên bản Rubric không khớp với phiên bản dự kiến.",
        )

    # Supersede previous approved banks
    stmt_sup = (
        update(InterviewQuestionBank)
        .where(
            InterviewQuestionBank.rubric_version_id == bank.rubric_version_id,
            InterviewQuestionBank.status == "approved",
        )
        .values(status="superseded")
    )
    await db.execute(stmt_sup)

    now = datetime.now(timezone.utc)
    bank.status = "approved"
    bank.approved_by = ctx.user.id
    bank.approved_at = now
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="question_bank.approved",
        entity_type="interview_question_bank",
        entity_id=bank.id,
        requisition_id=rubric.requisition_id,
        safe_metadata={
            "rubric_version_id": str(bank.rubric_version_id),
            "version_no": bank.version_no,
            "content_hash": bank.content_hash,
        },
    )

    q_list = bank.questions_payload.get("questions", [])
    return QuestionBankResponse(
        id=bank.id,
        rubric_version_id=bank.rubric_version_id,
        version_no=bank.version_no,
        status=bank.status,
        questions=[CoreQuestionSchema.model_validate(q) for q in q_list],
        content_hash=bank.content_hash,
        approved_by=bank.approved_by,
        approved_at=bank.approved_at,
        created_at=bank.created_at,
    )


# ---------------- Interview Draft Domain Methods ---------------- #


async def create_interview_draft_job(
    db: AsyncSession,
    application_id: uuid.UUID,
    payload: InterviewDraftCreateRequest,
    ctx: AuthenticatedContext,
) -> InterviewDraftResponse:
    """Enqueue an on-demand Interview Draft generation job."""
    from app.services.decision import _verify_application_and_membership
    app_obj, _ = await _verify_application_and_membership(db, application_id, ctx)

    # Invariant: Active approved Question Bank
    stmt_bank = select(InterviewQuestionBank).where(
        InterviewQuestionBank.id == payload.expected_question_bank_id,
        InterviewQuestionBank.status == "approved",
    )
    bank = (await db.execute(stmt_bank)).scalar_one_or_none()
    if not bank:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="QUESTION_BANK_NOT_APPROVED: Ngân hàng câu hỏi chưa được duyệt hoặc không tồn tại.",
        )

    # Invariant: Bank must match current approved rubric of requisition
    stmt_rubric = select(RubricVersion).where(
        RubricVersion.id == bank.rubric_version_id,
        RubricVersion.requisition_id == app_obj.requisition_id,
        RubricVersion.status == RubricStatus.APPROVED,
    )
    rubric = (await db.execute(stmt_rubric)).scalar_one_or_none()
    if not rubric:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RUBRIC_MISMATCH: Ngân hàng câu hỏi không gắn với Rubric đã duyệt hiện tại của vị trí tuyển dụng.",
        )

    # Invariant: Verify effective assessment / HR revision
    if payload.effective_result.kind == "assessment_run":
        stmt_run = select(AssessmentRun).where(
            AssessmentRun.id == payload.effective_result.id,
            AssessmentRun.application_id == application_id,
            AssessmentRun.status == "succeeded",
        )
        run = (await db.execute(stmt_run)).scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Kết quả đánh giá không hợp lệ.")
        if run.document_id != app_obj.current_document_id or run.sanitized_version_id != app_obj.current_sanitized_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="RUN_STALE: Đánh giá này dựa trên tài liệu cũ.")
    else:
        stmt_rev = select(HRRevision).where(
            HRRevision.id == payload.effective_result.id,
            HRRevision.application_id == application_id,
            HRRevision.status == "finalized",
        )
        rev = (await db.execute(stmt_rev)).scalar_one_or_none()
        if not rev:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bản đánh giá HR chưa được hoàn tất.")
        if rev.document_id != app_obj.current_document_id or rev.sanitized_version_id != app_obj.current_sanitized_version_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="REVISION_STALE: Bản đánh giá dựa trên tài liệu cũ.")

    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    source_snapshot = {
        "effective_result_kind": payload.effective_result.kind,
        "effective_result_id": str(payload.effective_result.id),
        "question_bank_id": str(bank.id),
        "rubric_version_id": str(rubric.id),
        "document_id": str(app_obj.current_document_id),
        "sanitized_version_id": str(app_obj.current_sanitized_version_id),
        "application_generation": app_obj.generation,
    }
    source_hash = hashlib.sha256(json.dumps(source_snapshot, sort_keys=True).encode("utf-8")).hexdigest()

    job = Job(
        id=job_id,
        type=JobType.DRAFT_INTERVIEW,
        target_type="interview_draft",
        status=JobStatus.QUEUED,
        target_id=draft_id,
        input_snapshot_hash=source_hash,
        payload_ref={"draft_id": str(draft_id), "application_id": str(application_id)},
        created_at=now,
    )
    db.add(job)
    await db.flush()

    draft = InterviewDraft(
        id=draft_id,
        application_id=application_id,
        job_id=job_id,
        source_snapshot=source_snapshot,
        source_hash=source_hash,
        question_bank_id=bank.id,
        status="queued",
        created_by=ctx.user.id,
    )
    db.add(draft)
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="interview_draft.enqueued",
        entity_type="interview_draft",
        entity_id=draft.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={"job_id": str(job_id), "question_bank_id": str(bank.id)},
    )

    core_q_list = bank.questions_payload.get("questions", [])
    return InterviewDraftResponse(
        id=draft.id,
        application_id=draft.application_id,
        question_bank_id=draft.question_bank_id,
        job_id=draft.job_id,
        status="queued",
        core_questions=[CoreQuestionSchema.model_validate(q) for q in core_q_list],
        ai_followups=[],
        created_at=draft.created_at,
    )


async def execute_interview_job(
    db: AsyncSession,
    job_id: uuid.UUID,
    provider_override: Optional[BaseLLMProvider] = None,
) -> None:
    """Worker job execution for Interview follow-up questions."""
    stmt_draft = (
        select(InterviewDraft)
        .options(selectinload(InterviewDraft.application), selectinload(InterviewDraft.bank))
        .where(InterviewDraft.job_id == job_id)
        .with_for_update()
    )
    draft = (await db.execute(stmt_draft)).scalar_one_or_none()
    if not draft:
        raise ValueError(f"InterviewDraft for job {job_id} not found.")

    draft.status = "running"
    await db.flush()

    app_obj = draft.application
    bank = draft.bank
    snapshot = draft.source_snapshot

    # 1. Load rubric criteria
    rubric_id = uuid.UUID(snapshot["rubric_version_id"])
    stmt_crit = select(RubricCriterion).where(RubricCriterion.rubric_version_id == rubric_id)
    criteria = (await db.execute(stmt_crit)).scalars().all()
    rubric_data = [
        {"criterion_id": c.criterion_id, "label": c.label_vi, "description": c.description_vi}
        for c in criteria
    ]

    # 2. Load core questions
    core_questions = [
        CoreQuestionSchema.model_validate(q)
        for q in bank.questions_payload.get("questions", [])
    ]

    # 3. Load assessment findings
    eff_kind = snapshot["effective_result_kind"]
    eff_id = uuid.UUID(snapshot["effective_result_id"])
    assessment_data = []

    if eff_kind == "assessment_run":
        stmt_run = select(AssessmentRun).where(AssessmentRun.id == eff_id).options(selectinload(AssessmentRun.criteria))
        run = (await db.execute(stmt_run)).scalar_one()
        assessment_data = [
            {
                "criterion_id": ca.criterion_id,
                "status": ca.status.value,
                "score": ca.score,
                "rationale": ca.rationale,
                "missing_information": ca.missing_information or [],
            }
            for ca in run.criteria
        ]
    else:
        stmt_hr = select(HRRevision).where(HRRevision.id == eff_id)
        hr_rev = (await db.execute(stmt_hr)).scalar_one()
        assessment_data = hr_rev.criteria_payload.get("criteria", [])

    # 4. Load allowed source spans
    sanitized_id = uuid.UUID(snapshot["sanitized_version_id"])
    stmt_spans = select(SourceSpan).where(SourceSpan.sanitized_version_id == sanitized_id)
    spans = (await db.execute(stmt_spans)).scalars().all()
    valid_span_ids = {s.span_id for s in spans}

    # 5. Build prompts
    sys_prompt = build_interview_system_prompt()
    user_prompt = build_interview_user_prompt(rubric_data, core_questions, assessment_data, spans)

    provider = provider_override or get_llm_provider()

    # Attempt 1
    llm_resp = await provider.complete(
        CompletionRequest(
            task_kind="interview",
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            temperature=0.2,
        )
    )

    validated_output = None
    try:
        validated_output = validate_interview_output(llm_resp.content, valid_span_ids)
    except InterviewValidationError as e:
        logger.warning(f"Interview attempt 1 failed validation: {e}. Executing bounded repair attempt 2.")
        # Attempt 2 Bounded Repair
        repair_user_prompt = build_interview_repair_prompt(user_prompt, e.errors)
        llm_resp2 = await provider.complete(
            CompletionRequest(
                task_kind="repair",
                system_prompt=sys_prompt,
                user_prompt=repair_user_prompt,
                temperature=0.0,
            )
        )
        validated_output = validate_interview_output(llm_resp2.content, valid_span_ids)

    # SEC-10 Late arrival / Deletion check
    stmt_app_check = select(Application.status, Application.generation).where(Application.id == draft.application_id)
    app_check = (await db.execute(stmt_app_check)).first()
    if not app_check or app_check[0] == "deleted" or app_check[1] > snapshot.get("application_generation", 1):
        logger.warning(f"Application {draft.application_id} was deleted or tombstoned during interview LLM call. Discarding output.")
        draft.status = "failed"
        await db.flush()
        return

    # 6. Save validated followups
    draft.questions_payload = {
        "followups": [f.model_dump() for f in validated_output.followups]
    }
    draft.status = "succeeded"
    await db.flush()

    await record_audit_event(
        db,
        actor_id=draft.created_by,
        action="interview_draft.completed",
        entity_type="interview_draft",
        entity_id=draft.id,
        requisition_id=app_obj.requisition_id,
        safe_metadata={"followup_count": len(validated_output.followups)},
    )


async def get_interview_draft_detail(
    db: AsyncSession,
    draft_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> InterviewDraftResponse:
    """Fetch complete Interview Draft with core bank questions rendered read-only, AI followups, and latest HR revision."""
    stmt = (
        select(InterviewDraft)
        .options(
            selectinload(InterviewDraft.application),
            selectinload(InterviewDraft.bank),
            selectinload(InterviewDraft.revisions),
        )
        .where(InterviewDraft.id == draft_id)
    )
    draft = (await db.execute(stmt)).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bộ câu hỏi phỏng vấn không tồn tại.")

    from app.services.decision import _verify_application_and_membership
    await _verify_application_and_membership(db, draft.application_id, ctx)

    core_q_list = draft.bank.questions_payload.get("questions", [])
    ai_followups_list = (draft.questions_payload or {}).get("followups", [])

    # Latest revision if any
    latest_rev = None
    if draft.revisions:
        sorted_revs = sorted(draft.revisions, key=lambda r: r.revision_no, reverse=True)
        r_top = sorted_revs[0]
        latest_rev = InterviewRevisionResponse(
            id=r_top.id,
            interview_draft_id=r_top.interview_draft_id,
            revision_no=r_top.revision_no,
            followups=[FollowupQuestionSchema.model_validate(f) for f in r_top.followups_payload.get("followups", [])],
            change_reason=r_top.change_reason,
            created_by=r_top.created_by,
            created_at=r_top.created_at,
        )

    # Staleness checks
    app_obj = draft.application
    snapshot = draft.source_snapshot
    is_stale = False
    stale_reasons = []

    if snapshot.get("document_id") != str(app_obj.current_document_id):
        is_stale = True
        stale_reasons.append("DOCUMENT_CHANGED: Ứng viên đã nộp tài liệu CV mới.")

    if snapshot.get("sanitized_version_id") != str(app_obj.current_sanitized_version_id):
        is_stale = True
        stale_reasons.append("SANITIZED_VERSION_CHANGED: Phiên bản sanitized mới đã được tạo.")

    if draft.bank.status != "approved":
        is_stale = True
        stale_reasons.append("QUESTION_BANK_SUPERSEDED: Ngân hàng câu hỏi cốt lõi đã có phiên bản mới.")

    return InterviewDraftResponse(
        id=draft.id,
        application_id=draft.application_id,
        question_bank_id=draft.question_bank_id,
        job_id=draft.job_id,
        status=draft.status,
        core_questions=[CoreQuestionSchema.model_validate(q) for q in core_q_list],
        ai_followups=[FollowupQuestionSchema.model_validate(f) for f in ai_followups_list],
        latest_revision=latest_rev,
        is_stale=is_stale,
        stale_reasons=stale_reasons,
        created_at=draft.created_at,
    )


async def create_interview_revision(
    db: AsyncSession,
    draft_id: uuid.UUID,
    payload: InterviewRevisionCreateRequest,
    ctx: AuthenticatedContext,
) -> InterviewRevisionResponse:
    """Create an HR revision for candidate-specific follow-ups. Invariant: Core bank text CANNOT be modified here."""
    stmt_draft = (
        select(InterviewDraft)
        .options(selectinload(InterviewDraft.application))
        .where(InterviewDraft.id == draft_id)
        .with_for_update()
    )
    draft = (await db.execute(stmt_draft)).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bộ câu hỏi phỏng vấn không tồn tại.")

    from app.services.decision import _verify_application_and_membership
    await _verify_application_and_membership(db, draft.application_id, ctx)

    # Optimistic concurrency check
    if payload.expected_previous_revision_id != draft.current_revision_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="CONCURRENT_EDIT_CONFLICT: Phiên bản chỉnh sửa câu hỏi đã thay đổi. Vui lòng tải lại trang.",
        )

    # Anti-discrimination check
    f_reason = scan_forbidden_criteria(payload.change_reason)
    if f_reason:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Lý do chỉnh sửa nhắc đến thuộc tính cấm: '{f_reason}'.",
        )

    for idx, f in enumerate(payload.followups):
        f_q = scan_forbidden_criteria(f.question_vi)
        if f_q:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Câu hỏi follow-up {idx} nhắc đến thuộc tính cấm: '{f_q}'.",
            )
        f_p = scan_forbidden_criteria(f.purpose_vi)
        if f_p:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Mục đích follow-up {idx} nhắc đến thuộc tính cấm: '{f_p}'.",
            )
        for ind in f.answer_indicators:
            f_ind = scan_forbidden_criteria(ind)
            if f_ind:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Tiêu chí trả lời follow-up {idx} nhắc đến thuộc tính cấm: '{f_ind}'.",
                )

    stmt_max = select(func.max(InterviewRevision.revision_no)).where(
        InterviewRevision.interview_draft_id == draft_id
    )
    max_rev = (await db.execute(stmt_max)).scalar() or 0
    next_rev = max_rev + 1

    serialized = json.dumps([f.model_dump() for f in payload.followups], sort_keys=True)
    source_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    revision = InterviewRevision(
        id=uuid.uuid4(),
        interview_draft_id=draft_id,
        revision_no=next_rev,
        followups_payload={"followups": [f.model_dump() for f in payload.followups]},
        change_reason=payload.change_reason,
        created_by=ctx.user.id,
        source_hash=source_hash,
    )
    db.add(revision)
    await db.flush()

    draft.current_revision_id = revision.id
    await db.flush()

    await record_audit_event(
        db,
        actor_id=ctx.user.id,
        action="interview_revision.created",
        entity_type="interview_revision",
        entity_id=revision.id,
        requisition_id=draft.application.requisition_id,
        safe_metadata={"draft_id": str(draft_id), "revision_no": next_rev},
    )

    return InterviewRevisionResponse(
        id=revision.id,
        interview_draft_id=revision.interview_draft_id,
        revision_no=revision.revision_no,
        followups=payload.followups,
        change_reason=revision.change_reason,
        created_by=revision.created_by,
        created_at=revision.created_at,
    )


async def list_interview_revisions(
    db: AsyncSession,
    draft_id: uuid.UUID,
    ctx: AuthenticatedContext,
) -> list[InterviewRevisionResponse]:
    """List historical follow-up revisions for an interview draft."""
    stmt_draft = select(InterviewDraft).where(InterviewDraft.id == draft_id)
    draft = (await db.execute(stmt_draft)).scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bộ câu hỏi phỏng vấn không tồn tại.")

    from app.services.decision import _verify_application_and_membership
    await _verify_application_and_membership(db, draft.application_id, ctx)

    stmt = (
        select(InterviewRevision)
        .where(InterviewRevision.interview_draft_id == draft_id)
        .order_by(InterviewRevision.revision_no.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        InterviewRevisionResponse(
            id=r.id,
            interview_draft_id=r.interview_draft_id,
            revision_no=r.revision_no,
            followups=[FollowupQuestionSchema.model_validate(f) for f in r.followups_payload.get("followups", [])],
            change_reason=r.change_reason,
            created_by=r.created_by,
            created_at=r.created_at,
        )
        for r in rows
    ]
