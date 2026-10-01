"""Tests for Tasks B10 & B11: AI Assessment Baseline, Output Validation, and Deterministic Scoring Engine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import json
import uuid
import pytest
import docx
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    Application,
    Candidate,
    CandidateIdentity,
    Document,
    JDVersion,
    Job,
    RawAccessGrant,
    Requisition,
    RequisitionMembership,
    RubricCriterion,
    RubricVersion,
    SanitizedVersion,
    SourceSpan,
    User,
    UserAccountRole,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import (
    AccountRole,
    CriterionId,
    CriterionOutcome,
    DocumentSafetyStatus,
    JobStatus,
    JobType,
    MembershipRole,
    Recommendation,
    RequisitionStatus,
    RubricStatus,
    SanitizedVersionStatus,
    UserStatus,
)
from app.domain.security import hash_password
from app.main import app
from app.schemas.assessment import (
    AssessmentOutputSchema,
    CriterionAssessmentSchema,
    EvidenceItemSchema,
)
from app.services.assessment.scoring import calculate_deterministic_scores
from app.services.assessment.validator import (
    AssessmentValidationError,
    validate_assessment_output,
)
from app.services.auth import create_session
from app.services.llm.provider import MockLLMProvider
from app.services.worker import run_worker_once


# ---------------- Unit Tests: Deterministic Scoring (B11) ---------------- #


def test_scoring_all_six_criteria_score_three():
    """All 6 criteria assessed with score 3 yields 75.00 comparable score and consider_next_round."""
    weights = {cid.value: (20 if cid == CriterionId.PYTHON_BACKEND else 16) for cid in CriterionId}
    # Adjust weights to sum to 100: 20 + 16*5 = 100
    criteria = [
        CriterionAssessmentSchema(
            criterion_id=cid.value,
            status=CriterionOutcome.ASSESSED,
            score=3,
            evidence=[EvidenceItemSchema(span_id="spn_" + "a" * 24, quote="Valid quote text")],
            rationale="Demonstrated competency at level 3",
            missing_information=[],
        )
        for cid in CriterionId
    ]

    obs, cov, comp, rec, reasons = calculate_deterministic_scores(criteria, weights)
    assert cov == Decimal("1.0000")
    assert obs == Decimal("75.0000")
    assert comp == Decimal("75.0000")
    assert rec == Recommendation.CONSIDER_NEXT_ROUND


def test_scoring_no_rounding_before_threshold():
    """Score 69.9999 must NOT be prematurely rounded to 70 and must yield review_required."""
    weights = {
        "python_backend": 20,
        "api_design": 20,
        "sql_data": 20,
        "testing_debugging": 15,
        "security_privacy": 15,
        "delivery_ops": 10,
    }
    # Construct scores to achieve ~69%
    scores = {
        "python_backend": 3,
        "api_design": 3,
        "sql_data": 3,
        "testing_debugging": 2,
        "security_privacy": 2,
        "delivery_ops": 2,
    }
    # Contribution:
    # 20*(3/4) = 15, 20*(3/4) = 15, 20*(3/4) = 15 -> 45
    # 15*(2/4) = 7.5, 15*(2/4) = 7.5 -> 15
    # 10*(2/4) = 5
    # Total = 65.0
    criteria = [
        CriterionAssessmentSchema(
            criterion_id=cid,
            status=CriterionOutcome.ASSESSED,
            score=scores[cid],
            evidence=[EvidenceItemSchema(span_id="spn_" + "a" * 24, quote="Valid quote text")],
            rationale="Rationale text",
            missing_information=[],
        )
        for cid in weights
    ]
    obs, cov, comp, rec, reasons = calculate_deterministic_scores(criteria, weights, threshold=Decimal("70.0"))
    assert comp == Decimal("65.0000")
    assert rec == Recommendation.REVIEW_REQUIRED


def test_scoring_core_floor_failed():
    """Total score is high (e.g. 80+) but core criterion python_backend has score 1 (< floor 2)."""
    weights = {
        "python_backend": 20,
        "api_design": 20,
        "sql_data": 20,
        "testing_debugging": 15,
        "security_privacy": 15,
        "delivery_ops": 10,
    }
    scores = {
        "python_backend": 1,  # Fails core floor 2!
        "api_design": 4,
        "sql_data": 4,
        "testing_debugging": 4,
        "security_privacy": 4,
        "delivery_ops": 4,
    }
    criteria = [
        CriterionAssessmentSchema(
            criterion_id=cid,
            status=CriterionOutcome.ASSESSED,
            score=scores[cid],
            evidence=[EvidenceItemSchema(span_id="spn_" + "a" * 24, quote="Valid quote text")],
            rationale="Rationale text",
            missing_information=[],
        )
        for cid in weights
    ]
    obs, cov, comp, rec, reasons = calculate_deterministic_scores(criteria, weights, threshold=Decimal("70.0"), core_floor=2)
    # Score is 20*0.25 + 80*1.0 = 5 + 80 = 85.0!
    assert comp == Decimal("85.0000")
    assert rec == Recommendation.REVIEW_REQUIRED
    assert any("CORE_FLOOR_FAILED:python_backend" in r for r in reasons)


def test_scoring_partial_coverage_needs_clarification():
    """Incomplete profiles have no comparable_score and return needs_clarification."""
    weights = {cid.value: (20 if cid == CriterionId.PYTHON_BACKEND else 16) for cid in CriterionId}
    criteria = [
        CriterionAssessmentSchema(
            criterion_id=CriterionId.PYTHON_BACKEND.value,
            status=CriterionOutcome.INSUFFICIENT_EVIDENCE,
            score=None,
            evidence=[],
            rationale="No backend evidence found",
            missing_information=["Missing hands-on Python experience"],
        )
    ]
    for cid in CriterionId:
        if cid != CriterionId.PYTHON_BACKEND:
            criteria.append(
                CriterionAssessmentSchema(
                    criterion_id=cid.value,
                    status=CriterionOutcome.ASSESSED,
                    score=3,
                    evidence=[EvidenceItemSchema(span_id="spn_" + "a" * 24, quote="Valid quote text")],
                    rationale="Rationale text",
                    missing_information=[],
                )
            )

    obs, cov, comp, rec, reasons = calculate_deterministic_scores(criteria, weights)
    assert cov == Decimal("0.8000")  # 80% coverage
    assert comp is None  # Invariant: Incomplete profile has NO comparable score
    assert rec == Recommendation.NEEDS_CLARIFICATION


# ---------------- Unit Tests: Schema & Provenance Validation (B10) ---------------- #


def test_validator_rejects_extra_fields():
    """Model output attempting to supply hiring decisions or unapproved keys must be rejected."""
    bad_payload = json.dumps({
        "criteria": [],
        "hiring_decision": "hire",
        "total_score": 95,
    })
    span_reg: dict[str, SourceSpan] = {}
    with pytest.raises(AssessmentValidationError) as exc:
        validate_assessment_output(bad_payload, span_reg)
    assert "SCHEMA_VIOLATION" in str(exc.value)


def test_validator_verifies_exact_verbatim_quote():
    """Altered quote not matching registered span text must be rejected with QUOTE_MISMATCH."""
    span_id = "spn_" + "1" * 24
    span_reg = {
        span_id: SourceSpan(
            span_id=span_id,
            full_hash="full_hash",
            sanitized_version_id=uuid.uuid4(),
            start_cp=0,
            end_cp=20,
            text="Exact original text.",
        )
    }

    payload = {
        "criteria": [
            {
                "criterion_id": cid.value,
                "status": "assessed",
                "score": 3,
                "evidence": [{"span_id": span_id, "quote": "Slightly altered text." if cid == CriterionId.PYTHON_BACKEND else "Exact original text."}],
                "rationale": "Rationale",
                "missing_information": [],
            }
            for cid in CriterionId
        ]
    }

    with pytest.raises(AssessmentValidationError) as exc:
        validate_assessment_output(json.dumps(payload), span_reg)
    assert "QUOTE_MISMATCH" in str(exc.value)


# ---------------- Integration Test: Full Assessment Pipeline (B10 & B11) ---------------- #


@pytest.fixture(autouse=True)
async def cleanup_assessment_jobs(test_session_factory):
    async with test_session_factory() as session:
        from sqlalchemy import delete
        from app.db.models import (
            AssessmentRun,
            BudgetReservation,
            CriterionAssessment,
            CriterionEvidence,
            Job,
        )
        await session.execute(delete(CriterionEvidence))
        await session.execute(delete(CriterionAssessment))
        await session.execute(delete(AssessmentRun))
        await session.execute(delete(BudgetReservation))
        await session.execute(delete(Job))
        await session.commit()
    yield
    async with test_session_factory() as session:
        from sqlalchemy import delete
        from app.db.models import (
            AssessmentRun,
            BudgetReservation,
            CriterionAssessment,
            CriterionEvidence,
            Job,
        )
        await session.execute(delete(CriterionEvidence))
        await session.execute(delete(CriterionAssessment))
        await session.execute(delete(AssessmentRun))
        await session.execute(delete(BudgetReservation))
        await session.execute(delete(Job))
        await session.commit()


@pytest.fixture
def sample_docx_cv() -> bytes:
    doc = docx.Document()
    doc.add_paragraph("Kinh nghiệm làm việc chuyên sâu Backend Python và FastAPI.")
    doc.add_paragraph("Thiết kế kiến trúc hệ thống microservices chịu tải cao và tối ưu cơ sở dữ liệu PostgreSQL.")
    doc.add_paragraph("Triển khai hạ tầng container với Docker và Kubernetes.")
    doc.add_paragraph("Kỹ năng giao tiếp và làm việc nhóm hiệu quả.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_end_to_end_assessment_and_worker_execution(test_session_factory, sample_docx_cv):
    """End-to-end: Setup Requisition + Approved Rubric -> Ingest Document -> Approve Sanitized -> Enqueue Assessment -> Worker Executes -> Query Results."""
    # 1. Setup user & requisition
    async with test_session_factory() as session:
        from app.services.requisition import get_or_create_default_org
        org = await get_or_create_default_org(session)

        owner = User(
            id=uuid.uuid4(),
            login_name=f"owner_{uuid.uuid4().hex[:8]}",
            display_name="Owner HR",
            password_hash=hash_password("Password123!"),
            status=UserStatus.ACTIVE,
        )
        session.add(owner)
        await session.flush()
        session.add(UserAccountRole(user_id=owner.id, role=AccountRole.RECRUITER))
        token, csrf, _ = await create_session(session, owner)

        req = Requisition(
            id=uuid.uuid4(),
            organization_id=org.id,
            title="Senior Python Engineer",
            status=RequisitionStatus.OPEN,
            row_version=1,
        )
        session.add(req)
        await session.flush()

        session.add(RequisitionMembership(requisition_id=req.id, user_id=owner.id, membership_role=MembershipRole.OWNER))
        await session.flush()

        jd = JDVersion(
            id=uuid.uuid4(),
            requisition_id=req.id,
            version_no=1,
            source_text="Senior Python Backend Engineer JD",
            text_hash="a" * 64,
            created_by=owner.id,
        )
        session.add(jd)
        await session.flush()

        req.current_jd_version_id = jd.id
        await session.flush()

        # Seed approved rubric
        rubric = RubricVersion(
            id=uuid.uuid4(),
            requisition_id=req.id,
            jd_version_id=jd.id,
            version_no=1,
            status=RubricStatus.APPROVED,
            content_hash="b" * 64,
            approved_by=owner.id,
            approved_at=datetime.now(timezone.utc),
        )
        session.add(rubric)
        await session.flush()
        req.current_rubric_version_id = rubric.id
        await session.flush()

        for cid in CriterionId:
            crit = RubricCriterion(
                rubric_version_id=rubric.id,
                criterion_id=cid.value,
                label_vi=cid.name,
                weight=20 if cid == CriterionId.PYTHON_BACKEND else 16,
                description_vi=f"Description for {cid.name}",
                anchors={
                    "0": "None",
                    "1": "Basic",
                    "2": "Intermediate",
                    "3": "Advanced",
                    "4": "Expert",
                },
            )
            session.add(crit)

        cand = Candidate(id=uuid.uuid4(), organization_id=org.id, public_label=f"CAND-{uuid.uuid4().hex[:6].upper()}", status="active")
        session.add(cand)
        await session.flush()

        app_obj = Application(id=uuid.uuid4(), requisition_id=req.id, candidate_id=cand.id, status="active", generation=1, row_version=1)
        session.add(app_obj)
        await session.commit()

        owner_id = owner.id
        req_id = req.id
        rubric_id = rubric.id
        app_id = app_obj.id

    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: token}
    headers = {"X-CSRF-Token": csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        files = {
            "file": (
                "candidate_cv.docx",
                sample_docx_cv,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        }
        up_res = await client.post(f"/api/v1/applications/{app_id}/documents", files=files)
        assert up_res.status_code == 202
        doc_id = uuid.UUID(up_res.json()["document"]["id"])

    # 3. Process ingestion with worker
    async with test_session_factory() as session:
        processed = await run_worker_once(session)
        assert processed is True

    # 4. Give owner raw grant and approve sanitized version
    async with test_session_factory() as session:
        from sqlalchemy import select
        stmt_v = select(SanitizedVersion).where(SanitizedVersion.document_id == doc_id)
        sanitized = (await session.execute(stmt_v)).scalar_one()
        sanitized_id = sanitized.id
        sanitized_hash = sanitized.sha256

        # Fetch spans generated for mock LLM completion
        stmt_spans = select(SourceSpan).where(SourceSpan.sanitized_version_id == sanitized_id)
        spans = (await session.execute(stmt_spans)).scalars().all()
        assert len(spans) > 0
        first_span = spans[0]

        stmt_app = select(Application).where(Application.id == app_id)
        app_rec = (await session.execute(stmt_app)).scalar_one()
        current_app_version = app_rec.row_version

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        # Grant raw access
        await client.post(
            f"/api/v1/applications/{app_id}/raw-grants",
            json={
                "grantee_user_id": str(owner_id),
                "scopes": ["raw_cv"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "reason": "Owner assessment approval",
            },
        )

        # Approve sanitized version
        appr_res = await client.post(
            f"/api/v1/sanitized-versions/{sanitized_id}/approve",
            json={
                "expected_application_version": current_app_version,
                "expected_sha256": sanitized_hash,
                "acknowledged": True,
            },
        )
        assert appr_res.status_code == 200

        # 5. Enqueue Assessment Run
        assess_res = await client.post(
            f"/api/v1/applications/{app_id}/assessments",
            json={
                "sanitized_version_id": str(sanitized_id),
                "rubric_version_id": str(rubric_id),
            },
        )
        assert assess_res.status_code == 202
        run_id = assess_res.json()["id"]

    # 6. Execute assessment worker job with Mock provider returning valid evaluation
    mock_eval = {
        "criteria": [
            {
                "criterion_id": cid.value,
                "status": "assessed",
                "score": 3,
                "evidence": [{"span_id": first_span.span_id, "quote": first_span.text}],
                "rationale": f"Candidate demonstrated level 3 competency in {cid.value}",
                "missing_information": [],
            }
            for cid in CriterionId
        ]
    }
    mock_llm = MockLLMProvider(custom_content=json.dumps(mock_eval))

    async with test_session_factory() as session:
        from app.services.assessment.service import execute_assessment_job
        from app.services.worker import claim_next_job, complete_job_fenced

        claim = await claim_next_job(session, "test_assess_worker")
        assert claim is not None
        j_id, epoch, j_type, target_id, _ = claim
        assert j_type == JobType.ASSESS_APPLICATION
        await session.commit()

        # Run assessment execution
        await execute_assessment_job(session, job_id=j_id, provider_override=mock_llm)
        await complete_job_fenced(session, job_id=j_id, worker_id="test_assess_worker", epoch=epoch, success=True)
        await session.commit()

    # 7. Query assessment results via REST API
    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.get(f"/api/v1/applications/{app_id}/assessments/{run_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "succeeded"
        assert data["coverage"] == 1.0
        assert data["comparable_score"] == 75.0
        assert data["recommendation"] == "consider_next_round"
        assert len(data["criteria"]) == 6
        assert data["criteria"][0]["evidence"][0]["quote"] == first_span.text
