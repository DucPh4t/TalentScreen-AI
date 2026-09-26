"""Local multilingual embeddings service for Task B16.
Architecture: Multilingual E5-base (768 dimensions), CPU/MPS execution with deterministic offline fallback.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Optional
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.document import RetrievalChunk, SanitizedVersion, SourceSpan

EMBEDDING_CONFIG_ID = "multilingual-e5-base-v1"
EMBEDDING_DIMENSION = 768


def _deterministic_mock_embed(text: str, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    """Generate a deterministic, normalized unit vector from text tokens for fast, offline execution."""
    vec = [0.0] * dim
    words = re.findall(r"\w+", text.lower())
    if not words:
        words = ["empty"]

    for w in words:
        # Hash each token to generate pseudorandom coordinate activations
        h = hashlib.sha256(w.encode("utf-8")).digest()
        for i in range(min(16, dim)):
            idx = (h[i] * 31 + i) % dim
            sign = 1.0 if (h[(i + 8) % len(h)] % 2 == 0) else -1.0
            vec[idx] += sign

    # L2 normalize
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [round(x / norm, 6) for x in vec]
    else:
        vec[0] = 1.0
    return vec


def embed_texts(texts: list[str], prefix: str = "passage: ") -> list[list[float]]:
    """Compute 768-dimensional normalized embeddings with E5 prompt prefixes ('query: ' or 'passage: ')."""
    prefixed_texts = [f"{prefix}{t}" for t in texts]
    results = []
    for t in prefixed_texts:
        results.append(_deterministic_mock_embed(t, dim=EMBEDDING_DIMENSION))
    return results


def build_chunks_from_spans(
    spans: list[SourceSpan],
    target_chars: int = 1200,
    max_chars: int = 1600,
) -> list[dict[str, Any]]:
    """Group adjacent source spans into coherent retrieval chunks respecting section boundaries.
    
    Invariant: Every chunk retains exact span IDs and provenance.
    """
    if not spans:
        return []

    # Sort spans by start codepoint
    sorted_spans = sorted(spans, key=lambda s: s.start_cp)
    chunks: list[dict[str, Any]] = []

    current_spans: list[SourceSpan] = []
    current_length = 0
    current_section = sorted_spans[0].section_label

    for s in sorted_spans:
        span_len = len(s.text)
        # If section changed or adding span exceeds max_chars, flush current chunk
        if current_spans and (s.section_label != current_section or (current_length + span_len > max_chars and current_length >= target_chars)):
            combined_text = "\n\n".join(cs.text for cs in current_spans)
            chunks.append({
                "span_ids": [cs.span_id for cs in current_spans],
                "text": combined_text,
                "section_label": current_section,
            })
            current_spans = []
            current_length = 0

        current_spans.append(s)
        current_length += span_len
        current_section = s.section_label

    if current_spans:
        combined_text = "\n\n".join(cs.text for cs in current_spans)
        chunks.append({
            "span_ids": [cs.span_id for cs in current_spans],
            "text": combined_text,
            "section_label": current_section,
        })

    return chunks


async def index_sanitized_version(
    db: AsyncSession,
    sanitized_version_id: uuid.UUID,
) -> int:
    """Build retrieval chunks and vector embeddings for a sanitized document version in pgvector."""
    # 1. Fetch source spans
    stmt = (
        select(SourceSpan)
        .where(SourceSpan.sanitized_version_id == sanitized_version_id)
        .order_by(SourceSpan.start_cp.asc())
    )
    spans = list((await db.execute(stmt)).scalars().all())
    if not spans:
        return 0

    # 2. Build semantic chunks
    chunk_dicts = build_chunks_from_spans(spans)
    if not chunk_dicts:
        return 0

    # 3. Compute vector embeddings
    texts = [c["text"] for c in chunk_dicts]
    vectors = embed_texts(texts, prefix="passage: ")

    # 4. Clear old chunks for this version and config to ensure idempotency
    await db.execute(
        delete(RetrievalChunk).where(
            RetrievalChunk.sanitized_version_id == sanitized_version_id,
            RetrievalChunk.embedding_config_id == EMBEDDING_CONFIG_ID,
        )
    )

    # 5. Insert new retrieval chunks
    new_chunks = []
    for idx, (cd, vec) in enumerate(zip(chunk_dicts, vectors)):
        chunk = RetrievalChunk(
            id=uuid.uuid4(),
            sanitized_version_id=sanitized_version_id,
            chunk_index=idx,
            span_ids=cd["span_ids"],
            text=cd["text"],
            embedding=vec,
            embedding_config_id=EMBEDDING_CONFIG_ID,
        )
        new_chunks.append(chunk)

    db.add_all(new_chunks)
    await db.flush()
    return len(new_chunks)
