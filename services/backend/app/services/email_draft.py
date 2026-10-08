"""Versioned correspondence templates. No LLM, delivery tool, or autonomous hiring action."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import logging
from typing import Any, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models.assessment import AssessmentRun, CriterionAssessment
from app.db.models.candidate import Application, Candidate
from app.db.models.decision import Decision
from app.db.models.email_draft import EmailDraft
from app.db.models.requisition import Requisition, RequisitionMembership
from app.domain.authorization import AuthenticatedContext
from app.domain.enums import DecisionBasis, DecisionOutcome, MembershipRole, RequisitionStatus, SanitizedVersionStatus
from app.db.models.document import SanitizedVersion
from app.db.models.requisition import RubricCriterion, RubricVersion
from app.services.audit import record_audit_event
from app.services.sanitizer import residual_contact_types

logger = logging.getLogger(__name__)


def _compose_invitation_email(requisition_title: str, candidate_label: str) -> tuple[str, str]:
    subject = f"[TalentScreen] Thư mời tham gia phỏng vấn chuyên môn — Vị trí {requisition_title} ({candidate_label})"
    body = f"""Kính gửi Ứng viên {candidate_label},

Bộ phận Tuyển dụng trân trọng cảm ơn bạn đã quan tâm và ứng tuyển cho vị trí {requisition_title}.

Qua vòng rà soát hồ sơ năng lực chuyên môn và đối chiếu tiêu chuẩn kỹ thuật của vị trí, chúng tôi đánh giá cao kinh nghiệm thực tế cùng nền tảng chuyên môn của bạn. Ban tuyển dụng trân trọng kính mời bạn tham gia Vòng phỏng vấn chuyên môn (Technical Interview).

Thông tin chi tiết về buổi trao đổi:
• Hình thức: Phỏng vấn trực tuyến (Google Meet / MS Teams) hoặc trực tiếp tại văn phòng
• Thời lượng dự kiến: 45 – 60 phút
• Thành phần tham dự: Tech Lead / Hiring Manager và Chuyên viên Tuyển dụng
• Nội dung chính:
  - Trao đổi sâu về các dự án thực tế và các giải pháp kiến trúc bạn đã triển khai
  - Thảo luận về phương pháp giải quyết vấn đề kỹ thuật và môi trường làm việc
  - Lắng nghe những kỳ vọng và định hướng phát triển của bạn

Khung giờ đề xuất (vui lòng chọn 1 khung giờ thuận tiện nhất):
  [ ] Lựa chọn 1: 09:30 - 10:30, [Ngày làm việc tới]
  [ ] Lựa chọn 2: 14:30 - 15:30, [Ngày làm việc tới]
  [ ] Khung giờ khác phù hợp với lịch của bạn: [Vui lòng phản hồi]

Bạn vui lòng phản hồi lại email này trước 17:00 ngày [Ngày xác nhận] để chúng tôi hoàn tất lịch hẹn và gửi thư mời lịch kèm đường dẫn phỏng vấn.

Nếu có bất kỳ câu hỏi nào cần giải đáp thêm, bạn đừng ngần ngại phản hồi trực tiếp qua email này.

Chúc bạn một ngày làm việc hiệu quả và nhiều niềm vui!

Trân trọng,
Bộ phận Tuyển dụng & Đội ngũ Kỹ thuật
TalentScreen AI"""
    return subject, body


def _compose_clarification_email(
    requisition_title: str,
    candidate_label: str,
    clarification_points: list[str],
) -> tuple[str, str]:
    subject = f"[TalentScreen] Đề nghị làm rõ thông tin chuyên môn — Vị trí {requisition_title} ({candidate_label})"

    clarification_points = [point for point in clarification_points if not unsafe_email_content(point) and not residual_contact_types(point)]
    points_text = ""
    if clarification_points:
        formatted = "\n".join(f"  • {pt}" for pt in clarification_points[:4])
        points_text = f"\nMột số nội dung cụ thể ban chuyên môn mong muốn được tìm hiểu thêm:\n{formatted}\n"
    else:
        points_text = "\nBan chuyên môn mong muốn bạn chia sẻ thêm một số ví dụ thực tế hoặc dự án tiêu biểu minh họa cho kinh nghiệm kỹ thuật gần nhất của bạn.\n"

    body = f"""Kính gửi Ứng viên {candidate_label},

Cảm ơn bạn đã nộp hồ sơ ứng tuyển vị trí {requisition_title}.

Trong quá trình xem xét hồ sơ năng lực theo các tiêu chuẩn trọng tâm của vị trí, Hội đồng tuyển dụng mong muốn trao đổi thêm một số thông tin kỹ thuật bổ sung để có đánh giá toàn diện và khách quan nhất.
{points_text}
Bạn có thể phản hồi trực tiếp qua email này kèm theo mô tả tóm tắt kinh nghiệm hoặc liên kết (GitHub, tài liệu kỹ thuật, portfolio nếu có).

Chúng tôi rất mong nhận được thông tin phản hồi từ bạn trong vòng 3 ngày làm việc kể từ khi nhận được email này.

Trân trọng cảm ơn sự hợp tác của bạn!

Ban Tuyển dụng Chuyên môn
TalentScreen AI"""
    return subject, body


def _compose_rejection_email(requisition_title: str, candidate_label: str) -> tuple[str, str]:
    subject = f"[TalentScreen] Thông báo kết quả rà soát hồ sơ — Vị trí {requisition_title} ({candidate_label})"
    body = f"""Kính gửi Ứng viên {candidate_label},

Lời đầu tiên, Bộ phận Tuyển dụng xin gửi lời cảm ơn chân thành đến bạn vì đã dành thời gian và sự quan tâm đối với vị trí {requisition_title}.

Sau khi rà soát kỹ lưỡng hồ sơ năng lực theo các tiêu chí chuyên môn ưu tiên của đợt tuyển dụng hiện tại, chúng tôi rất tiếc phải thông báo rằng hiện chưa thể sắp xếp cơ hội phỏng vấn tiếp theo cùng bạn cho vị trí này. Quyết định này chỉ phản ánh mức độ phù hợp cụ thể với các yêu cầu trọng tâm của dự án ở thời điểm hiện tại, hoàn toàn không phủ nhận những kinh nghiệm và nỗ lực nghề nghiệp quý báu của bạn.

Chúc bạn luôn gặt hái được nhiều thành công và phát triển vượt bậc trên con đường sự nghiệp.

Trân trọng cảm ơn,
Bộ phận Tuyển dụng
TalentScreen AI"""
    return subject, body


TEMPLATES = {"interview_invitation", "technical_clarification", "rejection_polite"}
OUTCOME_TEMPLATE = {
    DecisionOutcome.ADVANCE: "interview_invitation",
    DecisionOutcome.REQUEST_INFORMATION: "technical_clarification",
    DecisionOutcome.NOT_ADVANCE: "rejection_polite",
}
_INTERNAL_CONTENT = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*/\s*(?:4|100)\b|\b\d+(?:[.,]\d+)?\s*%"
    r"|\b(?:rubric|comparable_score|observed_score|missing_information|source_spans?|system_prompt|tool_call)\b"
    r"|\b(?:spn_[a-z0-9_]+|sk-[a-z0-9_-]+)\b"
    r"|\b(?:score|rating|coverage|confidence|recommendation|not_advance|consider_next_round|needs_clarification)\b"
    r"|(?:điểm\s*(?:số|đánh giá|nội bộ|của bạn|ứng viên)|xếp hạng|thiếu core|dưới ngưỡng)", re.IGNORECASE)


def unsafe_email_content(text: str) -> bool:
    return bool(_INTERNAL_CONTENT.search(text))


def _validate_content(subject: str, body: str) -> None:
    if unsafe_email_content(subject + "\n" + body):
        raise HTTPException(422, "EMAIL_CONTENT_UNSAFE: Thư chứa điểm số hoặc dữ liệu đánh giá nội bộ; hãy sửa trước khi lưu/duyệt.")


def _snapshot(application, requisition) -> str:
    material = {"decision": str(application.current_decision_id), "assessment": str(application.current_assessment_run_id),
        "generation": application.generation, "document": str(application.current_document_id),
        "sanitized": str(application.current_sanitized_version_id), "rubric": str(requisition.current_rubric_version_id),
        "jd": str(requisition.current_jd_version_id)}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


async def invalidate_email_drafts(db: AsyncSession, application_ids: list[uuid.UUID]) -> None:
    if application_ids:
        await db.execute(update(EmailDraft).where(EmailDraft.application_id.in_(application_ids),
            EmailDraft.status != "invalidated").values(status="invalidated", updated_at=datetime.now(timezone.utc)))


async def _verify_application_access(db, application_id, ctx, *, write=False):
    stmt = select(Application).where(Application.id == application_id).options(
        selectinload(Application.requisition), selectinload(Application.candidate))
    application = (await db.execute(stmt)).scalar_one_or_none()
    if not application or application.status != "active":
        raise HTTPException(404, "Hồ sơ ứng viên không tồn tại.")
    membership = (await db.execute(select(RequisitionMembership).where(
        RequisitionMembership.requisition_id == application.requisition_id,
        RequisitionMembership.user_id == ctx.user.id, RequisitionMembership.active.is_(True)))).scalar_one_or_none()
    if not membership or membership.membership_role != MembershipRole.OWNER:
        raise HTTPException(403, "Chỉ Owner của đợt tuyển dụng được quản lý thư ứng viên.")
    if write:
        await db.execute(select(Requisition.id).where(Requisition.id == application.requisition_id).with_for_update())
        # Use the same Requisition -> Application order as rubric approval.
        application = (await db.execute(select(Application).where(Application.id == application_id)
            .options(selectinload(Application.requisition), selectinload(Application.candidate))
            .with_for_update().execution_options(populate_existing=True))).scalar_one()
        if application.status != "active":
            raise HTTPException(404, "Hồ sơ ứng viên không còn hoạt động.")
        await db.refresh(application.requisition)
        if application.requisition.status == RequisitionStatus.CLOSED:
            raise HTTPException(409, "REQUISITION_CLOSED: Đợt đã đóng.")
    return application, application.requisition, application.candidate


def _dto(draft):
    return {"id": str(draft.id), "application_id": str(draft.application_id),
        "decision_id": str(draft.decision_id) if draft.decision_id else None,
        "template_type": draft.template_type, "subject": draft.subject, "body": draft.body,
        "variables": draft.variables, "status": draft.status, "version_no": draft.version_no,
        "created_by": str(draft.created_by) if draft.created_by else None,
        "approved_by": str(draft.approved_by) if draft.approved_by else None,
        "approved_at": draft.approved_at.isoformat() if draft.approved_at else None,
        "created_at": draft.created_at.isoformat(), "updated_at": draft.updated_at.isoformat()}


async def _latest(db, application_id):
    return (await db.execute(select(EmailDraft).where(EmailDraft.application_id == application_id)
        .order_by(EmailDraft.version_no.desc()))).scalars().first()


async def get_email_draft(db: AsyncSession, application_id: uuid.UUID, ctx: AuthenticatedContext):
    application, requisition, _ = await _verify_application_access(db, application_id, ctx)
    draft = await _latest(db, application_id)
    if draft is None:
        raise HTTPException(404, "Chưa có thư nháp. Tạo mẫu thư bằng thao tác riêng.")
    await _validate_fresh_source(db, application, requisition, draft)
    return _dto(draft)


async def _validate_fresh_source(db, application, requisition, draft):
    if draft.status == "invalidated" or draft.source_snapshot_hash != _snapshot(application, requisition):
        raise HTTPException(410, "EMAIL_DRAFT_STALE: Quyết định hoặc nguồn đã đổi. Tạo thư nháp mới và duyệt lại.")
    if application.current_sanitized_version_id:
        version = await db.get(SanitizedVersion, application.current_sanitized_version_id)
        if version is None or version.status in {SanitizedVersionStatus.REVOKED, SanitizedVersionStatus.SUPERSEDED}:
            raise HTTPException(410, "EMAIL_SOURCE_UNAVAILABLE: Nguồn CV đã che không còn hiệu lực.")


async def get_or_generate_email_draft(db: AsyncSession, application_id: uuid.UUID, ctx: AuthenticatedContext,
                                      force_template: Optional[str] = None):
    """Generate an explicit draft. AI recommendations never authorize an invitation or rejection."""
    application, requisition, candidate = await _verify_application_access(db, application_id, ctx, write=True)
    decision = await db.get(Decision, application.current_decision_id) if application.current_decision_id else None
    template = force_template or (OUTCOME_TEMPLATE.get(decision.outcome) if decision else None) or "technical_clarification"
    if template not in TEMPLATES:
        raise HTTPException(422, "INVALID_EMAIL_TEMPLATE: Chọn thư mời, yêu cầu làm rõ hoặc thông báo kết quả.")
    clarification_points = []
    if template == "technical_clarification" and application.current_assessment_run_id:
        run = (await db.execute(select(AssessmentRun).where(AssessmentRun.id == application.current_assessment_run_id)
            .options(selectinload(AssessmentRun.criteria)))).scalar_one_or_none()
        if run and run.status == "succeeded" and run.application_generation == application.generation and (
            run.rubric_version_id == requisition.current_rubric_version_id and run.document_id == application.current_document_id
            and run.sanitized_version_id == application.current_sanitized_version_id):
            version = await db.get(SanitizedVersion, run.sanitized_version_id)
            if version and version.status == SanitizedVersionStatus.APPROVED:
                labels = {criterion.criterion_id: criterion.label_vi for criterion in (await db.execute(select(RubricCriterion)
                    .where(RubricCriterion.rubric_version_id == run.rubric_version_id))).scalars()}
                # Model free text is never copied into candidate communications.
                for criterion in run.criteria:
                    label = labels.get(criterion.criterion_id)
                    if label and (criterion.missing_information or criterion.score is None):
                        clarification_points.append(f"Bạn có thể chia sẻ một ví dụ thực tế thể hiện năng lực {label} không?")
    composer = {"interview_invitation": _compose_invitation_email, "rejection_polite": _compose_rejection_email}.get(template)
    subject, body = composer(requisition.title, candidate.public_label) if composer else _compose_clarification_email(
        requisition.title, candidate.public_label, clarification_points)
    _validate_content(subject, body)
    latest = await _latest(db, application_id)
    await invalidate_email_drafts(db, [application_id])
    now = datetime.now(timezone.utc)
    draft = EmailDraft(id=uuid.uuid4(), application_id=application_id, decision_id=decision.id if decision else None,
        version_no=(latest.version_no + 1 if latest else 1), source_snapshot_hash=_snapshot(application, requisition),
        created_by=ctx.user.id, template_type=template, subject=subject, body=body, status="draft",
        variables={"generator": "template-v2", "clarification_count": len(clarification_points)}, created_at=now, updated_at=now)
    db.add(draft)
    await db.flush()
    await record_audit_event(db, actor_id=ctx.user.id, action="email_draft.created", entity_type="email_draft", entity_id=draft.id,
        requisition_id=requisition.id, safe_metadata={"version_no": draft.version_no, "template_type": template})
    return _dto(draft)


async def update_email_draft(db: AsyncSession, application_id: uuid.UUID, subject_text: str, body_text: str,
                            status_str: str, ctx: AuthenticatedContext, draft_id: uuid.UUID,
                            expected_version: int, acknowledged_content: bool = False):
    application, requisition, _ = await _verify_application_access(db, application_id, ctx, write=True)
    previous = await _latest(db, application_id)
    if previous is None or previous.id != draft_id or previous.version_no != expected_version:
        raise HTTPException(409, "EMAIL_VERSION_CONFLICT: Thư đã đổi; tải lại trước khi sửa/duyệt.")
    await _validate_fresh_source(db, application, requisition, previous)
    _validate_content(subject_text, body_text)
    if status_str not in {"draft", "approved"}:
        raise HTTPException(422, "INVALID_EMAIL_STATUS")
    if status_str == "approved":
        decision = await db.get(Decision, application.current_decision_id) if application.current_decision_id else None
        if not acknowledged_content:
            raise HTTPException(422, "EMAIL_REVIEW_REQUIRED: Xác nhận đã kiểm tra nội dung trước khi duyệt.")
        if decision is None or decision.id != previous.decision_id or OUTCOME_TEMPLATE.get(decision.outcome) != previous.template_type:
            raise HTTPException(409, "EMAIL_DECISION_REQUIRED: Thư phải phù hợp quyết định hiện hành của HR.")
        if (decision.document_id != application.current_document_id
            or decision.source_snapshot.get("application_generation") != application.generation
            or (decision.decision_basis != DecisionBasis.TECHNICAL_INFORMATION_REQUEST
                and decision.rubric_version_id != requisition.current_rubric_version_id)
            or (decision.run_id and decision.run_id != application.current_assessment_run_id)):
            raise HTTPException(409, "EMAIL_DECISION_STALE: Cần HR rà soát lại quyết định theo nguồn hiện hành.")
        if decision.decision_basis != DecisionBasis.TECHNICAL_INFORMATION_REQUEST:
            rubric = await db.get(RubricVersion, decision.rubric_version_id) if decision.rubric_version_id else None
            if not rubric or rubric.jd_version_id != requisition.current_jd_version_id:
                raise HTTPException(409, "EMAIL_DECISION_STALE: JD đã đổi; cần rubric và quyết định HR theo JD hiện hành.")
        if decision.decision_basis == DecisionBasis.ASSESSMENT_REVIEW:
            version = await db.get(SanitizedVersion, application.current_sanitized_version_id) if application.current_sanitized_version_id else None
            if not version or version.status != SanitizedVersionStatus.APPROVED:
                raise HTTPException(409, "EMAIL_DECISION_STALE: Nguồn đánh giá đã bị thu hồi hoặc chưa duyệt.")
    now = datetime.now(timezone.utc)
    await invalidate_email_drafts(db, [application_id])
    draft = EmailDraft(id=uuid.uuid4(), application_id=application_id, decision_id=previous.decision_id,
        version_no=previous.version_no + 1, source_snapshot_hash=previous.source_snapshot_hash,
        created_by=ctx.user.id, approved_by=ctx.user.id if status_str == "approved" else None,
        approved_at=now if status_str == "approved" else None, template_type=previous.template_type,
        subject=subject_text, body=body_text, status=status_str, variables=previous.variables, created_at=now, updated_at=now)
    db.add(draft)
    await db.flush()
    await record_audit_event(db, actor_id=ctx.user.id, action=f"email_draft.{status_str}", entity_type="email_draft", entity_id=draft.id,
        requisition_id=requisition.id, safe_metadata={"version_no": draft.version_no, "previous_version": previous.version_no,
            "content_hash": hashlib.sha256((subject_text + "\n" + body_text).encode()).hexdigest()})
    return _dto(draft)
