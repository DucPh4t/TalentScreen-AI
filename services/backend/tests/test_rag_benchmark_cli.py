"""Privacy and determinism checks for the aggregate-only benchmark CLI."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "run_rag_benchmark.py"
DATASET = ROOT / "fixtures" / "rag_benchmark" / "synthetic.jsonl"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_report_is_deterministic_and_contains_aggregates_only(tmp_path: Path) -> None:
    outputs = [tmp_path / "first.json", tmp_path / "second.json"]
    for output in outputs:
        result = _run("--dataset", str(DATASET), "--output", str(output))
        assert result.returncode == 0, result.stderr

    first, second = (path.read_text(encoding="utf-8") for path in outputs)
    assert first == second
    report = json.loads(first)
    assert report["readiness"] == "NOT_AUTHORIZED_FOR_LIVE_DECISIONS"
    assert report["data_scope"] == "synthetic_only"
    assert report["overall"]["sample_count"] == 4
    assert set(report["overall"]["provider_aggregates"]) == {"deepseek", "mock"}
    deepseek = report["overall"]["provider_aggregates"]["deepseek"]
    mock = report["overall"]["provider_aggregates"]["mock"]
    assert deepseek["fairness"]["counterfactual_invariance_rate"] == 1.0
    assert deepseek["grounding"]["citation_validity"] == 1.0
    assert mock["grounding"]["citation_validity"] == 0.0
    assert deepseek["scoring"]["criterion_mae"] == pytest.approx(1 / 6)
    assert "version_context" in report
    assert "syn_backend_base_001" not in first
    assert "candidate_name" not in first


def test_cli_requires_explicit_unlock_for_locked_holdout(tmp_path: Path) -> None:
    output = tmp_path / "holdout.json"
    blocked = _run(
        "--dataset", str(DATASET), "--output", str(output), "--split", "locked_holdout"
    )
    assert blocked.returncode == 2
    assert "--allow-locked-holdout" in blocked.stderr
    assert not output.exists()

    allowed = _run(
        "--dataset", str(DATASET), "--output", str(output), "--split", "locked_holdout",
        "--allow-locked-holdout",
    )
    assert allowed.returncode == 0, allowed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["split"] == "locked_holdout"
    jev = report["overall"]["provider_aggregates"]["jev"]
    assert jev["operations"]["provider_failure_manual_review_rate"] == 1.0
    assert jev["operations"]["manual_review_count"] == 1


def test_cli_rejects_unapproved_identity_fields_even_when_jsonl_hash_matches(tmp_path: Path) -> None:
    dataset = tmp_path / "unsafe.jsonl"
    manifest = tmp_path / "unsafe.manifest.json"
    shutil.copyfile(DATASET, dataset)
    shutil.copyfile(DATASET.with_suffix(".manifest.json"), manifest)
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    rows[0]["candidate_name"] = "synthetic-only-name"
    raw = "\n".join(json.dumps(row) for row in rows) + "\n"
    dataset.write_text(raw, encoding="utf-8")
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["dataset_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    output = tmp_path / "unsafe-report.json"
    result = _run("--dataset", str(dataset), "--output", str(output))
    assert result.returncode == 2
    assert "only aggregate-safe schema fields are allowed" in result.stderr
    assert not output.exists()


def test_private_report_suppresses_small_role_and_overall_groups(tmp_path: Path) -> None:
    dataset = tmp_path / "private.jsonl"
    manifest = tmp_path / "private.manifest.json"
    shutil.copyfile(DATASET, dataset)
    shutil.copyfile(DATASET.with_suffix(".manifest.json"), manifest)
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_data["benchmark_id"] = "private_review_v1"
    manifest_data["data_scope"] = "restricted_evaluation"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    output = tmp_path / "private-report.json"
    result = _run("--dataset", str(dataset), "--output", str(output))
    assert result.returncode == 0, result.stderr
    rendered = output.read_text(encoding="utf-8")
    report = json.loads(rendered)
    assert report["overall"] == {"suppressed": True, "reason": "below_minimum_group_size"}
    assert report["role_provider_aggregates"] == [
        {"suppressed": True, "reason": "below_minimum_group_size"}
    ] * 3
    assert "backend_node" not in rendered
    assert all(
        status == "NOT_EVALUABLE"
        for checks in report["provisional_slo_checks_by_provider"].values()
        for status in checks.values()
    )
