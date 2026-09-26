"""Prompt templates and context builders for AI Assessment and bounded repair."""
from __future__ import annotations

import json
from typing import Any

from app.db.models.document import SourceSpan
from app.db.models import RubricCriterion


def build_assessment_system_prompt() -> str:
    """Construct deterministic system prompt enforcing JSON mode and evidence contracts."""
    return """You are an impartial technical evaluation assistant for TalentScreen AI.
Your task is to evaluate a candidate's technical competencies based ONLY on provided CV source spans and an approved Rubric.

CRITICAL INVARIANTS:
1. You must respond strictly in JSON matching the requested schema.
2. Evaluate exactly six canonical criteria:
   - python_backend
   - api_design
   - sql_data
   - testing_debugging
   - security_privacy
   - delivery_ops
3. For each criterion:
   - status must be one of: "assessed", "insufficient_evidence", "conflicting_evidence"
   - if assessed: score must be an integer from 0 to 4 based on anchors; evidence must have at least 1 item; missing_information must be []
   - if insufficient_evidence: score must be null; missing_information must list specific questions or missing details
   - if conflicting_evidence: score must be null; evidence must have at least 2 conflicting items; missing_information must list items to verify
4. EVIDENCE CITATION:
   - Every evidence item must cite an exact span_id provided in the user prompt.
   - The 'quote' field MUST be copied VERBATIM and ENTIRELY from the text of that cited span.
   - DO NOT alter, truncate, or paraphrase quotes.
5. DO NOT provide overall scores, rankings, or hiring recommendations. Those are computed deterministically by the system.
"""


def build_assessment_user_prompt(
    rubric_criteria: list[RubricCriterion],
    source_spans: list[SourceSpan],
) -> str:
    """Build user prompt containing structured Rubric definitions and candidate Source Spans."""
    rubric_data = []
    for c in rubric_criteria:
        rubric_data.append(
            {
                "criterion_id": c.criterion_id,
                "label": getattr(c, "label_vi", getattr(c, "label", "")),
                "weight": c.weight,
                "description": getattr(c, "description_vi", getattr(c, "description", "")),
                "anchors": c.anchors if hasattr(c, "anchors") and isinstance(c.anchors, dict) else {},
            }
        )

    spans_data = [
        {
            "span_id": s.span_id,
            "text": s.text,
        }
        for s in source_spans
    ]

    payload = {
        "rubric": rubric_data,
        "source_spans": spans_data,
        "instructions": (
            "Evaluate each of the 6 criteria using the rubric anchors and candidate source spans. "
            "Return JSON object with key 'criteria' containing an array of 6 objects."
        ),
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_repair_user_prompt(
    original_user_prompt: str,
    validation_errors: list[str],
) -> str:
    """Build a targeted repair prompt for attempt 2 without leaking system secrets."""
    error_summary = "\n".join(f"- {err}" for err in validation_errors[:5])
    return f"""The previous response failed validation with the following contract errors:
{error_summary}

Please regenerate the complete JSON evaluation correcting these errors.
Ensure exact schema adherence, exact 6 canonical criteria, valid scores (0..4 or null), and verbatim quotes matching provided span_ids.

Original Data:
{original_user_prompt}
"""
