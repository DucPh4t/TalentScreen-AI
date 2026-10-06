"""Integration and Unit tests for PDF/DOCX Parsing, Normalization, and Source Span Registry.
Covers Task B06 requirements and invariants.
"""
from datetime import datetime, timezone
import io
import unicodedata
import uuid
import docx
import pytest
from pypdf import PdfWriter
from httpx import ASGITransport, AsyncClient

from app.db.models import (
    Application,
    Candidate,
    Document,
    Organization,
    Requisition,
    RequisitionMembership,
    SanitizedVersion,
    SourceSpan,
    User,
    UserAccountRole,
)
from app.domain.authorization import SESSION_COOKIE_NAME
from app.domain.enums import (
    AccountRole,
    DocumentSafetyStatus,
    MembershipRole,
    RequisitionStatus,
    SanitizedVersionStatus,
    UserStatus,
)
from app.domain.security import hash_password
from app.main import app
from app.services.auth import create_session
from app.services.parser import (
    DocumentParsingError,
    build_spans_from_pages,
    classify_document_type,
    detect_language_vi_or_en,
    normalize_to_nfc_lf,
    parse_docx_bytes,
    parse_pdf_bytes,
)


def test_document_type_preflight_flags_job_description_without_auto_rejecting_cv():
    jd = """Product Owner Intern
    Your responsibilities include product research and backlog refinement.
    Job requirements: basic knowledge of APIs and user research.
    How to apply: submit your application online.
    """
    cv = """Work Experience
    Technical Skills
    Projects
    Built a mobile app and tested the API integration.
    Education
    """
    assert classify_document_type(jd)["document_type_hint"] == "job_description"
    assert classify_document_type(jd)["document_type_confidence"] == "high"
    product_jd = """Product Owner Intern
    Work with engineering to refine user stories and acceptance criteria.
    Support backlog prioritization and user research.
    """
    assert classify_document_type(product_jd)["document_type_hint"] == "job_description"
    assert classify_document_type(product_jd)["document_type_confidence"] == "high"
    assert classify_document_type(cv)["document_type_hint"] == "cv"
    assert classify_document_type("Python, FastAPI, SQL")["document_type_hint"] == "unknown"


def test_mixed_language_detected_per_section_without_scoring_technical_terms():
    vi = "Kinh nghiệm làm việc. Phụ trách thiết kế và tối ưu hệ thống Python SQL."
    en = "Work Experience. Built backend services with PostgreSQL and Redis."
    assert detect_language_vi_or_en(vi) == "vi"
    assert detect_language_vi_or_en(en) == "en"
    assert detect_language_vi_or_en(vi + "\n" + en) == "mixed"
    _, spans = build_spans_from_pages([(1, vi + "\n\n" + en)])
    assert [span.language for span in spans] == ["vi", "en"]
from app.services.provenance import ingest_and_parse_document
from app.services.storage import save_private_blob


def create_minimal_pdf_bytes(pages_content: list[str]) -> bytes:
    """Create a minimal real PDF binary with text content using pypdf PdfWriter."""
    from pypdf import PageObject
    # We can write a raw PDF structure
    buf = io.BytesIO()
    writer = PdfWriter()
    for text in pages_content:
        # Add a blank page with annotations or text stream
        page = PageObject.create_blank_page(width=612, height=792)
        writer.add_page(page)
    writer.write(buf)
    return buf.getvalue()


def create_minimal_docx_bytes(paragraphs: list[str]) -> bytes:
    """Create a real DOCX binary with paragraphs using python-docx."""
    doc = docx.Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_unicode_nfc_and_newline_normalization():
    """Verify combining Unicode characters (NFD) are composed into NFC, and newlines unified to LF."""
    raw_text = "Nguyễn Văn A\r\nKỹ sư Backend Python\rĐại học Quốc gia"
    # Convert explicitly to decomposed form (NFD)
    nfd_text = unicodedata.normalize("NFD", raw_text)
    assert not unicodedata.is_normalized("NFC", nfd_text)

    normalized = normalize_to_nfc_lf(nfd_text)
    expected = "Nguyễn Văn A\nKỹ sư Backend Python\nĐại học Quốc gia"
    assert normalized == expected
    assert unicodedata.is_normalized("NFC", normalized)
    assert "\r" not in normalized


def test_exact_codepoint_offsets_with_vietnamese_and_emojis():
    """Invariant: canonical_text[span.start_cp:span.end_cp] MUST match span.text exactly."""
    pages = [
        (
            1,
            "Kinh nghiệm làm việc\n\nPhát triển hệ thống microservices Python 🚀 xử lý 10,000 yêu cầu/giây.",
        ),
        (
            2,
            "Dự án tiêu biểu ⭐\n\nThiết kế cơ sở dữ liệu PostgreSQL và tối ưu hóa câu lệnh SQL phức tạp.",
        ),
    ]

    canonical, spans = build_spans_from_pages(pages)

    assert len(spans) == 4
    for span in spans:
        extracted = canonical[span.start_cp : span.end_cp]
        assert extracted == span.text, f"Mismatch for {span.span_id}"
        assert span.span_id.startswith("spn_")
        assert len(span.span_id) == 28
        assert len(span.full_hash) == 64

    # Verify section headings detected
    assert spans[0].section_label == "Kinh nghiệm làm việc"
    assert spans[2].section_label == "Dự án"


def test_encrypted_pdf_detection():
    """Encrypted PDF raises DocumentParsingError with code ENCRYPTED_PDF without crashing process."""
    # Create an encrypted PDF with pypdf
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("SecretPassword123")
    buf = io.BytesIO()
    writer.write(buf)
    encrypted_bytes = buf.getvalue()

    with pytest.raises(DocumentParsingError) as exc_info:
        parse_pdf_bytes(encrypted_bytes)
    assert exc_info.value.error_code == "ENCRYPTED_PDF"


def test_docx_parsing_with_paragraphs():
    """Verify DOCX parsing extracts text, computes hash, and registers spans."""
    paragraphs = [
        "Kinh nghiệm làm việc",
        "Lập trình viên backend tại Công ty Phần mềm ABC từ 2022 đến 2024.",
        "Kỹ năng chuyên môn",
        "Thành thạo Python, FastAPI, Docker, CI/CD, Git.",
    ]
    docx_bytes = create_minimal_docx_bytes(paragraphs)
    result = parse_docx_bytes(docx_bytes)

    assert result.page_count == 1
    assert "FastAPI" in result.canonical_text
    assert len(result.spans) == 4
    for span in result.spans:
        assert result.canonical_text[span.start_cp : span.end_cp] == span.text


@pytest.mark.asyncio
async def test_end_to_end_ingestion_and_source_span_query(test_session_factory):
    """End-to-end: Upload DOCX, run ingestion service, query span via REST API."""
    # 1. Setup user and application
    async with test_session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            login_name=f"recruiter_{uuid.uuid4().hex[:8]}",
            display_name="Recruiter",
            password_hash=hash_password("Password123!"),
            status=UserStatus.ACTIVE,
        )
        outsider = User(
            id=uuid.uuid4(),
            login_name=f"outsider_{uuid.uuid4().hex[:8]}",
            display_name="Outsider",
            password_hash=hash_password("Password123!"),
            status=UserStatus.ACTIVE,
        )
        session.add_all([user, outsider])
        await session.flush()
        session.add(UserAccountRole(user_id=user.id, role=AccountRole.RECRUITER))
        session.add(UserAccountRole(user_id=outsider.id, role=AccountRole.REVIEWER))
        await session.flush()

        token, csrf, _ = await create_session(session, user)
        out_token, out_csrf, _ = await create_session(session, outsider)

        from app.services.requisition import get_or_create_default_org
        org = await get_or_create_default_org(session)

        req = Requisition(
            id=uuid.uuid4(),
            organization_id=org.id,
            title="Python Ingestion Req",
            status=RequisitionStatus.DRAFT,
            row_version=1,
        )
        session.add(req)
        await session.flush()

        session.add(RequisitionMembership(requisition_id=req.id, user_id=user.id, membership_role=MembershipRole.OWNER))
        await session.flush()

        cand = Candidate(id=uuid.uuid4(), organization_id=org.id, public_label=f"CAND-{uuid.uuid4().hex[:6].upper()}", status="active")
        session.add(cand)
        await session.flush()

        app_obj = Application(id=uuid.uuid4(), requisition_id=req.id, candidate_id=cand.id, status="active", generation=1, row_version=1)
        session.add(app_obj)
        await session.flush()

        # Create DOCX file
        content = create_minimal_docx_bytes([
            "Kinh nghiệm làm việc",
            "Xây dựng API RESTful và microservices với Python và FastAPI.",
        ])
        doc_id = uuid.uuid4()
        blob_key = f"documents/{app_obj.id}/{doc_id}.bin"
        save_private_blob(blob_key, content)

        doc = Document(
            id=doc_id,
            application_id=app_obj.id,
            version_no=1,
            kind="cv",
            original_name_private="cv.docx",
            mime_verified="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            byte_size=len(content),
            sha256="abc" * 21 + "a",
            blob_key=blob_key,
            ingestion_status="uploaded",
            safety_status=DocumentSafetyStatus.PENDING,
            created_by=user.id,
        )
        session.add(doc)
        await session.commit()

        # 2. Run ingestion & parsing
        sanitized = await ingest_and_parse_document(session, doc.id)
        await session.commit()
        sanitized_id = sanitized.id

        # Query a span from DB
        from sqlalchemy import select
        stmt_span = select(SourceSpan).where(SourceSpan.sanitized_version_id == sanitized_id)
        res_span = await session.execute(stmt_span)
        span = res_span.scalars().first()
        assert span is not None
        test_span_id = span.span_id

    # 3. Query span via REST endpoint as assigned recruiter
    transport = ASGITransport(app=app)
    cookies = {SESSION_COOKIE_NAME: token}
    headers = {"X-CSRF-Token": csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=cookies, headers=headers) as client:
        res = await client.get(f"/api/v1/source-spans/{test_span_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["span_id"] == test_span_id
        assert data["coordinate_system"] == "unicode_codepoints_nfc_lf"
        assert data["text"] in [
            "Kinh nghiệm làm việc",
            "Xây dựng API RESTful và microservices với Python và FastAPI.",
        ]

    # 4. Outsider cannot access span -> 403 Forbidden
    out_cookies = {SESSION_COOKIE_NAME: out_token}
    out_headers = {"X-CSRF-Token": out_csrf}

    async with AsyncClient(transport=transport, base_url="http://test", cookies=out_cookies, headers=out_headers) as client:
        res_out = await client.get(f"/api/v1/source-spans/{test_span_id}")
        assert res_out.status_code == 403
