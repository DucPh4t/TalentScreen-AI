"""Run the bounded synthetic DeepSeek capability probe from the repository root.

Reads .env through app settings. Prints protocol/usage metadata only, never the
API key, prompt body, or candidate data. Requires LLM_PROVIDER=deepseek.
"""
from __future__ import annotations

import asyncio
import json

from app.config import get_settings
from app.services.llm.probe import run_capability_probe


async def main() -> int:
    settings = get_settings()
    if settings.LLM_PROVIDER != "deepseek":
        print(json.dumps({"success": False, "reason": "Set LLM_PROVIDER=deepseek in .env to run a live provider probe."}))
        return 2
    report = await run_capability_probe()
    # Report fields are deliberately limited to avoid leaking provider response.
    allowed = ("provider", "requested_model", "reported_model", "timestamp_utc", "key_configured", "probes", "success", "latency_ms", "input_tokens", "output_tokens", "error_code")
    print(json.dumps({key: report[key] for key in allowed if key in report}, ensure_ascii=False))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
