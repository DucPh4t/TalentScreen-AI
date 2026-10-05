"""Read-only, Owner-only grounded Copilot. No transcripts or raw CVs are stored."""
from __future__ import annotations
import hashlib, json, uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import Application, AssessmentRun, CriterionAssessment, CriterionEvidence, JDVersion, Job, Requisition, RubricCriterion, RubricVersion, SanitizedVersion, SourceSpan
from app.domain.authorization import AuthenticatedContext, get_current_context
from app.domain.enums import JobStatus, JobType, RubricStatus, SanitizedVersionStatus
from app.api.v1.workflow import _authorized_requisition
from app.services.audit import record_audit_event
from app.services.copilot_prompt import PROMPT_VERSION, SYSTEM_PROMPT
from app.services.llm.orchestrator import execute_bounded_llm_call
from app.services.llm.types import CompletionRequest
from app.services.llm.exceptions import LLMProviderError
from app.services.sanitizer import residual_contact_types
from app.config import get_settings

router = APIRouter(tags=["Copilot"])
class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=3, max_length=600)
class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["explain", "missing", "questions", "out_of_scope"]
    criterion_ids: list[str] = Field(max_length=12)

async def context_for(db: AsyncSession, id: uuid.UUID, ctx: AuthenticatedContext):
    application = await db.get(Application, id, populate_existing=True)
    if application is None or application.status != "active": raise HTTPException(404, "Không tìm thấy hồ sơ đang hoạt động.")
    requisition = await _authorized_requisition(db, application.requisition_id, ctx, owner_only=True)
    await db.refresh(requisition)
    version = await db.get(SanitizedVersion, application.current_sanitized_version_id, populate_existing=True) if application.current_sanitized_version_id else None
    rubric = await db.get(RubricVersion, requisition.current_rubric_version_id) if requisition.current_rubric_version_id else None
    run = await db.get(AssessmentRun, application.current_assessment_run_id) if application.current_assessment_run_id else None
    jd = await db.get(JDVersion, requisition.current_jd_version_id) if requisition.current_jd_version_id else None
    if not (version and version.status == SanitizedVersionStatus.APPROVED and version.document_id == application.current_document_id
            and rubric and rubric.status == RubricStatus.APPROVED and jd and jd.egress_reviewed_at
            and rubric.jd_version_id == jd.id and run and run.status == "succeeded"
            and run.document_id == application.current_document_id and run.sanitized_version_id == version.id
            and run.rubric_version_id == rubric.id and run.application_generation == application.generation):
        raise HTTPException(409, "Copilot cần CV, JD đã duyệt gửi AI và đánh giá còn hiệu lực theo tiêu chí hiện hành.")
    if residual_contact_types(version.canonical_text) or residual_contact_types(jd.source_text):
        raise HTTPException(409, "Nguồn còn thông tin liên hệ; cần rà soát trước khi dùng Copilot.")
    pending = (await db.execute(select(func.count(Job.id)).where(Job.target_id == id, Job.type == JobType.ASSESS_APPLICATION,
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRY_WAIT])))).scalar_one()
    if pending: raise HTTPException(409, "Đánh giá mới đang xử lý; đợi hoàn tất trước khi hỏi Copilot.")
    return application, requisition, version, rubric, run, jd

@router.post("/applications/{id}/copilot")
async def ask(id: uuid.UUID, payload: Question, db: AsyncSession = Depends(get_db), ctx: AuthenticatedContext = Depends(get_current_context)):
    application, requisition, version, rubric, run, jd = await context_for(db, id, ctx)
    if residual_contact_types(payload.message): raise HTTPException(422, "Không nhập thông tin liên hệ vào câu hỏi Copilot.")
    definitions = (await db.execute(select(RubricCriterion).where(RubricCriterion.rubric_version_id == rubric.id))).scalars().all()
    results = (await db.execute(select(CriterionAssessment).where(CriterionAssessment.run_id == run.id))).scalars().all()
    spans = {span.span_id: span for span in (await db.execute(select(SourceSpan).where(SourceSpan.sanitized_version_id == version.id))).scalars().all()}
    evidence_rows = (await db.execute(select(CriterionEvidence).where(CriterionEvidence.run_id == run.id))).scalars().all()
    facts = []
    for criterion in definitions:
        result = next((row for row in results if row.criterion_id == criterion.criterion_id), None)
        if result is None: continue
        evidence = []
        for item in [row for row in evidence_rows if row.criterion_id == result.criterion_id]:
            span = spans.get(item.span_id)
            if not span or item.quote != span.text or version.canonical_text[span.start_cp:span.end_cp] != span.text:
                raise HTTPException(409, "Bằng chứng không còn khớp nguồn. Cần chạy lại đánh giá.")
            evidence.append({"span_id": span.span_id, "quote": span.text, "resolved_start_cp": span.start_cp, "resolved_end_cp": span.end_cp})
        facts.append({"criterion_id": criterion.criterion_id, "label": criterion.label_vi, "description": criterion.description_vi,
                      "status": result.status.value, "score": result.score, "rationale": result.rationale,
                      "missing_information": result.missing_information or [], "evidence": evidence})
    if len(facts) != len(definitions) or not facts: raise HTTPException(409, "Kết quả đánh giá chưa đầy đủ.")
    # Admit under a per-actor transaction lock. Cost cap is independently enforced by the LLM ledger.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "copilot-global-admission"})
    now = datetime.now(timezone.utc)
    count = (await db.execute(select(func.count(Job.id)).where(Job.type == JobType.COPILOT_SELECT,
        Job.created_at >= now - timedelta(minutes=1), Job.payload_ref["actor_id"].astext == str(ctx.user.id)))).scalar_one()
    if count >= 3: raise HTTPException(429, "Tối đa 3 câu hỏi/phút. Hãy đọc câu trả lời hiện có trước khi hỏi tiếp.")
    active_calls = (await db.execute(select(func.count(Job.id)).where(Job.type == JobType.COPILOT_SELECT, Job.status == JobStatus.RUNNING, Job.lease_expires_at > now))).scalar_one()
    if active_calls >= get_settings().LLM_MAX_CONCURRENCY: raise HTTPException(429, "Copilot đang phục vụ yêu cầu khác; thử lại sau khi hoàn tất.")
    snapshot = (application.generation, version.id, rubric.id, run.id)
    job = Job(type=JobType.COPILOT_SELECT, status=JobStatus.RUNNING, target_type="application", target_id=id,
              input_snapshot_hash=hashlib.sha256(str(snapshot).encode()).hexdigest(),
              payload_ref={"actor_id": str(ctx.user.id), "prompt_version": PROMPT_VERSION},
              lease_owner="copilot-http", lease_expires_at=now + timedelta(seconds=120))
    db.add(job); await db.commit()
    job_id = job.id
    try:
        result = await execute_bounded_llm_call(db, job_id, CompletionRequest(task_kind="copilot", system_prompt=SYSTEM_PROMPT,
            user_prompt=json.dumps({"question": payload.message, "facts": [{key: fact[key] for key in ("criterion_id", "label", "status", "score")} for fact in facts]}, ensure_ascii=False),
            model=get_settings().DEEPSEEK_MODEL, max_output_tokens=256, timeout_seconds=45, thinking_mode="disabled"),
            logical_step=PROMPT_VERSION, attempt_no=1, sanitized_version_id=version.id)
        selected = Selection.model_validate_json(result.content)
        if len(set(selected.criterion_ids)) != len(selected.criterion_ids) or not set(selected.criterion_ids).issubset({fact["criterion_id"] for fact in facts}):
            raise ValueError("Unknown source selections")
        current = await context_for(db, id, ctx)
        if snapshot != (current[0].generation, current[2].id, current[3].id, current[4].id):
            raise HTTPException(409, "Hồ sơ thay đổi trong lúc trả lời; hãy tải lại trước khi hỏi tiếp.")
        job = await db.get(Job, job_id)
        if job.cancel_requested_at: raise HTTPException(409, "Yêu cầu đã bị hủy.")
        job.status = JobStatus.SUCCEEDED; job.lease_expires_at = None
        await record_audit_event(db, actor_id=ctx.user.id, action="copilot.answered", entity_type="application", entity_id=id,
            requisition_id=requisition.id, safe_metadata={"job_id": str(job_id), "prompt_version": PROMPT_VERSION, "criterion_ids": selected.criterion_ids})
        await db.commit()
    except Exception as exc:
        await db.rollback()
        job = await db.get(Job, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.last_error_code = exc.error_code if isinstance(exc, LLMProviderError) else "COPILOT_INVALID_SELECTION" if isinstance(exc, ValueError) else "COPILOT_RESPONSE_UNAVAILABLE"
            job.lease_expires_at = None
        await db.commit()
        if isinstance(exc, HTTPException): raise
        raise HTTPException(503, "Copilot chưa trả lời được. Kết quả đánh giá đã lưu vẫn có thể xem; không tự chạy lại để tránh phí trùng.") from None
    chosen = [] if selected.mode == "out_of_scope" else [fact for fact in facts if fact["criterion_id"] in selected.criterion_ids]
    if selected.mode == "missing": chosen = [fact for fact in chosen if fact["status"] != "assessed"]
    questions = [f"Bạn hãy trình bày một ví dụ cụ thể về {fact['label']}, vai trò của bạn và kết quả có thể kiểm chứng." for fact in chosen][:3] if selected.mode == "questions" else []
    return {"mode": selected.mode, "message": "Thông tin đối chiếu từ đánh giá đã lưu; HR cần kiểm tra bằng chứng." if chosen else "Chưa có thông tin phù hợp trong nguồn hiện tại. Copilot chỉ hỗ trợ giải thích tiêu chí, bằng chứng và câu hỏi làm rõ.",
            "facts": chosen, "questions": questions, "run_id": str(run.id), "sanitized_version_id": str(version.id),
            "rubric_version_id": str(rubric.id), "prompt_version": PROMPT_VERSION, "provider": get_settings().LLM_PROVIDER}
