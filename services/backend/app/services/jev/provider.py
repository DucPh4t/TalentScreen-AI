"""Typed HTTP adapter for Jev's bounded-decision API.

This adapter intentionally does not decide hiring outcomes. Callers must send
only approved, minimized, sanitized evidence and keep Jev disabled until the
organization has approved the provider and configured its verified rate card.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any, Literal, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.config import get_settings
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMMalformedJSONError,
    LLMModelUnavailableError,
    LLMProviderError,
    LLMQuotaExhaustedError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
)
from app.services.llm.types import CompletionRequest, CompletionResult
from app.services.llm.provider import BaseLLMProvider

JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


class JevQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["choice", "score", "noul"]
    instructions: str = Field(min_length=1, max_length=1000)
    criteria: Optional[list[str] | dict[str, str]] = None

    @model_validator(mode="after")
    def validate_criteria_shape(self) -> "JevQuestion":
        if self.type == "score":
            if not isinstance(self.criteria, list) or not 2 <= len(self.criteria) <= 10:
                raise ValueError("Jev score questions require 2 to 10 ordered criterion levels")
        elif self.type == "choice":
            if not isinstance(self.criteria, dict) or not 2 <= len(self.criteria) <= 24:
                raise ValueError("Jev choice questions require 2 to 24 named choices")
        elif self.criteria is not None and not isinstance(self.criteria, dict):
            raise ValueError("Jev noul criteria, when supplied, must be a yes/no description object")
        return self


class JevDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str | dict[str, Any]
    questions: dict[str, JevQuestion] = Field(min_length=1, max_length=20)
    model: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_state_size(self) -> "JevDecisionRequest":
        encoded = self.state if isinstance(self.state, str) else json.dumps(self.state, ensure_ascii=False)
        if len(encoded) > 100_000:
            raise ValueError("Jev state exceeds the configured 100,000 character safety limit")
        return self


class JevDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    model_version: Optional[str] = None
    answers: dict[str, dict[str, Any]]
    usage: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_answer_values(self) -> "JevDecisionResponse":
        for question_id, answer in self.answers.items():
            kind = answer.get("type")
            if kind == "score":
                score = answer.get("score")
                confidence = answer.get("confidence")
                if not _finite_range(score, 0, 9) or not _finite_range(confidence, 0, 1):
                    raise ValueError(f"Jev score answer '{question_id}' has invalid score or confidence")
                probabilities = answer.get("probabilities")
                if not _valid_probabilities(probabilities):
                    raise ValueError(f"Jev score answer '{question_id}' has invalid probabilities")
            elif kind == "choice":
                if not isinstance(answer.get("choice"), str) or not _finite_range(answer.get("confidence"), 0, 1):
                    raise ValueError(f"Jev choice answer '{question_id}' is malformed")
                if not _valid_probabilities(answer.get("probabilities")):
                    raise ValueError(f"Jev choice answer '{question_id}' has invalid probabilities")
            elif kind == "noul":
                if not _finite_range(answer.get("noul"), 0, 1):
                    raise ValueError(f"Jev noul answer '{question_id}' is malformed")
            else:
                raise ValueError(f"Jev answer '{question_id}' has an unknown answer type")
        return self


def _finite_range(value: Any, minimum: float, maximum: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and minimum <= value <= maximum


def _valid_probabilities(value: Any) -> bool:
    if not isinstance(value, dict) or not value:
        return False
    vals = list(value.values())
    return all(_finite_range(v, 0, 1) for v in vals) and abs(sum(vals) - 1.0) <= 0.02


class JevHTTPXProvider(BaseLLMProvider):
    """HTTPX client for TypeSafe's System One endpoint; never logs request content."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.JEV_API_KEY
        self.api_url = api_url or settings.JEV_BASE_URL or JEV_ENDPOINT
        self.model = model or settings.JEV_MODEL
        self._external_client = client

    def _mask_secret(self, message: str) -> str:
        return message.replace(self.api_key, "[REDACTED_API_KEY]") if self.api_key else message

    async def evaluate(
        self,
        *,
        state: str | dict[str, Any],
        questions: dict[str, JevQuestion | dict[str, Any]],
        timeout_seconds: float = 30.0,
    ) -> JevDecisionResponse:
        settings = get_settings()
        if settings.JEV_MODE != "shadow":
            raise LLMProviderError("Jev is disabled; set JEV_MODE=shadow only after provider and data approval.")
        if not settings.JEV_DATA_PROCESSING_APPROVED:
            raise LLMProviderError("Jev external processing is not approved by the organization.")
        if not self.api_key or len(self.api_key.strip()) < 8:
            raise LLMAuthenticationError("JEV_API_KEY is not configured or invalid.")

        try:
            request = JevDecisionRequest(
                state=state,
                model=self.model,
                questions={
                    key: value if isinstance(value, JevQuestion) else JevQuestion.model_validate(value)
                    for key, value in questions.items()
                },
            )
        except ValidationError as exc:
            raise LLMProviderError(f"Invalid Jev request contract: {exc.errors()[0]['msg']}") from exc

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = request.model_dump(exclude_none=True)
        started = time.monotonic()
        client = self._external_client or httpx.AsyncClient(timeout=timeout_seconds)
        try:
            response = await client.post(self.api_url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Timeout contacting Jev API.") from exc
        except httpx.RequestError as exc:
            raise LLMServerError("Network error contacting Jev API.") from exc
        finally:
            if not self._external_client:
                await client.aclose()

        if response.status_code == 401:
            raise LLMAuthenticationError("Jev returned 401: invalid API key.")
        if response.status_code == 402:
            raise LLMQuotaExhaustedError("Jev returned 402: account quota or credits are exhausted.")
        if response.status_code == 404:
            raise LLMModelUnavailableError("Jev model or endpoint is unavailable.")
        if response.status_code == 429:
            raise LLMRateLimitError("Jev rate limit exceeded.")
        if response.status_code >= 500:
            raise LLMServerError(f"Jev server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            # Do not include provider body: it could echo candidate data.
            raise LLMProviderError(f"Jev rejected the request (HTTP {response.status_code}).")

        try:
            body = response.json()
            result = JevDecisionResponse.model_validate(body)
        except (ValueError, ValidationError) as exc:
            raise LLMMalformedJSONError("Jev returned an invalid response contract.") from exc

        if set(result.answers) != set(request.questions):
            raise LLMEmptyResponseError("Jev did not return exactly one answer for each requested question.")
        for question_id, question in request.questions.items():
            answer = result.answers[question_id]
            if answer.get("type") != question.type:
                raise LLMMalformedJSONError(f"Jev answer '{question_id}' has the wrong type.")
            if question.type == "score":
                max_level = len(question.criteria or []) - 1
                if answer["score"] > max_level:
                    raise LLMMalformedJSONError(f"Jev score '{question_id}' exceeds its rubric levels.")
                if set(answer["probabilities"]) != {str(i) for i in range(max_level + 1)}:
                    raise LLMMalformedJSONError(f"Jev probabilities '{question_id}' do not match its rubric levels.")
            elif question.type == "choice":
                if answer["choice"] not in (question.criteria or {}):
                    raise LLMMalformedJSONError(f"Jev choice '{question_id}' is outside the allowed set.")
                if set(answer["probabilities"]) != set(question.criteria or {}):
                    raise LLMMalformedJSONError(f"Jev choice probabilities '{question_id}' do not match its options.")
        return result

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Adapt Jev's typed response to the existing invocation ledger contract."""
        try:
            envelope = json.loads(request.user_prompt)
        except (TypeError, ValueError) as exc:
            raise LLMProviderError("Jev call requires a JSON envelope with state and questions.") from exc
        if not isinstance(envelope, dict) or "state" not in envelope or "questions" not in envelope:
            raise LLMProviderError("Jev call requires a JSON envelope with state and questions.")
        started = time.monotonic()
        result = await self.evaluate(
            state=envelope["state"],
            questions=envelope["questions"],
            timeout_seconds=request.timeout_seconds,
        )
        usage = result.usage
        return CompletionResult(
            content=result.model_dump_json(),
            requested_model=request.model,
            reported_model=result.model_version or result.model,
            finish_reason="stop",
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens", 0),
            provider_request_id=None,
            latency_ms=int((time.monotonic() - started) * 1000),
            raw_response=result.model_dump(mode="json"),
        )


def get_jev_provider() -> JevHTTPXProvider:
    """Create a provider; the evaluation method still enforces the off-by-default gate."""
    return JevHTTPXProvider()
