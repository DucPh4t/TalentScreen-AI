"""PDF and DOCX document parser, Unicode NFC/LF normalization, and Source Span Registry."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
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
    """Conservative vi/en/mixed heuristic per span and document.

    Technical terms such as Python or SQL alone do not make a Vietnamese CV
    mixed-language. This is metadata for evaluation grouping, never scoring.
    """
    lower = text.lower()
    vi_chars = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ")
    vi_diacritics = sum(char in vi_chars for char in lower)
    vi_terms = len(re.findall(r"\b(?:kinh nghiệm|làm việc|dự án|phụ trách|xây dựng|thiết kế|tối ưu|và|học vấn|kỹ năng)\b", lower))
    en_terms = len(re.findall(r"\b(?:work experience|projects?|built|implemented|developed|designed|improved|responsible|using|with|and|skills|education|at the)\b", lower))
    has_vi = vi_diacritics >= 2 or vi_terms >= 2
    has_en = en_terms >= 2
    if has_vi and has_en:
        return "mixed"
    return "vi" if has_vi else "en"


_JD_DOCUMENT_PATTERNS = (
    re.compile(r"\bjob description\b", re.IGNORECASE),
    re.compile(r"\b(?:your|key) responsibilities\b", re.IGNORECASE),
    re.compile(r"\b(?:job|candidate|application) requirements\b", re.IGNORECASE),
    re.compile(r"\bqualifications\b", re.IGNORECASE),
    re.compile(r"\bapply now\b|\bhow to apply\b", re.IGNORECASE),
    re.compile(r"mô tả công việc|yêu cầu ứng viên|quyền lợi|cách thức ứng tuyển", re.IGNORECASE),
    # Product roles often describe deliverables rather than using generic job-ad headings.
    re.compile(r"\bproduct owner intern\b", re.IGNORECASE),
    re.compile(r"\buser stories?\b", re.IGNORECASE),
    re.compile(r"\bacceptance criteria\b", re.IGNORECASE),
)
_CV_DOCUMENT_PATTERNS = (
    re.compile(r"\bwork experience\b|\bprofessional experience\b", re.IGNORECASE),
    re.compile(r"\btechnical skills\b|\bskills summary\b", re.IGNORECASE),
    re.compile(r"\bprojects?\b|\bpersonal projects?\b", re.IGNORECASE),
    re.compile(r"\beducation\b|\bcertifications\b", re.IGNORECASE),
    re.compile(r"kinh nghiệm làm việc|kỹ năng chuyên môn|dự án cá nhân|học vấn", re.IGNORECASE),
    re.compile(r"\bresume\b|\bcurriculum vitae\b", re.IGNORECASE),
)


def classify_document_type(text: str) -> dict[str, Any]:
    """Return a conservative CV/JD hint for HR review; never use it as an eligibility decision."""
    jd_hits = sum(bool(pattern.search(text or "")) for pattern in _JD_DOCUMENT_PATTERNS)
    cv_hits = sum(bool(pattern.search(text or "")) for pattern in _CV_DOCUMENT_PATTERNS)
    if jd_hits >= 3 and jd_hits - cv_hits >= 2:
        kind, confidence = "job_description", "high"
    elif cv_hits >= 2 and cv_hits - jd_hits >= 2:
        kind, confidence = "cv", "medium"
    else:
        kind, confidence = "unknown", "low"
    return {
        "document_type_hint": kind,
        "document_type_confidence": confidence,
        "document_type_jd_signals": jd_hits,
        "document_type_cv_signals": cv_hits,
    }


def docx_renderer_available() -> bool:
    return shutil.which("soffice") is not None or shutil.which("libreoffice") is not None


def render_docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Render in a private temporary directory; never infer pages from length."""
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if not binary:
        raise DocumentParsingError("DOCX_RENDERER_UNAVAILABLE", "Máy chủ chưa có LibreOffice để xác minh số trang DOCX.")
    with tempfile.TemporaryDirectory(prefix="talentscreen-docx-") as temp_dir:
        root = Path(temp_dir)
        source = root / "candidate.docx"
        source.write_bytes(docx_bytes)
        profile = (root / "lo-profile").as_uri()
        try:
            result = subprocess.run(
                [binary, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf", "--outdir", str(root), str(source)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise DocumentParsingError("DOCX_RENDER_TIMEOUT", "Render DOCX quá thời gian cho phép.") from exc
        output = root / "candidate.pdf"
        if result.returncode != 0 or not output.is_file():
            raise DocumentParsingError("DOCX_RENDER_FAILED", "Không thể render DOCX để xác minh trang.")
        return output.read_bytes()


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


import os
import shutil
from PIL import Image

try:
    import pytesseract
    # Auto-discover tesseract executable path
    _tess_cmd = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
    if os.path.exists(_tess_cmd):
        pytesseract.pytesseract.tesseract_cmd = _tess_cmd
    HAVE_TESSERACT = True
except ImportError:
    HAVE_TESSERACT = False


def run_ocr_on_image_bytes(img_bytes: bytes, lang: str = "vie+eng") -> str:
    """Run local Tesseract OCR on image bytes with Vietnamese and English recognition."""
    if not HAVE_TESSERACT:
        return ""
    try:
        with Image.open(io.BytesIO(img_bytes)) as pil_img:
            # Convert to grayscale if not RGB for optimal OCR contrast
            if pil_img.mode not in ("RGB", "L"):
                pil_img = pil_img.convert("RGB")
            try:
                text = pytesseract.image_to_string(pil_img, lang=lang)
            except Exception:
                # Fallback to English only if combined model fails
                text = pytesseract.image_to_string(pil_img, lang="eng")
            return text.strip()
    except Exception:
        return ""


def compute_quality_report(
    pages_text: list[tuple[int, str]],
    total_text_length: int,
    total_pages: int,
    ocr_applied: bool = False,
    ocr_pages: Optional[list[int]] = None,
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
            scanned_pages += 1

    suspected_scanned = total_pages > 0 and (scanned_pages + empty_pages) == total_pages
    avg_chars_per_page = total_chars / max(1, total_pages)

    status = "ok"
    if ocr_applied:
        status = "ok_ocr_recovered"
    elif suspected_scanned:
        status = "warning_scanned"

    combined_text = "\n".join(text for _, text in pages_text)
    return {
        "total_pages": total_pages,
        "total_characters": total_chars,
        "empty_pages": empty_pages,
        "scanned_suspected_pages": scanned_pages,
        "suspected_scanned": suspected_scanned,
        "ocr_applied": ocr_applied,
        "ocr_pages": ocr_pages or [],
        "average_chars_per_page": round(avg_chars_per_page, 1),
        "quality_status": status,
        **classify_document_type(combined_text),
    }


def parse_pdf_bytes(pdf_bytes: bytes) -> ParseResult:
    """Parse PDF file bytes into canonical text, page metadata, and registered spans with OCR fallback."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as e:
        raise DocumentParsingError("MALFORMED_PDF", f"Không thể đọc cấu trúc tệp PDF: {e}")

    if reader.is_encrypted:
        try:
            decrypt_res = reader.decrypt("")
            if decrypt_res == 0:
                raise DocumentParsingError("ENCRYPTED_PDF", "Tệp PDF có mật khẩu bảo vệ, không thể giải mã.")
        except Exception:
            raise DocumentParsingError("ENCRYPTED_PDF", "Tệp PDF có mật khẩu bảo vệ, không thể giải mã.")

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise DocumentParsingError("EMPTY_PDF", "Tệp PDF không có trang nào.")

    pages_text: list[tuple[int, str]] = []
    ocr_applied = False
    ocr_pages: list[int] = []

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        try:
            p_text = page.extract_text() or ""
        except Exception:
            p_text = ""

        # Task B15 OCR Fallback: If page text is empty or very sparse (< 25 chars), attempt OCR on embedded images
        if len(p_text.strip()) < 25 and hasattr(page, "images") and len(page.images) > 0:
            ocr_text_accum = []
            for img in page.images:
                try:
                    ocr_res = run_ocr_on_image_bytes(img.data, lang="vie+eng")
                    if ocr_res:
                        ocr_text_accum.append(ocr_res)
                except Exception:
                    continue

            if ocr_text_accum:
                p_text = "\n\n".join(ocr_text_accum)
                ocr_applied = True
                ocr_pages.append(page_num)

        pages_text.append((page_num, p_text))

    canonical_text, spans = build_spans_from_pages(pages_text)
    sha256 = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    quality = compute_quality_report(
        pages_text,
        len(canonical_text),
        total_pages,
        ocr_applied=ocr_applied,
        ocr_pages=ocr_pages,
    )
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
    """Parse DOCX with verified rendered page count and source pages."""
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
                # Deduplicate adjacent duplicate cells from merged table cells
                deduped: list[str] = []
                for cell_txt in row_texts:
                    if not deduped or cell_txt != deduped[-1]:
                        deduped.append(cell_txt)
                paragraphs.append(" | ".join(deduped))

    raw_text = "\n\n".join(paragraphs).strip()

    rendered_pdf = render_docx_to_pdf(docx_bytes)
    try:
        rendered_page_count = len(PdfReader(io.BytesIO(rendered_pdf)).pages)
    except Exception as exc:
        raise DocumentParsingError("DOCX_RENDER_FAILED", "Không đọc được bản render DOCX.") from exc
    if rendered_page_count == 0:
        raise DocumentParsingError("DOCX_RENDER_FAILED", "Bản render DOCX không có trang.")
    if rendered_page_count > 10:
        raise DocumentParsingError("DOCX_TOO_MANY_PAGES", "CV DOCX vượt quá giới hạn 10 trang thực tế.")
    if rendered_page_count > 1:
        result = parse_pdf_bytes(rendered_pdf)
        result.quality_report["docx_pages_verified"] = True
        result.quality_report["rendered_page_count"] = rendered_page_count
        return result
    pages_text = [(1, raw_text)]

    canonical_text, spans = build_spans_from_pages(pages_text)
    sha256 = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    quality = compute_quality_report(pages_text, len(canonical_text), total_pages=rendered_page_count)
    quality["docx_pages_verified"] = True
    quality["rendered_page_count"] = rendered_page_count
    quality["excessive_page_count"] = False

    lang = detect_language_vi_or_en(canonical_text)

    return ParseResult(
        canonical_text=canonical_text,
        sha256=sha256,
        page_count=rendered_page_count,
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
