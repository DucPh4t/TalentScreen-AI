"""The production trace boundary must never export candidate content or affect results."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
from types import SimpleNamespace
import uuid

import pytest
from app.config import Settings


class RecordingClient:
    """Replace only LangSmith transport; the real SDK RunTree serializes spans."""
    def __init__(self, fail=False):
        self.posts = []
        self.patches = []
        self.fail = fail

    def create_run(self, **payload):
        if self.fail:
            raise RuntimeError("secret@example.com should never reach a log")
        self.posts.append(json.loads(json.dumps(payload, default=str)))

    def update_run(self, **payload):
        if self.fail:
            raise RuntimeError("secret@example.com should never reach a log")
        self.patches.append(json.loads(json.dumps(payload, default=str)))


def enable_recording(monkeypatch, *, fail=False):
    from app.services import observability
    client = RecordingClient(fail=fail)
    settings = SimpleNamespace(LANGSMITH_TRACING=True, LANGSMITH_API_KEY="test-only-key",
        LANGSMITH_PROJECT="talentscreen-test", LANGSMITH_ENDPOINT="https://api.smith.langchain.com")
    monkeypatch.setattr(observability, "get_settings", lambda: settings)
    monkeypatch.setattr(observability, "_get_client", lambda *_: client)
    return client


def test_langsmith_disabled_by_default_and_requires_key_when_enabled():
    settings = Settings(_env_file=None, LLM_PROVIDER="mock")
    assert settings.LANGSMITH_TRACING is False
    with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
        Settings(_env_file=None, LLM_PROVIDER="mock", LANGSMITH_TRACING=True, LANGSMITH_API_KEY="")


def test_langsmith_secret_is_redacted_and_credentials_in_endpoint_rejected():
    settings = Settings(_env_file=None, LLM_PROVIDER="mock", LANGSMITH_API_KEY="test-only-secret")
    assert settings.safe_dict()["LANGSMITH_API_KEY"] == "[REDACTED]"
    with pytest.raises(ValueError):
        Settings(_env_file=None, LANGSMITH_ENDPOINT="https://key@example.com/?token=secret")


def test_disabled_tracing_never_constructs_a_client(monkeypatch):
    from app.services import observability
    monkeypatch.setattr(observability, "get_settings", lambda: SimpleNamespace(LANGSMITH_TRACING=False))
    monkeypatch.setattr(observability, "_get_client", lambda *_: pytest.fail("disabled tracing contacted SDK"))
    with observability.trace_span("assessment") as span:
        span.record({"outcome": "succeeded"})
    assert span.run_id is None


def test_trace_exports_only_allowlisted_metadata_and_suppresses_automatic_state_capture(monkeypatch):
    from app.services import observability
    from langsmith.utils import tracing_is_enabled
    client = enable_recording(monkeypatch)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    marker = "RAW_CV_SECRET_person@example.com"
    with observability.trace_span("assessment", metadata={
        "job_id": str(uuid.uuid4()), "prompt": marker, "source_text": marker,
        "criterion_count": 2, "model": marker,
    }) as root:
        assert tracing_is_enabled() is False
        with observability.trace_span("model", metadata={"node": "model"}) as child:
            child.record({"outcome": "succeeded", "input_tokens": 12, "output_tokens": 3,
                "query_hint": marker, "error_code": marker, "raw_response": marker})
        root.record({"outcome": "validated", "model_round_trips": 1})
    exported = json.dumps([client.posts, client.patches])
    assert marker not in exported
    assert client.posts[1]["parent_run_id"] == client.posts[0]["id"]
    assert client.patches[0]["extra"]["metadata"]["input_tokens"] == 12
    assert client.patches[1]["extra"]["metadata"]["outcome"] == "validated"
    assert all(not entry.get("inputs") and not entry.get("outputs") for entry in client.posts + client.patches)
    for entry in client.patches:
        assert datetime.fromisoformat(entry["end_time"]) >= datetime.fromisoformat(entry["start_time"])


def test_trace_errors_export_a_code_without_exception_message_or_stack(monkeypatch, caplog):
    from app.services import observability
    client = enable_recording(monkeypatch)
    with pytest.raises(RuntimeError, match="Candidate_Name"):
        with observability.trace_span("validate"):
            raise RuntimeError("Candidate_Name person@example.com secret-token")
    assert client.patches[0]["error"] == "TRACE_STEP_FAILED"
    assert "Candidate_Name" not in json.dumps([client.posts, client.patches]) + caplog.text


def test_telemetry_outage_preserves_business_result_and_never_logs_raw_error(monkeypatch, caplog):
    from app.services import observability
    enable_recording(monkeypatch, fail=True)
    with observability.trace_span("assessment"):
        with observability.trace_span("model"):
            result = 42
    assert result == 42
    assert "secret@example.com" not in caplog.text


@pytest.mark.asyncio
async def test_concurrent_traces_do_not_mix_parents_and_reset_after_failure(monkeypatch):
    from app.services import observability
    client = enable_recording(monkeypatch)
    async def work(job_id):
        with observability.trace_span("assessment", metadata={"job_id": job_id}):
            await asyncio.sleep(0)
            with observability.trace_span("model"):
                await asyncio.sleep(0)
    jobs = [str(uuid.uuid4()), str(uuid.uuid4())]
    await asyncio.gather(*(work(job) for job in jobs))
    roots = [entry for entry in client.posts if entry["name"] == "assessment"]
    children = [entry for entry in client.posts if entry["name"] == "model"]
    assert {entry["parent_run_id"] for entry in children} == {entry["id"] for entry in roots}
    assert {entry["extra"]["metadata"]["job_id"] for entry in roots} == set(jobs)
    with pytest.raises(RuntimeError):
        with observability.trace_span("validate"):
            raise RuntimeError("raw CV")
    with observability.trace_span("assessment"):
        pass
    assert not client.posts[-1].get("parent_run_id")


@pytest.mark.asyncio
async def test_cancelled_business_operation_propagates_and_finalizes_trace(monkeypatch):
    from app.services import observability
    client = enable_recording(monkeypatch)
    with pytest.raises(asyncio.CancelledError):
        with observability.trace_span("model"):
            raise asyncio.CancelledError("private content")
    assert client.patches[0]["error"] == "TRACE_CANCELLED"
    assert "private content" not in json.dumps(client.patches)


def test_rubric_prompt_version_is_exported_without_accepting_arbitrary_text(monkeypatch):
    from app.services import observability
    client = enable_recording(monkeypatch)
    with observability.trace_span("jd_to_rubric", metadata={
        "rubric_prompt_version": "jd-competencies-v6",
        "assessment_prompt_version": "assessment-v1.4.0",
        "agent_prompt_version": "Candidate_Name_person@example.com",
    }):
        pass
    metadata = client.posts[0]["extra"]["metadata"]
    assert metadata["rubric_prompt_version"] == "jd-competencies-v6"
    assert metadata["assessment_prompt_version"] == "assessment-v1.4.0"
    assert "agent_prompt_version" not in metadata


def test_span_does_not_consult_ambient_replica_destinations(monkeypatch):
    from app.services import observability
    from langsmith import run_trees
    client = enable_recording(monkeypatch)
    def reject_ambient_destinations():
        raise RuntimeError("ambient replica configuration should be ignored")
    monkeypatch.setattr(run_trees, "_get_write_replicas_from_env", reject_ambient_destinations)
    with observability.trace_span("assessment"):
        result = "unchanged"
    assert result == "unchanged"
    assert len(client.posts) == 1
    assert len(client.patches) == 1


def test_tracing_configuration_error_does_not_print_other_application_secrets():
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None,
            LANGSMITH_ENDPOINT="https://PRIVATE_KEY@example.com")
    assert "PRIVATE_KEY" not in str(exc.value)


def test_exception_with_unstructured_code_is_not_replaced_by_telemetry(monkeypatch):
    from app.services import observability
    client = enable_recording(monkeypatch)
    error = RuntimeError("private business error")
    error.code = {"unsafe": "private detail"}
    with pytest.raises(RuntimeError) as captured:
        with observability.trace_span("model"):
            raise error
    assert captured.value is error
    assert client.patches[0]["error"] == "TRACE_STEP_FAILED"
    assert "private detail" not in json.dumps(client.patches)
