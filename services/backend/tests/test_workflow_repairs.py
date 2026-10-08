"""Regression coverage for JD-driven rubrics and safe recruitment workflow repairs."""
from datetime import datetime, timedelta, timezone
import uuid

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import select

from app.db.models import Application, AssessmentRun, Candidate, CriterionAssessment, Document, JDVersion, Requisition
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import CriterionOutcome, Recommendation
from app.main import app
from tests.test_decisions import setup_test_context, sample_docx_cv


def client_for(ctx, role="o"):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test",
                       cookies={SESSION_COOKIE_NAME: ctx[f"{role}_token"]},
                       headers={"X-CSRF-Token": ctx[f"{role}_csrf"]})


async def add_run(session, ctx, completed_hours=0, missing=None):
    run = AssessmentRun(application_id=ctx["app_id"], job_id=uuid.uuid4(), run_no=1,
        status="succeeded", snapshot={}, snapshot_hash="a" * 64, application_generation=1,
        document_id=ctx["doc_id"], sanitized_version_id=ctx["sanitized_id"], rubric_version_id=ctx["rubric_id"],
        recommendation=Recommendation.NEEDS_CLARIFICATION, coverage=1, observed_score=75,
        comparable_score=75, strategy="evidence_anchored", execution_trace={},
        completed_at=datetime.now(timezone.utc) - timedelta(hours=completed_hours))
    session.add(run)
    await session.flush()
    session.add(CriterionAssessment(run_id=run.id, criterion_id="python_backend", status=CriterionOutcome.INSUFFICIENT_EVIDENCE,
        score=None, rationale="Cần làm rõ.", missing_information=missing or []))
    application = await session.get(Application, ctx["app_id"])
    application.current_assessment_run_id = run.id
    await session.commit()
    return run


@pytest.mark.asyncio
async def test_duplicate_file_across_new_candidates_is_flagged(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        requisition = await session.get(Requisition, ctx["req_id"])
        original = await session.get(Document, ctx["doc_id"])
        other = Candidate(organization_id=requisition.organization_id, public_label=f"CAND-{uuid.uuid4().hex[:10]}")
        session.add(other)
        await session.flush()
        duplicate = Application(requisition_id=ctx["req_id"], candidate_id=other.id, status="active", generation=1, row_version=1)
        session.add(duplicate)
        await session.flush()
        doc = Document(application_id=duplicate.id, version_no=1, original_name_private="duplicate.docx",
            mime_verified=original.mime_verified, byte_size=original.byte_size, sha256=original.sha256,
            blob_key="synthetic-duplicate", ingestion_status="parsed")
        session.add(doc)
        await session.flush()
        duplicate.current_document_id = doc.id
        await session.commit()
    async with client_for(ctx) as client:
        response = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")
        assert response.status_code == 200
        own = next(item for item in response.json() if item["application_id"] == str(ctx["app_id"]))
        assert own["is_duplicate"] is True
        assert own["application_history_count"] == 2
        assert "same_file" in own["duplicate_reasons"]
        progress = await client.get(f"/api/v1/applications/{ctx['app_id']}/progress")
        assert progress.json()["is_duplicate"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["dangling_decision", "ready_for_ai"])
async def test_hr_decision_sla_does_not_cover_other_stages(test_session_factory, sample_docx_cv, stage):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        application = await session.get(Application, ctx["app_id"])
        application.received_at = datetime.now(timezone.utc) - timedelta(hours=150)
        if stage == "dangling_decision":
            application.current_decision_id = uuid.uuid4()
        await session.commit()
    async with client_for(ctx) as client:
        response = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")
        own = next(item for item in response.json() if item["application_id"] == str(ctx["app_id"]))
        assert own["workflow_stage"] == "ready_for_ai"
        assert own["sla_breached"] is False
        assert own["hours_in_stage"] == 0


@pytest.mark.asyncio
async def test_hr_decision_sla_starts_at_assessment_completion(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        await add_run(session, ctx, completed_hours=80)
    async with client_for(ctx) as client:
        response = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")
        own = next(item for item in response.json() if item["application_id"] == str(ctx["app_id"]))
        assert own["workflow_stage"] == "awaiting_decision"
        assert own["sla_breached"] is True
        assert 79 <= own["hours_in_stage"] <= 81


@pytest.mark.asyncio
async def test_clarification_template_never_copies_internal_missing_information(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        await add_run(session, ctx, missing=["Điểm đánh giá nội bộ 3/4; SYSTEM_PROMPT=secret; spn_a1234"])
    async with client_for(ctx) as client:
        response = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate?template=technical_clarification")
        assert response.status_code == 200, response.text
        draft = response.json()
        assert "3/4" not in draft["body"]
        assert "SYSTEM_PROMPT" not in draft["body"]
        assert "spn_a1234" not in draft["body"]
        assert draft["version_no"] == 1
        assert draft["created_by"] == str(ctx["owner"].id)


@pytest.mark.asyncio
async def test_email_get_is_read_only_and_unknown_templates_are_rejected(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    async with client_for(ctx) as client:
        response = await client.get(f"/api/v1/applications/{ctx['app_id']}/email-draft")
        assert response.status_code == 404
        response = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate?template=does_not_exist")
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_email_update_blocks_internal_scores_and_stale_edits(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        await add_run(session, ctx)
    async with client_for(ctx) as client:
        draft = (await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")).json()
        update = {"subject": "Thông tin tiếp theo cho ứng viên", "body": "Điểm đánh giá nội bộ của bạn là 3/4, hãy bổ sung hồ sơ.",
                  "status": "draft", "draft_id": draft["id"], "expected_version": draft.get("version_no", 1)}
        unsafe = await client.put(f"/api/v1/applications/{ctx['app_id']}/email-draft", json=update)
        assert unsafe.status_code == 422
        assert "EMAIL_CONTENT_UNSAFE" in unsafe.text
        update["body"] = "Cảm ơn bạn đã ứng tuyển. Vui lòng bổ sung ví dụ dự án gần đây."
        saved = await client.put(f"/api/v1/applications/{ctx['app_id']}/email-draft", json=update)
        assert saved.status_code == 200, saved.text
        assert saved.json()["version_no"] == 2
        stale = await client.put(f"/api/v1/applications/{ctx['app_id']}/email-draft", json=update)
        assert stale.status_code == 409


@pytest.mark.asyncio
async def test_email_draft_is_unusable_after_source_changes(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        await add_run(session, ctx)
    async with client_for(ctx) as client:
        created = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")
        assert created.status_code == 200
        async with test_session_factory() as session:
            application = await session.get(Application, ctx["app_id"])
            application.current_decision_id = uuid.uuid4()
            await session.commit()
        response = await client.get(f"/api/v1/applications/{ctx['app_id']}/email-draft")
        assert response.status_code == 410


@pytest.mark.asyncio
@pytest.mark.parametrize("jd_text, expected", [
    ("Frontend React Engineer\nYêu cầu:\n- Phát triển giao diện bằng React và TypeScript.\n- Xây dựng giao diện responsive và đảm bảo accessibility.\n- Viết kiểm thử giao diện bằng Playwright.", "React"),
    ("Chuyên viên thiết kế sản phẩm\nYêu cầu:\n- Thiết kế trải nghiệm người dùng trong Figma.\n- Thực hiện nghiên cứu người dùng và phỏng vấn khách hàng.\n- Tạo prototype và kiểm thử khả năng sử dụng.", "Figma"),
])
async def test_rubric_draft_tracks_user_jd_instead_of_backend_template(test_session_factory, sample_docx_cv, jd_text, expected):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        req = await session.get(Requisition, ctx["req_id"])
        jd = await session.get(JDVersion, req.current_jd_version_id)
        jd.source_text = jd_text
        await session.commit()
    async with client_for(ctx) as client:
        response = await client.post(f"/api/v1/requisitions/{ctx['req_id']}/rubrics/draft-from-jd")
        assert response.status_code == 201, response.text
        data = response.json()
        descriptions = " ".join(c["label"] + c["description"] for c in data["criteria"])
        assert expected in descriptions
        assert "gRPC" not in descriptions
        assert "cơ sở dữ liệu" not in descriptions.lower()
        assert data["status"] == "draft"
        for criterion in data["criteria"]:
            assert all(ref["quote"] in jd_text for ref in criterion["source_requirements"])
            assert "Không có bằng chứng" not in criterion["scoring_anchors"][0]["description"]


@pytest.mark.asyncio
async def test_new_rubric_queues_reassessment_for_previous_runs(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        await add_run(session, ctx)
        req = await session.get(Requisition, ctx["req_id"])
        jd = await session.get(JDVersion, req.current_jd_version_id)
        jd.source_text = "Yêu cầu:\n- Xây dựng giao diện bằng React và TypeScript.\n- Kiểm thử giao diện bằng Playwright."
        await session.commit()
    async with client_for(ctx) as client:
        created = await client.post(f"/api/v1/requisitions/{ctx['req_id']}/rubrics/draft-from-jd")
        assert created.status_code == 201
        req = (await client.get(f"/api/v1/requisitions/{ctx['req_id']}")).json()
        approved = await client.post(f"/api/v1/rubrics/{created.json()['id']}/approve", json={
            "expected_requisition_version": req["row_version"], "expected_jd_version_id": req["current_jd_version_id"],
            "acknowledge_thresholds": True})
        assert approved.status_code == 200, approved.text
    async with test_session_factory() as session:
        runs = (await session.execute(select(AssessmentRun).where(AssessmentRun.application_id == ctx["app_id"]))).scalars().all()
        assert any(str(run.rubric_version_id) == created.json()["id"] and run.status == "queued" for run in runs)


async def manual_decision(client, ctx, outcome="advance", previous=None):
    from app.domain.enums import CriterionId
    if previous is None:
        grant = await client.post(f"/api/v1/applications/{ctx['app_id']}/raw-grants", json={
            "grantee_user_id": str(ctx["owner"].id), "scopes": ["raw_cv"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(), "reason": "Synthetic correspondence regression"})
        assert grant.status_code == 201, grant.text
    attestation = await client.post(f"/api/v1/applications/{ctx['app_id']}/review-attestations", json={
        "decision_basis": "manual_document_review", "document_id": str(ctx["doc_id"]),
        "expected_document_sha256": "c" * 64, "expected_rubric_version_id": str(ctx["rubric_id"]),
        "reviewed_criterion_ids": [cid.value for cid in CriterionId], "acknowledged": True,
        "manual_evidence_refs": [{"criterion_id": "python_backend", "document_id": str(ctx["doc_id"]),
            "page_number": 1, "note": "Đã kiểm tra bằng chứng trong tài liệu gốc."}]})
    assert attestation.status_code == 201, attestation.text
    decision = await client.post(f"/api/v1/applications/{ctx['app_id']}/decisions", json={
        "decision_basis": "manual_document_review", "outcome": outcome,
        "reason": "Đã đối chiếu các yêu cầu năng lực và ghi nhận quyết định của HR.",
        "override_reason": "Quyết định thủ công từ bằng chứng đã kiểm tra trong tài liệu gốc.",
        "attestation_id": attestation.json()["id"], "expected_previous_decision_id": previous,
        "expected_rubric_version_id": str(ctx["rubric_id"])})
    assert decision.status_code == 201, decision.text
    return decision.json()


async def prepare_invitation(client, ctx):
    from app.domain.enums import CriterionId
    route = f"/api/v1/applications/{ctx['app_id']}/interview-rounds/1"
    state = (await client.get(route)).json()
    result = await client.put(route, json={"source_hash": state["source_hash"], "expected_version": state["row_version"],
        "label": "Trao đổi chuyên môn", "focus_criterion_ids": [cid.value for cid in CriterionId],
        "interviewer_ids": [str(ctx["owner"].id)], "starts_at": "2026-10-22T03:00:00+00:00", "duration_minutes": 45,
        "channel": "online", "meeting_location": "https://meet.example.com/synthetic"})
    assert result.status_code == 200, result.text


@pytest.mark.asyncio
async def test_email_approval_is_versioned_attributed_and_invalidated_by_actual_decision_api(test_session_factory, sample_docx_cv):
    from app.db.models.email_draft import EmailDraft
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    async with client_for(ctx) as client:
        decision = await manual_decision(client, ctx)
        await prepare_invitation(client, ctx)
        draft = (await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")).json()
        assert draft["template_type"] == "interview_invitation"
        payload = {"draft_id": draft["id"], "expected_version": draft["version_no"], "subject": draft["subject"],
                   "body": draft["body"], "status": "approved", "acknowledged_content": True}
        approved = await client.put(f"/api/v1/applications/{ctx['app_id']}/email-draft", json=payload)
        assert approved.status_code == 200, approved.text
        data = approved.json()
        assert data["version_no"] == 2
        assert data["approved_by"] == str(ctx["owner"].id)
        assert data["approved_at"] is not None
        await manual_decision(client, ctx, "not_advance", decision["id"])
        assert (await client.get(f"/api/v1/applications/{ctx['app_id']}/email-draft")).status_code == 410
    async with test_session_factory() as session:
        versions = list((await session.execute(select(EmailDraft).where(EmailDraft.application_id == ctx["app_id"]))).scalars())
        assert len(versions) == 2
        assert all(draft.status == "invalidated" for draft in versions)
        assert next(draft for draft in versions if draft.version_no == 2).approved_by == ctx["owner"].id


@pytest.mark.asyncio
async def test_reviewer_cannot_generate_or_approve_candidate_correspondence(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    async with client_for(ctx, "r") as client:
        assert (await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")).status_code == 403


@pytest.mark.asyncio
async def test_contact_match_across_different_files_and_candidate_ids_stays_local(test_session_factory, sample_docx_cv):
    from app.services.duplicates import contact_fingerprints
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        req = await session.get(Requisition, ctx["req_id"])
        original = await session.get(Document, ctx["doc_id"])
        original.duplicate_fingerprints = contact_fingerprints("DEV@example.test +84 912 345 678", req.organization_id)
        other = Candidate(organization_id=req.organization_id, public_label=f"CAND-{uuid.uuid4().hex[:10]}")
        session.add(other)
        await session.flush()
        application = Application(requisition_id=req.id, candidate_id=other.id, status="active", generation=1, row_version=1)
        session.add(application)
        await session.flush()
        document = Document(application_id=application.id, version_no=1, original_name_private="updated.docx",
            mime_verified=original.mime_verified, byte_size=50, sha256="f" * 64, blob_key="synthetic-updated",
            ingestion_status="parsed", duplicate_fingerprints=contact_fingerprints("dev@example.test 0912345678", req.organization_id))
        session.add(document)
        await session.flush()
        application.current_document_id = document.id
        await session.commit()
    async with client_for(ctx) as client:
        response = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")
        own = next(item for item in response.json() if item["application_id"] == str(ctx["app_id"]))
        assert own["is_duplicate"] is True
        assert own["duplicate_reasons"] == ["same_contact"]
        assert "example.test" not in response.text
        assert original.duplicate_fingerprints[0] not in response.text
    assert contact_fingerprints("dev@example.test", uuid.uuid4()) != contact_fingerprints("dev@example.test", req.organization_id)


@pytest.mark.asyncio
async def test_configured_provider_drafts_validated_jd_rubric_with_ledger(test_session_factory, sample_docx_cv, monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace
    from app.services import rubric_drafting
    from app.services.llm import orchestrator
    from app.services.llm.provider import MockLLMProvider
    from app.db.models import Job, LLMInvocation
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        req = await session.get(Requisition, ctx["req_id"])
        jd = await session.get(JDVersion, req.current_jd_version_id)
        jd.source_text = "Yêu cầu:\n- Thiết kế giao diện React và TypeScript.\n- Viết kiểm thử giao diện Playwright."
        jd.text_hash = hashlib.sha256(jd.source_text.encode()).hexdigest()
        jd.egress_reviewed_at = datetime.now(timezone.utc)
        jd.egress_reviewed_by = ctx["owner"].id
        await session.commit()
        valid = rubric_drafting.local_jd_draft(jd.source_text)
        # Provider selects immutable JD passage IDs; the server owns source quotes.
        for index, criterion in enumerate(valid["criteria"], start=2):
            criterion["source_requirements"] = [{"requirement_id": f"JD-SOURCE-{index:03d}"}]
    class RecordingProvider(MockLLMProvider):
        def __init__(self):
            super().__init__(custom_content=json.dumps(valid))
            self.requests = []

        async def complete(self, request):
            self.requests.append(request)
            return await super().complete(request)

    provider = RecordingProvider()
    monkeypatch.setattr(rubric_drafting, "get_settings", lambda: SimpleNamespace(LLM_PROVIDER="deepseek", DEEPSEEK_MODEL="deepseek-flash"))
    monkeypatch.setattr(orchestrator, "get_llm_provider", lambda: provider)
    async with client_for(ctx) as client:
        response = await client.post(f"/api/v1/requisitions/{ctx['req_id']}/rubrics/draft-from-jd")
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "draft"
    async with test_session_factory() as session:
        job = (await session.execute(select(Job).where(Job.target_id == jd.id))).scalar_one()
        assert job.status.value == "succeeded"
        assert job.payload_ref["prompt_version"] == rubric_drafting.RUBRIC_PROMPT_VERSION
        invocation = (await session.execute(select(LLMInvocation).where(LLMInvocation.job_id == job.id))).scalar_one()
        assert invocation.cost_actual is not None
    assert provider.invocation_count == 1
    # Rubric JSON must not lose its output allowance to default reasoning.
    assert provider.requests[0].thinking_mode == "disabled"
    prompt = json.loads(provider.requests[0].user_prompt)
    anchor_schema = prompt["output_schema"]["$defs"]["ProposalAnchor"]
    # Keep five anchors useful without expanding optional evidence arrays per score.
    assert set(anchor_schema["properties"]) == {"score", "description"}
    assert anchor_schema["additionalProperties"] is False
    assert anchor_schema["properties"]["description"]["maxLength"] == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("fault, status_code, expected_code", [
    ("401", 502, "RUBRIC_DRAFT_AUTHENTICATION_FAILED"),
    ("402", 502, "RUBRIC_DRAFT_QUOTA_EXHAUSTED"),
    ("timeout", 504, "RUBRIC_DRAFT_NETWORK_TIMEOUT"),
    ("truncated", 502, "RUBRIC_DRAFT_RESPONSE_TRUNCATED"),
    ("malformed_json", 502, "RUBRIC_DRAFT_INVALID"),
])
async def test_rubric_provider_failure_explains_cause_without_storing_draft(
    test_session_factory, sample_docx_cv, monkeypatch, fault, status_code, expected_code
):
    from types import SimpleNamespace
    from app.db.models import Job, RubricVersion
    from app.services import rubric_drafting
    from app.services.llm import orchestrator
    from app.services.llm.provider import MockLLMProvider
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        req = await session.get(Requisition, ctx["req_id"])
        jd = await session.get(JDVersion, req.current_jd_version_id)
        jd.egress_reviewed_at = datetime.now(timezone.utc)
        jd.egress_reviewed_by = ctx["owner"].id
        await session.commit()
        before = (await session.execute(select(RubricVersion.id).where(RubricVersion.requisition_id == ctx["req_id"]))).scalars().all()
    provider = MockLLMProvider(fault_mode=fault)
    monkeypatch.setattr(rubric_drafting, "get_settings", lambda: SimpleNamespace(LLM_PROVIDER="deepseek", DEEPSEEK_MODEL="deepseek-flash"))
    monkeypatch.setattr(orchestrator, "get_llm_provider", lambda: provider)
    async with client_for(ctx) as client:
        response = await client.post(f"/api/v1/requisitions/{ctx['req_id']}/rubrics/draft-from-jd")
        assert response.status_code == status_code
        assert response.json()["detail"].startswith(expected_code + ":")
        assert "Not valid JSON" not in response.text
    async with test_session_factory() as session:
        after = (await session.execute(select(RubricVersion.id).where(RubricVersion.requisition_id == ctx["req_id"]))).scalars().all()
        assert set(after) == set(before)
        job = (await session.execute(select(Job).where(Job.target_id == jd.id))).scalar_one()
        assert job.status.value == "failed"
        assert job.last_error_code == expected_code


@pytest.mark.asyncio
async def test_unreviewed_jd_cannot_call_external_provider(test_session_factory, sample_docx_cv, monkeypatch):
    from types import SimpleNamespace
    from app.services import rubric_drafting
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    monkeypatch.setattr(rubric_drafting, "get_settings", lambda: SimpleNamespace(LLM_PROVIDER="deepseek"))
    async with client_for(ctx) as client:
        response = await client.post(f"/api/v1/requisitions/{ctx['req_id']}/rubrics/draft-from-jd")
        assert response.status_code == 409
        assert "JD_EGRESS_NOT_APPROVED" in response.text


def test_rubric_validation_rejects_fake_citations_and_zero_for_missing_evidence():
    import json
    from app.services.rubric_drafting import local_jd_draft, validate_jd_draft
    source = "Yêu cầu:\n- Thiết kế giao diện React và TypeScript.\n- Viết kiểm thử giao diện Playwright."
    payload = local_jd_draft(source)
    payload["criteria"][0]["source_requirements"][0]["quote"] = "Invented quote"
    with pytest.raises(ValueError, match="JD_CITATION_NOT_VERBATIM"):
        validate_jd_draft(json.dumps(payload), source)
    payload = local_jd_draft(source)
    payload["criteria"][0]["scoring_anchors"][0]["description"] = "Không có bằng chứng"
    with pytest.raises(ValueError, match="MISSING_EVIDENCE_IS_NOT_ZERO"):
        validate_jd_draft(json.dumps(payload), source)


@pytest.mark.parametrize("text", ["Your internal score is 75 and coverage is 0.5.", "AI score: 3 out of 4. Recommendation: not_advance.", "Điểm của bạn là 75", "Mức phù hợp: 85/100"])
def test_email_boundary_catches_vietnamese_and_english_score_leaks(text):
    from app.services.email_draft import unsafe_email_content
    assert unsafe_email_content(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("source_change", ["edit", "revoke"])
async def test_regenerating_email_cannot_revive_a_stale_hr_decision(test_session_factory, sample_docx_cv, source_change):
    from app.db.models import SanitizedVersion
    from app.domain.enums import SanitizedVersionStatus
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    async with client_for(ctx) as client:
        await manual_decision(client, ctx)
        async with test_session_factory() as session:
            application = await session.get(Application, ctx["app_id"])
            application.generation += 1
            if source_change == "revoke":
                version = await session.get(SanitizedVersion, application.current_sanitized_version_id)
                version.status = SanitizedVersionStatus.REVOKED
                application.current_sanitized_version_id = None
            await session.commit()
        response = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")
        assert response.status_code == 200
        draft = response.json()
        approve = await client.put(f"/api/v1/applications/{ctx['app_id']}/email-draft", json={
            "draft_id": draft["id"], "expected_version": draft["version_no"], "subject": draft["subject"],
            "body": draft["body"], "status": "approved", "acknowledged_content": True})
        assert approve.status_code == 409, approve.text
        assert "EMAIL_DECISION_STALE" in approve.text


@pytest.mark.asyncio
async def test_candidate_deletion_purges_all_correspondence_revisions(test_session_factory):
    from tests.test_deletion import setup_deletion_fixture
    from app.services.deletion import execute_purge_job
    from app.db.models.email_draft import EmailDraft
    from app.db.models import DeletionRequest
    async with test_session_factory() as session:
        ctx = await setup_deletion_fixture(session)
    async with client_for(ctx) as client:
        created = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")
        assert created.status_code == 200, created.text
        deleted = await client.post("/api/v1/deletion-requests", json={"scope": "application", "target_id": str(ctx["app_id"]), "reason_category": "gdpr_erasure"})
        assert deleted.status_code == 201, deleted.text
    async with test_session_factory() as session:
        await execute_purge_job(session, job_id=uuid.UUID(deleted.json()["job_id"]))
        await session.commit()
        assert list((await session.execute(select(EmailDraft).where(EmailDraft.application_id == ctx["app_id"]))).scalars()) == []
        request = await session.get(DeletionRequest, uuid.UUID(deleted.json()["id"]))
        assert request.verification_report["email_drafts_purged"] == 1


@pytest.mark.asyncio
async def test_new_jd_requires_new_rubric_and_hr_decision_before_email_approval(test_session_factory, sample_docx_cv):
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    async with client_for(ctx) as client:
        await manual_decision(client, ctx)
        req = (await client.get(f"/api/v1/requisitions/{ctx['req_id']}")).json()
        new_jd = await client.post(f"/api/v1/requisitions/{ctx['req_id']}/jd-versions", json={
            "source_text": "Yêu cầu mới:\n- Thiết kế giao diện React cho ứng dụng nghiệp vụ.\n- Kiểm thử accessibility và responsive trên điện thoại.",
            "change_reason": "Đổi phạm vi năng lực cần tuyển", "expected_requisition_version": req["row_version"]})
        assert new_jd.status_code == 201, new_jd.text
        created = await client.post(f"/api/v1/applications/{ctx['app_id']}/email-draft/generate")
        assert created.status_code == 200
        draft = created.json()
        approved = await client.put(f"/api/v1/applications/{ctx['app_id']}/email-draft", json={
            "draft_id": draft["id"], "expected_version": draft["version_no"], "subject": draft["subject"],
            "body": draft["body"], "status": "approved", "acknowledged_content": True})
        assert approved.status_code == 409, approved.text
        assert "EMAIL_DECISION_STALE" in approved.text


@pytest.mark.asyncio
async def test_shortlist_does_not_invent_core_floors_from_dynamic_weights(test_session_factory, sample_docx_cv):
    from app.db.models import RubricVersion, RubricCriterion
    from sqlalchemy import delete
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
        rubric = await session.get(RubricVersion, ctx["rubric_id"])
        rubric.threshold_config = {"threshold": 60, "core_minimum_scores": {}}
        await session.execute(delete(RubricCriterion).where(RubricCriterion.rubric_version_id == rubric.id))
        for criterion_id in ("ui_delivery", "ui_testing"):
            session.add(RubricCriterion(rubric_version_id=rubric.id, criterion_id=criterion_id, label_vi=criterion_id,
                description_vi="Năng lực theo JD", weight=50, anchors={str(i): "Mức bằng chứng" for i in range(5)}))
        run = await add_run(session, ctx)
        await session.execute(delete(CriterionAssessment).where(CriterionAssessment.run_id == run.id))
        run.comparable_score = 62.5
        run.observed_score = 62.5
        for criterion_id, score in (("ui_delivery", 1), ("ui_testing", 4)):
            session.add(CriterionAssessment(run_id=run.id, criterion_id=criterion_id, status=CriterionOutcome.ASSESSED,
                score=score, rationale="Theo bằng chứng từ CV", missing_information=[]))
        await session.commit()
    async with client_for(ctx) as client:
        result = await client.get(f"/api/v1/requisitions/{ctx['req_id']}/shortlist")
        assert result.status_code == 200
        own = next(item for item in result.json()["candidates"] if item["application_id"] == str(ctx["app_id"]))
        assert own["tier"] == "recommend"
        assert own["core_failed_criteria"] == []


@pytest.mark.asyncio
async def test_reassessment_and_source_revoke_do_not_deadlock(test_session_factory, sample_docx_cv):
    """A source mutation must wait for Application before locking assessment FK rows."""
    import asyncio
    from sqlalchemy import text
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, sample_docx_cv)
    async with client_for(ctx) as client:
        grant = await client.post(f"/api/v1/applications/{ctx['app_id']}/raw-grants", json={
            "grantee_user_id": str(ctx["owner"].id), "scopes": ["raw_cv"],
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "reason": "Synthetic concurrent source mutation regression"})
        assert grant.status_code == 201, grant.text
        async with test_session_factory() as enqueue_session:
            await enqueue_session.execute(select(Application).where(Application.id == ctx["app_id"]).with_for_update())
            blocker_pid = (await enqueue_session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            revoke_task = asyncio.create_task(client.post(f"/api/v1/sanitized-versions/{ctx['sanitized_id']}/revoke", json={
                "expected_application_version": 1, "reason": "Synthetic concurrent source revoke"}))
            try:
                # Wait for the actual lock conflict rather than guessing request timing.
                async def wait_for_application_lock():
                    while True:
                        async with test_session_factory() as observer:
                            waiting = (await observer.execute(text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE :pid = ANY(pg_blocking_pids(pid)) AND wait_event_type = 'Lock')"
                            ), {"pid": blocker_pid})).scalar_one()
                        if waiting:
                            return
                        if revoke_task.done():
                            response = await revoke_task
                            pytest.fail(f"Revoke did not wait for application lock: {response.status_code}")
                        await asyncio.sleep(0.02)
                await asyncio.wait_for(wait_for_application_lock(), timeout=3)
                # This inserts real FKs to the document + sanitized source while App is locked,
                # the same interleaving produced by rubric-driven reassessment enqueue.
                await asyncio.wait_for(add_run(enqueue_session, ctx), timeout=4)
                response = await asyncio.wait_for(revoke_task, timeout=4)
                assert response.status_code == 200, response.text
            finally:
                await enqueue_session.rollback()
                if not revoke_task.done():
                    revoke_task.cancel()
                await asyncio.gather(revoke_task, return_exceptions=True)


def test_rubric_proposal_resolves_original_markdown_sources_and_normalizes_priorities():
    import json
    from app.services import rubric_drafting
    source = "Yêu cầu:\n* Thiết kế API **Python** có phân quyền.\n* Kiểm thử backend bằng **pytest**."
    proposal = rubric_drafting.local_jd_draft(source)
    proposal["criteria"][0]["weight"] = 80
    proposal["criteria"][1]["weight"] = 40
    for index, criterion in enumerate(proposal["criteria"], start=2):
        criterion["source_requirements"] = [{"requirement_id": f"JD-SOURCE-{index:03d}"}]
    output = rubric_drafting.validate_jd_proposal(json.dumps(proposal), source)
    assert output is not None
    assert [c["weight"] for c in output["criteria"]] == [67, 33]
    assert output["criteria"][0]["source_requirements"][0]["quote"] == "* Thiết kế API **Python** có phân quyền."
    assert output["criteria"][1]["source_requirements"][0]["quote"] == "* Kiểm thử backend bằng **pytest**."
    assert sum(c["weight"] for c in output["criteria"]) == 100


def test_rubric_proposal_never_uses_an_unknown_source_id_or_model_supplied_quote():
    import json
    from app.services import rubric_drafting
    source = "Yêu cầu:\n- Thiết kế giao diện React và TypeScript.\n- Viết kiểm thử giao diện Playwright."
    proposal = rubric_drafting.local_jd_draft(source)
    for index, criterion in enumerate(proposal["criteria"], start=2):
        criterion["source_requirements"] = [{"requirement_id": f"JD-SOURCE-{index:03d}"}]
    validate = rubric_drafting.validate_jd_proposal
    proposal["criteria"][0]["source_requirements"][0]["requirement_id"] = "JD-SOURCE-999"
    with pytest.raises(ValueError, match="JD_SOURCE_ID_UNKNOWN"):
        validate(json.dumps(proposal), source)
    proposal["criteria"][0]["source_requirements"][0] = {"requirement_id": "JD-SOURCE-002", "quote": "Invented source quote"}
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        validate(json.dumps(proposal), source)


def test_rubric_proposal_keeps_minimum_weights_and_never_turns_missing_evidence_into_zero():
    import json
    from app.services import rubric_drafting
    source = "Yêu cầu:\n- Thiết kế API Python và phân quyền.\n- Viết kiểm thử backend với pytest."
    base = rubric_drafting.local_jd_draft(source)
    proposal = {"criteria": [], "recommendation_policy": base["recommendation_policy"]}
    for index in range(11):
        item = json.loads(json.dumps(base["criteria"][index % 2]))
        item["id"] = f"competency_{index}"
        item["weight"] = 10
        item["source_requirements"] = [{"requirement_id": f"JD-SOURCE-{2 + index % 2:03d}"}]
        proposal["criteria"].append(item)
    validate = rubric_drafting.validate_jd_proposal
    output = validate(json.dumps(proposal), source)
    assert output is not None
    assert [item["weight"] for item in output["criteria"]] == [10] + [9] * 10
    extreme = json.loads(json.dumps(proposal))
    for index, item in enumerate(extreme["criteria"]):
        item["weight"] = 99 if index == 0 else 1
    assert [item["weight"] for item in validate(json.dumps(extreme), source)["criteria"]] == [90] + [1] * 10
    proposal["criteria"][0]["weight"] = 0
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        validate(json.dumps(proposal), source)
    proposal["criteria"][0]["weight"] = 10
    proposal["criteria"][0]["scoring_anchors"][0]["description"] = "Không có bằng chứng"
    with pytest.raises(ValueError, match="MISSING_EVIDENCE_IS_NOT_ZERO"):
        validate(json.dumps(proposal), source)


@pytest.mark.parametrize("minimum", [True, False, "2", 2.0, "0", -1, 5])
def test_rubric_proposal_rejects_coerced_or_out_of_range_core_minima(minimum):
    import json
    from pydantic import ValidationError
    from app.services import rubric_drafting
    source = "Yêu cầu:\n- Bắt buộc thiết kế API Python có phân quyền.\n- Viết kiểm thử backend với pytest."
    proposal = rubric_drafting.local_jd_draft(source)
    for index, criterion in enumerate(proposal["criteria"], start=2):
        criterion["source_requirements"] = [{"requirement_id": f"JD-SOURCE-{index:03d}"}]
    proposal["recommendation_policy"]["core_minimum_scores"] = {"jd_competency_01": minimum}
    with pytest.raises(ValidationError):
        rubric_drafting.validate_jd_proposal(json.dumps(proposal), source)


@pytest.mark.parametrize("threshold", [True, "70", 70.0])
def test_rubric_proposal_rejects_coerced_threshold(threshold):
    import json
    from pydantic import ValidationError
    from app.services import rubric_drafting
    source = "Yêu cầu:\n- Thiết kế API Python có phân quyền.\n- Viết kiểm thử backend với pytest."
    proposal = rubric_drafting.local_jd_draft(source)
    for index, criterion in enumerate(proposal["criteria"], start=2):
        criterion["source_requirements"] = [{"requirement_id": f"JD-SOURCE-{index:03d}"}]
    proposal["recommendation_policy"]["threshold"] = threshold
    with pytest.raises(ValidationError):
        rubric_drafting.validate_jd_proposal(json.dumps(proposal), source)


@pytest.mark.parametrize("zero_description", [
    "Không thể hiện kinh nghiệm thiết kế RESTful API.",
    "Không chứng minh kiến thức về kiến trúc phần mềm.",
    "CV không đề cập kỹ năng kiểm thử.",
    "Does not demonstrate backend experience.",
])
def test_rubric_proposal_rejects_absence_of_claims_as_zero(zero_description):
    import json
    from app.services import rubric_drafting
    source = "Yêu cầu:\n- Thiết kế API Python có phân quyền.\n- Viết kiểm thử backend với pytest."
    proposal = rubric_drafting.local_jd_draft(source)
    for index, criterion in enumerate(proposal["criteria"], start=2):
        criterion["source_requirements"] = [{"requirement_id": f"JD-SOURCE-{index:03d}"}]
    proposal["criteria"][0]["scoring_anchors"][0]["description"] = zero_description
    with pytest.raises(ValueError, match="MISSING_EVIDENCE_IS_NOT_ZERO"):
        rubric_drafting.validate_jd_proposal(json.dumps(proposal), source)
