"""Hybrid Retrieval service for Task B16: Dense pgvector cosine + Lexical search + RRF fusion."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import RetrievalChunk, SanitizedVersion
from app.services.embedding import EMBEDDING_CONFIG_ID, embed_texts


@dataclass
class RetrievedChunkScore:
    chunk_id: uuid.UUID
    chunk_index: int
    text: str
    span_ids: list[str]
    dense_rank: Optional[int]
    lexical_rank: Optional[int]
    rrf_score: float


async def hybrid_retrieve_for_criterion(
    db: AsyncSession,
    sanitized_version_id: uuid.UUID,
    criterion_name: str,
    criterion_description: str,
    top_k: int = 4,
) -> list[RetrievedChunkScore]:
    """Execute dense cosine search and lexical search on pgvector chunks, fusing results with RRF."""
    # 1. Prepare query embedding with 'query: ' prefix
    query_str = f"{criterion_name} {criterion_description}"
    query_vec = embed_texts([query_str], prefix="query: ")[0]

    # 2. Dense search via pgvector cosine distance (top 10)
    dense_stmt = (
        select(RetrievalChunk)
        .where(
            RetrievalChunk.sanitized_version_id == sanitized_version_id,
            RetrievalChunk.embedding_config_id == EMBEDDING_CONFIG_ID,
        )
        .order_by(RetrievalChunk.embedding.cosine_distance(query_vec))
        .limit(10)
    )
    dense_res = (await db.execute(dense_stmt)).scalars().all()
    dense_rank_map = {chunk.id: idx + 1 for idx, chunk in enumerate(dense_res)}

    # 3. Lexical search with PostgreSQL simple full-text ranking (top 10).
    # Technical tokens such as FastAPI and PostgreSQL remain searchable without
    # language-specific stemming. Restrict scope before ranking.
    keywords = [w for w in re.findall(r"\w+", query_str.lower()) if len(w) > 2]
    lexical_rank_map: dict[uuid.UUID, int] = {}
    all_chunks_by_id = {c.id: c for c in dense_res}

    if keywords:
        vector = func.to_tsvector("simple", RetrievalChunk.text)
        query = func.to_tsquery("simple", " | ".join(keywords[:8]))
        lex_stmt = (
            select(RetrievalChunk)
            .where(
                RetrievalChunk.sanitized_version_id == sanitized_version_id,
                RetrievalChunk.embedding_config_id == EMBEDDING_CONFIG_ID,
                vector.op("@@")(query),
            )
            .order_by(func.ts_rank_cd(vector, query).desc(), RetrievalChunk.chunk_index.asc())
            .limit(10)
        )
        lex_res = (await db.execute(lex_stmt)).scalars().all()
        for idx, chunk in enumerate(lex_res):
            lexical_rank_map[chunk.id] = idx + 1
            if chunk.id not in all_chunks_by_id:
                all_chunks_by_id[chunk.id] = chunk

    # 4. RRF (Reciprocal Rank Fusion): score = sum(1 / (60 + rank))
    scores: list[RetrievedChunkScore] = []
    for c_id, chunk in all_chunks_by_id.items():
        d_rank = dense_rank_map.get(c_id)
        l_rank = lexical_rank_map.get(c_id)

        rrf = 0.0
        if d_rank is not None:
            rrf += 1.0 / (60.0 + d_rank)
        if l_rank is not None:
            rrf += 1.0 / (60.0 + l_rank)

        scores.append(
            RetrievedChunkScore(
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                span_ids=chunk.span_ids,
                dense_rank=d_rank,
                lexical_rank=l_rank,
                rrf_score=rrf,
            )
        )

    # 5. Deterministic tie-breaking: RRF descending, then chunk_index ascending
    scores.sort(key=lambda s: (-s.rrf_score, s.chunk_index))
    return scores[:top_k]


async def build_hybrid_assessment_pack(
    db: AsyncSession,
    sanitized_version_id: uuid.UUID,
    criteria: list[dict[str, Any]],
    max_evidence_chars: int = 24000,  # ~6000-8000 tokens
) -> dict[str, Any]:
    """Build a deterministic hybrid retrieval assessment pack across all rubric criteria.
    
    Includes RRF scores, candidate span IDs, and fallback detection.
    """
    criterion_retrievals: dict[str, list[dict[str, Any]]] = {}
    selected_chunk_ids = set()
    unique_chunks = []
    total_chars = 0

    for crit in criteria:
        c_id = crit.get("id") or crit.get("name", "unknown")
        c_name = crit.get("name", "")
        c_desc = crit.get("description", "")

        matches = await hybrid_retrieve_for_criterion(
            db, sanitized_version_id, c_name, c_desc, top_k=4
        )

        crit_matches = []
        for m in matches:
            crit_matches.append({
                "chunk_id": str(m.chunk_id),
                "chunk_index": m.chunk_index,
                "span_ids": m.span_ids,
                "dense_rank": m.dense_rank,
                "lexical_rank": m.lexical_rank,
                "rrf_score": round(m.rrf_score, 5),
            })
            if m.chunk_id not in selected_chunk_ids:
                selected_chunk_ids.add(m.chunk_id)
                unique_chunks.append(m)
                total_chars += len(m.text)

        criterion_retrievals[c_id] = crit_matches

    # Sort gathered chunks chronologically by chunk_index to preserve narrative flow
    unique_chunks.sort(key=lambda c: c.chunk_index)

    # Check if fallback to fulltext is needed (e.g. no chunks found at all)
    fallback_needed = len(unique_chunks) == 0

    return {
        "strategy": "hybrid" if not fallback_needed else "fulltext_fallback",
        "embedding_config_id": EMBEDDING_CONFIG_ID,
        "criteria_retrieval_map": criterion_retrievals,
        "packed_chunks_count": len(unique_chunks),
        "total_evidence_characters": total_chars,
        "fallback_needed": fallback_needed,
        "chunks": [
            {
                "chunk_id": str(c.chunk_id),
                "chunk_index": c.chunk_index,
                "text": c.text,
                "span_ids": c.span_ids,
            }
            for c in unique_chunks
        ],
    }
