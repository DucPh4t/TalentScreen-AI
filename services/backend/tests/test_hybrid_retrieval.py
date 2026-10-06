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


@pytest.fixture
def deterministic_embedding_model(monkeypatch):
    """Explicit deterministic test double; production code never falls back to it."""
    from app.services import embedding

    class FakeTokenizer:
        def encode(self, text, add_special_tokens=False):
            return text.split()

    class FakeModel:
        tokenizer = FakeTokenizer()

        def __init__(self):
            self.encode_calls = 0

        def encode(self, texts, **kwargs):
            self.encode_calls += 1
            return [embedding._deterministic_mock_embed(text) for text in texts]

    model = FakeModel()
    monkeypatch.setattr(embedding, "_get_embedding_model", lambda: model, raising=False)
    return model


def test_embedding_vector_properties(deterministic_embedding_model):
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

    chunks = build_chunks_from_spans(spans, token_count=lambda text: len(text.split()))
    # Section "Kinh nghiệm" and "Học vấn" produce separate chunks
    assert len(chunks) == 2
    assert chunks[0]["section_label"] == "Kinh nghiệm"
    assert "spn_001" in chunks[0]["span_ids"]
    assert "spn_002" in chunks[0]["span_ids"]
    assert chunks[1]["section_label"] == "Học vấn"
    assert "spn_003" in chunks[1]["span_ids"]


@pytest.mark.asyncio
async def test_index_and_hybrid_retrieval(test_session_factory, deterministic_embedding_model):
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

        original_chunk_ids = {
            chunk.id
            for chunk in (await session.execute(
                select(RetrievalChunk).where(RetrievalChunk.sanitized_version_id == san.id)
            )).scalars().all()
        }
        original_encode_calls = deterministic_embedding_model.encode_calls
        assert await index_sanitized_version(session, san.id) == 2
        await session.commit()
        repeated_chunk_ids = {
            chunk.id
            for chunk in (await session.execute(
                select(RetrievalChunk).where(RetrievalChunk.sanitized_version_id == san.id)
            )).scalars().all()
        }
        assert repeated_chunk_ids == original_chunk_ids
        assert deterministic_embedding_model.encode_calls == original_encode_calls

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
async def test_hybrid_retrieval_empty_triggers_fallback(test_session_factory, deterministic_embedding_model):
    """When a sanitized version has 0 chunks, hybrid assessment pack signals fallback_needed."""
    empty_version_id = uuid.uuid4()
    async with test_session_factory() as session:
        criteria_list = [{"id": "c1", "name": "General", "description": "General requirements"}]
        pack = await build_hybrid_assessment_pack(session, empty_version_id, criteria_list)
        assert pack["fallback_needed"] is True
        assert pack["strategy"] == "fulltext_fallback"


def test_embed_texts_uses_e5_prefix_and_returns_normalized_768d_vectors(monkeypatch):
    """Runtime embedding must call the E5 encoder with the task-specific prefix."""
    from app.services import embedding

    class FakeModel:
        def __init__(self):
            self.inputs = []

        def encode(self, texts, **kwargs):
            self.inputs.extend(texts)
            return [[3.0, 4.0] + [0.0] * 766 for _ in texts]

    model = FakeModel()
    monkeypatch.setattr(embedding, "_get_embedding_model", lambda: model, raising=False)

    vectors = embed_texts(["Kỹ năng FastAPI"], prefix="query: ")

    assert model.inputs == ["query: Kỹ năng FastAPI"]
    assert len(vectors) == 1
    assert len(vectors[0]) == 768
    assert all(math.isfinite(value) for value in vectors[0])
    assert abs(math.sqrt(sum(value * value for value in vectors[0])) - 1.0) < 1e-6


def test_embedding_model_is_loaded_once_per_process(monkeypatch, request):
    """A repeated assessment should reuse the configured embedding model instance."""
    import sys
    from types import SimpleNamespace
    from app.config import get_settings
    from app.services import embedding

    settings = get_settings()
    constructed = []

    class FakeModel:
        def __init__(self, model_name, revision, device):
            constructed.append((model_name, revision, device))

        def encode(self, texts, **kwargs):
            return [[1.0] + [0.0] * 767 for _ in texts]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeModel),
    )
    loader = getattr(embedding, "_load_embedding_model", None)
    if loader is not None and hasattr(loader, "cache_clear"):
        loader.cache_clear()
        request.addfinalizer(loader.cache_clear)
    monkeypatch.setattr(settings, "EMBEDDING_DEVICE", "cpu")

    embed_texts(["Python"], prefix="query: ")
    embed_texts(["FastAPI"], prefix="passage: ")

    assert len(constructed) == 1
    model_name, revision, device = constructed[0]
    assert model_name == settings.EMBEDDING_MODEL
    assert revision == settings.EMBEDDING_MODEL_REVISION
    assert device == "cpu"


def test_chunking_preserves_sections_and_span_ids_for_mixed_language_cv():
    """Mixed-language spans stay in their sections and long spans are losslessly split."""
    dummy_version_id = uuid.uuid4()
    long_text = " ".join(f"token{i}" for i in range(1000))
    spans = [
        SourceSpan(
            span_id="spn_vi_exp",
            full_hash="h_vi_exp",
            sanitized_version_id=dummy_version_id,
            start_cp=0,
            end_cp=46,
            page_number=1,
            section_label="Kinh nghiệm / Experience",
            language="vi",
            text="Xây dựng API bằng Python và PostgreSQL.",
        ),
        SourceSpan(
            span_id="spn_en_exp",
            full_hash="h_en_exp",
            sanitized_version_id=dummy_version_id,
            start_cp=47,
            end_cp=95,
            page_number=1,
            section_label="Kinh nghiệm / Experience",
            language="en",
            text="Designed distributed services with FastAPI.",
        ),
        SourceSpan(
            span_id="spn_long_project",
            full_hash="h_long_project",
            sanitized_version_id=dummy_version_id,
            start_cp=96,
            end_cp=96 + len(long_text),
            page_number=2,
            section_label="Projects",
            language="en",
            text=long_text,
        ),
        SourceSpan(
            span_id="spn_education",
            full_hash="h_education",
            sanitized_version_id=dummy_version_id,
            start_cp=97 + len(long_text),
            end_cp=125 + len(long_text),
            page_number=3,
            section_label="Học vấn / Education",
            language="vi",
            text="Chuyên ngành Khoa học máy tính.",
        ),
    ]
    token_count = lambda text: len(text.split())

    chunks = build_chunks_from_spans(
        spans,
        token_count=token_count,
        target_tokens=300,
        max_tokens=480,
    )

    assert {span_id for chunk in chunks for span_id in chunk["span_ids"]} == {
        "spn_vi_exp",
        "spn_en_exp",
        "spn_long_project",
        "spn_education",
    }
    assert all(token_count(chunk["text"]) <= 480 for chunk in chunks)
    assert all(
        len({chunk["section_label"] for chunk in chunks if span_id in chunk["span_ids"]}) == 1
        for span_id in {span.span_id for span in spans}
    )
    long_chunks = [chunk for chunk in chunks if "spn_long_project" in chunk["span_ids"]]
    assert len(long_chunks) >= 3
    assert "".join(chunk["text"] for chunk in long_chunks) == long_text


def test_embedding_load_failure_raises_typed_error_in_hybrid(monkeypatch, request):
    """A missing local model must fail closed instead of returning hash vectors."""
    import sys
    from types import SimpleNamespace
    from app.config import get_settings
    from app.services import embedding

    class BrokenModel:
        def __init__(self, *args, **kwargs):
            raise OSError("weights unavailable")

    loader = getattr(embedding, "_load_embedding_model", None)
    if loader is not None and hasattr(loader, "cache_clear"):
        loader.cache_clear()
        request.addfinalizer(loader.cache_clear)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=BrokenModel),
    )
    monkeypatch.setattr(get_settings(), "RAG_MODE", "hybrid")
    monkeypatch.setattr(get_settings(), "EMBEDDING_DEVICE", "cpu")

    with pytest.raises(RuntimeError) as error:
        embed_texts(["Kỹ năng Python"])

    assert type(error.value).__name__ == "EmbeddingModelUnavailableError"


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeRetrievalDB:
    def __init__(self, results=()):
        self._results = iter(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _FakeScalarResult(next(self._results, []))


def _fake_chunk(index, text, span_id, *, score=0.01):
    from types import SimpleNamespace

    chunk_id = uuid.uuid4()
    return SimpleNamespace(
        id=chunk_id,
        chunk_id=chunk_id,
        chunk_index=index,
        text=text,
        span_ids=[span_id],
        dense_rank=index,
        lexical_rank=index,
        rrf_score=score,
    )


@pytest.mark.asyncio
async def test_hybrid_retrieval_uses_approved_bilingual_terms_and_anchor_terms(monkeypatch):
    from app.services import retrieval

    embedded_queries = []

    def fake_embed_texts(texts, prefix):
        assert prefix == "query: "
        embedded_queries.extend(texts)
        return [[0.0] * EMBEDDING_DIMENSION]

    monkeypatch.setattr(retrieval, "embed_texts", fake_embed_texts)
    db = _FakeRetrievalDB([[], []])

    await retrieval.hybrid_retrieve_for_criterion(
        db,
        uuid.uuid4(),
        criterion_name="Python backend",
        criterion_description="Scalable production services",
        bilingual_terms={"en": ["PostgreSQL relational database"], "vi": ["cơ sở dữ liệu"]},
        anchor_terms=["FastAPI REST API"],
    )

    query_text = embedded_queries[0].lower()
    assert "postgresql relational database" in query_text
    assert "fastapi rest api" in query_text
    assert "cơ sở dữ liệu" in query_text

    lexical_params = db.statements[1].compile().params.values()
    lexical_query = next(value for value in lexical_params if isinstance(value, str) and " | " in value)
    lexical_terms = lexical_query.split(" | ")
    assert len(lexical_terms) <= 8
    assert "fastapi" in lexical_terms
    assert "postgresql" in lexical_terms


@pytest.mark.asyncio
async def test_rrf_is_deterministic_and_deduplicates_chunks(monkeypatch):
    from app.services import retrieval

    monkeypatch.setattr(retrieval, "embed_texts", lambda *_args, **_kwargs: [[0.0] * EMBEDDING_DIMENSION])
    lower_index = _fake_chunk(2, "PostgreSQL evidence", "spn_postgres")
    higher_index = _fake_chunk(8, "FastAPI evidence", "spn_fastapi")
    db = _FakeRetrievalDB([[higher_index, lower_index], [lower_index, higher_index]])

    scores = await retrieval.hybrid_retrieve_for_criterion(
        db, uuid.uuid4(), "backend", "Python API", top_k=4
    )

    assert [score.chunk_id for score in scores] == [lower_index.chunk_id, higher_index.chunk_id]
    assert len({score.chunk_id for score in scores}) == 2
    assert scores[0].rrf_score == pytest.approx(scores[1].rrf_score)


@pytest.mark.asyncio
async def test_retrieval_is_scoped_to_sanitized_version(monkeypatch):
    from app.services import retrieval

    monkeypatch.setattr(retrieval, "embed_texts", lambda *_args, **_kwargs: [[0.0] * EMBEDDING_DIMENSION])
    sanitized_version_id = uuid.uuid4()
    db = _FakeRetrievalDB([[], []])

    await retrieval.hybrid_retrieve_for_criterion(
        db, sanitized_version_id, "Python", "backend assessment"
    )

    assert len(db.statements) == 2
    for statement in db.statements:
        compiled = statement.compile()
        assert sanitized_version_id in compiled.params.values()
        assert EMBEDDING_CONFIG_ID in compiled.params.values()
        assert "sanitized_version_id" in str(statement)


@pytest.mark.asyncio
async def test_hybrid_assessment_uses_null_when_retrieval_has_no_reliable_evidence(monkeypatch):
    from app.services import retrieval

    monkeypatch.setattr(retrieval, "embed_texts", lambda *_args, **_kwargs: [[0.0] * EMBEDDING_DIMENSION])
    db = _FakeRetrievalDB([[], []])
    pack = await retrieval.build_hybrid_assessment_pack(
        db, uuid.uuid4(), [{"id": "python", "name": "Python", "description": "Backend"}]
    )

    assert pack["fallback_needed"] is True
    assert pack["strategy"] == "fulltext_fallback"
    assert pack["chunks"] == []
    assert pack["source_span_ids"] == []
    assert pack["criteria_retrieval_map"]["python"] == []


@pytest.mark.asyncio
async def test_hybrid_pack_deduplicates_chunks_and_returns_ordered_span_ids(monkeypatch):
    from types import SimpleNamespace
    from app.services import retrieval

    first = _fake_chunk(2, "A" * 40, "spn_a", score=0.04)
    same_section = _fake_chunk(1, "B" * 40, "spn_b", score=0.03)
    another_section = _fake_chunk(3, "C" * 40, "spn_c", score=0.02)
    fourth = _fake_chunk(4, "D" * 40, "spn_d", score=0.01)
    database_match = _fake_chunk(3, "C" * 40, "spn_c", score=0.07)
    database_match.id = another_section.id
    database_match.chunk_id = another_section.chunk_id
    database_match.dense_rank = 1
    database_match.lexical_rank = 1
    by_criterion = {
        "Python": [first, same_section, another_section, fourth],
        "Database": [database_match, fourth],
    }

    async def fake_retrieve(_db, _version_id, criterion_name, _description, **_kwargs):
        return by_criterion[criterion_name]

    monkeypatch.setattr(retrieval, "hybrid_retrieve_for_criterion", fake_retrieve)
    source_spans = [
        SimpleNamespace(span_id="spn_a", section_label="Experience"),
        SimpleNamespace(span_id="spn_b", section_label="Experience"),
        SimpleNamespace(span_id="spn_c", section_label="Projects"),
        SimpleNamespace(span_id="spn_d", section_label="Skills"),
    ]
    db = _FakeRetrievalDB([source_spans])

    sanitized_version_id = uuid.uuid4()
    pack = await retrieval.build_hybrid_assessment_pack(
        db,
        sanitized_version_id,
        [
            {"id": "python", "name": "Python", "description": "Backend", "anchors": {"3": "production services"}},
            {"id": "database", "name": "Database", "description": "SQL"},
        ],
        max_evidence_chars=100,
    )

    assert pack["packed_chunks_count"] == 2
    assert pack["total_evidence_characters"] == 80
    assert pack["source_span_ids"] == ["spn_a", "spn_c"]
    assert [chunk["section_label"] for chunk in pack["chunks"]] == ["Experience", "Projects"]
    assert len(pack["criteria_retrieval_map"]["python"]) <= 4
    assert pack["criteria_retrieval_map"]["database"][0]["chunk_index"] == 3
    assert pack["criteria_retrieval_map"]["database"][0]["dense_rank"] == 1
    assert pack["criteria_retrieval_map"]["database"][0]["rrf_score"] == 0.07
    assert "candidate_id" not in pack and "application_id" not in pack
    scope_params = db.statements[0].compile().params.values()
    assert sanitized_version_id in scope_params
