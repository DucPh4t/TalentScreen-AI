"""Rubric-aware hybrid retrieval over one approved sanitized CV snapshot."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re
from typing import Any, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.observability import observed
from app.services.assessment.diagnostics import AssessmentDiagnostics, safe_record

from app.db.models.document import RetrievalChunk, SourceSpan
from app.services.embedding import EMBEDDING_CONFIG_ID, embedding_config_id, embed_texts

RRF_K = 60
DENSE_CANDIDATE_LIMIT = 10
LEXICAL_CANDIDATE_LIMIT = 10
MAX_LEXICAL_QUERY_TERMS = 8
MAX_EVIDENCE_CHUNKS_PER_CRITERION = 4
MAX_CRITERION_QUERY_CHARS = 4000


@dataclass
class RetrievedChunkScore:
    chunk_id: uuid.UUID
    chunk_index: int
    text: str
    span_ids: list[str]
    dense_rank: Optional[int]
    lexical_rank: Optional[int]
    rrf_score: float


def _flatten_text_values(value: Any) -> list[str]:
    """Return only human-authored phrase values from approved rubric JSON."""
    if isinstance(value, str):
        phrase = re.sub(r"\s+", " ", value).strip()
        return [phrase] if phrase else []
    if isinstance(value, Mapping):
        phrases: list[str] = []
        for key in sorted(value, key=lambda item: str(item)):
            phrases.extend(_flatten_text_values(value[key]))
        return phrases
    if isinstance(value, (list, tuple)):
        return [phrase for item in value for phrase in _flatten_text_values(item)]
    return []


def _unique_phrases(values: list[str]) -> list[str]:
    phrases: list[str] = []
    seen: set[str] = set()
    for value in values:
        phrase = re.sub(r"\s+", " ", value).strip()
        normalized = phrase.casefold()
        if phrase and normalized not in seen:
            seen.add(normalized)
            phrases.append(phrase)
    return phrases


def _build_criterion_query(
    criterion_name: str,
    criterion_description: str,
    bilingual_terms: dict[str, Any] | None,
    anchor_terms: list[str] | None,
) -> tuple[str, list[str]]:
    """Build E5 context and a safe, bounded lexical query from approved rubric text."""
    name = re.sub(r"\s+", " ", criterion_name or "").strip()
    description = re.sub(r"\s+", " ", criterion_description or "").strip()
    anchors = _unique_phrases(_flatten_text_values(anchor_terms or []))
    synonyms = _unique_phrases(_flatten_text_values(bilingual_terms or {}))
    full_phrases = _unique_phrases([name, description, *anchors, *synonyms])
    query_text = " ".join(full_phrases)[:MAX_CRITERION_QUERY_CHARS]

    # The lexical parser receives simple word tokens only. Put labels, approved
    # anchors, and bilingual synonyms ahead of descriptive filler so the eight
    # token cap retains the role-specific vocabulary.
    lexical_sources = [name, *anchors, *synonyms, description]
    lexical_terms: list[str] = []
    seen_tokens: set[str] = set()
    for source in lexical_sources:
        for token in re.findall(r"\w+", source.casefold()):
            if len(token) <= 2 or token in seen_tokens:
                continue
            seen_tokens.add(token)
            lexical_terms.append(token)
            if len(lexical_terms) >= MAX_LEXICAL_QUERY_TERMS:
                return query_text, lexical_terms
    return query_text, lexical_terms


def _build_evidence_query(criterion_name, criterion_description, bilingual_terms, anchor_terms):
    """Prioritize approved skill vocabulary within E5's finite query context."""
    synonyms = _unique_phrases(_flatten_text_values(bilingual_terms or {}))
    anchors = _unique_phrases(_flatten_text_values(anchor_terms or []))
    phrases = _unique_phrases([*synonyms, criterion_name or '', criterion_description or '', *anchors])
    query = ' '.join(phrases)[:800]
    terms = []
    for phrase in [*synonyms, criterion_name or '', *anchors, criterion_description or '']:
        for token in re.findall(r'\w+', phrase.casefold()):
            if len(token) >= 2 and token not in terms:
                terms.append(token)
                if len(terms) >= 16:
                    return query, terms
    return query, terms


@observed("hybrid_retrieve_for_criterion", run_type="retriever",
    result_metadata=lambda result: {"result_count": len(result)})
async def hybrid_retrieve_for_criterion(
    db: AsyncSession,
    sanitized_version_id: uuid.UUID,
    criterion_name: str,
    criterion_description: str,
    top_k: int = 4,
    *,
    bilingual_terms: dict[str, Any] | None = None,
    anchor_terms: list[str] | None = None,
    channels: frozenset[str] = frozenset({"dense", "lexical"}),
    pipeline_version: str = "v1",
) -> list[RetrievedChunkScore]:
    """Fuse scoped dense and lexical results using deterministic Reciprocal Rank Fusion."""
    if not channels or not channels.issubset({"dense", "lexical"}):
        raise ValueError("RETRIEVAL_CHANNELS_INVALID")
    config_id = embedding_config_id(pipeline_version)
    candidate_limit = 30 if pipeline_version == "v2" else 10
    query_text, keywords = (_build_evidence_query if pipeline_version == "v2" else _build_criterion_query)(
        criterion_name,
        criterion_description,
        bilingual_terms,
        anchor_terms,
    )
    if not query_text:
        return []

    query_vec = embed_texts([query_text], prefix="query: ")[0] if "dense" in channels else None

    # Both retrieval channels are constrained to the exact approved sanitized
    # document version and embedding configuration before ranking.
    scope = (
        RetrievalChunk.sanitized_version_id == sanitized_version_id,
        RetrievalChunk.embedding_config_id == config_id,
    )
    dense_stmt = (
        select(RetrievalChunk)
        .where(*scope)
        .order_by(
            RetrievalChunk.embedding.cosine_distance(query_vec),
            RetrievalChunk.chunk_index.asc(),
        )
        .limit(candidate_limit)
    )
    dense_res = (await db.execute(dense_stmt)).scalars().all() if "dense" in channels else []
    dense_rank_map = {chunk.id: idx + 1 for idx, chunk in enumerate(dense_res)}
    all_chunks_by_id = {chunk.id: chunk for chunk in dense_res}

    lexical_rank_map: dict[uuid.UUID, int] = {}
    if keywords and "lexical" in channels:
        vector = func.to_tsvector("simple", RetrievalChunk.text)
        query = func.to_tsquery("simple", " | ".join(keywords))
        lex_stmt = (
            select(RetrievalChunk)
            .where(*scope, vector.op("@@")(query))
            .order_by(
                func.ts_rank_cd(vector, query).desc(),
                RetrievalChunk.chunk_index.asc(),
            )
            .limit(candidate_limit)
        )
        lex_res = (await db.execute(lex_stmt)).scalars().all()
        for idx, chunk in enumerate(lex_res):
            lexical_rank_map[chunk.id] = idx + 1
            all_chunks_by_id.setdefault(chunk.id, chunk)

    scores: list[RetrievedChunkScore] = []
    for chunk_id, chunk in all_chunks_by_id.items():
        dense_rank = dense_rank_map.get(chunk_id)
        lexical_rank = lexical_rank_map.get(chunk_id)
        rrf_score = 0.0
        if dense_rank is not None:
            rrf_score += 1.0 / (RRF_K + dense_rank)
        if lexical_rank is not None:
            rrf_score += 1.0 / (RRF_K + lexical_rank)
        scores.append(
            RetrievedChunkScore(
                chunk_id=chunk_id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                span_ids=list(chunk.span_ids or []),
                dense_rank=dense_rank,
                lexical_rank=lexical_rank,
                rrf_score=rrf_score,
            )
        )

    scores.sort(key=lambda score: (-score.rrf_score, score.chunk_index, str(score.chunk_id)))
    return scores[: max(0, top_k)]


async def _load_span_sections(
    db: AsyncSession,
    sanitized_version_id: uuid.UUID,
    matches: list[RetrievedChunkScore],
) -> dict[str, str | None]:
    """Load section labels only from source spans in the current sanitized version."""
    span_ids = list(dict.fromkeys(span_id for match in matches for span_id in match.span_ids))
    if not span_ids:
        return {}
    stmt = select(SourceSpan).where(
        SourceSpan.sanitized_version_id == sanitized_version_id,
        SourceSpan.span_id.in_(span_ids),
    )
    spans = (await db.execute(stmt)).scalars().all()
    return {span.span_id: span.section_label for span in spans}


def _select_diverse_matches(
    matches: list[RetrievedChunkScore],
    section_by_chunk_id: dict[uuid.UUID, str | None],
    valid_span_ids_by_chunk_id: dict[uuid.UUID, list[str]],
    limit: int,
) -> list[RetrievedChunkScore]:
    """Prefer one chunk per source section, then fill remaining slots by RRF rank."""
    selected: list[RetrievedChunkScore] = []
    deferred: list[RetrievedChunkScore] = []
    seen_sections: set[str] = set()
    for match in matches:
        if not valid_span_ids_by_chunk_id.get(match.chunk_id):
            continue
        section = section_by_chunk_id.get(match.chunk_id)
        section_key = section if section else f"__unknown__:{match.chunk_id}"
        if section_key in seen_sections:
            deferred.append(match)
            continue
        selected.append(match)
        seen_sections.add(section_key)
        if len(selected) >= limit:
            return selected
    for match in deferred:
        selected.append(match)
        if len(selected) >= limit:
            break
    return selected


@observed("initial_rag", run_type="retriever",
    input_metadata=lambda args: {"criterion_count": len(args["criteria"]), "retrieval_strategy": "hybrid"},
    result_metadata=lambda pack: {"source_span_count": len(pack.get("source_span_ids") or [])})
async def build_hybrid_assessment_pack(
    db: AsyncSession,
    sanitized_version_id: uuid.UUID,
    criteria: list[dict[str, Any]],
    max_evidence_chars: int = 24000,
    *,
    channels: frozenset[str] = frozenset({"dense", "lexical"}),
    pipeline_version: str = "v1",
    diagnostics: AssessmentDiagnostics | None = None,
) -> dict[str, Any]:
    """Build a bounded, section-diverse evidence pack for the approved rubric."""
    config_id = embedding_config_id(pipeline_version)
    if max_evidence_chars < 0:
        raise ValueError("max_evidence_chars must be non-negative")

    candidate_matches_by_criterion: dict[str, list[RetrievedChunkScore]] = {}
    all_matches_by_chunk_id: dict[uuid.UUID, RetrievedChunkScore] = {}

    for criterion in criteria:
        criterion_id = criterion.get("id") or criterion.get("name", "unknown")
        matches = await hybrid_retrieve_for_criterion(
            db,
            sanitized_version_id,
            criterion.get("name", ""),
            criterion.get("description", ""),
            top_k=30 if pipeline_version == "v2" else DENSE_CANDIDATE_LIMIT,
            **({"pipeline_version": pipeline_version} if pipeline_version != "v1" else {}),
            bilingual_terms=criterion.get("bilingual_terms"),
            **({"channels": channels} if channels != frozenset({"dense", "lexical"}) else {}),
            anchor_terms=[
                *_flatten_text_values(criterion.get("anchors")),
                *_flatten_text_values(criterion.get("anchor_terms")),
            ],
        )
        candidate_matches_by_criterion[criterion_id] = matches
        for match in matches:
            all_matches_by_chunk_id.setdefault(match.chunk_id, match)

    all_matches = list(all_matches_by_chunk_id.values())
    span_sections = await _load_span_sections(db, sanitized_version_id, all_matches)
    valid_span_ids_by_chunk_id: dict[uuid.UUID, list[str]] = {}
    section_by_chunk_id: dict[uuid.UUID, str | None] = {}
    for match in all_matches:
        valid_span_ids = list(
            dict.fromkeys(span_id for span_id in match.span_ids if span_id in span_sections)
        )
        valid_span_ids_by_chunk_id[match.chunk_id] = valid_span_ids
        labels = {span_sections[span_id] for span_id in valid_span_ids if span_sections[span_id]}
        # A chunk crossing source sections violates the chunking contract; fail
        # closed and let the baseline/manual path handle it.
        if len(labels) > 1:
            valid_span_ids_by_chunk_id[match.chunk_id] = []
        section_by_chunk_id[match.chunk_id] = next(iter(labels)) if len(labels) == 1 else None

    criterion_retrievals: dict[str, list[dict[str, Any]]] = {}
    selected_matches_by_id: dict[uuid.UUID, tuple[RetrievedChunkScore, list[str], str | None]] = {}
    total_chars = 0
    eligible_chunk_ids = set()
    size_excluded_chunk_ids = set()
    for criterion_id, candidates in candidate_matches_by_criterion.items():
        diverse_matches = _select_diverse_matches(
            candidates,
            section_by_chunk_id,
            valid_span_ids_by_chunk_id,
            MAX_EVIDENCE_CHUNKS_PER_CRITERION,
        )
        criterion_results: list[dict[str, Any]] = []
        for match in diverse_matches:
            eligible_chunk_ids.add(match.chunk_id)
            valid_span_ids = valid_span_ids_by_chunk_id[match.chunk_id]
            if match.chunk_id not in selected_matches_by_id:
                if total_chars + len(match.text) > max_evidence_chars:
                    size_excluded_chunk_ids.add(match.chunk_id)
                    continue
                total_chars += len(match.text)
                selected_matches_by_id[match.chunk_id] = (
                    match,
                    valid_span_ids,
                    section_by_chunk_id.get(match.chunk_id),
                )
            _, span_ids, section = selected_matches_by_id[match.chunk_id]
            criterion_results.append({
                "chunk_id": str(match.chunk_id),
                "chunk_index": match.chunk_index,
                "span_ids": span_ids,
                "section_label": section,
                "dense_rank": match.dense_rank,
                "lexical_rank": match.lexical_rank,
                "rrf_score": round(match.rrf_score, 5),
            })
        criterion_retrievals[criterion_id] = criterion_results
        safe_record(diagnostics, "record_retrieval", criterion_id,
                    [match.span_ids for match in candidates],
                    [span_id for match in criterion_results for span_id in match["span_ids"]])

    ordered_selected = sorted(
        selected_matches_by_id.values(),
        key=lambda item: (item[0].chunk_index, str(item[0].chunk_id)),
    )
    chunks = [
        {
            "chunk_id": str(match.chunk_id),
            "chunk_index": match.chunk_index,
            "text": match.text,
            "span_ids": span_ids,
            "section_label": section,
        }
        for match, span_ids, section in ordered_selected
    ]
    source_span_ids = list(
        dict.fromkeys(span_id for chunk in chunks for span_id in chunk["span_ids"])
    )
    fallback_needed = not chunks
    safe_record(diagnostics, "record_packing", eligible_chunks=len(eligible_chunk_ids),
                packed_chunks=len(chunks), size_excluded_chunks=len(size_excluded_chunk_ids),
                packed_characters=total_chars, character_limit=max_evidence_chars)

    return {
        "strategy": "fulltext_fallback" if fallback_needed else "hybrid",
        "embedding_config_id": config_id,
        "criteria_retrieval_map": criterion_retrievals,
        "packed_chunks_count": len(chunks),
        "total_evidence_characters": total_chars,
        "size_excluded_chunks": len(size_excluded_chunk_ids),
        "fallback_needed": fallback_needed,
        "chunks": chunks,
        "source_span_ids": source_span_ids,
    }
