"""Validation engine for LLM Assessment output.
Enforces JSON schema conformance, exact source span equality, and forbidden attribute guards.
"""
from __future__ import annotations

import json
import logging
from typing import Mapping, Optional
from pydantic import ValidationError

from app.db.models.document import SourceSpan
from app.domain.rubric_policy import scan_forbidden_criteria
from app.schemas.assessment import AssessmentOutputSchema, EvidenceOnlyAssessmentSchema

logger = logging.getLogger(__name__)


class AssessmentValidationError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]


def validate_assessment_output(
    raw_content: str,
    span_registry: dict[str, SourceSpan],
    expected_criterion_ids: Optional[set[str]] = None,
    *,
    allowed_span_ids_by_criterion: Mapping[str, set[str]] | None = None,
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

    if expected_criterion_ids is not None:
        returned_ids = {criterion.criterion_id for criterion in assessment.criteria}
        if returned_ids != expected_criterion_ids:
            missing = sorted(expected_criterion_ids - returned_ids)
            unexpected = sorted(returned_ids - expected_criterion_ids)
            raise AssessmentValidationError(
                f"CRITERION_SET_MISMATCH: Missing={missing}; unexpected={unexpected}.",
                errors=["CRITERION_SET_MISMATCH"],
            )

    # 3. Provenance & Source Span Registry Cross-Verification
    provenance_errors = []
    for crit in assessment.criteria:
        for ev in crit.evidence:
            allowed_for_criterion = (
                allowed_span_ids_by_criterion.get(crit.criterion_id)
                if allowed_span_ids_by_criterion is not None
                else None
            )
            if allowed_for_criterion is not None and ev.span_id not in allowed_for_criterion:
                provenance_errors.append(
                    f"UNRETRIEVED_SPAN: Span '{ev.span_id}' was not retrieved for criterion '{crit.criterion_id}'."
                )
                continue
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


def validate_evidence_only_output(
    raw_content: str,
    span_registry: dict[str, SourceSpan],
    expected_criterion_ids: set[str],
    *,
    allowed_span_ids_by_criterion: Mapping[str, set[str]] | None = None,
) -> EvidenceOnlyAssessmentSchema:
    """Validate a Jev-mode agent response without allowing scoring fields."""
    if not raw_content or not raw_content.strip():
        raise AssessmentValidationError("EMPTY_CONTENT: Model returned empty content.")
    try:
        parsed_json = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise AssessmentValidationError(f"MALFORMED_JSON: Cannot decode JSON response: {exc}")
    if not isinstance(parsed_json, dict):
        raise AssessmentValidationError("INVALID_ROOT_TYPE: Response must be a JSON object.")
    try:
        assessment = EvidenceOnlyAssessmentSchema.model_validate(parsed_json)
    except ValidationError as exc:
        err_msgs = [f"{err['loc']}: {err['msg']}" for err in exc.errors()]
        raise AssessmentValidationError(
            f"SCHEMA_VIOLATION: Evidence-only output is invalid: {'; '.join(err_msgs[:3])}",
            errors=err_msgs,
        )
    returned_ids = {criterion.criterion_id for criterion in assessment.criteria}
    if returned_ids != expected_criterion_ids:
        missing = sorted(expected_criterion_ids - returned_ids)
        unexpected = sorted(returned_ids - expected_criterion_ids)
        raise AssessmentValidationError(
            f"CRITERION_SET_MISMATCH: Missing={missing}; unexpected={unexpected}.",
            errors=["CRITERION_SET_MISMATCH"],
        )
    errors: list[str] = []
    for criterion in assessment.criteria:
        for evidence in criterion.evidence:
            permitted = allowed_span_ids_by_criterion.get(criterion.criterion_id) if allowed_span_ids_by_criterion is not None else None
            if permitted is not None and evidence.span_id not in permitted:
                errors.append(f"UNRETRIEVED_SPAN: {evidence.span_id} is not allowed for {criterion.criterion_id}.")
                continue
            span = span_registry.get(evidence.span_id)
            if span is None:
                errors.append(f"UNKNOWN_SPAN: {evidence.span_id} is not in the approved document.")
            elif evidence.quote != span.text:
                errors.append(f"QUOTE_MISMATCH: {evidence.span_id} is not verbatim.")
        forbidden = scan_forbidden_criteria(criterion.rationale)
        if forbidden:
            errors.append(f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: {criterion.criterion_id}: {forbidden}")
        for question in criterion.missing_information:
            forbidden = scan_forbidden_criteria(question)
            if forbidden:
                errors.append(f"FORBIDDEN_DEMOGRAPHIC_ATTRIBUTE: {criterion.criterion_id}: {forbidden}")
    if errors:
        raise AssessmentValidationError(f"PROVENANCE_VIOLATION: {'; '.join(errors[:3])}", errors=errors)
    return assessment
