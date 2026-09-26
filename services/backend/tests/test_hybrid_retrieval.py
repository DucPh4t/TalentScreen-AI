"""Tests for Task B16: Local multilingual embeddings and hybrid retrieval with pgvector and RRF."""
import math
import uuid
import pytest
from sqlalchemy import select

from app.db.models.candidate import Application, Candidate
from app.db.models.document import Document, RetrievalChunk, SanitizedVersion, SourceSpan
from app.db.models.requisition import Requisition
from app.domain.enums import RequisitionStatus, SanitizedVersionStatus
from app.services.embedding import (
    EMBEDDING_CONFIG_ID,
    EMBEDDING_DIMENSION,
    build_chunks_from_spans,
    embed_texts,
    index_sanitized_version,
)
from app.services.retrieval import build_hybrid_assessment_pack, hybrid_retrieve_for_criterion


def test_embedding_vector_properties():
    """Embedding vectors are normalized to unit length with 768 dimensions."""
    texts = ["Kỹ sư Golang với 5 năm kinh nghiệm", "Senior Frontend React Developer"]
    vectors = embed_texts(texts, prefix="passage: ")

    assert len(vectors) == 2
    for v in vectors:
        assert len(v) == EMBEDDING_DIMENSION
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-4

    # Distinct texts produce distinct embeddings
    dot_prod = sum(a * b for a, b in zip(vectors[0], vectors[1]))
    assert dot_prod < 0.99


def test_build_chunks_from_spans():
    """Spans are grouped into semantic chunks preserving span IDs and section headers."""
    dummy_version_id = uuid.uuid4()
    spans = [
        SourceSpan(
            span_id="spn_001",
            full_hash="h1",
            sanitized_version_id=dummy_version_id,
            start_cp=0,
            end_cp=40,
            page_number=1,
            section_label="Kinh nghiệm",
            language="vi",
            text="Lập trình hệ thống phân tán hiệu năng cao bằng Golang.",
        ),
        SourceSpan(
            span_id="spn_002",
            full_hash="h2",
            sanitized_version_id=dummy_version_id,
            start_cp=42,
            end_cp=90,
            page_number=1,
            section_label="Kinh nghiệm",
            language="vi",
            text="Tối ưu hóa truy vấn PostgreSQL với 100M bản ghi.",
        ),
        SourceSpan(
            span_id="spn_003",
            full_hash="h3",
            sanitized_version_id=dummy_version_id,
            start_cp=92,
            end_cp=130,
            page_number=1,
            section_label="Học vấn",
            language="vi",
            text="Tốt nghiệp chuyên ngành Khoa học Máy tính.",
        ),
    ]

    chunks = build_chunks_from_spans(spans)
    # Section "Kinh nghiệm" and "Học vấn" produce separate chunks
    assert len(chunks) == 2
    assert chunks[0]["section_label"] == "Kinh nghiệm"
    assert "spn_001" in chunks[0]["span_ids"]
    assert "spn_002" in chunks[0]["span_ids"]
    assert chunks[1]["section_label"] == "Học vấn"
    assert "spn_003" in chunks[1]["span_ids"]


@pytest.mark.asyncio
async def test_index_and_hybrid_retrieval(test_session_factory):
    """End-to-end: index sanitized spans into pgvector and query via dense + lexical + RRF."""
    async with test_session_factory() as session:
        # 1. Setup minimal database records
        from app.db.models.org_user import Organization
        org = Organization(id=uuid.uuid4(), name="Test Org B16")
        req = Requisition(
            id=uuid.uuid4(),
            organization_id=org.id,
            title="Backend Engineer Search",
            status=RequisitionStatus.OPEN,
        )
        cand = Candidate(
            id=uuid.uuid4(),
            organization_id=org.id,
            public_label=f"CAND-{uuid.uuid4().hex[:6].upper()}",
            status="active",
        )
        app = Application(
            id=uuid.uuid4(),
            requisition_id=req.id,
            candidate_id=cand.id,
            status="sanitized",
        )
        doc = Document(
            id=uuid.uuid4(),
            application_id=app.id,
            version_no=1,
            original_name_private="cv.pdf",
            sha256="abc123sha256document",
            blob_key="dummy/blob",
            byte_size=1024,
            mime_verified="application/pdf",
        )
        san = SanitizedVersion(
            id=uuid.uuid4(),
            application_id=app.id,
            document_id=doc.id,
            version_no=1,
            status=SanitizedVersionStatus.APPROVED,
            canonical_text="Golang backend microservices. Database indexing in PostgreSQL.",
            sha256="abc123hash",
        )

        spans = [
            SourceSpan(
                span_id="spn_go_1",
                full_hash="h_go",
                sanitized_version_id=san.id,
                start_cp=0,
                end_cp=29,
                page_number=1,
                section_label="Kinh nghiệm",
                language="en",
                text="Golang backend microservices.",
            ),
            SourceSpan(
                span_id="spn_db_2",
                full_hash="h_db",
                sanitized_version_id=san.id,
                start_cp=30,
                end_cp=68,
                page_number=1,
                section_label="Kỹ năng",
                language="en",
                text="Database indexing in PostgreSQL.",
            ),
        ]

        session.add_all([org, req, cand, app, doc, san] + spans)
        await session.commit()

        # 2. Index sanitized version into pgvector
        indexed_count = await index_sanitized_version(session, san.id)
        await session.commit()
        assert indexed_count == 2

        # Verify pgvector rows exist
        chunks = (
            await session.execute(
                select(RetrievalChunk).where(RetrievalChunk.sanitized_version_id == san.id)
            )
        ).scalars().all()
        assert len(chunks) == 2
        assert all(c.embedding_config_id == EMBEDDING_CONFIG_ID for c in chunks)

        # 3. Hybrid search for "Golang" criterion
        results = await hybrid_retrieve_for_criterion(
            session,
            san.id,
            criterion_name="Golang Backend",
            criterion_description="Kinh nghiệm xây dựng microservices và API",
            top_k=2,
        )

        assert len(results) >= 1
        best_match = results[0]
        assert best_match.rrf_score > 0
        assert "Golang" in best_match.text

        # 4. Build hybrid assessment pack for 6 standard criteria
        criteria_list = [
            {"id": "python_backend", "name": "Năng lực backend", "description": "Lập trình backend"},
            {"id": "sql_data", "name": "Cơ sở dữ liệu", "description": "PostgreSQL và lưu trữ"},
        ]
        pack = await build_hybrid_assessment_pack(session, san.id, criteria_list)
        assert pack["strategy"] == "hybrid"
        assert pack["fallback_needed"] is False
        assert pack["packed_chunks_count"] >= 1
        assert "python_backend" in pack["criteria_retrieval_map"]
        assert "sql_data" in pack["criteria_retrieval_map"]


@pytest.mark.asyncio
async def test_hybrid_retrieval_empty_triggers_fallback(test_session_factory):
    """When a sanitized version has 0 chunks, hybrid assessment pack signals fallback_needed."""
    empty_version_id = uuid.uuid4()
    async with test_session_factory() as session:
        criteria_list = [{"id": "c1", "name": "General", "description": "General requirements"}]
        pack = await build_hybrid_assessment_pack(session, empty_version_id, criteria_list)
        assert pack["fallback_needed"] is True
        assert pack["strategy"] == "fulltext_fallback"
