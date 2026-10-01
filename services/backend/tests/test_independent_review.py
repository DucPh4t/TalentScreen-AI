"""Independent labels must be locked to the source snapshot before AI reveal."""
from __future__ import annotations

from types import SimpleNamespace
import io

import docx
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1 import independent_review
from app.db.models import Application, Requisition, RubricCriterion, RubricVersion, User
from app.domain.authorization import AuthenticatedContext, SESSION_COOKIE_NAME
from app.domain.enums import AccountRole
from app.main import app
from tests.test_decisions import setup_test_context
from tests.test_admin_observability import create_admin_user


@pytest.mark.asyncio
async def test_independent_label_snapshot_and_shadow_gate(test_session_factory, monkeypatch):
    document = docx.Document()
    document.add_paragraph("Backend Python and FastAPI experience.")
    data = io.BytesIO()
    document.save(data)
    async with test_session_factory() as session:
        ctx = await setup_test_context(session, data.getvalue())
        requisition = await session.get(Requisition, ctx["req_id"])
        requisition.current_rubric_version_id = ctx["rubric_id"]
        await session.commit()

    transport = ASGITransport(app=app)
    async with test_session_factory() as session:
        admin, admin_token, _ = await create_admin_user(session)
        await session.commit()
    async with AsyncClient(transport=transport, base_url="http://test",
                           cookies={SESSION_COOKIE_NAME: admin_token}) as admin_client:
        queue = await admin_client.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")
        assert queue.status_code == 200
        assert queue.json()[0]["sanitized_status"] == "approved"
        assert "canonical_text" not in queue.text
        matrix = await admin_client.get(f"/api/v1/requisitions/{ctx['req_id']}/comparison")
        assert matrix.status_code == 404
    async with AsyncClient(transport=transport, base_url="http://test",
                           cookies={SESSION_COOKIE_NAME: ctx["o_token"]}) as owner:
        queue = await owner.get(f"/api/v1/requisitions/{ctx['req_id']}/review-queue")
        assert queue.status_code == 200
        assert queue.json()[0]["sanitized_status"] == "approved"
        matrix = await owner.get(f"/api/v1/requisitions/{ctx['req_id']}/comparison")
        assert matrix.status_code == 200
        assert matrix.json()["candidates"][0]["comparable_score"] is None
        labels_before = await owner.get(f"/api/v1/requisitions/{ctx['req_id']}/independent-reviews")
        assert labels_before.status_code == 200
        assert labels_before.json() == []
    async with AsyncClient(transport=transport, base_url="http://test",
                           cookies={SESSION_COOKIE_NAME: ctx["r_token"]},
                           headers={"X-CSRF-Token": ctx["r_csrf"]}) as reviewer:
        forbidden_matrix = await reviewer.get(f"/api/v1/requisitions/{ctx['req_id']}/comparison")
        assert forbidden_matrix.status_code == 403
        forbidden_labels = await reviewer.get(f"/api/v1/requisitions/{ctx['req_id']}/independent-reviews")
        assert forbidden_labels.status_code == 403
        worklist = await reviewer.get(f"/api/v1/requisitions/{ctx['req_id']}/independent-reviews/mine")
        assert worklist.status_code == 200
        assert worklist.json()[0]["ready"] is True
        assert worklist.json()[0]["submitted"] is False

        response = await reviewer.get(f"/api/v1/applications/{ctx['app_id']}/independent-review/context")
        assert response.status_code == 200
        source = response.json()
        assert "sanitized_text" in source
        assert "observed_score" not in source
        assert "AI" not in source

        payload = {
            "review_kind": "it",
            "expected_generation": source["application_generation"],
            "expected_document_id": source["document_id"],
            "expected_sanitized_version_id": source["sanitized_version_id"],
            "expected_rubric_version_id": source["rubric_version_id"],
            "criterion_scores": {criterion["id"]: None for criterion in source["criteria"]},
            "criterion_statuses": {criterion["id"]: "insufficient_evidence" for criterion in source["criteria"]},
            "criterion_quotes": {criterion["id"]: None for criterion in source["criteria"]},
            "criterion_notes": {criterion["id"]: "Chưa đủ bằng chứng trong CV." for criterion in source["criteria"]},
            "recommendation": "needs_clarification",
        }
        stale = await reviewer.post(f"/api/v1/applications/{ctx['app_id']}/independent-review",
                                    json={**payload, "expected_generation": 99})
        assert stale.status_code == 409
        first_id = source["criteria"][0]["id"]
        invalid_grounding = {
            **payload,
            "criterion_scores": {**payload["criterion_scores"], first_id: 3},
            "criterion_statuses": {**payload["criterion_statuses"], first_id: "assessed"},
            "criterion_quotes": {**payload["criterion_quotes"], first_id: "Một kinh nghiệm hoàn toàn không có trong CV."},
        }
        ungrounded = await reviewer.post(f"/api/v1/applications/{ctx['app_id']}/independent-review", json=invalid_grounding)
        assert ungrounded.status_code == 422
        payload = {**invalid_grounding, "criterion_quotes": {
            **invalid_grounding["criterion_quotes"], first_id: "Kinh nghiệm làm việc chuyên sâu Backend Python và FastAPI."
        }}
        accepted = await reviewer.post(f"/api/v1/applications/{ctx['app_id']}/independent-review", json=payload)
        assert accepted.status_code == 201, accepted.text
        duplicate = await reviewer.post(f"/api/v1/applications/{ctx['app_id']}/independent-review", json=payload)
        assert duplicate.status_code == 409
        updated = await reviewer.get(f"/api/v1/applications/{ctx['app_id']}/independent-review/context")
        assert updated.json()["already_submitted"] is True

    async with AsyncClient(transport=transport, base_url="http://test",
                           cookies={SESSION_COOKIE_NAME: ctx["o_token"]}) as owner:
        exported = await owner.get(f"/api/v1/requisitions/{ctx['req_id']}/independent-reviews")
        assert exported.status_code == 200
        assert len(exported.json()) == 1
        assert exported.json()[0]["criterion_quotes"][first_id] == "Kinh nghiệm làm việc chuyên sâu Backend Python và FastAPI."
        assert exported.json()[0]["current_snapshot"] is True

    # Updating a rubric does not change the CV generation. The reviewer must be
    # able to label the new rubric while preserving the immutable previous label.
    async with test_session_factory() as session:
        previous = await session.get(RubricVersion, ctx["rubric_id"])
        replacement = RubricVersion(
            requisition_id=previous.requisition_id,
            jd_version_id=previous.jd_version_id,
            version_no=2,
            status=previous.status,
            content_hash="e" * 64,
            approved_by=previous.approved_by,
            approved_at=previous.approved_at,
        )
        session.add(replacement)
        await session.flush()
        criteria = (await session.execute(select(RubricCriterion).where(
            RubricCriterion.rubric_version_id == previous.id
        ))).scalars().all()
        for criterion in criteria:
            session.add(RubricCriterion(
                rubric_version_id=replacement.id,
                criterion_id=criterion.criterion_id,
                label_vi=criterion.label_vi,
                description_vi=criterion.description_vi,
                weight=criterion.weight,
                anchors=criterion.anchors,
            ))
        requisition = await session.get(Requisition, ctx["req_id"])
        requisition.current_rubric_version_id = replacement.id
        replacement_id = str(replacement.id)
        await session.commit()

    async with AsyncClient(transport=transport, base_url="http://test",
                           cookies={SESSION_COOKIE_NAME: ctx["r_token"]},
                           headers={"X-CSRF-Token": ctx["r_csrf"]}) as reviewer:
        context = await reviewer.get(f"/api/v1/applications/{ctx['app_id']}/independent-review/context")
        assert context.json()["already_submitted"] is False
        accepted = await reviewer.post(f"/api/v1/applications/{ctx['app_id']}/independent-review",
                                       json={**payload, "expected_rubric_version_id": replacement_id})
        assert accepted.status_code == 201, accepted.text

    async with AsyncClient(transport=transport, base_url="http://test",
                           cookies={SESSION_COOKIE_NAME: ctx["o_token"]}) as owner:
        exported = await owner.get(f"/api/v1/requisitions/{ctx['req_id']}/independent-reviews")
        assert len(exported.json()) == 2
        assert sum(label["current_snapshot"] for label in exported.json()) == 1
        assert all(label["blind_enforced"] is False for label in exported.json())

    monkeypatch.setattr(independent_review, "get_settings", lambda: SimpleNamespace(APP_ENV="pilot", PILOT_STAGE="shadow"))
    async with test_session_factory() as session:
        application = await session.get(Application, ctx["app_id"])
        user = await session.get(User, ctx["reviewer"].id)
        await independent_review.enforce_shadow_blind(session, application, AuthenticatedContext(user, [AccountRole.RECRUITER], None))
        application.generation += 1
        await session.flush()
        with pytest.raises(HTTPException) as denied:
            await independent_review.enforce_shadow_blind(session, application, AuthenticatedContext(user, [AccountRole.RECRUITER], None))
        assert denied.value.status_code == 403
