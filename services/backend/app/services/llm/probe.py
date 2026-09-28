"""Synthetic Capability Probe for LLM provider validation.
Verifies API key validity, model availability, JSON mode, and usage parsing
using purely synthetic test data.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any

from app.config import get_settings
from app.services.llm.exceptions import LLMProviderError
from app.services.llm.provider import BaseLLMProvider, get_llm_provider
from app.services.llm.types import CompletionRequest

logger = logging.getLogger(__name__)


async def run_capability_probe(
    provider: BaseLLMProvider | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Execute synthetic preflight capability probe.
    Does NOT use candidate data or egress real CVs.
    """
    settings = get_settings()
    llm = provider or get_llm_provider()
    model = model or settings.DEEPSEEK_MODEL

    system_prompt = "You are a synthetic diagnostic agent. You must respond strictly in JSON."
    user_prompt = "Generate a JSON object with key 'status' equal to 'ok' and key 'timestamp' with current time."

    request = CompletionRequest(
        task_kind="repair",  # synthetic testing task
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        max_output_tokens=512,
        timeout_seconds=15.0,
        response_format={"type": "json_object"},
        thinking_mode="disabled",
    )

    started_at = datetime.now(timezone.utc)
    probe_report: dict[str, Any] = {
        "provider": settings.LLM_PROVIDER,
        "requested_model": model,
        "timestamp_utc": started_at.isoformat(),
        "key_configured": bool(settings.DEEPSEEK_API_KEY and not settings.DEEPSEEK_API_KEY.startswith("sk-placeholder")),
        "probes": {
            "authentication": False,
            "model_accepted": False,
            "json_mode": False,
            "usage_reporting": False,
        },
        "success": False,
        "disclaimer": (
            "Capability probe verifies protocol connectivity, JSON mode, and usage parsing only. "
            "It does NOT verify semantic evaluation correctness, candidate suitability, or vendor privacy retention."
        ),
    }

    try:
        res = await llm.complete(request)
        probe_report["probes"]["authentication"] = True
        probe_report["probes"]["model_accepted"] = True
        probe_report["reported_model"] = res.reported_model
        probe_report["latency_ms"] = res.latency_ms

        # Test JSON parsing
        if res.content:
            try:
                parsed = json.loads(res.content)
                probe_report["probes"]["json_mode"] = isinstance(parsed, dict)
            except Exception:
                probe_report["probes"]["json_mode"] = False

        # Test usage reporting
        if res.input_tokens is not None and res.output_tokens is not None:
            probe_report["probes"]["usage_reporting"] = True
            probe_report["input_tokens"] = res.input_tokens
            probe_report["output_tokens"] = res.output_tokens

        probe_report["success"] = all(probe_report["probes"].values())
        return probe_report

    except LLMProviderError as e:
        probe_report["error_code"] = e.error_code
        probe_report["error_message"] = e.message
        probe_report["success"] = False
        return probe_report
    except Exception as e:
        probe_report["error_code"] = "UNEXPECTED_PROBE_ERROR"
        probe_report["error_message"] = str(e)
        probe_report["success"] = False
        return probe_report
