"""Sanitization and PII redaction engine for TalentScreen AI.
Implements Vietnamese & English detector rules, counterfactual invariance,
preserves technical keywords, and generates exact source spans.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Any, Optional
import uuid

from app.db.models.document import SourceSpan

# Preserved technical keywords that MUST NOT be redacted even if capitalized
TECHNICAL_ALLOWLIST = {
    "python", "fastapi", "django", "flask", "postgresql", "postgres", "mysql", "mongodb",
    "redis", "docker", "kubernetes", "k8s", "aws", "gcp", "azure", "git", "github", "gitlab",
    "react", "vue", "angular", "next.js", "nextjs", "node.js", "nodejs", "typescript",
    "javascript", "go", "golang", "java", "spring", "c++", "c#", ".net", "dotnet", "rust",
    "kafka", "rabbitmq", "graphql", "rest", "grpc", "ci/cd", "ci", "cd", "linux", "ubuntu",
    "nginx", "apache", "terraform", "ansible", "elasticsearch", "solr", "spark", "hadoop",
    "pandas", "numpy", "pytorch", "tensorflow", "scikit-learn", "pytest", "unittest", "selenium",
}

# Regex patterns for contact and demographic attributes
PHONE_REGEX = re.compile(
    r"(?:\+?84|0)(?:3[2-9]|5[689]|7[06-9]|8[1-9]|9[0-9])[\s.-]?\d{3}[\s.-]?\d{4}\b"
    r"|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",
    re.IGNORECASE,
)

EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)

URL_SOCIAL_REGEX = re.compile(
    r"\b(?:https?://|www\.)[^\s<>'\"`]+\b"
    r"|\b(?:linkedin\.com/in/|github\.com/|facebook\.com/)[^\s<>'\"`]+\b",
    re.IGNORECASE,
)

DOB_AGE_REGEX = re.compile(
    r"(?:ngày\s*sinh|dob|date\s*of\s*birth|birthdate|sinh\s*ngày|năm\s*sinh)[\s:]*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{4}|[0-9]{4})"
    r"|(\b[0-9]{1,2}\s*tuổi\b)"
    r"|(\b(?:age|tuổi)[\s:]*[0-9]{1,2}\b)",
    re.IGNORECASE,
)

GENDER_MARITAL_REGEX = re.compile(
    r"(?:giới\s*tính|gender|sex)[\s:]*(nam|nữ|male|female|other|khác)"
    r"|(?:tình\s*trạng\s*hôn\s*nhân|marital\s*status)[\s:]*(độc\s*thân|đã\s*kết\s*hôn|single|married)",
    re.IGNORECASE,
)

ADDRESS_ORIGIN_REGEX = re.compile(
    r"(?:địa\s*chỉ|address|quê\s*quán|nơi\s*sinh|hộ\s*khẩu|thường\s*trú|tạm\s*trú|place\s*of\s*birth|residence)[\s:]*([^\n\r,;]{3,60}(?:,[^\n\r,;]{2,60})*)",
    re.IGNORECASE,
)

# University / School names (Vietnamese & International prestige)
SCHOOL_REGEX = re.compile(
    r"\b(?:trường\s*đại\s*học|đại\s*học|học\s*viện|trường\s*cao\s*đẳng|university\s*of|college\s*of)\s+[^\n\r,;.()0-9]{2,50}\b"
    r"|\b(?:đhqg|đh\s*bách\s*khoa|đh\s*khoa\s*học\s*tự\s*nhiên|đh\s*ngoại\s*thương|đh\s*kinh\s*tế|đh\s*công\s*nghệ|đh\s*sư\s*phạm|đh\s*fpt|đh\s*rmit)\b"
    r"|\b(?:stanford|harvard|mit|oxford|cambridge|berkeley|cmu|yale|princeton|columbia)\s+(?:university|college|institute)?\b",
    re.IGNORECASE,
)

# Company / Organization indicators (single-line only, do not match across newlines)
ORG_REGEX = re.compile(
    r"\b(?:công\s*ty\s*(?:tnhh|cp|cổ\s*phần)?|tập\s*đoàn|ngân\s*hàng|bank)[ \t]+[A-Za-z0-9À-ỹ \t&.-]{2,40}\b"
    r"|\b[A-Za-z0-9À-ỹ \t&.-]{2,30}[ \t]+(?:corp|corporation|inc|jsc|ltd|llc|co\.,\s*ltd)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RedactionMatch:
    start_cp: int
    end_cp: int
    original_text: str
    replacement: str
    entity_type: str


def normalize_text_nfc_lf(text: str) -> str:
    """Normalize string to Unicode NFC and LF line breaks."""
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def sanitize_text(
    raw_text: str,
    candidate_name: Optional[str] = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Sanitize raw document text by redacting PII and sensitive demographic entities.
    Returns:
        (sanitized_text, list_of_redactions, quality_flags)
    """
    normalized = normalize_text_nfc_lf(raw_text)
    redaction_candidates: list[RedactionMatch] = []

    # 1. Candidate Name (if provided)
    if candidate_name and len(candidate_name.strip()) >= 2:
        c_norm = normalize_text_nfc_lf(candidate_name.strip())
        pattern = re.compile(re.escape(c_norm), re.IGNORECASE)
        for m in pattern.finditer(normalized):
            redaction_candidates.append(
                RedactionMatch(
                    start_cp=m.start(),
                    end_cp=m.end(),
                    original_text=m.group(),
                    replacement="[ỨNG_VIÊN]",
                    entity_type="candidate_name",
                )
            )

    # 2. Email
    for m in EMAIL_REGEX.finditer(normalized):
        redaction_candidates.append(
            RedactionMatch(
                start_cp=m.start(),
                end_cp=m.end(),
                original_text=m.group(),
                replacement="[EMAIL]",
                entity_type="email",
            )
        )

    # 3. Phone
    for m in PHONE_REGEX.finditer(normalized):
        redaction_candidates.append(
            RedactionMatch(
                start_cp=m.start(),
                end_cp=m.end(),
                original_text=m.group(),
                replacement="[SỐ_ĐIỆN_THOẠI]",
                entity_type="phone",
            )
        )

    # 4. URLs & Social Profiles
    for m in URL_SOCIAL_REGEX.finditer(normalized):
        redaction_candidates.append(
            RedactionMatch(
                start_cp=m.start(),
                end_cp=m.end(),
                original_text=m.group(),
                replacement="[LIÊN_KẾT]",
                entity_type="url",
            )
        )

    # 5. Date of Birth / Age
    for m in DOB_AGE_REGEX.finditer(normalized):
        redaction_candidates.append(
            RedactionMatch(
                start_cp=m.start(),
                end_cp=m.end(),
                original_text=m.group(),
                replacement="[NGÀY_SINH/TUỔI]",
                entity_type="dob_age",
            )
        )

    # 6. Gender & Marital Status
    for m in GENDER_MARITAL_REGEX.finditer(normalized):
        redaction_candidates.append(
            RedactionMatch(
                start_cp=m.start(),
                end_cp=m.end(),
                original_text=m.group(),
                replacement="[THÔNG_TIN_NHÂN_THÂN]",
                entity_type="demographic",
            )
        )

    # 7. Address & Origin
    for m in ADDRESS_ORIGIN_REGEX.finditer(normalized):
        redaction_candidates.append(
            RedactionMatch(
                start_cp=m.start(),
                end_cp=m.end(),
                original_text=m.group(),
                replacement="[ĐỊA_CHỈ]",
                entity_type="address",
            )
        )

    # 8. School / University
    for m in SCHOOL_REGEX.finditer(normalized):
        matched_str = m.group()
        # Avoid redacting if pure technical keyword
        if matched_str.strip().lower() not in TECHNICAL_ALLOWLIST:
            redaction_candidates.append(
                RedactionMatch(
                    start_cp=m.start(),
                    end_cp=m.end(),
                    original_text=matched_str,
                    replacement="[TRƯỜNG_ĐẠI_HỌC]",
                    entity_type="school",
                )
            )

    # 9. Company / Organization (with technical keyword protection)
    for m in ORG_REGEX.finditer(normalized):
        matched_str = m.group()
        cleaned_words = {w.strip().lower() for w in re.split(r"[\s,.-]+", matched_str) if w.strip()}
        # If the match is solely a technical keyword, DO NOT redact
        if cleaned_words and cleaned_words.issubset(TECHNICAL_ALLOWLIST):
            continue
        redaction_candidates.append(
            RedactionMatch(
                start_cp=m.start(),
                end_cp=m.end(),
                original_text=matched_str,
                replacement="[TỔ_CHỨC]",
                entity_type="organization",
            )
        )

    # Filter overlaps: sort by start_cp ascending, end_cp descending
    redaction_candidates.sort(key=lambda x: (x.start_cp, -x.end_cp))

    non_overlapping: list[RedactionMatch] = []
    last_end = -1
    for r in redaction_candidates:
        if r.start_cp >= last_end:
            non_overlapping.append(r)
            last_end = r.end_cp

    # Reconstruct sanitized text
    out_parts: list[str] = []
    cur_idx = 0
    redaction_dicts: list[dict[str, Any]] = []

    for r in non_overlapping:
        if r.start_cp > cur_idx:
            out_parts.append(normalized[cur_idx : r.start_cp])
        out_parts.append(r.replacement)
        redaction_dicts.append(
            {
                "original_text": r.original_text,
                "replacement": r.replacement,
                "entity_type": r.entity_type,
                "raw_start_cp": r.start_cp,
                "raw_end_cp": r.end_cp,
            }
        )
        cur_idx = r.end_cp

    if cur_idx < len(normalized):
        out_parts.append(normalized[cur_idx:])

    sanitized_text = "".join(out_parts)
    sanitized_text = normalize_text_nfc_lf(sanitized_text)

    quality_flags = {
        "redaction_count": len(redaction_dicts),
        "entities_detected": list({r["entity_type"] for r in redaction_dicts}),
        "contains_phone_placeholder": "[SỐ_ĐIỆN_THOẠI]" in sanitized_text,
        "contains_email_placeholder": "[EMAIL]" in sanitized_text,
        "contains_school_placeholder": "[TRƯỜNG_ĐẠI_HỌC]" in sanitized_text,
    }

    return sanitized_text, redaction_dicts, quality_flags


def build_source_spans_from_canonical(
    sanitized_version_id: uuid.UUID,
    canonical_text: str,
    max_span_codepoints: int = 1200,
) -> list[SourceSpan]:
    """Generate deterministic SourceSpans from canonical sanitized text.
    Invariants:
      1. source_span.text == canonical_text[start_cp:end_cp]
      2. span_id = 'spn_' + sha256(sanitized_version_uuid + ':' + start_cp + ':' + end_cp)[0:24]
      3. Length <= max_span_codepoints (1,200 codepoints)
      4. Exact half-open [start_cp, end_cp) codepoint offsets.
    """
    text = normalize_text_nfc_lf(canonical_text)
    spans: list[SourceSpan] = []

    # Keep citations small enough to copy exactly and to cite contradictory
    # statements independently, even when a CV puts them on one line.
    for m in re.finditer(r"[^\n]+", text):
        paragraph = m.group()
        sentence_start = 0
        boundaries = [match.start() for match in re.finditer(r"(?<=[.!?])\s+(?=\S)", paragraph)]
        for boundary in boundaries + [len(paragraph)]:
            start_cp = m.start() + sentence_start
            end_cp = m.start() + boundary
            while start_cp < end_cp and text[start_cp].isspace():
                start_cp += 1
            while end_cp > start_cp and text[end_cp - 1].isspace():
                end_cp -= 1
            sentence_start = boundary
            if start_cp == end_cp:
                continue

            # Long sentences remain bounded; offsets always refer to the
            # unchanged canonical text, including across mixed languages.
            sub_start = start_cp
            while sub_start < end_cp:
                sub_end = min(sub_start + max_span_codepoints, end_cp)
                span_slice = text[sub_start:sub_end]

                span_key = f"{sanitized_version_id}:{sub_start}:{sub_end}"
                full_h = hashlib.sha256(span_key.encode("utf-8")).hexdigest()
                span_id = f"spn_{full_h[:24]}"

                spans.append(
                    SourceSpan(
                        span_id=span_id,
                        full_hash=full_h,
                        sanitized_version_id=sanitized_version_id,
                        start_cp=sub_start,
                        end_cp=sub_end,
                        page_number=1,
                        section_label=None,
                        language="vi",
                        text=span_slice,
                    )
                )
                sub_start = sub_end

    return spans
