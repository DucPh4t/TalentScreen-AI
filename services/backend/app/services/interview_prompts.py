"""Interview Agent prompts and output validator (Task B14)."""
from __future__ import annotations

import json
import logging
from typing import Any
from pydantic import ValidationError

from app.db.models.document import SourceSpan
from app.domain.rubric_policy import scan_forbidden_criteria
from app.schemas.interview import CoreQuestionSchema, FollowupQuestionSchema, InterviewOutputSchema

logger = logging.getLogger(__name__)


def build_interview_system_prompt() -> str:
    """Build canonical system prompt for Interview Agent follow-up generation."""
    return (
        "Task: draft clarification questions for HR, not a hiring decision.\n"
        "Keep the approved core questions unchanged and in their given order. Create at most\n"
        "three candidate-specific follow-ups addressing missing or conflicting evidence.\n"
        "Every follow-up must reference a valid criterion_id and explain its purpose.\n"
        "Only assert candidate facts explicitly supported by supplied spans. If evidence is\n"
        "missing, ask neutrally for an example; do not assert the candidate lacks the skill.\n"
        "Do not ask about age, family, origin, health, gender, school identity or prestige.\n"
        "Do not infer language ability or personality from the CV. Keep task complexity\n"
        "consistent with the approved role. Do not provide an invented candidate answer.\n"
        "Return JSON with followups only; core questions are rendered separately by backend.\n"
        'Example JSON: {"followups":[{"criterion_id":"testing_debugging",'
        '"question_vi":"Bạn có thể mô tả một lỗi API đã xử lý và cách kiểm tra bản sửa?",'
        '"purpose_vi":"Làm rõ kinh nghiệm debugging và kiểm thử.","source_span_ids":[],'
        '"answer_indicators":["Nêu bước tái hiện","Giải thích kiểm thử tránh tái phát"]}]}'
    )


def build_interview_user_prompt(
    rubric_criteria: list[dict[str, Any]],
    core_questions: list[CoreQuestionSchema],
    assessment_criteria: list[dict[str, Any]],
    source_spans: list[SourceSpan],
) -> str:
    """Build user prompt containing rubric, core bank questions, candidate assessment findings, and source spans."""
    payload = {
        "rubric_criteria": rubric_criteria,
        "approved_core_questions": [q.model_dump() for q in core_questions],
        "candidate_assessment": assessment_criteria,
        "allowed_source_spans": [
            {"span_id": s.span_id, "text": s.text} for s in source_spans
        ],
        "instructions": (
            "Generate at most 3 candidate-specific follow-up questions targeting gaps or areas needing clarification. "
            "Return valid JSON adhering to contract: {'followups': [...]}"
        ),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_interview_repair_prompt(original_prompt: str, errors: list[str]) -> str:
    """Build repair prompt on validation failure."""
    err_text = "\n".join(f"- {e}" for e in errors[:5])
    return (
        f"Your prior attempt could not be accepted by the backend contract validators.\n"
        f"Contract violations:\n{err_text}\n\n"
        "Regenerate one complete JSON object from the original authorized input below.\n"
        "Correct only the reported contract violations; never invent evidence to satisfy a required field.\n"
        "Do not include error codes, commentary, Markdown or any extra keys in output.\n\n"
        f"Original Data:\n{original_prompt}"
    )


class InterviewValidationError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


def validate_interview_output(
    raw_content: str,
    valid_span_ids: set[str],
    valid_criterion_ids: set[str] | None = None,
) -> InterviewOutputSchema:
    """Validate model output against schema, span ownership, and anti-discrimination rules."""
    if not raw_content or not raw_content.strip():
        raise InterviewValidationError("EMPTY_CONTENT: Model returned empty content.")

    try:
        parsed_json = json.loads(raw_content)
    except json.JSONDecodeError as e:
        raise InterviewValidationError(f"MALFORMED_JSON: Cannot decode JSON response: {e}")

    if not isinstance(parsed_json, dict):
        raise InterviewValidationError("INVALID_ROOT_TYPE: Response must be a JSON object.")

    try:
        output = InterviewOutputSchema.model_validate(parsed_json)
    except ValidationError as e:
        err_msgs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        raise InterviewValidationError(
            f"SCHEMA_VIOLATION: Output does not conform to interview contract: {'; '.join(err_msgs[:3])}",
            errors=err_msgs,
        )

    # Cross-verification
    errors = []
    valid_cids = valid_criterion_ids or set()

    for idx, f in enumerate(output.followups):
        if f.criterion_id not in valid_cids:
            errors.append(f"INVALID_CRITERION: Followup {idx} references unknown criterion '{f.criterion_id}'.")

        # Anti-discrimination scan
        f_q = scan_forbidden_criteria(f.question_vi)
        if f_q:
            errors.append(f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Followup {idx} question mentions forbidden attribute: {f_q}")

        f_p = scan_forbidden_criteria(f.purpose_vi)
        if f_p:
            errors.append(f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Followup {idx} purpose mentions forbidden attribute: {f_p}")

        for ind in f.answer_indicators:
            f_ind = scan_forbidden_criteria(ind)
            if f_ind:
                errors.append(f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Followup {idx} indicator mentions forbidden attribute: {f_ind}")

        # Span validation
        for s_id in f.source_span_ids:
            if s_id not in valid_span_ids:
                errors.append(f"UNKNOWN_SPAN: Span '{s_id}' cited in followup {idx} does not exist in candidate sanitized version.")

    if errors:
        raise InterviewValidationError(
            f"VALIDATION_FAILURE: {'; '.join(errors[:3])}",
            errors=errors,
        )

    return output
