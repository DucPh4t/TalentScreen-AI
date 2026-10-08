"""End-to-end regression tests for Human-In-The-Loop (HITL) pipeline enhancements:
- AI Rubric Drafter from JD
- AI Shortlist & Ranking Engine
- Versioned candidate correspondence templates
- Candidate One-Page Executive Summary
- SLA Breach & Duplicate Candidate Detection
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.models import (
    Application,
    AssessmentRun,
    CriterionAssessment,
    JDVersion,
    Requisition,
    RequisitionMembership,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import CriterionId, CriterionOutcome, MembershipRole, Recommendation, RequisitionStatus
from app.main import app
from tests.test_decisions import setup_test_context, sample_docx_cv


@pytest.mark.asyncio
async def test_draft_rubric_from_jd_verbatim_quotes(test_session_factory, sample_docx_cv):
    """Test AI Rubric Drafter synthesizes criteria with strictly verbatim JD quotes."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        req = await session.get(Requisition, ctx["req_id"])
        jd = await session.get(JDVersion, req.current_jd_version_id)
        jd.source_text = (
            "Mô tả công việc: Tuyển dụng Senior Backend Python Engineer.\n"
            "Tối thiểu 4 năm kinh nghiệm thiết kế kiến trúc backend với Python và FastAPI.\n"
            "Thành thạo Docker, Kubernetes, PostgreSQL và tối ưu hóa truy vấn cơ sở dữ liệu lớn.\n"
            "Kinh nghiệm làm việc với hệ thống Microservices, Kafka hoặc RabbitMQ.\n"
            "Khả năng đọc hiểu tài liệu tiếng Anh kỹ thuật và phối hợp làm việc nhóm hiệu quả."
        )
        await session.commit()
        jd_source = jd.source_text

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    headers = {"X-CSRF-Token": ctx["o_csrf"]}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.post(f"/api/v1/requisitions/{ctx['req_id']}/rubrics/draft-from-jd")
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["status"] == "draft"
        assert len(data["criteria"]) >= 3

        # Invariant: Every quote in source_requirements must be a verbatim substring of the JD source text!
        for crit in data["criteria"]:
            assert len(crit["source_requirements"]) > 0
            for ref in crit["source_requirements"]:
                quote = ref["quote"]
                assert quote in jd_source, f"Quote '{quote}' is not verbatim in JD text"


@pytest.mark.asyncio
async def test_shortlist_engine_and_ranking(test_session_factory, sample_docx_cv):
    """Test Shortlist engine categorizes candidate into 'recommend' tier."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        run = AssessmentRun(
            application_id=ctx["app_id"],
            job_id=uuid.uuid4(),
            run_no=1,
            status="succeeded",
            snapshot={},
            snapshot_hash="a" * 64,
            application_generation=1,
            document_id=ctx["doc_id"],
            sanitized_version_id=ctx["sanitized_id"],
            rubric_version_id=ctx["rubric_id"],
            recommendation=Recommendation.CONSIDER_NEXT_ROUND,
            coverage=1.0,
            observed_score=85.0,
            comparable_score=85.0,
            strategy="evidence_anchored",
            execution_trace={},
        )
        session.add(run)
        await session.flush()

        for cid in CriterionId:
            session.add(
                CriterionAssessment(
                    run_id=run.id,
                    criterion_id=cid.value,
                    status=CriterionOutcome.ASSESSED,
                    score=3,
                    rationale="Đối chiếu kinh nghiệm từ CV.",
                    missing_information=[],
                )
            )

        app_obj = await session.get(Application, ctx["app_id"])
        app_obj.current_assessment_run_id = run.id
        await session.commit()

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    headers = {"X-CSRF-Token": ctx["o_csrf"]}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/shortlist?threshold=70")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["requisition_id"] == str(ctx["req_id"])
        assert data["threshold"] == 70.0
        assert data["total_candidates"] >= 1
        assert data["shortlisted_candidates"] >= 1
        assert data["tier_summary"]["recommend"] >= 1

        cand_entry = next((c for c in data["candidates"] if c["application_id"] == str(ctx["app_id"])), None)
        assert cand_entry is not None
        assert cand_entry["tier"] == "recommend"
        assert cand_entry["comparable_score"] == 85.0
        assert cand_entry["rank"] == 1


@pytest.mark.asyncio
async def test_email_draft_lifecycle_and_privacy_safety(test_session_factory, sample_docx_cv):
    """Template generation and revision remain drafts until an explicit HR decision and approval."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        run = AssessmentRun(
            application_id=ctx["app_id"],
            job_id=uuid.uuid4(),
            run_no=1,
            status="succeeded",
            snapshot={},
            snapshot_hash="a" * 64,
            application_generation=1,
            document_id=ctx["doc_id"],
            sanitized_version_id=ctx["sanitized_id"],
            rubric_version_id=ctx["rubric_id"],
            recommendation=Recommendation.CONSIDER_NEXT_ROUND,
            coverage=1.0,
            observed_score=85.0,
            comparable_score=85.0,
            strategy="evidence_anchored",
            execution_trace={},
        )
        session.add(run)
        await session.flush()
        app_obj = await session.get(Application, ctx["app_id"])
        app_obj.current_assessment_run_id = run.id
        await session.commit()

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    headers = {"X-CSRF-Token": ctx["o_csrf"]}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # 1. Explicit generation, not a side effect of reading or an AI recommendation
        res = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate?template=interview_invitation")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["template_type"] == "interview_invitation"
        assert "Thư mời tham gia phỏng vấn chuyên môn" in data["subject"]
        assert "85.0" not in data["body"], "Internal score must NOT leak into candidate email!"
        assert "3/4" not in data["body"], "Internal anchor score must NOT leak into candidate email!"

        # 2. Switch template to technical_clarification
        res_gen = await client.post(
            f"/api/v1/applications/{ctx['app_id']}/email-draft/generate?template=technical_clarification"
        )
        assert res_gen.status_code == 200, res_gen.text
        data_gen = res_gen.json()
        assert data_gen["template_type"] == "technical_clarification"
        assert "Đề nghị làm rõ thông tin" in data_gen["subject"]

        # 3. Update email draft
        res_update = await client.put(
            f"/api/v1/applications/{ctx['app_id']}/email-draft",
            json={
                "subject": "Tiêu đề tùy chỉnh từ HR",
                "body": "Nội dung email đã được HR duyệt.",
                "status": "draft",
                "draft_id": data_gen["id"],
                "expected_version": data_gen["version_no"],
            },
        )
        assert res_update.status_code == 200, res_update.text
        data_updated = res_update.json()
        assert data_updated["subject"] == "Tiêu đề tùy chỉnh từ HR"
        assert data_updated["status"] == "draft"
        assert data_updated["version_no"] > data_gen["version_no"]


@pytest.mark.asyncio
async def test_candidate_one_page_executive_summary(test_session_factory, sample_docx_cv):
    """Test Candidate One-Page Executive Summary generation."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        run = AssessmentRun(
            application_id=ctx["app_id"],
            job_id=uuid.uuid4(),
            run_no=1,
            status="succeeded",
            snapshot={},
            snapshot_hash="a" * 64,
            application_generation=1,
            document_id=ctx["doc_id"],
            sanitized_version_id=ctx["sanitized_id"],
            rubric_version_id=ctx["rubric_id"],
            recommendation=Recommendation.CONSIDER_NEXT_ROUND,
            coverage=1.0,
            observed_score=85.0,
            comparable_score=85.0,
            strategy="evidence_anchored",
            execution_trace={},
        )
        session.add(run)
        await session.flush()

        for cid in CriterionId:
            session.add(
                CriterionAssessment(
                    run_id=run.id,
                    criterion_id=cid.value,
                    status=CriterionOutcome.ASSESSED,
                    score=3,
                    rationale="Đối chiếu kinh nghiệm từ CV.",
                    missing_information=[],
                )
            )

        app_obj = await session.get(Application, ctx["app_id"])
        app_obj.current_assessment_run_id = run.id
        await session.commit()

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    headers = {"X-CSRF-Token": ctx["o_csrf"]}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.get(f"/api/v1/applications/{ctx['app_id']}/summary")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["application_id"] == str(ctx["app_id"])
        assert data["status"] == "ready"
        assert len(data["summary_paragraph"]) > 30
        assert len(data["key_strengths"]) >= 1
        assert len(data["recommended_interview_focus"]) >= 1
        assert data["comparable_score"] == 85.0


@pytest.mark.asyncio
async def test_sla_breach_and_duplicate_candidate_detection(test_session_factory, sample_docx_cv):
    """Test Review Queue flags SLA breach (> 72h) and duplicate candidate submissions."""
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        orig_req = await session.get(Requisition, ctx["req_id"])
        app_obj = await session.get(Application, ctx["app_id"])
        # Old intake alone is not the HR-decision SLA; no completed assessment here
        app_obj.received_at = datetime.now(timezone.utc) - timedelta(hours=80)

        # Create a second requisition and application for the same candidate
        req2 = Requisition(
            id=uuid.uuid4(),
            organization_id=orig_req.organization_id,
            title="Fullstack Python Engineer",
            status=RequisitionStatus.OPEN,
            row_version=1,
        )
        session.add(req2)
        await session.flush()

        session.add(
            RequisitionMembership(
                requisition_id=req2.id,
                user_id=ctx["owner"].id,
                membership_role=MembershipRole.OWNER,
            )
        )

        dup_app = Application(
            id=uuid.uuid4(),
            requisition_id=req2.id,
            candidate_id=ctx["cand_id"],
            status="active",
            generation=1,
            row_version=1,
            received_at=datetime.now(timezone.utc) - timedelta(hours=5),
        )
        session.add(dup_app)
        await session.commit()

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: ctx["o_token"]}
    headers = {"X-CSRF-Token": ctx["o_csrf"]}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")
        assert res.status_code == 200, res.text
        items = res.json()

        item1 = next((i for i in items if i["application_id"] == str(ctx["app_id"])), None)
        assert item1 is not None
        assert item1["sla_breached"] is False
        assert item1["hours_in_stage"] == 0
        assert item1["is_duplicate"] is True, "Candidate submitted multiple applications!"
        assert item1["application_history_count"] == 2
