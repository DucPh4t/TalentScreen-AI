"""Developer-only LangSmith spans. Never export graph state, CVs, prompts or responses.

Manual RunTree spans deliberately suppress LangGraph's automatic tracing, which
would otherwise serialize the entire candidate-derived state at every node.
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
import inspect
import logging
import math
import re
from typing import Any, Callable, Iterator
import uuid

from langsmith import Client, RunTree
from langsmith.run_helpers import tracing_context

from app.config import get_settings

logger = logging.getLogger(__name__)
NODES = frozenset({"authorize", "model", "tools", "validate", "repair"})
OUTCOMES = frozenset({"running", "completed", "succeeded", "validated", "failed", "blocked",
    "validation_rejected", "insufficient_evidence"})
ERROR_CODES = frozenset({"TRACE_STEP_FAILED", "TRACE_CANCELLED", "ASSESSMENT_OUTPUT_INVALID",
    "ASSESSMENT_INPUT_STALE", "APPLICATION_TOMBSTONED", "AGENT_MODEL_ROUND_LIMIT",
    "AGENT_TOOL_LIMIT", "AGENT_TOOL_SCOPE_REJECTED", "AGENT_UNAUTHORIZED_TOOL_CALL",
    "HYBRID_RETRIEVAL_FAILED", "HYBRID_RETRIEVAL_PROVENANCE_INVALID",
    "ASSESSMENT_PROMPT_VERSION_UNKNOWN", "ASSESSMENT_RETRIEVAL_STRATEGY_UNKNOWN",
    "ASSESSMENT_CONTEXT_LIMIT", "PreconditionViolationError", "BudgetExceededError",
    "LLMAuthenticationError", "LLMQuotaExhaustedError", "LLMModelUnavailableError",
    "LLMProviderError", "LLMTimeoutError", "LLMTruncatedError", "LLMEmptyResponseError",
    "LLMMalformedJSONError", "LLMRefusalError", "AgentToolError",
    "JEV_RERANK_FAILED", "RERANK_POLICY_INVALID", "RERANK_BOUND_EXCLUDED", "RERANK_RECONCILIATION_REQUIRED"})
COUNTERS = frozenset({"model_round_trips", "tool_execution_count", "repair_count", "criterion_count",
    "result_criterion_count", "result_count", "source_span_count", "tool_call_count",
    "input_tokens", "output_tokens", "total_tokens", "validation_error_count", "attempt_no",
    "max_output_tokens", "external_call_count", "provider_latency_ms", "cached_input_tokens",
    "rejected_citations", "citation_malformed", "citation_unknown_span", "citation_out_of_scope",
    "citation_quote_mismatch", "normalized_criteria", "schema_failures", "rerank_elapsed_ms", "omitted_count"})
UUID_FIELDS = frozenset({"assessment_run_id", "job_id", "jd_version_id", "experiment_id"})
ENUMS = {
    "rerank_mode": {"off", "shadow", "rerank", "gate_experiment"},
    "rerank_policy_version": {"jev-evidence-ranking.v1"},
    "benchmark_profile": {"full_text", "dense", "hybrid", "hybrid_agent"},
    "node": NODES, "outcome": OUTCOMES, "error_code": ERROR_CODES,
    "retrieval_strategy": {"hybrid", "full_text_baseline"},
    "provider": {"mock", "deepseek", "jev", "custom"},
    "ls_provider": {"mock", "deepseek", "jev", "custom"},
    "task_kind": {"assessment", "rubric", "interview", "repair"},
}
_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./_-]{0,99}\Z")
_PROMPT_RE = re.compile(r"(?:(?:assessment|rubric|interview)(?:[-.]agent)?|jd-competencies)[-.]v[0-9.]{1,20}\Z")


def safe_metadata(values: dict[str, Any]) -> dict[str, Any]:
    """Allow known enums/counts and opaque correlation IDs; reject arbitrary strings."""
    result: dict[str, Any] = {}
    for key, value in values.items():
        if key in ENUMS and isinstance(value, str) and value in ENUMS[key]:
            result[key] = value
        elif key == 'case_id_sha256' and isinstance(value,str) and re.fullmatch(r'[0-9a-f]{64}',value):
            result[key]=value
        elif key in COUNTERS and type(value) is int and 0 <= value <= 100_000_000:
            result[key] = value
        elif key in UUID_FIELDS:
            try:
                result[key] = str(uuid.UUID(str(value)))
            except (ValueError, TypeError, AttributeError):
                pass
        elif key in {"model", "ls_model_name"} and isinstance(value, str) and _LABEL_RE.fullmatch(value):
            if not value.lower().startswith(("sk-", "lsv2_", "ls__", "bearer")):
                result[key] = value
        elif key in {"agent_prompt_version", "assessment_prompt_version", "rubric_prompt_version"}:
            if isinstance(value, str) and _PROMPT_RE.fullmatch(value):
                result[key] = value
        elif key == "cost_actual_usd" and type(value) in (int, float) and math.isfinite(value) and value >= 0:
            result[key] = value
        elif key == "usage_metadata" and isinstance(value, dict):
            usage = {name: count for name, count in value.items()
                if name in {"input_tokens", "output_tokens", "total_tokens"}
                and type(count) is int and 0 <= count <= 100_000_000}
            if usage:
                result[key] = usage
    return result


def _export_failed(_exc: Exception | None = None) -> None:
    # Exception messages and stacks can contain provider bodies or candidate data.
    logger.warning("LANGSMITH_EXPORT_FAILED: assessment continues without telemetry")


@lru_cache(maxsize=1)
def _get_client(endpoint: str, api_key: str) -> Client:
    return Client(api_url=endpoint, api_key=api_key, auto_batch_tracing=True,
        hide_inputs=True, hide_outputs=True, omit_traced_runtime_info=True,
        timeout_ms=1000, tracing_error_callback=_export_failed, tracing_mode="langsmith")


class TraceSpan:
    def __init__(self, run: RunTree | None):
        self._run = run
        self._metadata: dict[str, Any] = {}

    @property
    def run_id(self) -> str | None:
        return str(self._run.id) if self._run else None

    def record(self, metadata: dict[str, Any]) -> None:
        self._metadata.update(safe_metadata(metadata))

    def _finish(self) -> None:
        if self._run is None:
            return
        metadata = dict(self._metadata)
        metadata.setdefault("outcome", "completed")
        error = None
        if metadata["outcome"] in {"failed", "blocked", "validation_rejected"}:
            error = metadata.get("error_code", "TRACE_STEP_FAILED")
        try:
            self._run.end(outputs={}, error=error, metadata=metadata)
            self._run.patch(exclude_inputs=True)
        except Exception:
            _export_failed()


_current_span: ContextVar[TraceSpan | None] = ContextVar("talentscreen_trace_span", default=None)


@contextmanager
def trace_span(name: str, *, run_type: str = "chain", metadata: dict[str, Any] | None = None) -> Iterator[TraceSpan]:
    """Export only explicitly supplied metadata; telemetry failures never escape.

    Never pass user text as the name. Names are fixed in source at each call site.
    Automatic tracing is disabled even when an SDK tracing env flag is enabled.
    """
    with tracing_context(enabled=False, parent=False, replicas=[]):
        run = None
        parent = _current_span.get()
        filtered = safe_metadata(metadata or {})
        try:
            settings = get_settings()
            if settings.LANGSMITH_TRACING and (parent is None or parent._run is not None):
                if parent is not None:
                    run = parent._run.create_child(name=name, run_type=run_type, inputs={},
                        extra={"metadata": filtered})
                else:
                    run = RunTree(name=name, run_type=run_type, inputs={},
                        project_name=settings.LANGSMITH_PROJECT, tags=["talentscreen", "metadata-only"],
                        extra={"metadata": filtered}, replicas=[],
                        ls_client=_get_client(settings.LANGSMITH_ENDPOINT, settings.LANGSMITH_API_KEY))
                run.post()
        except Exception:
            run = None
            _export_failed()
        span = TraceSpan(run)
        span.record(filtered)
        token = _current_span.set(span)
        try:
            yield span
        except BaseException as exc:
            code = "TRACE_CANCELLED" if isinstance(exc, asyncio.CancelledError) else getattr(exc, "code", type(exc).__name__)
            if not isinstance(code, str) or code not in ERROR_CODES:
                code = "TRACE_STEP_FAILED"
            span.record({"outcome": "failed", "error_code": code})
            raise
        finally:
            _current_span.reset(token)
            span._finish()


def record_trace_metadata(metadata: dict[str, Any]) -> None:
    span = _current_span.get()
    if span is not None:
        span.record(metadata)


def observed(name: str, *, run_type: str = "chain",
    input_metadata: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    result_metadata: Callable[[Any], dict[str, Any]] | None = None):
    """Observe an async operation without ever sending arguments or return values."""
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        async def wrapper(*args, **kwargs):
            metadata = {}
            if input_metadata is not None:
                try:
                    bound = signature.bind(*args, **kwargs)
                    bound.apply_defaults()
                    metadata = input_metadata(bound.arguments)
                except Exception:
                    _export_failed()
            with trace_span(name, run_type=run_type, metadata=metadata) as span:
                result = await function(*args, **kwargs)
                if result_metadata is not None:
                    try:
                        span.record(result_metadata(result))
                    except Exception:
                        _export_failed()
                return result
        return wrapper
    return decorate


def observe_node(name: str, function):
    """Record actual graph invocations, including validation rejection and loops."""
    def result_metadata(update):
        metadata = dict(update.get("trace") or {})
        metadata.update({"node": name, "outcome": "completed"})
        if update.get("error_code"):
            metadata.update(outcome="failed", error_code=update["error_code"])
        elif update.get("validation_errors"):
            metadata.update(outcome="validation_rejected", error_code="ASSESSMENT_OUTPUT_INVALID",
                validation_error_count=len(update["validation_errors"]))
        elif name == "validate" and update.get("output") is not None:
            metadata["outcome"] = "validated"
        return metadata
    return observed(name, input_metadata=lambda args: {"node": name,
        "model_round_trips": args["current"].get("model_round_trips", 0),
        "repair_count": args["current"].get("repair_count", 0)}, result_metadata=result_metadata)(function)
