"""Regression of upload response-loss retries and private blind drafts."""
import io, uuid
from datetime import datetime, timezone
import docx, pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.main import app
from app.db.models import Application, AssessmentRun, CriterionAssessment, CriterionEvidence, JDVersion, Job, IndependentReviewDraft, Requisition, SanitizedVersion
from app.domain.enums import CriterionId, CriterionOutcome, SanitizedVersionStatus, JobType, JobStatus
from app.domain.authorization import SESSION_COOKIE_NAME
from tests.test_decisions import setup_test_context

def cv_bytes():
    document = docx.Document(); document.add_paragraph("Synthetic Python FastAPI experience.")
    out = io.BytesIO(); document.save(out); return out.getvalue()

async def context(factory, assessment=False):
    async with factory() as session:
        ctx = await setup_test_context(session, cv_bytes())
        req = await session.get(Requisition, ctx["req_id"]); req.current_rubric_version_id = ctx["rubric_id"]
        jd = await session.get(JDVersion, req.current_jd_version_id); jd.egress_reviewed_at = datetime.now(timezone.utc); jd.egress_reviewed_by = ctx["owner"].id
        if assessment:
            run = AssessmentRun(application_id=ctx["app_id"], job_id=uuid.uuid4(), run_no=1, status="succeeded", snapshot={}, snapshot_hash="a"*64,
                application_generation=1, document_id=ctx["doc_id"], sanitized_version_id=ctx["sanitized_id"], rubric_version_id=ctx["rubric_id"])
            session.add(run); await session.flush()
            application = await session.get(Application, ctx["app_id"]); application.current_assessment_run_id = run.id
            for cid in CriterionId:
                session.add(CriterionAssessment(run_id=run.id, criterion_id=cid.value, status=CriterionOutcome.ASSESSED, score=2, rationale="Đối chiếu kinh nghiệm từ CV.", missing_information=[]))
                session.add(CriterionEvidence(run_id=run.id, criterion_id=cid.value, span_id=ctx["span_id"], quote=ctx["span_text"], resolved_start_cp=0, resolved_end_cp=len(ctx["span_text"])))
            # Normalize synthetic source coordinates to actual Python Unicode codepoints.
            from app.db.models import SourceSpan
            span = await session.get(SourceSpan, ctx["span_id"]); span.end_cp = len(span.text)
        await session.commit()
        return ctx

def client(ctx, role="o"):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={SESSION_COOKIE_NAME: ctx[f"{role}_token"]}, headers={"X-CSRF-Token": ctx[f"{role}_csrf"]})

@pytest.mark.asyncio
async def test_copilot_route_is_removed(test_session_factory):
    ctx = await context(test_session_factory)
    async with client(ctx) as api:
        result = await api.post(f"/api/v1/applications/{ctx['app_id']}/copilot", json={"message": "Giải thích tiêu chí Python"})
    assert result.status_code == 404

@pytest.mark.asyncio
async def test_application_response_loss_idempotency(test_session_factory):
    ctx = await context(test_session_factory)
    async with client(ctx) as api:
        route = f"/api/v1/requisitions/{ctx['req_id']}/applications"
        first = await api.post(route, json={}, headers={"Idempotency-Key": "lost-response"})
        retry = await api.post(route, json={}, headers={"Idempotency-Key": "lost-response"})
        assert first.status_code == retry.status_code == 201
        assert first.json()["id"] == retry.json()["id"]
        changed = await api.post(route, json={"candidate_id": str(ctx["cand_id"])}, headers={"Idempotency-Key": "lost-response"})
        assert changed.status_code == 409
        applications = await api.get(route); assert len(applications.json()) == 2

@pytest.mark.asyncio
async def test_current_workflow_progress(test_session_factory):
    ctx = await context(test_session_factory, assessment=True)
    async with client(ctx) as api:
        path = f"/api/v1/applications/{ctx['app_id']}/progress"
        result = await api.get(path); assert result.status_code == 200
        assert result.json()["stage"] == "awaiting_decision"
        async with test_session_factory() as session:
            application = await session.get(Application, ctx["app_id"]); application.generation += 1; await session.commit()
        stale = await api.get(path)
        assert stale.json()["stage"] == "ready_for_ai"
        assert stale.json()["assessment_status"] == "missing_or_stale"

@pytest.mark.asyncio
async def test_private_draft_restore_conflict_and_locked_label(test_session_factory):
    ctx = await context(test_session_factory)
    async with client(ctx, "r") as reviewer:
        route = f"/api/v1/applications/{ctx['app_id']}/independent-review"
        source = (await reviewer.get(route + "/context")).json()
        ids = [c["id"] for c in source["criteria"]]
        payload = {"review_kind": "hr", "expected_generation": 1, "expected_document_id": source["document_id"], "expected_sanitized_version_id": source["sanitized_version_id"], "expected_rubric_version_id": source["rubric_version_id"],
            "criterion_scores": {cid: None for cid in ids}, "criterion_statuses": {cid: "insufficient_evidence" for cid in ids},
            "criterion_quotes": {cid: "" for cid in ids}, "criterion_notes": {cid: "Chưa đủ bằng chứng trong CV." for cid in ids}, "recommendation": "needs_clarification"}
        saved = await reviewer.put(route + "/draft", json={**payload, "expected_draft_version": 0})
        assert saved.status_code == 200, saved.text
        assert saved.json()["version"] == 1
        restored = await reviewer.get(route + "/draft"); assert restored.json()["payload"] == payload
        conflict = await reviewer.put(route + "/draft", json={**payload, "expected_draft_version": 0}); assert conflict.status_code == 409
        locked = await reviewer.post(route, json={**payload, "criterion_quotes": {cid: None for cid in ids}}); assert locked.status_code == 201
        deny = await reviewer.put(route + "/draft", json={**payload, "expected_draft_version": 1}); assert deny.status_code == 409
    async with client(ctx) as owner:
        assert (await owner.get(route + "/draft")).status_code == 403
    async with test_session_factory() as session:
        assert not (await session.execute(select(IndependentReviewDraft).where(IndependentReviewDraft.application_id == ctx["app_id"]))).scalars().all()

@pytest.mark.asyncio
async def test_hr_revision_rejects_fabricated_quote(test_session_factory):
    ctx = await context(test_session_factory)
    async with client(ctx) as api:
        payload = {"expected_application_version": 1, "source_snapshot_ref": {"document_id": str(ctx["doc_id"]), "sanitized_version_id": str(ctx["sanitized_id"]), "rubric_version_id": str(ctx["rubric_id"]), "application_generation": 1},
            "criteria": [{"criterion_id": cid.value, "status": "assessed", "score": 3, "evidence": [{"span_id": ctx["span_id"], "quote": "Invented achievement that is not in the CV"}], "rationale": "Claim to verify", "missing_information": []} for cid in CriterionId], "summary_reason": "Reviewer must use existing evidence."}
        result = await api.post(f"/api/v1/applications/{ctx['app_id']}/hr-revisions", json=payload)
        assert result.status_code == 422
        assert "INVALID_EVIDENCE" in result.text

@pytest.mark.asyncio
async def test_pending_assessment_hides_previous_results(test_session_factory):
    ctx = await context(test_session_factory, assessment=True)
    async with test_session_factory() as session:
        session.add(Job(type=JobType.ASSESS_APPLICATION, status=JobStatus.QUEUED, target_type="application", target_id=ctx["app_id"], input_snapshot_hash="b" * 64, payload_ref={}))
        await session.commit()
    async with client(ctx) as api:
        progress = (await api.get(f"/api/v1/applications/{ctx['app_id']}/progress")).json()
        assert progress["stage"] == "analyzing" and progress["assessment_status"] == "running"
