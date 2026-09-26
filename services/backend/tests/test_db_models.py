"""Integration tests for Database Models, PostgreSQL, pgvector and Constraints.
Runs against real PostgreSQL database as mandated by Task B01 acceptance criteria.
"""
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    Application,
    Candidate,
    CandidateIdentity,
    Document,
    IdempotencyRecord,
    JDVersion,
    Job,
    Organization,
    Requisition,
    RequisitionMembership,
    RetrievalChunk,
    RubricCriterion,
    RubricVersion,
    SanitizedVersion,
    SourceSpan,
    User,
    UserAccountRole,
)
from app.domain.enums import (
    AccountRole,
    CriterionId,
    EnvironmentMode,
    JobStatus,
    JobType,
    MembershipRole,
    RequisitionStatus,
    RubricStatus,
    UserStatus,
)


@pytest.mark.asyncio
async def test_organization_and_user_creation(test_session_factory):
    """Test creating organization, user, and verifying unique login constraint."""
    factory = test_session_factory
    login = f"user_{uuid.uuid4().hex[:8]}"

    async with factory() as session:
        org = Organization(
            name="Đại học Công nghệ Quốc gia",
            environment=EnvironmentMode.SANDBOX,
        )
        session.add(org)
        await session.flush()
        assert org.id is not None

        user = User(
            login_name=login,
            display_name="Trần Thị Mai (HR)",
            password_hash="argon2id_hash_placeholder",
            status=UserStatus.ACTIVE,
        )
        session.add(user)
        await session.flush()

        role = UserAccountRole(
            user_id=user.id,
            role=AccountRole.RECRUITER,
        )
        session.add(role)
        await session.commit()

    # Verify duplicate login_name is rejected in a separate session
    async with factory() as session:
        dup_user = User(
            login_name=login,
            display_name="Duplicate User",
            password_hash="hash",
        )
        session.add(dup_user)
        with pytest.raises(IntegrityError):
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise


@pytest.mark.asyncio
async def test_requisition_rubric_and_criteria(test_session_factory):
    """Test requisition, JD version, rubric version and 6 criteria."""
    factory = test_session_factory
    async with factory() as session:
        org = Organization(name="Đại học Test", environment=EnvironmentMode.SANDBOX)
        user = User(login_name=f"recruiter_{uuid.uuid4().hex[:8]}", display_name="Recruiter", password_hash="hash")
        session.add_all([org, user])
        await session.flush()

        req = Requisition(
            organization_id=org.id,
            title="Chuyên viên phát triển phần mềm Backend Python",
            status=RequisitionStatus.DRAFT,
        )
        session.add(req)
        await session.flush()

        membership = RequisitionMembership(
            requisition_id=req.id,
            user_id=user.id,
            membership_role=MembershipRole.OWNER,
        )
        session.add(membership)

        jd = JDVersion(
            requisition_id=req.id,
            version_no=1,
            source_text="Mô tả công việc Backend Python cho hệ thống trường...",
            text_hash="a" * 64,
            created_by=user.id,
        )
        session.add(jd)
        await session.flush()

        rubric = RubricVersion(
            requisition_id=req.id,
            jd_version_id=jd.id,
            version_no=1,
            status=RubricStatus.APPROVED,
            threshold_config={"consider_next_round_min": 70, "core_min": 2},
            content_hash="b" * 64,
            approved_by=user.id,
        )
        session.add(rubric)
        await session.flush()

        criteria_weights = {
            CriterionId.PYTHON_BACKEND.value: 20,
            CriterionId.API_DESIGN.value: 25,
            CriterionId.SQL_DATA.value: 20,
            CriterionId.TESTING_DEBUGGING.value: 15,
            CriterionId.SECURITY_PRIVACY.value: 10,
            CriterionId.DELIVERY_OPS.value: 10,
        }
        for crit_id, weight in criteria_weights.items():
            crit = RubricCriterion(
                rubric_version_id=rubric.id,
                criterion_id=crit_id,
                label_vi=f"Tiêu chí {crit_id}",
                description_vi="Mô tả mức năng lực",
                weight=weight,
                anchors={"0": "Kém", "1": "Cơ bản", "2": "Đạt", "3": "Tốt", "4": "Xuất sắc"},
            )
            session.add(crit)

        await session.commit()
        assert sum(criteria_weights.values()) == 100


@pytest.mark.asyncio
async def test_duplicate_application_constraint(test_session_factory):
    """Test that duplicate application for same (requisition_id, candidate_id) is rejected."""
    factory = test_session_factory
    req_id = None
    cand_id = None

    async with factory() as session:
        org = Organization(name="Đại học Test 2", environment=EnvironmentMode.SANDBOX)
        session.add(org)
        await session.flush()

        req = Requisition(organization_id=org.id, title="Tuyển dụng IT", status=RequisitionStatus.OPEN)
        candidate = Candidate(organization_id=org.id, public_label=f"CAND-{uuid.uuid4().hex[:6]}")
        session.add_all([req, candidate])
        await session.flush()

        req_id = req.id
        cand_id = candidate.id

        # First application succeeds
        app1 = Application(requisition_id=req.id, candidate_id=candidate.id)
        session.add(app1)
        await session.commit()

    # Second application for same candidate + requisition must fail
    async with factory() as session:
        app2 = Application(requisition_id=req_id, candidate_id=cand_id)
        session.add(app2)
        with pytest.raises(IntegrityError):
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise


@pytest.mark.asyncio
async def test_source_spans_and_pgvector_chunks(test_session_factory):
    """Test storing source spans and querying vector embeddings with pgvector."""
    factory = test_session_factory
    sanitized_id = None
    chunk_id = None

    async with factory() as session:
        org = Organization(name="Đại học Test 3", environment=EnvironmentMode.SANDBOX)
        session.add(org)
        await session.flush()

        req = Requisition(organization_id=org.id, title="Tuyển dụng IT", status=RequisitionStatus.OPEN)
        candidate = Candidate(organization_id=org.id, public_label=f"CAND-{uuid.uuid4().hex[:6]}")
        session.add_all([req, candidate])
        await session.flush()

        app = Application(requisition_id=req.id, candidate_id=candidate.id)
        session.add(app)
        await session.flush()

        doc = Document(
            application_id=app.id,
            version_no=1,
            original_name_private="cv_candidate.pdf",
            mime_verified="application/pdf",
            byte_size=10240,
            sha256="c" * 64,
            blob_key="storage/cv.pdf",
        )
        session.add(doc)
        await session.flush()

        sanitized = SanitizedVersion(
            application_id=app.id,
            document_id=doc.id,
            version_no=1,
            canonical_text="Kinh nghiệm 3 năm lập trình Python và FastAPI.",
            sha256="d" * 64,
        )
        session.add(sanitized)
        await session.flush()
        sanitized_id = sanitized.id

        span_id = f"spn_{uuid.uuid4().hex[:24]}"
        span = SourceSpan(
            span_id=span_id,
            full_hash="e" * 64,
            sanitized_version_id=sanitized.id,
            start_cp=0,
            end_cp=43,
            text="Kinh nghiệm 3 năm lập trình Python và FastAPI.",
        )
        session.add(span)

        # 768-dimensional mock embedding vector (for multilingual-e5-base)
        mock_vector = [0.01 * (i % 10) for i in range(768)]
        chunk = RetrievalChunk(
            sanitized_version_id=sanitized.id,
            chunk_index=0,
            span_ids=[span_id],
            text=span.text,
            embedding=mock_vector,
            embedding_config_id="multilingual-e5-base-v1",
        )
        session.add(chunk)
        await session.commit()
        chunk_id = chunk.id

    # Query using pgvector cosine distance: embedding.cosine_distance(...)
    async with factory() as session:
        query_vector = [0.01 * (i % 10) for i in range(768)]
        stmt = (
            select(RetrievalChunk)
            .where(RetrievalChunk.sanitized_version_id == sanitized_id)
            .order_by(RetrievalChunk.embedding.cosine_distance(query_vector))
            .limit(1)
        )
        result = await session.execute(stmt)
        retrieved_chunk = result.scalar_one()
        assert retrieved_chunk.id == chunk_id
        assert retrieved_chunk.chunk_index == 0


@pytest.mark.asyncio
async def test_idempotency_records_constraint(test_session_factory):
    """Test unique constraint on (actor_id, method, route_scope, key)."""
    factory = test_session_factory
    user_id = None
    key_val = f"idemp-key-{uuid.uuid4().hex[:8]}"

    async with factory() as session:
        user = User(login_name=f"actor_{uuid.uuid4().hex[:8]}", display_name="Actor", password_hash="hash")
        session.add(user)
        await session.flush()
        user_id = user.id

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        rec1 = IdempotencyRecord(
            actor_id=user.id,
            method="POST",
            route_scope="applications/upload",
            key=key_val,
            request_hash="f" * 64,
            expires_at=expires,
        )
        session.add(rec1)
        await session.commit()

    # Duplicate key for same actor & route must fail
    async with factory() as session:
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        rec2 = IdempotencyRecord(
            actor_id=user_id,
            method="POST",
            route_scope="applications/upload",
            key=key_val,
            request_hash="f" * 64,
            expires_at=expires,
        )
        session.add(rec2)
        with pytest.raises(IntegrityError):
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise


@pytest.mark.asyncio
async def test_job_queue_prioritization(test_session_factory):
    """Test jobs priority and index querying."""
    factory = test_session_factory
    target_id = uuid.uuid4()

    async with factory() as session:
        job1 = Job(
            type=JobType.ASSESS_APPLICATION,
            target_type="application",
            target_id=target_id,
            input_snapshot_hash="1" * 64,
            priority=0,
            status=JobStatus.QUEUED,
        )
        job2 = Job(
            type=JobType.ASSESS_APPLICATION,
            target_type="application",
            target_id=target_id,
            input_snapshot_hash="2" * 64,
            priority=100,  # higher priority
            status=JobStatus.QUEUED,
        )
        session.add_all([job1, job2])
        await session.commit()

    # Query claimable job ordered by priority DESC
    async with factory() as session:
        stmt = (
            select(Job)
            .where(Job.target_id == target_id, Job.status == JobStatus.QUEUED)
            .order_by(Job.priority.desc(), Job.created_at.asc())
        )
        result = await session.execute(stmt)
        top_job = result.scalars().first()
        assert top_job is not None
        assert top_job.priority == 100
