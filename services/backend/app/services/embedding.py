"""Cached local multilingual E5 embeddings and provenance-preserving chunks."""
from __future__ import annotations

import hashlib
import math
import platform
import re
import threading
import uuid
from functools import lru_cache
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.document import RetrievalChunk, SourceSpan

EMBEDDING_DIMENSION = 768
CHUNK_FORMAT_VERSION = "section-token-v1"
settings = get_settings()
EMBEDDING_CONFIG_ID = (
    f"{settings.EMBEDDING_MODEL}@{settings.EMBEDDING_MODEL_REVISION}:{CHUNK_FORMAT_VERSION}"
)
if len(EMBEDDING_CONFIG_ID) > 100:
    raise ValueError("EMBEDDING_CONFIG_ID exceeds the database column limit")


class EmbeddingError(RuntimeError):
    """Base class for local embedding failures; callers must fail closed."""


class EmbeddingDeviceError(EmbeddingError):
    """Raised when an explicitly requested accelerator is not available."""


class EmbeddingModelUnavailableError(EmbeddingError):
    """Raised when the configured local sentence-transformer cannot be loaded."""


class EmbeddingOutputError(EmbeddingError):
    """Raised when the encoder returns malformed or non-finite vectors."""


def _deterministic_mock_embed(text: str, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    """Deterministic test double; this helper is never used by the runtime path."""
    vector = [0.0] * dim
    words = re.findall(r"\w+", text.lower()) or ["empty"]
    for word in words:
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        for index in range(min(16, dim)):
            coordinate = (digest[index] * 31 + index) % dim
            sign = 1.0 if digest[(index + 8) % len(digest)] % 2 == 0 else -1.0
            vector[coordinate] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]


_MODEL_LOAD_LOCK = threading.Lock()


def _resolve_device(requested: str) -> str:
    normalized = requested.strip().lower()
    if normalized == "cpu":
        return "cpu"

    try:
        import torch
    except Exception as exc:
        if normalized == "auto":
            return "cpu"
        raise EmbeddingDeviceError(
            f"Embedding device {requested!r} requested but PyTorch is unavailable"
        ) from exc

    mps_available = bool(
        getattr(getattr(torch, "backends", None), "mps", None)
        and torch.backends.mps.is_available()
    )
    cuda_available = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())

    if normalized == "auto":
        if platform.system() == "Darwin" and mps_available:
            return "mps"
        return "cpu"
    if normalized == "mps":
        if platform.system() != "Darwin" or not mps_available:
            raise EmbeddingDeviceError("MPS was requested but is not available on this host")
        return "mps"
    if normalized == "cuda" or normalized.startswith("cuda:"):
        if not cuda_available:
            raise EmbeddingDeviceError("CUDA was requested but is not available on this host")
        return normalized
    raise EmbeddingDeviceError("EMBEDDING_DEVICE must be auto, cpu, mps, or cuda[:index]")


@lru_cache(maxsize=4)
def _load_embedding_model(model_name: str, revision: str, device: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:
        raise EmbeddingModelUnavailableError(
            "sentence-transformers is required for the configured hybrid RAG model"
        ) from exc

    try:
        return SentenceTransformer(model_name, revision=revision, device=device)
    except Exception as exc:
        raise EmbeddingModelUnavailableError(
            f"Could not load embedding model {model_name}@{revision} on {device}"
        ) from exc


def _get_embedding_model() -> Any:
    config = get_settings()
    device = _resolve_device(config.EMBEDDING_DEVICE)
    # functools.lru_cache is safe for concurrent reads, but may evaluate the
    # wrapped function more than once on concurrent misses. The lock prevents
    # multiple expensive model loads in a worker process.
    with _MODEL_LOAD_LOCK:
        return _load_embedding_model(
            config.EMBEDDING_MODEL,
            config.EMBEDDING_MODEL_REVISION,
            device,
        )


def _normalise_vectors(encoded: Any, expected_count: int) -> list[list[float]]:
    if hasattr(encoded, "tolist"):
        encoded = encoded.tolist()
    try:
        rows = list(encoded)
    except TypeError as exc:
        raise EmbeddingOutputError("Embedding model returned a non-iterable result") from exc
    if len(rows) != expected_count:
        raise EmbeddingOutputError("Embedding model returned an unexpected vector count")

    vectors: list[list[float]] = []
    for row in rows:
        if hasattr(row, "tolist"):
            row = row.tolist()
        try:
            vector = [float(value) for value in row]
        except (TypeError, ValueError) as exc:
            raise EmbeddingOutputError("Embedding model returned a malformed vector") from exc
        if len(vector) != EMBEDDING_DIMENSION:
            raise EmbeddingOutputError(
                f"Embedding model must return {EMBEDDING_DIMENSION}-dimensional vectors"
            )
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingOutputError("Embedding model returned a non-finite vector")
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            raise EmbeddingOutputError("Embedding model returned a zero vector")
        vectors.append([value / norm for value in vector])
    return vectors


def embed_texts(texts: list[str], prefix: str = "passage: ") -> list[list[float]]:
    """Embed text with E5's required query/passage prefix and normalized 768d output."""
    if prefix not in {"query: ", "passage: "}:
        raise ValueError("E5 prefix must be exactly 'query: ' or 'passage: '")
    if not texts:
        return []

    model = _get_embedding_model()
    prefixed_texts = [f"{prefix}{text}" for text in texts]
    try:
        encoded = model.encode(
            prefixed_texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except Exception as exc:
        raise EmbeddingError("Local embedding inference failed") from exc
    return _normalise_vectors(encoded, expected_count=len(prefixed_texts))


def _token_count_fn(model: Any) -> Callable[[str], int]:
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None or not callable(getattr(tokenizer, "encode", None)):
        raise EmbeddingModelUnavailableError(
            "Configured sentence-transformer does not expose its tokenizer"
        )

    def count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return count


def _split_text_at_token_limit(
    text: str,
    token_count: Callable[[str], int],
    max_tokens: int,
) -> list[str]:
    """Split an oversized span into exact adjacent substrings within the token limit."""
    if token_count(text) <= max_tokens:
        return [text]

    pieces: list[str] = []
    current = ""
    # Keep whitespace attached to neighboring source text so concatenating the
    # returned pieces recreates the original span byte-for-byte.
    atoms = re.findall(r"\s+|\S+\s*", text)
    for atom in atoms:
        candidate = current + atom
        if token_count(candidate) <= max_tokens:
            current = candidate
            continue

        if current:
            pieces.append(current)
            current = ""

        if token_count(atom) <= max_tokens:
            current = atom
            continue

        offset = 0
        while offset < len(atom):
            low, high, best = offset + 1, len(atom), offset
            while low <= high:
                middle = (low + high) // 2
                if token_count(atom[offset:middle]) <= max_tokens:
                    best = middle
                    low = middle + 1
                else:
                    high = middle - 1
            if best == offset:
                raise ValueError("Token counter cannot split one source character under the limit")
            pieces.append(atom[offset:best])
            offset = best

    if current:
        pieces.append(current)
    if not pieces or "".join(pieces) != text:
        raise AssertionError("Chunk splitting must preserve the exact source text")
    if any(token_count(piece) > max_tokens for piece in pieces):
        raise AssertionError("Chunk splitter emitted a piece above max_tokens")
    return pieces


def build_chunks_from_spans(
    spans: list[SourceSpan],
    token_count: Callable[[str], int],
    target_tokens: int = 300,
    max_tokens: int = 480,
) -> list[dict[str, Any]]:
    """Group adjacent spans into section-local chunks, splitting long spans losslessly."""
    if target_tokens <= 0 or max_tokens <= 0 or target_tokens > max_tokens:
        raise ValueError("Require 0 < target_tokens <= max_tokens")
    if not spans:
        return []

    sorted_spans = sorted(spans, key=lambda span: (span.start_cp, span.end_cp, span.span_id))
    chunks: list[dict[str, Any]] = []
    current_text = ""
    current_span_ids: list[str] = []
    current_section: str | None = None

    def flush() -> None:
        nonlocal current_text, current_span_ids, current_section
        if current_span_ids:
            chunks.append({
                "span_ids": current_span_ids,
                "text": current_text,
                "section_label": current_section,
            })
        current_text = ""
        current_span_ids = []
        current_section = None

    for span in sorted_spans:
        section = span.section_label
        if current_span_ids and section != current_section:
            flush()

        span_parts = _split_text_at_token_limit(span.text, token_count, max_tokens)
        if len(span_parts) > 1:
            flush()
            for part in span_parts:
                chunks.append({
                    "span_ids": [span.span_id],
                    "text": part,
                    "section_label": section,
                })
            continue

        span_text = span_parts[0]
        candidate = f"{current_text}\n\n{span_text}" if current_span_ids else span_text
        if current_span_ids and token_count(candidate) > target_tokens:
            flush()
            candidate = span_text
        if current_span_ids and token_count(candidate) > max_tokens:
            flush()
            candidate = span_text

        if not current_span_ids:
            current_section = section
        current_text = candidate
        current_span_ids.append(span.span_id)

    flush()
    return chunks


async def index_sanitized_version(
    db: AsyncSession,
    sanitized_version_id: uuid.UUID,
) -> int:
    """Index approved source spans with the pinned local E5 model in pgvector."""
    stmt = (
        select(SourceSpan)
        .where(SourceSpan.sanitized_version_id == sanitized_version_id)
        .order_by(SourceSpan.start_cp.asc())
    )
    spans = list((await db.execute(stmt)).scalars().all())
    if not spans:
        return 0

    model = _get_embedding_model()
    chunk_dicts = build_chunks_from_spans(
        spans,
        token_count=_token_count_fn(model),
        target_tokens=300,
        max_tokens=480,
    )
    if not chunk_dicts:
        return 0

    texts = [chunk["text"] for chunk in chunk_dicts]
    vectors = embed_texts(texts, prefix="passage: ")

    await db.execute(
        delete(RetrievalChunk).where(
            RetrievalChunk.sanitized_version_id == sanitized_version_id,
            RetrievalChunk.embedding_config_id == EMBEDDING_CONFIG_ID,
        )
    )

    new_chunks = [
        RetrievalChunk(
            id=uuid.uuid4(),
            sanitized_version_id=sanitized_version_id,
            chunk_index=index,
            span_ids=chunk["span_ids"],
            text=chunk["text"],
            embedding=vector,
            embedding_config_id=EMBEDDING_CONFIG_ID,
        )
        for index, (chunk, vector) in enumerate(zip(chunk_dicts, vectors, strict=True))
    ]
    db.add_all(new_chunks)
    await db.flush()
    return len(new_chunks)
