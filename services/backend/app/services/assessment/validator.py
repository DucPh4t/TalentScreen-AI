"""Validation engine for LLM Assessment output.
Enforces JSON schema conformance, exact source span equality, and forbidden attribute guards.
"""
from __future__ import annotations

import json
import logging
from typing import Optional
from pydantic import ValidationError

from app.db.models.document import SourceSpan
from app.domain.rubric_policy import scan_forbidden_criteria
from app.schemas.assessment import AssessmentOutputSchema

logger = logging.getLogger(__name__)


class AssessmentValidationError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


def validate_assessment_output(
    raw_content: str,
    span_registry: dict[str, SourceSpan],
) -> AssessmentOutputSchema:
    """Validate model output string against schema and DB source span registry.
    Raises AssessmentValidationError on failure with specific error codes.
    """
    if not raw_content or not raw_content.strip():
        raise AssessmentValidationError("EMPTY_CONTENT: Model returned empty content.")

    # 1. Parse JSON
    try:
        parsed_json = json.loads(raw_content)
    except json.JSONDecodeError as e:
        raise AssessmentValidationError(f"MALFORMED_JSON: Cannot decode JSON response: {e}")

    if not isinstance(parsed_json, dict):
        raise AssessmentValidationError("INVALID_ROOT_TYPE: Response must be a JSON object.")

    # 2. Pydantic Strict Schema Validation
    try:
        assessment = AssessmentOutputSchema.model_validate(parsed_json)
    except ValidationError as e:
        err_msgs = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        raise AssessmentValidationError(
            f"SCHEMA_VIOLATION: Output does not conform to assessment contract: {'; '.join(err_msgs[:3])}",
            errors=err_msgs,
        )

    # 3. Provenance & Source Span Registry Cross-Verification
    provenance_errors = []
    for crit in assessment.criteria:
        for ev in crit.evidence:
            span = span_registry.get(ev.span_id)
            if not span:
                provenance_errors.append(
                    f"UNKNOWN_SPAN: Span '{ev.span_id}' cited in criterion '{crit.criterion_id}' does not exist in approved version."
                )
                continue

            # Exact verbatim quote equality check
            if ev.quote != span.text:
                provenance_errors.append(
                    f"QUOTE_MISMATCH: Quote in span '{ev.span_id}' does not match registered canonical text verbatim."
                )

        # 4. Anti-discrimination scan on rationales
        forbidden = scan_forbidden_criteria(crit.rationale)
        if forbidden:
            provenance_errors.append(
                f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: Criterion '{crit.criterion_id}' rationale mentions forbidden demographic proxy: {forbidden}"
            )

    if provenance_errors:
        raise AssessmentValidationError(
            f"PROVENANCE_VIOLATION: {'; '.join(provenance_errors[:3])}",
            errors=provenance_errors,
        )

    return assessment
