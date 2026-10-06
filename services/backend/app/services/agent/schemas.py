"""Typed transient result returned by the evidence assessment graph."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.db.models.document import SourceSpan
from app.schemas.assessment import AssessmentOutputSchema


@dataclass(frozen=True)
class AgentExecutionResult:
    output: AssessmentOutputSchema
    trace: dict[str, Any]
    source_spans: dict[str, SourceSpan]
