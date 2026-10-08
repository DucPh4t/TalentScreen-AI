"""Verify optional LangSmith connectivity with one metadata-only, synthetic span."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from langsmith.utils import LangSmithNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "backend"))

from app.config import get_settings
from app.services.observability import _get_client, trace_span


def read_back_with_retry(client, run_id):
    """Wait briefly for asynchronous ingestion; never retry access/network errors."""
    stored = None
    for attempt in range(8):
        try:
            stored = client.read_run(run_id)
            if stored.end_time is not None:
                return stored
        except LangSmithNotFoundError:
            if attempt == 7:
                raise
        if attempt < 7:
            time.sleep(1)
    return stored


def main() -> int:
    try:
        settings = get_settings()
    except ValueError:
        print(json.dumps({"status": "invalid_configuration", "verified": False}))
        return 2
    if not settings.LANGSMITH_TRACING:
        print(json.dumps({"status": "not_enabled", "verified": False}))
        return 2
    try:
        with trace_span("langsmith_connectivity_probe") as span:
            span.record({"outcome": "succeeded", "model_round_trips": 0, "external_call_count": 0})
        if span.run_id is None:
            print(json.dumps({"status": "export_unavailable", "verified": False}))
            return 1
        client = _get_client(settings.LANGSMITH_ENDPOINT, settings.LANGSMITH_API_KEY)
        client.flush(timeout=5)
        stored = read_back_with_retry(client, span.run_id)
        verified = str(stored.id) == span.run_id and stored.end_time is not None
        print(json.dumps({"status": "verified" if verified else "not_verified", "verified": verified,
            "trace_id": span.run_id}))
        return 0 if verified else 1
    except Exception:
        # Never print SDK exception bodies, request headers or credentials.
        print(json.dumps({"status": "verification_failed", "verified": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
