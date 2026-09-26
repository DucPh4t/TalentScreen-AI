"""Typed request and response models for LLM completion tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class CompletionRequest:
    task_kind: Literal["rubric", "assessment", "interview", "repair"]
    system_prompt: str
    user_prompt: str
    model: str = "deepseek-flash"
    max_output_tokens: int = 4096
    timeout_seconds: float = 30.0
    temperature: float = 0.0
    response_format: Optional[dict[str, str]] = field(default_factory=lambda: {"type": "json_object"})
    manifest_id: Optional[str] = None


@dataclass
class CompletionResult:
    content: Optional[str]
    requested_model: str
    reported_model: Optional[str] = None
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    provider_request_id: Optional[str] = None
    latency_ms: int = 0
    raw_response: Optional[dict[str, Any]] = None
