"""Validated read-only tools scoped to one approved assessment snapshot."""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.observability import observed

from app.db.models.assessment import AssessmentRun
from app.db.models.candidate import Application
from app.db.models.document import SanitizedVersion, SourceSpan
from app.db.models.requisition import Requisition, RubricCriterion
from app.domain.enums import SanitizedVersionStatus
from app.services.retrieval import RetrievedChunkScore, hybrid_retrieve_for_criterion
from app.services.sanitizer import residual_contact_types

MAX_AGENT_QUERY_HINT_CHARS = 256
MAX_AGENT_CRITERIA_PER_RETRIEVAL = 4
MAX_AGENT_SPANS_PER_REQUEST = 8
MAX_AGENT_SPAN_CHARS = 24_000
INITIAL_SPAN_LOOKUP_BATCH_SIZE = 500
_SPAN_ID_RE = re.compile(r"^spn_[0-9a-f]{24}$")


class AgentToolError(ValueError):
    """Raised when a model tool request is outside the authorized read-only contract."""


def _anchor_query_terms(anchors: object) -> list[str]:
    """Normalize both score-key maps and the current list-shaped rubric anchors."""
    values = list(anchors.values()) if isinstance(anchors, dict) else anchors if isinstance(anchors, list) else []
    terms: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            terms.append(value.strip())
        elif isinstance(value, dict):
            description = value.get("description")
            if isinstance(description, str) and description.strip():
                terms.append(description.strip())
            qualifying = value.get("qualifying_evidence", [])
            if isinstance(qualifying, list):
                terms.extend(item.strip() for item in qualifying if isinstance(item, str) and item.strip())
    return terms


async def _require_approved_snapshot(db: AsyncSession, run: AssessmentRun) -> None:
    snapshot = run.snapshot or {}
    if (
        snapshot.get("application_id") != str(run.application_id)
        or snapshot.get("document_id") != str(run.document_id)
        or snapshot.get("sanitized_version_id") != str(run.sanitized_version_id)
        or snapshot.get("rubric_version_id") != str(run.rubric_version_id)
        or snapshot.get("application_generation") != run.application_generation
    ):
        raise AgentToolError("Assessment snapshot scope is invalid.")
    if await snapshot_failure_code(db, run):
        raise AgentToolError("Assessment snapshot is no longer current and approved.")


async def snapshot_failure_code(db: AsyncSession, run: AssessmentRun) -> str | None:
    """Return a safe failure code when deletion, revocation, or version drift invalidates a run."""
    snapshot = run.snapshot or {}
    if (
        snapshot.get("application_id") != str(run.application_id)
        or snapshot.get("document_id") != str(run.document_id)
        or snapshot.get("sanitized_version_id") != str(run.sanitized_version_id)
        or snapshot.get("rubric_version_id") != str(run.rubric_version_id)
        or snapshot.get("application_generation") != run.application_generation
    ):
        return "ASSESSMENT_INPUT_STALE"

    row = (await db.execute(
        select(
            Application.status,
            Application.generation,
            Application.current_document_id,
            Application.current_sanitized_version_id,
            Requisition.current_rubric_version_id,
            SanitizedVersion.status,
            SanitizedVersion.application_id,
            SanitizedVersion.document_id,
            SanitizedVersion.sha256,
        )
        .join(Requisition, Requisition.id == Application.requisition_id)
        .outerjoin(SanitizedVersion, SanitizedVersion.id == Application.current_sanitized_version_id)
        .where(Application.id == run.application_id)
    )).first()
    if not row or row[0] == "deleted":
        return "APPLICATION_TOMBSTONED"
    if row[0] != "active":
        return "ASSESSMENT_INPUT_STALE"
    if (
        row[1] != run.application_generation
        or row[2] != run.document_id
        or row[3] != run.sanitized_version_id
        or row[4] != run.rubric_version_id
        or row[5] != SanitizedVersionStatus.APPROVED
        or row[6] != run.application_id
        or row[7] != run.document_id
        or (snapshot.get("sanitized_sha256") and row[8] != snapshot["sanitized_sha256"])
    ):
        return "ASSESSMENT_INPUT_STALE"
    return None


def _safe_query_hint(query_hint: str) -> str:
    if not isinstance(query_hint, str) or len(query_hint) > MAX_AGENT_QUERY_HINT_CHARS:
        raise AgentToolError("Query hint is invalid or too long.")
    cleaned = "".join(" " if unicodedata.category(char) == "Cc" else char for char in query_hint)
    cleaned = " ".join(cleaned.split())
    if not cleaned or residual_contact_types(cleaned):
        raise AgentToolError("Query hint contains contact data or no searchable text.")
    return cleaned


@observed("retrieve_more_evidence", run_type="tool", result_metadata=lambda result: {"result_count": len(result)})
async def retrieve_more_evidence(
    *,
    db: AsyncSession,
    run: AssessmentRun,
    rubric_criteria: list[RubricCriterion],
    criterion_ids: list[str],
    query_hint: str,
) -> list[RetrievedChunkScore]:
    """Search only requested approved criteria in the run's sanitized CV version."""
    await _require_approved_snapshot(db, run)
    query = _safe_query_hint(query_hint)
    if (
        not isinstance(criterion_ids, list)
        or not criterion_ids
        or len(criterion_ids) > MAX_AGENT_CRITERIA_PER_RETRIEVAL
        or len(set(criterion_ids)) != len(criterion_ids)
    ):
        raise AgentToolError("Criterion scope is invalid.")

    criteria_by_id = {
        criterion.criterion_id: criterion
        for criterion in rubric_criteria
        if criterion.rubric_version_id == run.rubric_version_id
    }
    if set(criterion_ids) - set(criteria_by_id):
        raise AgentToolError("Requested criteria are outside the approved rubric.")

    results: list[RetrievedChunkScore] = []
    for criterion_id in criterion_ids:
        criterion = criteria_by_id[criterion_id]
        results.extend(await hybrid_retrieve_for_criterion(
            db,
            run.sanitized_version_id,
            criterion.label_vi,
            f"{criterion.description_vi} {query}",
            top_k=4,
            bilingual_terms=criterion.bilingual_terms,
            anchor_terms=_anchor_query_terms(criterion.anchors),
        ))
    return results


@observed("get_source_spans", run_type="tool", result_metadata=lambda result: {"result_count": len(result)})
async def get_source_spans(
    *,
    db: AsyncSession,
    run: AssessmentRun,
    span_ids: list[str],
) -> list[SourceSpan]:
    """Resolve exact canonical spans only from the current approved sanitized version."""
    await _require_approved_snapshot(db, run)
    if (
        not isinstance(span_ids, list)
        or not span_ids
        or len(span_ids) > MAX_AGENT_SPANS_PER_REQUEST
        or len(set(span_ids)) != len(span_ids)
        or any(not isinstance(span_id, str) or not _SPAN_ID_RE.fullmatch(span_id) for span_id in span_ids)
    ):
        raise AgentToolError("Source span request is invalid.")
    spans = (await db.execute(
        select(SourceSpan).where(
            SourceSpan.sanitized_version_id == run.sanitized_version_id,
            SourceSpan.span_id.in_(span_ids),
        )
    )).scalars().all()
    spans_by_id = {span.span_id: span for span in spans}
    if set(spans_by_id) != set(span_ids):
        raise AgentToolError("One or more source spans are outside the approved assessment snapshot.")
    ordered_spans = [spans_by_id[span_id] for span_id in span_ids]
    if sum(len(span.text) for span in ordered_spans) > MAX_AGENT_SPAN_CHARS:
        raise AgentToolError("Requested source spans exceed the assessment context limit.")
    return ordered_spans


async def load_initial_source_spans(
    *,
    db: AsyncSession,
    run: AssessmentRun,
    span_ids: list[str],
) -> list[SourceSpan]:
    """Resolve a worker-authorized initial pack without applying model-tool batch limits."""
    await _require_approved_snapshot(db, run)
    if (
        not isinstance(span_ids, list)
        or any(not isinstance(span_id, str) or not _SPAN_ID_RE.fullmatch(span_id) for span_id in span_ids)
        or len(set(span_ids)) != len(span_ids)
    ):
        raise AgentToolError("Initial source span registry is invalid.")
    if not span_ids:
        return []

    spans_by_id: dict[str, SourceSpan] = {}
    for offset in range(0, len(span_ids), INITIAL_SPAN_LOOKUP_BATCH_SIZE):
        batch = span_ids[offset : offset + INITIAL_SPAN_LOOKUP_BATCH_SIZE]
        rows = (await db.execute(
            select(SourceSpan).where(
                SourceSpan.sanitized_version_id == run.sanitized_version_id,
                SourceSpan.span_id.in_(batch),
            )
        )).scalars().all()
        spans_by_id.update({span.span_id: span for span in rows})
    if set(spans_by_id) != set(span_ids):
        raise AgentToolError("Initial source spans are outside the approved assessment snapshot.")
    return [spans_by_id[span_id] for span_id in span_ids]
