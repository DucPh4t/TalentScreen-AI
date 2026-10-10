"""Typed request and response models for LLM completion tasks."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from decimal import Decimal
import uuid
from app.services.evaluation.benchmark.contracts import InputBound
from typing import Any, Literal, Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.llm.call_policy import JevReservationPolicy

_TOOL_CALL_ID_RE = re.compile(r"^call_[A-Za-z0-9_-]{1,124}$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class StrictReservationPolicy:
    budget_period_id: uuid.UUID
    cap_usd: Decimal
    bound: InputBound
    requested_model: str

    def __post_init__(self):
        if (not isinstance(self.budget_period_id,uuid.UUID) or not self.cap_usd.is_finite()
            or not Decimal(0)<self.cap_usd<=Decimal(5) or self.requested_model not in {'deepseek-flash','mock'}):
            raise ValueError("STRICT_RESERVATION_POLICY_INVALID")

    @property
    def accepted_reported_models(self):
        return {'deepseek-flash','deepseek-v4.1-flash'} if self.requested_model=='deepseek-flash' else {'mock'}

    def input_reservation_tokens(self,request: CompletionRequest) -> int:
        from app.services.llm.orchestrator import PreconditionViolationError,_serialized_request_payload
        import json
        if request.model!=self.requested_model or type(request.max_output_tokens) is not int or not 1<=request.max_output_tokens<=4096 or request.temperature!=0 or request.provider!='deepseek':
            raise PreconditionViolationError("BENCHMARK_REQUEST_POLICY_MISMATCH")
        serialized=_serialized_request_payload(request)
        if self.bound.max_serialized_bytes is not None:
            if len(serialized.encode())>self.bound.max_serialized_bytes:
                raise PreconditionViolationError("BENCHMARK_REQUEST_BYTE_LIMIT")
            messages=request.messages if request.messages is not None else [
                {'role':'system','content':request.system_prompt},{'role':'user','content':request.user_prompt}]
            if not 1<=len(messages)<=8:
                raise PreconditionViolationError("BENCHMARK_REQUEST_FRAMING_LIMIT")
            calls=[]
            for message in messages:
                if message.get('role') not in {'system','user','assistant','tool'} or not isinstance(message.get('content'),(str,type(None))):
                    raise PreconditionViolationError("BENCHMARK_REQUEST_FRAMING_LIMIT")
                calls.extend(message.get('tool_calls') or [])
            if len(calls)>2 or len(request.tools or [])>2:
                raise PreconditionViolationError("BENCHMARK_REQUEST_FRAMING_LIMIT")
            params=0
            for call in calls:
                fn=call.get('function',{})
                args=json.loads(fn['arguments'])
                if fn.get('name') not in {'retrieve_more_evidence','get_source_spans'} or not isinstance(args,dict):
                    raise PreconditionViolationError("BENCHMARK_REQUEST_FRAMING_LIMIT")
                if set(args)-{'criterion_ids','query_hint','span_ids'}:
                    raise PreconditionViolationError("BENCHMARK_REQUEST_FRAMING_LIMIT")
                params+=len(args)
            schema=json.dumps(request.tools or [],ensure_ascii=False)
            if params>4 or schema.count(',')+schema.count(':')>512:
                raise PreconditionViolationError("BENCHMARK_REQUEST_FRAMING_LIMIT")
        return self.bound.max_input_tokens


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
    strict_reservation_policy: Optional[StrictReservationPolicy] = None
    purpose: Literal['primary', 'jev_secondary', 'jev_rerank', 'jev_primary', 'jev_primary_explanation'] | None = None
    jev_reservation_policy: 'JevReservationPolicy | None' = None


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
    cached_input_tokens: Optional[int] = None
    provider_request_id: Optional[str] = None
    latency_ms: int = 0
    raw_response: Optional[dict[str, Any]] = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    def __post_init__(self) -> None:
        for tokens in (self.input_tokens,self.output_tokens,self.cached_input_tokens):
            if tokens is not None and (type(tokens) is not int or tokens<0):
                raise ValueError("Completion token usage is invalid.")
        if self.cached_input_tokens is not None and (self.input_tokens is None or self.cached_input_tokens>self.input_tokens):
            raise ValueError("Completion cached usage exceeds input usage.")
        if self.content is not None and not isinstance(self.content, str):
            raise ValueError("Completion content must be text or None.")
        if not isinstance(self.tool_calls, list) or any(not isinstance(call, ToolCall) for call in self.tool_calls):
            raise ValueError("Completion tool_calls must contain validated ToolCall values.")
        if not self.content or not self.content.strip():
            if not self.tool_calls:
                raise ValueError("A completion must contain content or at least one valid tool call.")
