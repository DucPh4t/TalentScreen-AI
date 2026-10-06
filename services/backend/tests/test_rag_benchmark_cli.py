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
    assert report["report_schema_version"] == 2
    assert report["version_context_status"] == "SYNTHETIC_PLACEHOLDERS"
    assert report["readiness"] == "NOT_AUTHORIZED_FOR_LIVE_DECISIONS"
    assert report["data_scope"] == "synthetic_only"
    assert report["overall"]["sample_count"] == 4
    assert set(report["overall"]["provider_aggregates"]) == {"deepseek", "mock"}
    deepseek = report["overall"]["provider_aggregates"]["deepseek"]
    mock = report["overall"]["provider_aggregates"]["mock"]
    assert deepseek["fairness"]["counterfactual_invariance_rate"] == 1.0
    assert deepseek["grounding"]["citation_validity"] == 1.0
    assert mock["grounding"]["citation_validity"] == 0.0
    assert deepseek["grounding"]["scored_criterion_count"] == 6
    assert deepseek["grounding"]["unsupported_criterion_count"] == 1
    assert deepseek["grounding"]["unsupported_claim_rate"] == pytest.approx(1 / 6)
    assert deepseek["retrieval"]["evidence_query_count"] == 6
    assert deepseek["retrieval"]["sufficient_evidence_at_5_rate"] == 1.0
    assert deepseek["scoring"]["criterion_mae"] == pytest.approx(1 / 6)
    assert "human_human_linear_weighted_kappa" in deepseek["scoring"]
    assert deepseek["uncertainty"]["independent_candidate_cluster_count"] == 2
    assert deepseek["uncertainty"]["confidence_intervals_95"]["scoring.criterion_mae"] is not None
    assert "linear_weighted_kappa" in deepseek["scoring"]
    assert "version_context" in report
    assert "syn_backend_base_001" not in first
    assert "cluster_backend_001" not in first
    assert "candidate_name" not in first


def test_slo_checks_are_scoped_to_each_role_and_provider(tmp_path: Path) -> None:
    output = tmp_path / "scoped.json"
    result = _run("--dataset", str(DATASET), "--output", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    scopes = report["provisional_slo_checks_by_role_provider"]
    assert len(scopes) == 3
    assert {(item["role_id"], item["provider_id"]) for item in scopes} == {
        ("role_backend_node", "deepseek"),
        ("role_ai_ml_intern", "deepseek"),
        ("role_dotnet_fullstack", "mock"),
    }
    assert all("rag_design_candidate_v1" in item["profiles"] for item in scopes)
    assert all("mvp_p1_candidate_v1" in item["profiles"] for item in scopes)


def test_criterion_retrieval_does_not_credit_evidence_from_another_criterion(tmp_path: Path) -> None:
    dataset = tmp_path / "cross-criterion.jsonl"
    manifest_path = dataset.with_suffix(".manifest.json")
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()]
    row = rows[0]
    row["criterion_evidence"][0]["retrieved_span_ids"] = []
    row["criterion_evidence"][1]["retrieved_span_ids"].append("span_api_01")
    raw = "".join(json.dumps(item, sort_keys=True) + "\n" for item in rows)
    dataset.write_text(raw, encoding="utf-8")
    manifest = json.loads(DATASET.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    manifest["dataset_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    output = tmp_path / "cross-criterion-report.json"
    result = _run("--dataset", str(dataset), "--output", str(output))
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    deepseek_backend = next(
        item for item in report["role_provider_aggregates"]
        if item.get("role_id") == "role_backend_node" and item.get("provider_id") == "deepseek"
    )
    assert deepseek_backend["retrieval"]["recall_at_5"] == pytest.approx(0.75)
    assert deepseek_backend["retrieval"]["sufficient_evidence_at_5_rate"] == pytest.approx(0.75)
    assert deepseek_backend["uncertainty"]["independent_candidate_cluster_count"] == 1
    assert deepseek_backend["uncertainty"]["confidence_intervals_95"]["retrieval.recall_at_5"] is None


def test_manifest_keeps_related_candidate_clusters_in_one_split(tmp_path: Path) -> None:
    dataset = tmp_path / "cluster-leak.jsonl"
    manifest_path = dataset.with_suffix(".manifest.json")
    shutil.copyfile(DATASET, dataset)
    manifest = json.loads(DATASET.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    manifest["evaluation_clusters"]["syn_android_001"] = "cluster_ai_001"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = _run("--dataset", str(dataset), "--output", str(tmp_path / "report.json"))
    assert result.returncode == 2
    assert "cannot cross" in result.stderr


def test_private_report_redacts_benchmark_label_and_rejects_floating_versions(tmp_path: Path) -> None:
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
    assert report["benchmark_id"] == "restricted_evaluation"
    assert "private_review_v1" not in rendered

    manifest_data["version_context"]["retrieval_version"] = "main"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    output.unlink()
    rejected = _run("--dataset", str(dataset), "--output", str(output))
    assert rejected.returncode == 2
    assert "floating" in rejected.stderr
    assert not output.exists()


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
    assert report["jev_shadow_status"] == "INCOMPLETE"
    assert all(scope["provider_id"] == "deepseek" for scope in report["manual_fallback_scopes"])


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
    assert report["benchmark_id"] == "restricted_evaluation"
    assert all(
        status == "NOT_EVALUABLE"
        for provider in report["provisional_slo_checks_by_provider"].values()
        for profile in provider.values()
        for status in profile.values()
    )
