"""Regression checks for the production assessment prompt payload."""
from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.services.assessment.prompt import (
    ASSESSMENT_PROMPT_VERSION,
    build_assessment_system_prompt,
    build_assessment_user_prompt,
)
from app.services.llm.provider import DeepSeekHTTPXProvider
from app.services.llm.types import CompletionRequest
from app.services.rubric import load_seed_rubric_dict


def test_seed_rubric_anchors_and_jd_quotes_reach_assessment_prompt() -> None:
    seed = load_seed_rubric_dict()
    criteria = [
        SimpleNamespace(
            criterion_id=c["id"],
            label_vi=c["label"],
            description_vi=c["description"],
            weight=c["weight"],
            anchors=c["scoring_anchors"],
            jd_evidence_refs=c["source_requirements"],
        )
        for c in seed["criteria"]
    ]
    span = SimpleNamespace(span_id="spn_" + "a" * 24, text="Synthetic exact source span.")
    prompt = json.loads(build_assessment_user_prompt(criteria, [span]))

    assert len(prompt["rubric"]) == 6
    for supplied, packed in zip(seed["criteria"], prompt["rubric"]):
        assert packed["criterion_id"] == supplied["id"]
        assert packed["source_requirements"] == supplied["source_requirements"]
        assert packed["anchors"] == supplied["scoring_anchors"]
        assert {anchor["score"] for anchor in packed["anchors"]} == set(range(5))
    assert prompt["source_spans"] == [{"span_id": span.span_id, "quote": span.text}]


def test_assessment_prompt_requires_rationale_and_untrusted_source_handling() -> None:
    prompt = build_assessment_system_prompt()
    assert ASSESSMENT_PROMPT_VERSION == "assessment-v1.3.0"
    assert '"rationale"' in prompt
    assert "untrusted candidate data" in prompt
    assert "Missing information is not score 0" in prompt
    assert "Write every rationale and missing_information question in Vietnamese" in prompt
    assert "Never return an evidence 'text' field" in prompt


@pytest.mark.asyncio
async def test_deepseek_assessment_request_disables_thinking() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "synthetic-test",
            "model": "deepseek-flash",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "choices": [{"finish_reason": "stop", "message": {"content": '{"criteria":[]}'}}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = DeepSeekHTTPXProvider(api_key="sk-synthetic-test", api_url="https://example.invalid/chat/completions", client=client)
        await provider.complete(CompletionRequest(
            task_kind="assessment",
            system_prompt="Return JSON.",
            user_prompt="Synthetic only",
            model="deepseek-flash",
            thinking_mode="disabled",
        ))

    assert captured["thinking"] == {"type": "disabled"}
    assert captured["response_format"] == {"type": "json_object"}
