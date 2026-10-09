"""Typed transient result returned by the evidence assessment graph."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models.document import SourceSpan
from app.schemas.assessment import AssessmentOutputSchema, EvidenceOnlyAssessmentSchema


@dataclass(frozen=True)
class AgentExecutionResult:
    output: AssessmentOutputSchema | EvidenceOnlyAssessmentSchema
    trace: dict[str, Any]
    source_spans: dict[str, SourceSpan]
    allowed_span_ids_by_criterion: dict[str, set[str]]
