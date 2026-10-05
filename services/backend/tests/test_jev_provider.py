"""Contract and safety regression tests for the optional Jev provider."""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.services.jev.provider import JevHTTPXProvider, JevQuestion
from app.services.llm.exceptions import (
    LLMAuthenticationError,
    LLMEmptyResponseError,
    LLMMalformedJSONError,
    LLMProviderError,
)
from app.services.llm.types import CompletionRequest


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "APP_ENV": "sandbox",
        "LLM_PROVIDER": "mock",
        "JEV_MODE": "shadow",
        "JEV_API_KEY": "jev_test_secret_key",
        "JEV_DATA_PROCESSING_APPROVED": True,
        "JEV_BASE_URL": "https://openrouter.ai/api/v1/systemone",
        "JEV_MODEL": "typesafe/jev-1.13",
        "JEV_INPUT_PRICE_PER_MILLION_USD": 0.042,
        "JEV_RATE_CARD_VERIFIED_AT": "2026-09-21",
    }
    values.update(overrides)
    return Settings(**values)


def _runtime_settings(**overrides) -> SimpleNamespace:
    values = {
        "JEV_MODE": "shadow",
        "JEV_API_KEY": "jev_test_secret_key",
        "JEV_DATA_PROCESSING_APPROVED": True,
        "JEV_MODEL": "typesafe/jev-1.13",
        "JEV_BASE_URL": "https://openrouter.ai/api/v1/systemone",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _score_response(question_id: str = "react_ui", **answer_overrides) -> dict:
    answer = {
        "type": "score",
        "score": 3.25,
        "confidence": 0.72,
        "probabilities": {"0": 0.0, "1": 0.0, "2": 0.0, "3": 0.75, "4": 0.25},
    }
    answer.update(answer_overrides)
    return {
        "model": "typesafe/jev-1.13-20260917",
        "answers": {question_id: answer},
        "usage": {"input_tokens": 42, "output_tokens": 0},
    }


def _question() -> dict:
    return {
        "type": "score",
        "instructions": "Rate the evidence against the approved levels.",
        "criteria": [f"Anchor {index}" for index in range(5)],
    }


@pytest.mark.asyncio
async def test_jev_posts_typed_contract_and_accepts_fractional_score(monkeypatch) -> None:
    monkeypatch.setattr("app.services.jev.provider.get_settings", lambda: _settings())
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=_score_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = JevHTTPXProvider(
            api_url="https://openrouter.ai/api/v1/systemone",
            model="typesafe/jev-1.13",
            client=client,
        )
        response = await provider.evaluate(
            state={"cv_evidence": ["Built a React dashboard"]},
            questions={"react_ui": _question()},
        )

    assert captured["url"] == "https://openrouter.ai/api/v1/systemone"
    assert captured["authorization"] == "Bearer jev_test_secret_key"
    assert captured["payload"]["model"] == "typesafe/jev-1.13"
    assert captured["payload"]["questions"]["react_ui"]["type"] == "score"
    assert response.answers["react_ui"]["score"] == 3.25


@pytest.mark.asyncio
async def test_jev_completion_adapts_usage_without_emitting_text(monkeypatch) -> None:
    monkeypatch.setattr("app.services.jev.provider.get_settings", lambda: _settings())

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_score_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = JevHTTPXProvider(client=client, model="typesafe/jev-1.13")
        result = await provider.complete(
            CompletionRequest(
                task_kind="assessment",
                system_prompt="",
                user_prompt=json.dumps({"state": {"evidence": "React"}, "questions": {"react_ui": _question()}}),
                model="typesafe/jev-1.13",
                max_output_tokens=0,
                provider="jev",
            )
        )

    assert json.loads(result.content)["answers"]["react_ui"]["score"] == 3.25
    assert result.input_tokens == 42
    assert result.output_tokens == 0
    assert result.reported_model == "typesafe/jev-1.13-20260917"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_body", "error"),
    [
        (_score_response("unexpected_id"), LLMEmptyResponseError),
        (_score_response(score=4.1), LLMMalformedJSONError),
        (_score_response(probabilities={"0": 0.1, "1": 0.1, "2": 0.1, "3": 0.1, "4": 0.1}), LLMMalformedJSONError),
    ],
)
async def test_jev_rejects_mismatched_or_invalid_answers(monkeypatch, response_body, error) -> None:
    monkeypatch.setattr("app.services.jev.provider.get_settings", lambda: _settings())

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = JevHTTPXProvider(client=client, model="typesafe/jev-1.13")
        with pytest.raises(error):
            await provider.evaluate(state="evidence", questions={"react_ui": _question()})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("settings", "error"),
    [
        (_runtime_settings(JEV_MODE="off"), LLMProviderError),
        (_runtime_settings(JEV_DATA_PROCESSING_APPROVED=False), LLMProviderError),
        (_runtime_settings(JEV_API_KEY=None), LLMAuthenticationError),
    ],
)
async def test_jev_requires_explicit_provider_and_data_gates(monkeypatch, settings, error) -> None:
    monkeypatch.setattr("app.services.jev.provider.get_settings", lambda: settings)
    provider = JevHTTPXProvider(api_key=settings.JEV_API_KEY, model="typesafe/jev-1.13")
    with pytest.raises(error):
        await provider.evaluate(state="evidence", questions={"react_ui": _question()})


@pytest.mark.asyncio
async def test_jev_provider_does_not_expose_provider_body_or_key_on_http_error(monkeypatch) -> None:
    secret = "jev_test_secret_key"
    monkeypatch.setattr("app.services.jev.provider.get_settings", lambda: _settings())

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"rejected {secret} with candidate text")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = JevHTTPXProvider(client=client, model="typesafe/jev-1.13")
        with pytest.raises(LLMAuthenticationError) as exc:
            await provider.evaluate(state="evidence", questions={"react_ui": _question()})

    assert secret not in str(exc.value)
    assert "candidate text" not in str(exc.value)


def test_jev_question_bounds_levels_and_rejects_extra_fields() -> None:
    with pytest.raises(ValueError):
        JevQuestion(type="score", instructions="Rate", criteria=["only one"])
    with pytest.raises(ValueError):
        JevQuestion(type="score", instructions="Rate", criteria=[str(i) for i in range(11)])
    with pytest.raises(ValueError):
        JevQuestion.model_validate({**_question(), "untrusted": True})
