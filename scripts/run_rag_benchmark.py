#!/usr/bin/env python3
"""Evaluate a sanitized, schema-limited RAG benchmark and emit aggregates only."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "backend"))

from app.services.evaluation.metrics import (  # noqa: E402
    criterion_mae,
    counterfactual_invariance_rate,
    quadratic_weighted_kappa,
    recall_at_k,
)

ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
PROVIDERS = {"deepseek", "jev", "mock"}
SPLITS = {"development", "locked_holdout"}
TOP_KEYS = {
    "sample_id", "split", "role_id", "provider_id", "criterion_ids",
    "expected_span_ids", "retrieved_span_ids", "citation_checks",
    "reference_scores", "predicted_scores", "second_reviewer_scores",
    "counterfactual_pair_id", "counterfactual_variant", "changed_attributes",
    "assessment_latency_ms", "queue_wait_ms", "provider_latency_ms",
    "extraction_latency_ms", "estimated_cost_usd",
    "agent_tool_count", "file_class", "extraction_status", "provider_status",
    "result_state",
}
CITATION_KEYS = {"source_span_id", "supported"}
MANIFEST_KEYS = {
    "benchmark_id", "schema_version", "data_scope", "dataset_sha256", "split_sample_ids",
    "split_sha256", "version_context",
}
ALLOWED_CHANGED_ATTRIBUTES = {"name", "pronoun", "hometown", "school"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a stable lowercase ID")
    return value


def _score_vector(value: Any, field: str, length: int) -> list[int | None]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{field} must align with criterion_ids")
    if any(score is not None and (type(score) is not int or not 0 <= score <= 4) for score in value):
        raise ValueError(f"{field} values must be integer anchors 0..4 or null")
    return value


def _validate_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) != TOP_KEYS:
        raise ValueError("benchmark row has missing or unsupported fields; only aggregate-safe schema fields are allowed")
    _slug(row["sample_id"], "sample_id")
    _slug(row["role_id"], "role_id")
    if not isinstance(row["provider_id"], str) or row["provider_id"] not in PROVIDERS:
        raise ValueError("provider_id is unsupported")
    if not isinstance(row["split"], str) or row["split"] not in SPLITS:
        raise ValueError("provider_id or split is unsupported")

    criteria = row["criterion_ids"]
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 20:
        raise ValueError("criterion_ids must contain 1..20 stable IDs")
    for criterion in criteria:
        _slug(criterion, "criterion ID")
    if len(set(criteria)) != len(criteria):
        raise ValueError("criterion_ids must be unique")

    expected = row["expected_span_ids"]
    retrieved = row["retrieved_span_ids"]
    if not isinstance(expected, list) or not expected or not isinstance(retrieved, list):
        raise ValueError("span ID lists must be present and expected_span_ids must not be empty")
    for span_id in expected + retrieved:
        _slug(span_id, "source span ID")
    if len(expected) != len(set(expected)) or len(retrieved) != len(set(retrieved)):
        raise ValueError("span ID lists must not contain duplicates")

    citations = row["citation_checks"]
    if not isinstance(citations, list):
        raise ValueError("citation_checks must be a list")
    for item in citations:
        if not isinstance(item, dict) or set(item) != CITATION_KEYS:
            raise ValueError("citation check has missing or unsupported fields")
        _slug(item["source_span_id"], "citation span ID")
        if type(item["supported"]) is not bool:
            raise ValueError("citations need a boolean support label")

    for field in ("reference_scores", "predicted_scores", "second_reviewer_scores"):
        row[field] = _score_vector(row[field], field, len(criteria))
    pair_id = row["counterfactual_pair_id"]
    attrs = row["changed_attributes"]
    if not isinstance(pair_id, str):
        raise ValueError("counterfactual_pair_id must be a stable ID or empty string")
    if pair_id:
        _slug(pair_id, "counterfactual_pair_id")
        if not isinstance(row["counterfactual_variant"], str) or row["counterfactual_variant"] not in {"base", "identity_changed"}:
            raise ValueError("counterfactual_variant must identify a paired variant")
        if not isinstance(attrs, list) or any(not isinstance(item, str) or item not in ALLOWED_CHANGED_ATTRIBUTES for item in attrs):
            raise ValueError("changed_attributes contains unsupported values")
    elif row["counterfactual_variant"] != "" or attrs != []:
        raise ValueError("counterfactual fields must be empty for a non-paired row")

    for field in ("assessment_latency_ms", "queue_wait_ms", "provider_latency_ms", "extraction_latency_ms", "agent_tool_count"):
        if type(row[field]) is not int or row[field] < 0:
            raise ValueError(f"{field} must be a nonnegative integer")
    cost = row["estimated_cost_usd"]
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        raise ValueError("estimated_cost_usd must be a finite nonnegative number")
    if not isinstance(row["file_class"], str) or row["file_class"] not in {"digital", "scanned"}:
        raise ValueError("file_class must be digital or scanned")
    if not isinstance(row["extraction_status"], str) or row["extraction_status"] not in {"succeeded", "failed", "ocr_failed"}:
        raise ValueError("extraction_status is unsupported")
    if not isinstance(row["provider_status"], str) or row["provider_status"] not in {"succeeded", "failed", "timeout", "invalid_output"}:
        raise ValueError("provider_status is unsupported")
    if not isinstance(row["result_state"], str) or row["result_state"] not in {"accepted", "manual_review"}:
        raise ValueError("result_state is unsupported")
    failure = row["provider_status"] != "succeeded" or row["extraction_status"] != "succeeded"
    if failure and row["result_state"] != "manual_review":
        raise ValueError("provider and extraction failures must route to manual_review")
    if failure and any(score is not None for score in row["predicted_scores"]):
        raise ValueError("failed provider or extraction rows must not contain predicted scores")
    return row


def _load_dataset(dataset: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not dataset.is_file():
        raise ValueError("dataset file does not exist")
    manifest_path = dataset.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        raise ValueError("companion .manifest.json is required")
    raw = dataset.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS:
        raise ValueError("manifest has missing or unsupported fields")
    _slug(manifest["benchmark_id"], "benchmark_id")
    if not isinstance(manifest["data_scope"], str) or manifest["data_scope"] not in {"synthetic_only", "restricted_evaluation"}:
        raise ValueError("manifest data_scope is unsupported")
    if manifest["data_scope"] == "synthetic_only" and not manifest["benchmark_id"].startswith("synthetic_"):
        raise ValueError("synthetic fixture benchmark_id must start with synthetic_")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or manifest["dataset_sha256"] != _sha256(raw):
        raise ValueError("dataset schema version or hash does not match manifest")
    if not isinstance(manifest["split_sample_ids"], dict) or not isinstance(manifest["split_sha256"], dict):
        raise ValueError("manifest split metadata is invalid")
    version_context = manifest["version_context"]
    version_keys = {"approved_rubric_version", "prompt_versions", "retrieval_version", "embedding_model", "extractor_version", "model_ids"}
    if not isinstance(version_context, dict) or set(version_context) != version_keys:
        raise ValueError("manifest version_context has missing or unsupported fields")
    scalar_versions = version_keys - {"prompt_versions", "model_ids"}
    if any(not isinstance(version_context[key], str) or not version_context[key] for key in scalar_versions):
        raise ValueError("manifest version_context values must be nonempty version IDs")
    expected_providers = {"deepseek", "jev", "mock"}
    for map_name in ("prompt_versions", "model_ids"):
        versions = version_context[map_name]
        if not isinstance(versions, dict) or set(versions) != expected_providers:
            raise ValueError("manifest provider version maps must identify DeepSeek, Jev, and mock")
        if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._:/+-]{1,128}", value) for value in versions.values()):
            raise ValueError("manifest provider version identifiers must be short, safe labels")
    if manifest["data_scope"] == "synthetic_only":
        if version_context["prompt_versions"] != {"deepseek": "synthetic-assessment-v1", "jev": "synthetic-shadow-v1", "mock": "mock-v1"}:
            raise ValueError("synthetic fixture prompt versions must use the declared placeholders")
        if version_context["model_ids"] != {"deepseek": "deepseek-chat", "jev": "typesafe/jev-1.13", "mock": "mock"}:
            raise ValueError("synthetic fixture model IDs must use the declared placeholders")
    if set(manifest["split_sample_ids"]) != SPLITS or set(manifest["split_sha256"]) != SPLITS:
        raise ValueError("manifest must describe development and locked_holdout splits")
    try:
        lines = raw.decode("utf-8").splitlines()
        rows = [_validate_row(json.loads(line)) for line in lines if line.strip()]
    except UnicodeDecodeError as exc:
        raise ValueError("dataset must be UTF-8 JSONL") from exc
    if not rows:
        raise ValueError("dataset is empty")
    ids = [row["sample_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("sample IDs must be unique")
    actual_by_split = {split: sorted(row["sample_id"] for row in rows if row["split"] == split) for split in SPLITS}
    for split in sorted(SPLITS):
        listed = manifest["split_sample_ids"][split]
        if not isinstance(listed, list) or any(not isinstance(item, str) for item in listed) or sorted(listed) != actual_by_split[split]:
            raise ValueError("manifest split IDs do not match the dataset")
        digest = _sha256("\n".join(actual_by_split[split]).encode("utf-8"))
        if manifest["split_sha256"][split] != digest:
            raise ValueError("manifest split hash does not match the dataset")
    return rows, manifest


def _percentile(values: list[int | float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return float(ordered[max(0, math.ceil(quantile * len(ordered)) - 1)])


def _mean(values: list[int | float]) -> float | None:
    return sum(values) / len(values) if values else None


def _spearman(reference: list[float], predicted: list[float]) -> float | None:
    if len(reference) != len(predicted) or len(reference) < 2:
        return None

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=values.__getitem__)
        result = [0.0] * len(values)
        start = 0
        while start < len(order):
            end = start + 1
            while end < len(order) and values[order[end]] == values[order[start]]:
                end += 1
            average_rank = (start + 1 + end) / 2
            for position in range(start, end):
                result[order[position]] = average_rank
            start = end
        return result

    left, right = ranks(reference), ranks(predicted)
    left_mean, right_mean = _mean(left) or 0.0, _mean(right) or 0.0
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_sq = sum((x - left_mean) ** 2 for x in left)
    right_sq = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_sq * right_sq)
    return numerator / denominator if denominator else None


def _summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recalls5 = [recall_at_k(set(row["expected_span_ids"]), row["retrieved_span_ids"], 5) for row in rows]
    recalls10 = [recall_at_k(set(row["expected_span_ids"]), row["retrieved_span_ids"], 10) for row in rows]
    citations = [(item, row["retrieved_span_ids"]) for row in rows for item in row["citation_checks"]]
    score_reference: list[int] = []
    score_predicted: list[int] = []
    human_reference: list[int] = []
    human_second: list[int] = []
    rank_reference: list[float] = []
    rank_predicted: list[float] = []
    reference_assessable = 0
    for row in rows:
        ref, pred, second = row["reference_scores"], row["predicted_scores"], row["second_reviewer_scores"]
        reference_assessable += sum(value is not None for value in ref)
        model_pairs = [(r, p) for r, p in zip(ref, pred, strict=True) if r is not None and p is not None]
        human_pairs_for_row = [(r, h) for r, h in zip(ref, second, strict=True) if r is not None and h is not None]
        score_reference.extend(r for r, _ in model_pairs)
        score_predicted.extend(p for _, p in model_pairs)
        human_reference.extend(r for r, _ in human_pairs_for_row)
        human_second.extend(h for _, h in human_pairs_for_row)
        if model_pairs:
            rank_reference.append(sum(r for r, _ in model_pairs) / len(model_pairs))
            rank_predicted.append(sum(p for _, p in model_pairs) / len(model_pairs))
    qwk_pairs = list(zip(score_reference, score_predicted, strict=True))
    human_pairs = list(zip(human_reference, human_second, strict=True))
    unsupported = sum(not item["supported"] for item, _ in citations)
    citation_valid = sum(item["source_span_id"] in retrieved for item, retrieved in citations)
    latency = [row["assessment_latency_ms"] for row in rows]
    digital = [row for row in rows if row["file_class"] == "digital"]
    scanned = [row for row in rows if row["file_class"] == "scanned"]
    digital_success = [row for row in digital if row["extraction_status"] == "succeeded" and row["extraction_latency_ms"] <= 120_000]
    scanned_success = [row for row in scanned if row["extraction_status"] == "succeeded" and row["extraction_latency_ms"] <= 300_000]
    provider_failures = [row for row in rows if row["provider_status"] != "succeeded"]
    extraction_failures = [row for row in rows if row["extraction_status"] != "succeeded"]
    tool_counts = [row["agent_tool_count"] for row in rows]
    queue_wait = [row["queue_wait_ms"] for row in rows]
    provider_latency = [row["provider_latency_ms"] for row in rows]
    return {
        "sample_count": len(rows),
        "retrieval": {"recall_at_5": _mean(recalls5), "recall_at_10": _mean(recalls10)},
        "grounding": {
            "citation_validity": citation_valid / len(citations) if citations else None,
            "citation_count": len(citations),
            "unsupported_claim_rate": unsupported / len(citations) if citations else None,
        },
        "scoring": {
            "criterion_mae": criterion_mae(score_reference, score_predicted),
            "quadratic_weighted_kappa": quadratic_weighted_kappa(score_reference, score_predicted, scale=5),
            "human_human_quadratic_weighted_kappa": quadratic_weighted_kappa(human_reference, human_second, scale=5),
            "spearman_rank_correlation_diagnostic": _spearman(rank_reference, rank_predicted),
            "scorable_criterion_pairs": len(qwk_pairs),
            "human_human_scorable_criterion_pairs": len(human_pairs),
            "human_assessable_criterion_coverage": len(qwk_pairs) / reference_assessable if reference_assessable else None,
        },
        "fairness": {"counterfactual_invariance_rate": counterfactual_invariance_rate([
            {
                "counterfactual_pair_id": f"{row['provider_id']}_{row['role_id']}_{row['counterfactual_pair_id']}",
                "counterfactual_variant": row["counterfactual_variant"],
                "changed_attributes": row["changed_attributes"],
                "predicted_scores": row["predicted_scores"],
                "criterion_ids": row["criterion_ids"],
                "reference_scores": row["reference_scores"],
            }
            for row in rows if row["counterfactual_pair_id"]
        ])},
        "operations": {
            "assessment_latency_ms_p50": _percentile(latency, 0.50),
            "assessment_latency_ms_p95": _percentile(latency, 0.95),
            "assessment_within_2m_rate": sum(value <= 120_000 for value in latency) / len(latency),
            "queue_wait_ms_p50": _percentile(queue_wait, 0.50),
            "queue_wait_ms_p95": _percentile(queue_wait, 0.95),
            "provider_latency_ms_p50": _percentile(provider_latency, 0.50),
            "provider_latency_ms_p95": _percentile(provider_latency, 0.95),
            "digital_extraction_redaction_within_2m_rate": len(digital_success) / len(digital) if digital else None,
            "scanned_ocr_extraction_within_5m_rate": len(scanned_success) / len(scanned) if scanned else None,
            "extraction_failure_rate": len(extraction_failures) / len(rows),
            "provider_failure_count": len(provider_failures),
            "provider_failure_manual_review_rate": sum(row["result_state"] == "manual_review" for row in provider_failures) / len(provider_failures) if provider_failures else None,
            "extraction_failure_manual_review_rate": sum(row["result_state"] == "manual_review" for row in extraction_failures) / len(extraction_failures) if extraction_failures else None,
            "manual_review_count": sum(row["result_state"] == "manual_review" for row in rows),
            "agent_tool_count_mean": _mean(tool_counts),
            "agent_tool_count_p95": _percentile(tool_counts, 0.95),
        },
        "cost": {"estimated_cost_usd_total": sum(row["estimated_cost_usd"] for row in rows)},
    }


def _slo(value: float | None, predicate: Any) -> str:
    if value is None:
        return "NOT_EVALUABLE"
    return "PASS" if predicate(value) else "FAIL"


SLO_NAMES = (
    "retrieval_recall_at_5_at_least_0_85",
    "citation_validity_100_percent",
    "unsupported_claim_rate_zero",
    "criterion_mae_at_most_0_5",
    "weighted_agreement_at_least_0_60",
    "assessment_at_least_95_percent_within_2m",
    "digital_extraction_redaction_at_least_95_percent_within_2m",
    "scanned_ocr_at_least_95_percent_within_5m",
    "extraction_failure_below_5_percent",
    "provider_failures_route_to_manual_review",
    "extraction_failures_route_to_manual_review",
)


def _slo_checks(summary: dict[str, Any] | None) -> dict[str, str]:
    if summary is None:
        return {name: "NOT_EVALUABLE" for name in SLO_NAMES}
    operations = summary["operations"]
    return {
        "retrieval_recall_at_5_at_least_0_85": _slo(summary["retrieval"]["recall_at_5"], lambda x: x >= 0.85),
        "citation_validity_100_percent": _slo(summary["grounding"]["citation_validity"], lambda x: x == 1.0),
        "unsupported_claim_rate_zero": _slo(summary["grounding"]["unsupported_claim_rate"], lambda x: x == 0.0),
        "criterion_mae_at_most_0_5": _slo(summary["scoring"]["criterion_mae"], lambda x: x <= 0.5),
        "weighted_agreement_at_least_0_60": _slo(summary["scoring"]["quadratic_weighted_kappa"], lambda x: x >= 0.60),
        "assessment_at_least_95_percent_within_2m": _slo(operations["assessment_within_2m_rate"], lambda x: x >= 0.95),
        "digital_extraction_redaction_at_least_95_percent_within_2m": _slo(operations["digital_extraction_redaction_within_2m_rate"], lambda x: x >= 0.95),
        "scanned_ocr_at_least_95_percent_within_5m": _slo(operations["scanned_ocr_extraction_within_5m_rate"], lambda x: x >= 0.95),
        "extraction_failure_below_5_percent": _slo(operations["extraction_failure_rate"], lambda x: x < 0.05),
        "provider_failures_route_to_manual_review": _slo(operations["provider_failure_manual_review_rate"], lambda x: x == 1.0),
        "extraction_failures_route_to_manual_review": _slo(operations["extraction_failure_manual_review_rate"], lambda x: x == 1.0),
    }


def evaluate_dataset(dataset: Path, split: str = "development", minimum_group_size: int = 5) -> dict[str, Any]:
    if split not in SPLITS:
        raise ValueError("split must be development or locked_holdout")
    if type(minimum_group_size) is not int or minimum_group_size < 5:
        raise ValueError("minimum_group_size must be an integer >= 5")
    rows, manifest = _load_dataset(dataset)
    selected = sorted((row for row in rows if row["split"] == split), key=lambda row: (row["role_id"], row["provider_id"], row["sample_id"]))
    if not selected:
        raise ValueError("selected split is empty")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        groups[(row["role_id"], row["provider_id"])].append(row)
    provider_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in selected:
        provider_groups[row["provider_id"]].append(row)
    restricted = manifest["data_scope"] == "restricted_evaluation"
    minimum_group_size = minimum_group_size if restricted else 1

    def visible_summary(group: list[dict[str, Any]]) -> dict[str, Any] | None:
        return None if len(group) < minimum_group_size else _summarize_group(group)

    group_reports = []
    suppressed_role_group_count = 0
    for (role, provider), group in sorted(groups.items()):
        summary = visible_summary(group)
        if summary is None:
            suppressed_role_group_count += 1
            group_reports.append({"suppressed": True, "reason": "below_minimum_group_size"})
        else:
            group_reports.append({"role_id": role, "provider_id": provider, **summary})

    provider_summaries: dict[str, dict[str, Any] | None] = {
        provider: visible_summary(group) for provider, group in sorted(provider_groups.items())
    }
    slos_by_provider = {
        provider: _slo_checks(summary)
        for provider, summary in provider_summaries.items()
    }
    blockers = [
        (provider, name)
        for provider, checks in slos_by_provider.items()
        for name, status in checks.items()
        if status != "PASS"
    ]
    return {
        "report_schema_version": 1,
        "benchmark_id": manifest["benchmark_id"],
        "dataset_sha256": manifest["dataset_sha256"],
        "version_context": manifest["version_context"],
        "split": split,
        "data_scope": manifest["data_scope"],
        "minimum_group_size": minimum_group_size,
        "manifest_sha256": _sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")),
        "role_provider_aggregates": group_reports,
        "overall": (
            {"sample_count": len(selected), "provider_count": len(provider_summaries), "provider_aggregates": provider_summaries}
            if len(selected) >= minimum_group_size
            else {"suppressed": True, "reason": "below_minimum_group_size"}
        ),
        "provisional_slo_checks_by_provider": slos_by_provider,
        "suppressed_role_provider_group_count": suppressed_role_group_count,
        "manual_fallback_recommended": bool(blockers),
        "failed_or_unevaluable_slo_count": len(blockers),
        "readiness": "NOT_AUTHORIZED_FOR_LIVE_DECISIONS",
        "interpretation": "Synthetic benchmark output is a harness check only; it cannot establish job-family validity or authorize hiring decisions.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--split", choices=sorted(SPLITS), default="development")
    parser.add_argument("--minimum-group-size", type=int, default=5)
    parser.add_argument("--allow-locked-holdout", action="store_true")
    args = parser.parse_args()
    if args.split == "locked_holdout" and not args.allow_locked_holdout:
        parser.error("locked_holdout requires explicit --allow-locked-holdout after thresholds are approved")
    if args.dataset.resolve() == args.output.resolve():
        parser.error("output must not overwrite the dataset")
    try:
        report = evaluate_dataset(args.dataset, args.split, args.minimum_group_size)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"split": args.split, "sample_count": report["overall"].get("sample_count"), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
