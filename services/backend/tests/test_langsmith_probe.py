"""Cloud read-back must tolerate ingestion delay without hiding access errors."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from langsmith.utils import LangSmithNotFoundError


def load_probe():
    path = Path(__file__).resolve().parents[3] / "scripts" / "probe_langsmith.py"
    spec = importlib.util.spec_from_file_location("langsmith_probe_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_back_waits_for_run_and_completed_patch(monkeypatch):
    probe = load_probe()
    sleeps = []
    monkeypatch.setattr(probe.time, "sleep", sleeps.append)
    responses = [LangSmithNotFoundError("ingestion pending"),
        SimpleNamespace(end_time=None), SimpleNamespace(end_time="completed")]
    calls = []
    def read_run(run_id):
        calls.append(run_id)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    result = probe.read_back_with_retry(SimpleNamespace(read_run=read_run), "test-run")
    assert result.end_time == "completed"
    assert calls == ["test-run"] * 3
    assert sleeps == [1, 1]


def test_read_back_does_not_retry_unexpected_or_access_errors(monkeypatch):
    probe = load_probe()
    monkeypatch.setattr(probe.time, "sleep", lambda _: pytest.fail("access error was retried"))
    error = RuntimeError("access rejected")
    def read_run(_run_id):
        raise error
    with pytest.raises(RuntimeError) as captured:
        probe.read_back_with_retry(SimpleNamespace(read_run=read_run), "test-run")
    assert captured.value is error


def test_read_back_is_bounded_when_ingestion_never_completes(monkeypatch):
    probe = load_probe()
    sleeps, calls = [], []
    monkeypatch.setattr(probe.time, "sleep", sleeps.append)
    def read_run(run_id):
        calls.append(run_id)
        raise LangSmithNotFoundError("still pending")
    with pytest.raises(LangSmithNotFoundError):
        probe.read_back_with_retry(SimpleNamespace(read_run=read_run), "test-run")
    assert len(calls) == 8
    assert sleeps == [1] * 7


def test_disabled_probe_never_contacts_cloud(monkeypatch, capsys):
    probe = load_probe()
    monkeypatch.setattr(probe, "get_settings", lambda: SimpleNamespace(LANGSMITH_TRACING=False))
    monkeypatch.setattr(probe, "_get_client", lambda *_: pytest.fail("disabled probe contacted cloud"))
    assert probe.main() == 2
    assert '"verified": false' in capsys.readouterr().out
