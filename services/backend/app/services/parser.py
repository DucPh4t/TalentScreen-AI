"""PDF and DOCX document parser, Unicode NFC/LF normalization, and Source Span Registry."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import re
from typing import Any, Optional
import unicodedata
import uuid

import docx
from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError

# Detect common Vietnamese section headings
SECTION_HEADING_PATTERNS = [
    (re.compile(r"^(kinh nghiệm|kinh nghiệm làm việc|work experience|experience)\b", re.IGNORECASE), "Kinh nghiệm làm việc"),
    (re.compile(r"^(dự án|projects|công việc tiêu biểu)\b", re.IGNORECASE), "Dự án"),
    (re.compile(r"^(kỹ năng|skills|năng lực chuyên môn)\b", re.IGNORECASE), "Kỹ năng chuyên môn"),
    (re.compile(r"^(học vấn|education|đào tạo)\b", re.IGNORECASE), "Học vấn"),
    (re.compile(r"^(chứng chỉ|certifications|awards)\b", re.IGNORECASE), "Chứng chỉ & Giải thưởng"),
    (re.compile(r"^(mục tiêu|objective|summary|tổng quan)\b", re.IGNORECASE), "Tổng quan"),
]


class DocumentParsingError(Exception):
    """Raised when parsing fails due to encrypted or unreadable document."""
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass
class ExtractedSpan:
    span_id: str
    start_cp: int
    end_cp: int
    text: str
    page_number: int
    section_label: Optional[str]
    language: str
    full_hash: str


@dataclass
class ParseResult:
    canonical_text: str
    sha256: str
    page_count: int
    spans: list[ExtractedSpan]
    quality_report: dict[str, Any]
    detected_language: str = "vi"


def normalize_to_nfc_lf(raw_text: str) -> str:
    """Canonical Unicode NFC normalization with uniform Unix LF newlines and cleaned control chars."""
    if not raw_text:
        return ""
    # Strip null bytes and non-printable control characters except \n, \t
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw_text)
    # Uniform LF newlines
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    # NFC normalization (combining characters composed into canonical codepoints)
    normalized = unicodedata.normalize("NFC", cleaned)
    return normalized


def detect_language_vi_or_en(text: str) -> str:
    """Heuristic language detection: check for Vietnamese specific diacritics."""
    vi_chars = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ")
    count_vi = sum(1 for c in text if c in vi_chars)
    return "vi" if count_vi > 5 else "en"


def generate_span_id() -> str:
    """Generate 28-character span ID matching format 'spn_' + 24 hex digits."""
    return f"spn_{uuid.uuid4().hex[:24]}"


def build_spans_from_pages(pages_text: list[tuple[int, str]]) -> tuple[str, list[ExtractedSpan]]:
    """Build canonical text by joining pages and extract semantic spans with exact codepoint offsets.
    pages_text: list of (page_number, page_canonical_text)
    Invariant: canonical_text[span.start_cp:span.end_cp] == span.text MUST be true for every span.
    """
    spans: list[ExtractedSpan] = []
    full_text_builder: list[str] = []
    current_codepoint = 0
    current_section = "Thông tin chung"

    for page_idx, (page_num, page_raw) in enumerate(pages_text):
        normalized_page = normalize_to_nfc_lf(page_raw).strip()
        if not normalized_page:
            continue

        # Add page separator newline if not first page
        if page_idx > 0 and full_text_builder:
            full_text_builder.append("\n\n")
            current_codepoint += 2

        # Split page content into semantic paragraphs / blocks
        paragraphs = re.split(r"\n\s*\n+", normalized_page)

        for p_idx, para in enumerate(paragraphs):
            para_text = para.strip()
            if not para_text:
                continue

            # Detect section heading
            for pattern, sec_name in SECTION_HEADING_PATTERNS:
                if pattern.search(para_text):
                    current_section = sec_name
                    break

            # If not first paragraph on this page, account for paragraph break
            if p_idx > 0:
                full_text_builder.append("\n\n")
                current_codepoint += 2

            start_cp = current_codepoint
            full_text_builder.append(para_text)
            end_cp = start_cp + len(para_text)
            current_codepoint = end_cp

            span_hash = hashlib.sha256(para_text.encode("utf-8")).hexdigest()
            span_lang = detect_language_vi_or_en(para_text)

            spans.append(
                ExtractedSpan(
                    span_id=generate_span_id(),
                    start_cp=start_cp,
                    end_cp=end_cp,
                    text=para_text,
                    page_number=page_num,
                    section_label=current_section,
                    language=span_lang,
                    full_hash=span_hash,
                )
            )

    full_canonical_text = "".join(full_text_builder)

    # Invariant assertion check: verify every span matches exact slice
    for s in spans:
        slice_text = full_canonical_text[s.start_cp:s.end_cp]
        if slice_text != s.text:
            raise ValueError(
                f"SPAN_OFFSET_MISMATCH: Offset [{s.start_cp}:{s.end_cp}] does not match span text for {s.span_id}"
            )

    return full_canonical_text, spans


def compute_quality_report(
    pages_text: list[tuple[int, str]],
    total_text_length: int,
    total_pages: int,
) -> dict[str, Any]:
    """Calculate quality metrics and diagnostics on parsed document text."""
    empty_pages = 0
    scanned_pages = 0
    total_chars = total_text_length

    for _, p_text in pages_text:
        char_count = len(p_text.strip())
        if char_count == 0:
            empty_pages += 1
        elif char_count < 25:
            # High probability of being a scanned image page without embedded text
            scanned_pages += 1

    suspected_scanned = total_pages > 0 and (scanned_pages + empty_pages) == total_pages
    avg_chars_per_page = total_chars / max(1, total_pages)

    return {
        "total_pages": total_pages,
        "total_characters": total_chars,
        "empty_pages": empty_pages,
        "scanned_suspected_pages": scanned_pages,
        "suspected_scanned": suspected_scanned,
        "average_chars_per_page": round(avg_chars_per_page, 1),
        "quality_status": "warning_scanned" if suspected_scanned else "ok",
    }


def parse_pdf_bytes(pdf_bytes: bytes) -> ParseResult:
    """Parse PDF file bytes into canonical text, page metadata, and registered spans."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise DocumentParsingError("MALFORMED_PDF", f"Không thể đọc cấu trúc tệp PDF: {e}")

    if reader.is_encrypted:
        try:
            # Try empty password
            decrypt_res = reader.decrypt("")
            if decrypt_res == 0:
                raise DocumentParsingError("ENCRYPTED_PDF", "Tệp PDF có mật khẩu bảo vệ, không thể giải mã.")
        except Exception:
            raise DocumentParsingError("ENCRYPTED_PDF", "Tệp PDF có mật khẩu bảo vệ, không thể giải mã.")

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise DocumentParsingError("EMPTY_PDF", "Tệp PDF không có trang nào.")

    pages_text: list[tuple[int, str]] = []
    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        try:
            p_text = page.extract_text() or ""
        except Exception:
            p_text = ""
        pages_text.append((page_num, p_text))

    canonical_text, spans = build_spans_from_pages(pages_text)
    sha256 = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    quality = compute_quality_report(pages_text, len(canonical_text), total_pages)
    lang = detect_language_vi_or_en(canonical_text)

    return ParseResult(
        canonical_text=canonical_text,
        sha256=sha256,
        page_count=total_pages,
        spans=spans,
        quality_report=quality,
        detected_language=lang,
    )


def parse_docx_bytes(docx_bytes: bytes) -> ParseResult:
    """Parse DOCX file bytes into canonical text, page estimates, and registered spans."""
    try:
        doc = docx.Document(io.BytesIO(docx_bytes))
    except Exception as e:
        raise DocumentParsingError("MALFORMED_DOCX", f"Không thể đọc cấu trúc tệp DOCX: {e}")

    paragraphs: list[str] = []
    for p in doc.paragraphs:
        if p.text.strip():
            paragraphs.append(p.text.strip())

    for t in doc.tables:
        for row in t.rows:
            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_texts:
                paragraphs.append(" | ".join(row_texts))

    raw_text = "\n\n".join(paragraphs)
    # DOCX does not have explicit physical pages, treat as single page or estimate by length
    pages_text = [(1, raw_text)]

    canonical_text, spans = build_spans_from_pages(pages_text)
    sha256 = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    quality = compute_quality_report(pages_text, len(canonical_text), total_pages=1)
    lang = detect_language_vi_or_en(canonical_text)

    return ParseResult(
        canonical_text=canonical_text,
        sha256=sha256,
        page_count=1,
        spans=spans,
        quality_report=quality,
        detected_language=lang,
    )


def parse_document_content(content: bytes, mime_type: str) -> ParseResult:
    """Unified entrypoint to parse document content based on verified MIME type."""
    if mime_type == "application/pdf":
        return parse_pdf_bytes(content)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return parse_docx_bytes(content)
    else:
        raise DocumentParsingError("UNSUPPORTED_MIME", f"Không hỗ trợ bóc tách cho MIME type '{mime_type}'.")
