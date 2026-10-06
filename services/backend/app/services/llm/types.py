"""Typed request and response models for LLM completion tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal, Optional

_TOOL_CALL_ID_RE = re.compile(r"^call_[A-Za-z0-9_-]{1,124}$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


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
    thinking_mode: Optional[Literal["enabled", "disabled"]] = None
    messages: Optional[list[dict[str, Any]]] = None
    tools: Optional[list[dict[str, Any]]] = None
    tool_choice: Optional[str | dict[str, Any]] = None
    manifest_id: Optional[str] = None
    provider: Literal["deepseek", "jev"] = "deepseek"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _TOOL_CALL_ID_RE.fullmatch(self.id):
            raise ValueError("ToolCall id is malformed.")
        if not isinstance(self.name, str) or not _TOOL_NAME_RE.fullmatch(self.name):
            raise ValueError("ToolCall name is malformed.")
        if not isinstance(self.arguments, dict):
            raise ValueError("ToolCall arguments must be a JSON object.")


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
    tool_calls: list[ToolCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.content is not None and not isinstance(self.content, str):
            raise ValueError("Completion content must be text or None.")
        if not isinstance(self.tool_calls, list) or any(not isinstance(call, ToolCall) for call in self.tool_calls):
            raise ValueError("Completion tool_calls must contain validated ToolCall values.")
        if not self.content or not self.content.strip():
            if not self.tool_calls:
                raise ValueError("A completion must contain content or at least one valid tool call.")
