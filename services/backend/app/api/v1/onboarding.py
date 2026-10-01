"""Sandbox onboarding and interactive HR training endpoints (Task B21)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.org_user import OnboardingProgress
from app.db.session import get_db
from app.domain.authorization import AuthenticatedContext, get_current_context

router = APIRouter(prefix="/onboarding", tags=["Onboarding & Sandbox"])

CURRENT_WALKTHROUGH_VERSION = "v1.0-mvp"

CORE_ONBOARDING_STEPS = [
    "step_1_inspect_source",
    "step_2_missing_evidence",
    "step_3_hr_override",
    "step_4_attested_decision",
    "step_5_audit_trail",
]


class StepCompleteRequest(BaseModel):
    step_id: str = Field(min_length=1, max_length=100)
    exercise_result: Optional[dict[str, Any]] = None


class OnboardingStatusResponse(BaseModel):
    user_id: uuid.UUID
    walkthrough_version: str
    completed_steps: dict[str, Any]
    is_completed: bool
    completed_at: Optional[datetime] = None
    remaining_steps: list[str]


class SandboxScenarioDTO(BaseModel):
    id: str
    title: str
    category: str
    description: str
    candidate_profile: dict[str, Any]
    ai_preliminary_assessment: dict[str, Any]
    learning_objective: str
    instructions: list[str]


SANDBOX_TRAINING_SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "scenario_1_evidence_inspection",
        "title": "Tình huống 1: Mở Bằng Chứng & Kiểm Tra Trích Dẫn",
        "category": "evidence_provenance",
        "learning_objective": "Hiểu nguyên tắc trích xuất bằng chứng: Tuyệt đối không tin tưởng điểm số tổng quan mà phải nhấp mở từng SourceSpan trong Quote Drawer để đối chiếu văn bản gốc.",
        "description": "Ứng viên có trích dẫn về tối ưu hóa cơ sở dữ liệu PostgreSQL. Bạn cần kiểm tra xem đoạn trích dẫn có đúng vị trí và ngữ cảnh thực tế trong CV hay không.",
        "candidate_profile": {
            "public_label": "SANDBOX-CAND-01",
            "experience_summary": "4 năm phát triển Backend Python, cơ sở dữ liệu phân tán.",
            "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        },
        "ai_preliminary_assessment": {
            "criterion_id": "sql_data",
            "criterion_label": "Cơ Sở Dữ Liệu & Tối Ưu Hóa SQL",
            "ai_score": 3,
            "evidence_quote": "Đã thực hiện thiết kế schema và đánh chỉ mục B-tree/GIN giúp giảm thời gian truy vấn báo cáo từ 4.2s xuống 180ms trên cụm PostgreSQL 100GB.",
            "span_id": "spn_sandbox_01_sql",
            "provenance_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
            "missing_info": [],
        },
        "instructions": [
            "1. Nhấp vào trích dẫn bằng chứng của tiêu chí sql_data.",
            "2. Đọc đối chiếu đoạn trích trong Quote Drawer để xác thực metrics '180ms' và 'PostgreSQL 100GB'.",
            "3. Xác nhận bằng chứng hợp lệ và đánh dấu hoàn thành bước 1.",
        ],
    },
    {
        "id": "scenario_2_missing_evidence",
        "title": "Tình huống 2: Nhận Diện Thiếu Thông Tin & Bằng Chứng Yếu",
        "category": "missing_information",
        "learning_objective": "Học cách phát hiện các nhận định chung chung trong CV thiếu số liệu đo lường, không tự suy diễn năng lực khi CV không có căn cứ.",
        "description": "Ứng viên ghi kỹ năng 'Bảo mật & Phân quyền', nhưng nội dung CV chỉ có danh sách gạch đầu dòng liệt kê từ khóa mà không có dự án chứng minh.",
        "candidate_profile": {
            "public_label": "SANDBOX-CAND-02",
            "experience_summary": "3 năm lập trình viên Fullstack, tham gia nhiều dự án gia công phần mềm.",
            "skills": ["JavaScript", "Python", "OAuth2", "Security"],
        },
        "ai_preliminary_assessment": {
            "criterion_id": "security_privacy",
            "criterion_label": "Bảo Mật & Quyền Riêng Tư",
            "ai_score": None,
            "status": "insufficient_evidence",
            "evidence_quote": "Hiểu biết về bảo mật hệ thống và OWASP Top 10.",
            "span_id": "spn_sandbox_02_sec",
            "provenance_hash": "sha256:2c624232cdd221771294dfbb310aca000a0df6ec8b660466192ac11425b4fa66",
            "missing_info": [
                "Không có bằng chứng triển khai cơ chế xác thực JWT, RBAC hoặc mã hóa dữ liệu trong thực tế.",
                "Chưa nêu phương pháp phòng ngừa SQL Injection hoặc XSS ngoài việc liệt kê từ khóa OWASP.",
            ],
        },
        "instructions": [
            "1. Đọc cờ cảnh báo 'Thiếu thông tin chứng minh' do hệ thống gắn.",
            "2. Kiểm tra danh sách thiếu thông tin để chuẩn bị câu hỏi phỏng vấn kỹ thuật tương ứng.",
            "3. Đánh dấu hoàn thành bước 2.",
        ],
    },
    {
        "id": "scenario_3_hr_override",
        "title": "Tình huống 3: Ghi Đè Đánh Giá (HR Revision Override)",
        "category": "human_override",
        "learning_objective": "Thực hành quyền can thiệp của con người: Khi phát hiện AI bỏ sót đóng góp kỹ thuật có bằng chứng, HR đối chiếu nguồn rồi điều chỉnh kèm lý do.",
        "description": "AI chỉ chấm 1/4 cho tiêu chí API Design dù hồ sơ có mô tả rõ phần ứng viên trực tiếp thiết kế và kiểm thử giao diện gRPC/Protobuf.",
        "candidate_profile": {
            "public_label": "SANDBOX-CAND-03",
            "experience_summary": "5 năm chuyên sâu kiến trúc hệ thống phân tán và protocol thiết kế.",
            "skills": ["Python", "gRPC", "Protobuf", "FastAPI"],
        },
        "ai_preliminary_assessment": {
            "criterion_id": "api_design",
            "criterion_label": "Thiết Kế API & Chuẩn Hóa",
            "ai_score": 1,
            "evidence_quote": "Xây dựng microservices giao tiếp qua gRPC và Protobuf.",
            "span_id": "spn_sandbox_03_api",
            "provenance_hash": "sha256:4813494d137e1631bba301d5acab6e7bb7aa74ce1185d456565ef51d737677b2",
            "missing_info": ["CV không đề cập REST OpenAPI spec."],
        },
        "instructions": [
            "1. Đối chiếu đoạn CV mô tả tác vụ cá nhân với anchor của rubric trước khi chỉnh điểm.",
            "2. Nhập điểm điều chỉnh và lý do có dẫn nguồn; không dùng danh tiếng dự án hay thuộc tính nhân khẩu học.",
            "3. Bấm 'Ghi Đè & Tính Lại Điểm' để xác thực điểm số chuẩn hóa cập nhật tự động.",
        ],
    },
    {
        "id": "scenario_4_attested_decision",
        "title": "Tình huống 4: Ký Xác Nhận Attestation & Ra Quyết Định",
        "category": "attested_decision",
        "learning_objective": "Quy trình bất biến: AI không bao giờ được tự động ra quyết định tuyển dụng. Chỉ Requisition Owner mới có quyền ký ReviewAttestation và phê duyệt 'advance'.",
        "description": "Hồ sơ đạt ngưỡng 78.5/100, đủ điều kiện tiến vào vòng phỏng vấn kỹ thuật. Bạn sẽ thực hiện ký attestation với bằng chứng số và chốt quyết định.",
        "candidate_profile": {
            "public_label": "SANDBOX-CAND-04",
            "experience_summary": "Senior Python Developer đạt chuẩn yêu cầu công việc.",
            "skills": ["Python", "FastAPI", "PostgreSQL", "CI/CD"],
        },
        "ai_preliminary_assessment": {
            "overall_comparable_score": 78.5,
            "core_floor_passed": True,
            "coverage_pct": 100.0,
            "recommendation": "consider_next_round",
        },
        "instructions": [
            "1. Đọc biên bản cam kết thẩm định (ReviewAttestation) và snapshot hash.",
            "2. Chọn quyết định tuyển dụng: 'advance' (Chuyển sang phỏng vấn kỹ thuật).",
            "3. Xác nhận cam kết và lưu quyết định có dấu vết kiểm toán.",
        ],
    },
    {
        "id": "scenario_5_audit_trail",
        "title": "Tình huống 5: Kiểm Tra Dấu Vết Kiểm Toán (Audit Trail)",
        "category": "audit_trace",
        "learning_objective": "Đảm bảo tính giải trình: các thao tác chính được ghi vào audit log chỉ-ghi-thêm ở tầng ứng dụng với thời gian UTC và actor ID.",
        "description": "Xem lại toàn bộ lịch sử chuỗi sự kiện kiểm toán từ lúc tiếp nhận hồ sơ, làm sạch PII, chạy AI, HR ghi đè đến khi ký quyết định cuối cùng.",
        "candidate_profile": {
            "public_label": "SANDBOX-CAND-05",
            "experience_summary": "Hồ sơ đã hoàn tất toàn bộ chu trình đánh giá.",
            "skills": ["Python", "Docker"],
        },
        "ai_preliminary_assessment": {
            "audit_events_count": 5,
            "tamper_evident": False,
        },
        "instructions": [
            "1. Xem dòng thời gian kiểm toán và kiểm tra actor, thời gian, loại sự kiện.",
            "2. Kiểm tra cam kết bảo mật không rò rỉ PII trong log kiểm toán.",
            "3. Hoàn tất toàn bộ khóa huấn luyện Sandbox Onboarding.",
        ],
    },
]


@router.get("", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Retrieve the current user's onboarding progress and completed checklist steps."""
    stmt = select(OnboardingProgress).where(
        OnboardingProgress.user_id == ctx.user.id,
        OnboardingProgress.walkthrough_version == CURRENT_WALKTHROUGH_VERSION,
    )
    rec = (await db.execute(stmt)).scalar_one_or_none()

    if not rec:
        return OnboardingStatusResponse(
            user_id=ctx.user.id,
            walkthrough_version=CURRENT_WALKTHROUGH_VERSION,
            completed_steps={},
            is_completed=False,
            completed_at=None,
            remaining_steps=CORE_ONBOARDING_STEPS,
        )

    completed = rec.completed_steps or {}
    remaining = [s for s in CORE_ONBOARDING_STEPS if not completed.get(s)]
    is_done = len(remaining) == 0 and rec.completed_at is not None

    return OnboardingStatusResponse(
        user_id=rec.user_id,
        walkthrough_version=rec.walkthrough_version,
        completed_steps=completed,
        is_completed=is_done,
        completed_at=rec.completed_at,
        remaining_steps=remaining,
    )


@router.post("/step", response_model=OnboardingStatusResponse)
async def complete_onboarding_step(
    payload: StepCompleteRequest,
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Mark an onboarding training step as completed and save sandbox exercise result."""
    stmt = select(OnboardingProgress).where(
        OnboardingProgress.user_id == ctx.user.id,
        OnboardingProgress.walkthrough_version == CURRENT_WALKTHROUGH_VERSION,
    )
    rec = (await db.execute(stmt)).scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if not rec:
        rec = OnboardingProgress(
            user_id=ctx.user.id,
            walkthrough_version=CURRENT_WALKTHROUGH_VERSION,
            completed_steps={},
            completed_at=None,
            sandbox_exercise_result={},
        )
        db.add(rec)
        await db.flush()

    steps = dict(rec.completed_steps or {})
    steps[payload.step_id] = {
        "completed": True,
        "completed_at": now.isoformat(),
    }
    rec.completed_steps = steps

    if payload.exercise_result:
        res = dict(rec.sandbox_exercise_result or {})
        res[payload.step_id] = payload.exercise_result
        rec.sandbox_exercise_result = res

    # Check if all 5 core steps are completed
    remaining = [s for s in CORE_ONBOARDING_STEPS if not steps.get(s)]
    if len(remaining) == 0 and not rec.completed_at:
        rec.completed_at = now

    await db.commit()

    return OnboardingStatusResponse(
        user_id=rec.user_id,
        walkthrough_version=rec.walkthrough_version,
        completed_steps=rec.completed_steps,
        is_completed=rec.completed_at is not None,
        completed_at=rec.completed_at,
        remaining_steps=remaining,
    )


@router.post("/reset", response_model=OnboardingStatusResponse)
async def reset_onboarding_progress(
    db: AsyncSession = Depends(get_db),
    ctx: AuthenticatedContext = Depends(get_current_context),
):
    """Reset onboarding progress so HR / reviewer can repeat the simulation exercises."""
    stmt = select(OnboardingProgress).where(
        OnboardingProgress.user_id == ctx.user.id,
        OnboardingProgress.walkthrough_version == CURRENT_WALKTHROUGH_VERSION,
    )
    rec = (await db.execute(stmt)).scalar_one_or_none()

    if rec:
        rec.completed_steps = {}
        rec.completed_at = None
        rec.sandbox_exercise_result = {}
        await db.commit()

    return OnboardingStatusResponse(
        user_id=ctx.user.id,
        walkthrough_version=CURRENT_WALKTHROUGH_VERSION,
        completed_steps={},
        is_completed=False,
        completed_at=None,
        remaining_steps=CORE_ONBOARDING_STEPS,
    )


@router.get("/scenarios", response_model=list[SandboxScenarioDTO])
async def get_sandbox_scenarios():
    """Return the 5 preloaded sandbox training scenarios for interactive HR walkthrough."""
    return SANDBOX_TRAINING_SCENARIOS
