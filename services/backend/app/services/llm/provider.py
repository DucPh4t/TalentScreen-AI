"""LLM Provider interface, DeepSeek HTTPX adapter, and Mock provider with fault injection."""
from __future__ import annotations

import abc
import asyncio
import json
import logging
import time
from typing import Any, Optional
import httpx

from app.config import get_settings
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMMalformedJSONError,
    LLMModelUnavailableError,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMRateLimitError,
    LLMRefusalError,
    LLMServerError,
    LLMTimeoutError,
    LLMTruncatedError,
)
from app.services.llm.types import CompletionRequest, CompletionResult, ToolCall

logger = logging.getLogger(__name__)
MAX_TOOL_CALLS_PER_RESPONSE = 8
MAX_TOOL_ARGUMENT_NESTING = 64


def _reject_non_json_constant(_value: str) -> None:
    raise ValueError("Invalid JSON constant.")


def _has_excessive_json_nesting(value: str) -> bool:
    """Bound nesting before JSON decoding so hostile arguments stay cheap and predictable."""
    depth = 0
    in_string = False
    escaped = False
    for char in value:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_TOOL_ARGUMENT_NESTING:
                return True
        elif char in "]}":
            depth -= 1
    return False


def _parse_tool_calls(raw_tool_calls: Any) -> list[ToolCall]:
    """Parse OpenAI-compatible function calls without retaining malformed payload text."""
    if raw_tool_calls is None:
        return []
    if not isinstance(raw_tool_calls, list) or len(raw_tool_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
        raise LLMMalformedJSONError("DeepSeek returned malformed tool call data.")

    calls: list[ToolCall] = []
    seen_ids: set[str] = set()
    for raw_call in raw_tool_calls:
        if not isinstance(raw_call, dict):
            raise LLMMalformedJSONError("DeepSeek returned malformed tool call data.")
        call_id = raw_call.get("id")
        function = raw_call.get("function")
        if (
            not isinstance(call_id, str)
            or call_id in seen_ids
            or raw_call.get("type") != "function"
            or not isinstance(function, dict)
        ):
            raise LLMMalformedJSONError("DeepSeek returned malformed tool call data.")
        name = function.get("name")
        arguments_text = function.get("arguments")
        if (
            not isinstance(name, str)
            or not isinstance(arguments_text, str)
            or len(arguments_text) > 16_384
            or _has_excessive_json_nesting(arguments_text)
        ):
            raise LLMMalformedJSONError("DeepSeek returned malformed tool call data.")

        try:
            arguments = json.loads(arguments_text, parse_constant=_reject_non_json_constant)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise LLMMalformedJSONError("DeepSeek returned malformed tool call data.") from exc
        if not isinstance(arguments, dict):
            raise LLMMalformedJSONError("DeepSeek returned malformed tool call data.")

        try:
            tool_call = ToolCall(id=call_id, name=name, arguments=arguments)
        except ValueError as exc:
            raise LLMMalformedJSONError("DeepSeek returned malformed tool call data.") from exc
        seen_ids.add(call_id)
        calls.append(tool_call)
    return calls


class BaseLLMProvider(abc.ABC):
    """Abstract base provider for LLM completion requests."""

    @abc.abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Execute a completion request and return structured CompletionResult."""
        pass


class MockLLMProvider(BaseLLMProvider):
    """Mock provider with comprehensive fault injection support for unit & integration testing."""

    def __init__(
        self,
        fault_mode: str = "success",
        custom_content: Optional[str] = None,
        custom_tool_calls: Optional[list[ToolCall]] = None,
        latency_ms: int = 10,
    ):
        self.fault_mode = fault_mode
        self.custom_content = custom_content
        self.custom_tool_calls = custom_tool_calls or []
        self.latency_ms = latency_ms
        self.invocation_count = 0

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        self.invocation_count += 1
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000.0)

        if self.fault_mode == "401":
            raise LLMAuthenticationError("Mock 401: Unauthorized API key")
        elif self.fault_mode == "402":
            raise LLMQuotaExhaustedError("Mock 402: Insufficient account balance")
        elif self.fault_mode == "429":
            raise LLMRateLimitError("Mock 429: Rate limit exceeded")
        elif self.fault_mode == "500":
            raise LLMServerError("Mock 500: Provider internal error")
        elif self.fault_mode == "timeout":
            raise LLMTimeoutError("Mock Timeout: Request deadline exceeded")
        elif self.fault_mode == "refusal":
            raise LLMRefusalError("Mock Refusal: Content filter policy triggered")
        elif self.fault_mode == "truncated":
            raise LLMTruncatedError("Mock Truncated: Max tokens limit reached")
        elif self.fault_mode == "empty":
            raise LLMEmptyResponseError("Mock Empty: Response content was empty")
        elif self.fault_mode == "malformed_json":
            return CompletionResult(
                content="Not valid JSON at all {{{",
                requested_model=request.model,
                reported_model=request.model,
                finish_reason="stop",
                input_tokens=150,
                output_tokens=50,
                provider_request_id="mock_req_malformed",
                latency_ms=self.latency_ms,
            )

        # The default assessment response must honor the same strict contract as
        # a real provider. It deliberately assigns no scores or fabricated quotes.
        if self.custom_content is not None:
            content = self.custom_content
        elif request.task_kind == "interview":
            content = json.dumps({"followups": []})
        elif request.task_kind == "assessment":
            try:
                prompt_text = request.user_prompt
                if request.messages:
                    prompt_text = next(
                        (
                            message.get("content")
                            for message in reversed(request.messages)
                            if message.get("role") == "user"
                            and isinstance(message.get("content"), str)
                        ),
                        prompt_text,
                    )
                prompt_payload = json.loads(prompt_text)
            except (TypeError, ValueError):
                prompt_payload = {}
            rubric = prompt_payload.get("rubric", []) if isinstance(prompt_payload, dict) else []
            criterion_ids = [item["criterion_id"] for item in rubric if item.get("criterion_id")]
            # Generic mock calls used for adapter/ledger tests may not carry the
            # production assessment prompt envelope. Keep those calls schema-valid
            # while production requests continue to use the approved rubric IDs.
            if not criterion_ids:
                from app.domain.enums import CriterionId

                criterion_ids = [criterion.value for criterion in CriterionId]

            content = json.dumps({
                "criteria": [
                    {
                        "criterion_id": criterion_id,
                        "status": "insufficient_evidence",
                        "score": None,
                        "evidence": [],
                        "rationale": "Mock provider không đánh giá năng lực từ CV.",
                        "missing_information": ["Cần chạy đánh giá thật và người phụ trách kiểm tra bằng chứng."],
                    }
                    for criterion_id in criterion_ids
                ]
            })
        else:
            content = json.dumps({
                "status": "success",
                "message": "Mock completion response",
                "task": request.task_kind,
            })

        return CompletionResult(
            content=content,
            requested_model=request.model,
            reported_model=request.model,
            finish_reason="stop",
            input_tokens=200,
            output_tokens=100,
            provider_request_id=f"mock_req_{self.invocation_count}",
            latency_ms=self.latency_ms,
            tool_calls=list(self.custom_tool_calls),
        )


class DeepSeekHTTPXProvider(BaseLLMProvider):
    """Production adapter for DeepSeek API using HTTPX.
    Invariants:
      1. Secrets (API keys) are masked and never exposed in logs or errors.
      2. No silent model fallback.
      3. Accurately maps HTTP status, network errors, and finish reasons.
    """

    DEFAULT_API_URL = "https://api.deepseek.com/chat/completions"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self.api_url = api_url or f"{settings.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
        self._external_client = client

    def _mask_secret(self, text: str) -> str:
        """Ensure API key never leaks in exception strings."""
        if not self.api_key:
            return text
        return text.replace(self.api_key, "[REDACTED_API_KEY]")

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        if not self.api_key or self.api_key.startswith("sk-placeholder") or len(self.api_key) < 8:
            raise LLMAuthenticationError("DEEPSEEK_API_KEY is not configured or invalid.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages if request.messages is not None else [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.response_format:
            payload["response_format"] = request.response_format
        if request.thinking_mode is not None:
            payload["thinking"] = {"type": request.thinking_mode}
        if request.tools is not None:
            payload["tools"] = request.tools
        if request.tool_choice is not None:
            payload["tool_choice"] = request.tool_choice

        start_time = time.monotonic()
        client = self._external_client or httpx.AsyncClient(timeout=request.timeout_seconds)

        try:
            resp = await client.post(self.api_url, headers=headers, json=payload)
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(f"Network timeout contacting DeepSeek: {self._mask_secret(str(e))}")
        except httpx.RequestError as e:
            raise LLMServerError(f"Network error contacting DeepSeek: {self._mask_secret(str(e))}")
        finally:
            if not self._external_client:
                await client.aclose()

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

        # Map HTTP Status Codes
        if resp.status_code == 401:
            raise LLMAuthenticationError("DeepSeek returned 401: Invalid API Key")
        elif resp.status_code == 402:
            raise LLMQuotaExhaustedError("DeepSeek returned 402: Insufficient balance/credits")
        elif resp.status_code == 404:
            raise LLMModelUnavailableError(f"DeepSeek returned 404: Model '{request.model}' not found")
        elif resp.status_code == 429:
            raise LLMRateLimitError("DeepSeek returned 429: Rate limit exceeded")
        elif resp.status_code >= 500:
            raise LLMServerError(f"DeepSeek server error (HTTP {resp.status_code})")
        elif resp.status_code != 200:
            raise LLMProviderError(f"DeepSeek returned unexpected HTTP {resp.status_code}")

        try:
            body = resp.json()
        except Exception:
            raise LLMMalformedJSONError("Failed to parse DeepSeek response body as JSON.")
        if not isinstance(body, dict):
            raise LLMMalformedJSONError("DeepSeek response body must be a JSON object.")

        # Parse usage
        usage = body.get("usage", {})
        if not isinstance(usage, dict):
            raise LLMMalformedJSONError("DeepSeek response usage is malformed.")
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        cached_input_tokens = usage.get("prompt_cache_hit_tokens")
        if any(
            token_count is not None
            and (
                not isinstance(token_count, int)
                or isinstance(token_count, bool)
                or token_count < 0
            )
            for token_count in (input_tokens, output_tokens, cached_input_tokens)
        ):
            raise LLMMalformedJSONError("DeepSeek response usage is malformed.")
        if cached_input_tokens is not None and (input_tokens is None or cached_input_tokens > input_tokens):
            raise LLMMalformedJSONError("DeepSeek cache usage is malformed.")
        provider_req_id = body.get("id")
        reported_model = body.get("model")

        choices = body.get("choices", [])
        if not isinstance(choices, list):
            raise LLMMalformedJSONError("DeepSeek response choices are malformed.")
        if not choices:
            raise LLMEmptyResponseError("DeepSeek returned no choices in response.")

        choice = choices[0]
        if not isinstance(choice, dict):
            raise LLMMalformedJSONError("DeepSeek response choice is malformed.")
        finish_reason = choice.get("finish_reason")
        message = choice.get("message", {})
        if not isinstance(message, dict):
            raise LLMMalformedJSONError("DeepSeek response message is malformed.")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise LLMMalformedJSONError("DeepSeek response content is malformed.")
        tool_calls = _parse_tool_calls(message.get("tool_calls"))

        if finish_reason == "length":
            raise LLMTruncatedError("Response truncated: finish_reason is length")
        elif finish_reason in {"content_filter", "refusal"}:
            raise LLMRefusalError(f"Content refused by provider (finish_reason: {finish_reason})")
        elif finish_reason in {"insufficient_system_resource", "aborted"}:
            raise LLMServerError(f"DeepSeek did not complete generation (finish_reason: {finish_reason})")

        if finish_reason == "tool_calls" and not tool_calls:
            raise LLMEmptyResponseError("DeepSeek indicated a tool call but returned none.")
        if (not content or not content.strip()) and not tool_calls:
            raise LLMEmptyResponseError("DeepSeek choice message returned empty content.")

        return CompletionResult(
            content=content,
            requested_model=request.model,
            reported_model=reported_model,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            provider_request_id=provider_req_id,
            latency_ms=elapsed_ms,
            raw_response=body,
            tool_calls=tool_calls,
        )


def get_llm_provider(mock_fault: str = "success") -> BaseLLMProvider:
    """Factory to retrieve configured LLM provider according to settings."""
    settings = get_settings()
    if settings.LLM_PROVIDER == "deepseek":
        return DeepSeekHTTPXProvider(api_key=settings.DEEPSEEK_API_KEY)
    return MockLLMProvider(fault_mode=mock_fault)
