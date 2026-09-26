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
from app.services.llm.types import CompletionRequest, CompletionResult

logger = logging.getLogger(__name__)


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
        latency_ms: int = 10,
    ):
        self.fault_mode = fault_mode
        self.custom_content = custom_content
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

        # Default success
        content = self.custom_content or json.dumps(
            {
                "status": "success",
                "message": "Mock completion response",
                "task": request.task_kind,
            }
        )

        return CompletionResult(
            content=content,
            requested_model=request.model,
            reported_model=request.model,
            finish_reason="stop",
            input_tokens=200,
            output_tokens=100,
            provider_request_id=f"mock_req_{self.invocation_count}",
            latency_ms=self.latency_ms,
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
        self.api_url = api_url or self.DEFAULT_API_URL
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
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.response_format:
            payload["response_format"] = request.response_format

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
            raise LLMProviderError(f"DeepSeek returned unexpected HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            body = resp.json()
        except Exception:
            raise LLMMalformedJSONError("Failed to parse DeepSeek response body as JSON.")

        # Parse usage
        usage = body.get("usage", {})
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        provider_req_id = body.get("id")
        reported_model = body.get("model")

        choices = body.get("choices", [])
        if not choices:
            raise LLMEmptyResponseError("DeepSeek returned no choices in response.")

        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        message = choice.get("message", {})
        content = message.get("content")

        if finish_reason == "length":
            raise LLMTruncatedError("Response truncated: finish_reason is length")
        elif finish_reason in {"content_filter", "refusal"}:
            raise LLMRefusalError(f"Content refused by provider (finish_reason: {finish_reason})")

        if not content or not content.strip():
            raise LLMEmptyResponseError("DeepSeek choice message returned empty content.")

        return CompletionResult(
            content=content,
            requested_model=request.model,
            reported_model=reported_model,
            finish_reason=finish_reason,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            provider_request_id=provider_req_id,
            latency_ms=elapsed_ms,
            raw_response=body,
        )


def get_llm_provider(mock_fault: str = "success") -> BaseLLMProvider:
    """Factory to retrieve configured LLM provider according to settings."""
    settings = get_settings()
    if settings.LLM_PROVIDER == "deepseek":
        return DeepSeekHTTPXProvider(api_key=settings.DEEPSEEK_API_KEY)
    return MockLLMProvider(fault_mode=mock_fault)
