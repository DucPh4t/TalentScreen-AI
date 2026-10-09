#!/usr/bin/env python3
"""Evaluate a sanitized, schema-limited RAG benchmark and emit aggregates only."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "backend"))

from app.services.evaluation.metrics import (  # noqa: E402
    criterion_mae,
    counterfactual_invariance_rate,
    linear_weighted_kappa,
    quadratic_weighted_kappa,
    recall_at_k,
)

ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
ROLE_ID_RE = re.compile(r"^role_[a-z][a-z0-9_]{1,58}$")
SAFE_VERSION_RE = re.compile(r"^[A-Za-z0-9._:/+-]{1,128}$")
FLOATING_VERSION_RE = re.compile(r"^(main|master|latest|stable|head|current|dev|default)$", re.IGNORECASE)
PROVIDERS = {"deepseek", "jev", "mock"}
SPLITS = {"development", "locked_holdout"}
TOP_KEYS = {
    "sample_id", "split", "role_id", "provider_id", "criterion_ids",
    "criterion_evidence", "criterion_claims",
    "reference_scores", "predicted_scores", "second_reviewer_scores",
    "counterfactual_pair_id", "counterfactual_variant", "changed_attributes",
    "assessment_latency_ms", "queue_wait_ms", "provider_latency_ms", "extraction_latency_ms",
    "sanitized_ready_latency_ms", "estimated_cost_usd",
    "agent_tool_count", "file_class", "extraction_status", "provider_status",
    "sanitization_status", "result_state",
}
EVIDENCE_KEYS = {"criterion_id", "expected_span_ids", "sufficient_evidence_groups", "retrieved_span_ids"}
CLAIM_KEYS = {"criterion_id", "source_span_ids", "supported"}
MANIFEST_KEYS = {
    "benchmark_id", "schema_version", "data_scope", "dataset_sha256", "split_sample_ids",
    "split_sha256", "evaluation_clusters", "version_context",
}
ALLOWED_CHANGED_ATTRIBUTES = {"name", "pronoun", "hometown", "school"}
VERSION_CONTEXT_KEYS = {
    "approved_rubric_version", "prompt_versions", "prompt_sha256", "retrieval_version",
    "retrieval_revision", "embedding_model", "embedding_revision", "extractor_version", "model_ids",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValueError(f"{field} must be a stable lowercase ID")
    return value


def _version_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SAFE_VERSION_RE.fullmatch(value):
        raise ValueError(f"{field} must be a short safe version identifier")
    if FLOATING_VERSION_RE.fullmatch(value):
        raise ValueError(f"{field} cannot use a floating version such as main/latest")
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
    if not isinstance(row["role_id"], str) or not ROLE_ID_RE.fullmatch(row["role_id"]):
        raise ValueError("role_id must be an opaque role-family ID prefixed with role_")
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

    for field in ("reference_scores", "predicted_scores", "second_reviewer_scores"):
        row[field] = _score_vector(row[field], field, len(criteria))

    evidence = row["criterion_evidence"]
    claims = row["criterion_claims"]
    if not isinstance(evidence, list) or len(evidence) != len(criteria):
        raise ValueError("criterion_evidence must contain one item per criterion")
    if not isinstance(claims, list) or len(claims) != len(criteria):
        raise ValueError("criterion_claims must contain one item per criterion")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    claims_by_id: dict[str, dict[str, Any]] = {}
    for item in evidence:
        if not isinstance(item, dict) or set(item) != EVIDENCE_KEYS:
            raise ValueError("criterion evidence has missing or unsupported fields")
        criterion_id = _slug(item["criterion_id"], "criterion evidence ID")
        if criterion_id not in criteria or criterion_id in evidence_by_id:
            raise ValueError("criterion evidence IDs must align uniquely with criterion_ids")
        expected = item["expected_span_ids"]
        retrieved = item["retrieved_span_ids"]
        groups = item["sufficient_evidence_groups"]
        if not isinstance(expected, list) or not isinstance(retrieved, list) or not isinstance(groups, list):
            raise ValueError("criterion evidence span and sufficient-evidence fields must be lists")
        for span_id in expected + retrieved:
            _slug(span_id, "source span ID")
        if len(expected) != len(set(expected)) or len(retrieved) != len(set(retrieved)):
            raise ValueError("criterion span ID lists must not contain duplicates")
        if (not expected and groups) or (expected and not groups):
            raise ValueError("sufficient-evidence groups must exist exactly when expected evidence is labeled")
        for group in groups:
            if not isinstance(group, list) or not group:
                raise ValueError("sufficient-evidence groups must be nonempty lists")
            for span_id in group:
                _slug(span_id, "sufficient-evidence span ID")
            if len(group) != len(set(group)) or not set(group).issubset(expected):
                raise ValueError("sufficient-evidence groups must be unique subsets of expected spans")
        evidence_by_id[criterion_id] = item
    for item in claims:
        if not isinstance(item, dict) or set(item) != CLAIM_KEYS:
            raise ValueError("criterion claim has missing or unsupported fields")
        criterion_id = _slug(item["criterion_id"], "criterion claim ID")
        if criterion_id not in criteria or criterion_id in claims_by_id:
            raise ValueError("criterion claim IDs must align uniquely with criterion_ids")
        source_span_ids = item["source_span_ids"]
        if not isinstance(source_span_ids, list):
            raise ValueError("criterion claim source_span_ids must be a list")
        for span_id in source_span_ids:
            _slug(span_id, "claim source span ID")
        if len(source_span_ids) != len(set(source_span_ids)):
            raise ValueError("criterion claim source spans must be unique")
        if item["supported"] is not None and type(item["supported"]) is not bool:
            raise ValueError("criterion claim supported must be true, false, or null")
        claims_by_id[criterion_id] = item
    if set(evidence_by_id) != set(criteria) or set(claims_by_id) != set(criteria):
        raise ValueError("criterion evidence and claim IDs must exactly match criterion_ids")
    for index, criterion_id in enumerate(criteria):
        claim = claims_by_id[criterion_id]
        predicted = row["predicted_scores"][index]
        if predicted is None:
            if claim["supported"] is not None or claim["source_span_ids"]:
                raise ValueError("unscored criteria must not carry a scored claim or citations")
        elif type(claim["supported"]) is not bool:
            raise ValueError("every non-null score needs an explicit support label")
        elif claim["supported"] and not claim["source_span_ids"]:
            raise ValueError("a supported scored criterion needs at least one citation")
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
    if type(row["sanitized_ready_latency_ms"]) is not int or row["sanitized_ready_latency_ms"] < 0:
        raise ValueError("sanitized_ready_latency_ms must be a nonnegative integer")
    cost = row["estimated_cost_usd"]
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
        raise ValueError("estimated_cost_usd must be a finite nonnegative number")
    if not isinstance(row["file_class"], str) or row["file_class"] not in {"digital", "scanned"}:
        raise ValueError("file_class must be digital or scanned")
    if not isinstance(row["extraction_status"], str) or row["extraction_status"] not in {"succeeded", "failed", "ocr_failed"}:
        raise ValueError("extraction_status is unsupported")
    if not isinstance(row["sanitization_status"], str) or row["sanitization_status"] not in {"succeeded", "failed", "manual_review"}:
        raise ValueError("sanitization_status is unsupported")
    if not isinstance(row["provider_status"], str) or row["provider_status"] not in {"succeeded", "failed", "timeout", "invalid_output"}:
        raise ValueError("provider_status is unsupported")
    if not isinstance(row["result_state"], str) or row["result_state"] not in {"accepted", "manual_review"}:
        raise ValueError("result_state is unsupported")
    failure = (
        row["provider_status"] != "succeeded"
        or row["extraction_status"] != "succeeded"
        or row["sanitization_status"] != "succeeded"
    )
    if failure and row["result_state"] != "manual_review":
        raise ValueError("provider, extraction, and sanitization failures must route to manual_review")
    if failure and any(score is not None for score in row["predicted_scores"]):
        raise ValueError("failed provider, extraction, or sanitization rows must not contain predicted scores")
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
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 2 or manifest["dataset_sha256"] != _sha256(raw):
        raise ValueError("dataset schema version or hash does not match manifest")
    if not isinstance(manifest["split_sample_ids"], dict) or not isinstance(manifest["split_sha256"], dict):
        raise ValueError("manifest split metadata is invalid")
    version_context = manifest["version_context"]
    if not isinstance(version_context, dict) or set(version_context) != VERSION_CONTEXT_KEYS:
        raise ValueError("manifest version_context has missing or unsupported fields")
    scalar_versions = VERSION_CONTEXT_KEYS - {"prompt_versions", "prompt_sha256", "model_ids"}
    for key in scalar_versions:
        _version_id(version_context[key], f"version_context.{key}")
    expected_providers = {"deepseek", "jev", "mock"}
    for map_name in ("prompt_versions", "model_ids"):
        versions = version_context[map_name]
        if not isinstance(versions, dict) or set(versions) != expected_providers:
            raise ValueError("manifest provider version maps must identify DeepSeek, Jev, and mock")
        for value in versions.values():
            _version_id(value, f"version_context.{map_name}")
    prompt_hashes = version_context["prompt_sha256"]
    if not isinstance(prompt_hashes, dict) or set(prompt_hashes) != expected_providers:
        raise ValueError("manifest prompt_sha256 must identify DeepSeek, Jev, and mock")
    if any(not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value) for value in prompt_hashes.values()):
        raise ValueError("manifest prompt_sha256 values must be lowercase SHA-256 digests")
    if manifest["data_scope"] == "synthetic_only":
        if version_context["prompt_versions"] != {"deepseek": "synthetic-assessment-v1", "jev": "synthetic-shadow-v1", "mock": "mock-v1"}:
            raise ValueError("synthetic fixture prompt versions must use the declared placeholders")
        if version_context["model_ids"] != {"deepseek": "deepseek-chat", "jev": "typesafe/jev-1.13", "mock": "mock"}:
            raise ValueError("synthetic fixture model IDs must use the declared placeholders")
        if version_context["embedding_revision"] != "synthetic-e5-revision-v1" or version_context["retrieval_revision"] != "synthetic-code-revision-v1":
            raise ValueError("synthetic fixture revisions must use the declared placeholders")
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
    evaluation_clusters = manifest["evaluation_clusters"]
    if not isinstance(evaluation_clusters, dict) or set(evaluation_clusters) != set(ids):
        raise ValueError("manifest evaluation_clusters must map every sample ID to one opaque cluster ID")
    for row in rows:
        row["evaluation_cluster_id"] = _slug(evaluation_clusters[row["sample_id"]], "evaluation cluster ID")
    cluster_splits: dict[str, str] = {}
    pair_clusters: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        cluster = row["evaluation_cluster_id"]
        previous_split = cluster_splits.setdefault(cluster, row["split"])
        if previous_split != row["split"]:
            raise ValueError("an evaluation cluster cannot cross development and locked_holdout splits")
        if row["counterfactual_pair_id"]:
            pair_clusters[row["counterfactual_pair_id"]].add(cluster)
    if any(len(clusters) != 1 for clusters in pair_clusters.values()):
        raise ValueError("counterfactual variants must belong to the same evaluation cluster")
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


def _cluster_bootstrap_interval(
    rows: list[dict[str, Any]], statistic: Callable[[list[dict[str, Any]]], float | None]
) -> list[float] | None:
    """Deterministic candidate-cluster bootstrap percentile interval (95%)."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["evaluation_cluster_id"]].append(row)
    clusters = list(grouped.values())
    if len(clusters) < 2:
        return None
    rng = random.Random(1729)
    estimates: list[float] = []
    for _ in range(1000):
        sampled = [rng.choice(clusters) for _ in clusters]
        sample_rows = [row for cluster in sampled for row in cluster]
        value = statistic(sample_rows)
        if value is not None and math.isfinite(value):
            estimates.append(value)
    if len(estimates) < 200:
        return None
    estimates.sort()
    return [
        estimates[max(0, math.ceil(0.025 * len(estimates)) - 1)],
        estimates[max(0, math.ceil(0.975 * len(estimates)) - 1)],
    ]


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
    evidence_queries: list[dict[str, Any]] = [
        item for row in rows for item in row["criterion_evidence"] if item["expected_span_ids"]
    ]
    recalls5 = [recall_at_k(set(item["expected_span_ids"]), item["retrieved_span_ids"], 5) for item in evidence_queries]
    recalls10 = [recall_at_k(set(item["expected_span_ids"]), item["retrieved_span_ids"], 10) for item in evidence_queries]
    sufficient5 = [
        any(set(group).issubset(item["retrieved_span_ids"][:5]) for group in item["sufficient_evidence_groups"])
        for item in evidence_queries
    ]
    sufficient10 = [
        any(set(group).issubset(item["retrieved_span_ids"][:10]) for group in item["sufficient_evidence_groups"])
        for item in evidence_queries
    ]
    evidence_by_row = [
        (row, {item["criterion_id"]: item for item in row["criterion_evidence"]}) for row in rows
    ]
    claims = [
        (row, item, evidence_by_criterion[item["criterion_id"]])
        for row, evidence_by_criterion in evidence_by_row
        for item in row["criterion_claims"]
        if item["supported"] is not None
    ]
    citations = [
        (span_id, evidence["retrieved_span_ids"])
        for _row, claim, evidence in claims
        for span_id in claim["source_span_ids"]
    ]
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
    unsupported = sum(claim["supported"] is False for _row, claim, _evidence in claims)
    citation_valid = sum(span_id in retrieved for span_id, retrieved in citations)
    latency = [row["assessment_latency_ms"] for row in rows]
    digital = [row for row in rows if row["file_class"] == "digital"]
    scanned = [row for row in rows if row["file_class"] == "scanned"]
    digital_success = [row for row in digital if row["sanitization_status"] == "succeeded" and row["sanitized_ready_latency_ms"] <= 120_000]
    scanned_success = [row for row in scanned if row["extraction_status"] == "succeeded" and row["extraction_latency_ms"] <= 300_000]
    provider_failures = [row for row in rows if row["provider_status"] != "succeeded"]
    extraction_failures = [row for row in rows if row["extraction_status"] != "succeeded"]
    sanitization_failures = [row for row in rows if row["sanitization_status"] != "succeeded"]
    tool_counts = [row["agent_tool_count"] for row in rows]
    queue_wait = [row["queue_wait_ms"] for row in rows]
    provider_latency = [row["provider_latency_ms"] for row in rows]
    assessment_within_2m = [row["result_state"] == "accepted" and row["assessment_latency_ms"] <= 120_000 for row in rows]
    assessment_within_5m = [row["result_state"] == "accepted" and row["assessment_latency_ms"] <= 300_000 for row in rows]
    sanitized_within_5m = [row["sanitization_status"] == "succeeded" and row["sanitized_ready_latency_ms"] <= 300_000 for row in rows]

    def _retrieval_rate(batch: list[dict[str, Any]], k: int, sufficient: bool = False) -> float | None:
        values: list[int | float] = []
        for candidate in batch:
            for item in candidate["criterion_evidence"]:
                if not item["expected_span_ids"]:
                    continue
                if sufficient:
                    values.append(int(any(
                        set(group).issubset(item["retrieved_span_ids"][:k])
                        for group in item["sufficient_evidence_groups"]
                    )))
                else:
                    values.append(recall_at_k(set(item["expected_span_ids"]), item["retrieved_span_ids"], k))
        return _mean(values)

    def _score_vectors(batch: list[dict[str, Any]], right_field: str) -> tuple[list[int], list[int]]:
        left: list[int] = []
        right: list[int] = []
        for candidate in batch:
            for expected, actual in zip(candidate["reference_scores"], candidate[right_field], strict=True):
                if expected is not None and actual is not None:
                    left.append(expected)
                    right.append(actual)
        return left, right

    def _score_statistic(batch: list[dict[str, Any]], right_field: str, kind: str) -> float | None:
        left, right = _score_vectors(batch, right_field)
        if kind == "mae":
            return criterion_mae(left, right) if left else None
        if kind == "linear_kappa":
            return linear_weighted_kappa(left, right, scale=5)
        return quadratic_weighted_kappa(left, right, scale=5)

    def _grounding_rate(batch: list[dict[str, Any]], unsupported_rate: bool) -> float | None:
        supported_claims = 0
        unsupported_claims = 0
        valid_citations = 0
        citation_count = 0
        for candidate in batch:
            evidence_map = {item["criterion_id"]: item for item in candidate["criterion_evidence"]}
            for claim in candidate["criterion_claims"]:
                if claim["supported"] is None:
                    continue
                supported_claims += 1
                unsupported_claims += claim["supported"] is False
                retrieved = evidence_map[claim["criterion_id"]]["retrieved_span_ids"]
                for span_id in claim["source_span_ids"]:
                    citation_count += 1
                    valid_citations += span_id in retrieved
        denominator = supported_claims if unsupported_rate else citation_count
        if not denominator:
            return None
        return (unsupported_claims if unsupported_rate else valid_citations) / denominator

    def _operational_rate(batch: list[dict[str, Any]], field: str) -> float | None:
        if field == "assessment_2m":
            values = [row["result_state"] == "accepted" and row["assessment_latency_ms"] <= 120_000 for row in batch]
        elif field == "assessment_5m":
            values = [row["result_state"] == "accepted" and row["assessment_latency_ms"] <= 300_000 for row in batch]
        elif field == "sanitized_2m":
            subset = [row for row in batch if row["file_class"] == "digital"]
            if not subset:
                return None
            values = [row["sanitization_status"] == "succeeded" and row["sanitized_ready_latency_ms"] <= 120_000 for row in subset]
        elif field == "sanitized_5m":
            values = [row["sanitization_status"] == "succeeded" and row["sanitized_ready_latency_ms"] <= 300_000 for row in batch]
        elif field == "ocr_5m":
            subset = [row for row in batch if row["file_class"] == "scanned"]
            if not subset:
                return None
            values = [row["extraction_status"] == "succeeded" and row["extraction_latency_ms"] <= 300_000 for row in subset]
        else:
            values = [row["extraction_status"] != "succeeded" for row in batch]
        return _mean([int(value) for value in values])

    confidence_intervals = {
        "retrieval.recall_at_5": _cluster_bootstrap_interval(rows, lambda batch: _retrieval_rate(batch, 5)),
        "retrieval.sufficient_evidence_at_5_rate": _cluster_bootstrap_interval(rows, lambda batch: _retrieval_rate(batch, 5, True)),
        "grounding.citation_validity": _cluster_bootstrap_interval(rows, lambda batch: _grounding_rate(batch, False)),
        "grounding.unsupported_claim_rate": _cluster_bootstrap_interval(rows, lambda batch: _grounding_rate(batch, True)),
        "scoring.criterion_mae": _cluster_bootstrap_interval(rows, lambda batch: _score_statistic(batch, "predicted_scores", "mae")),
        "scoring.quadratic_weighted_kappa": _cluster_bootstrap_interval(rows, lambda batch: _score_statistic(batch, "predicted_scores", "quadratic_kappa")),
        "scoring.linear_weighted_kappa": _cluster_bootstrap_interval(rows, lambda batch: _score_statistic(batch, "predicted_scores", "linear_kappa")),
        "scoring.human_human_quadratic_weighted_kappa": _cluster_bootstrap_interval(rows, lambda batch: _score_statistic(batch, "second_reviewer_scores", "quadratic_kappa")),
        "scoring.human_human_linear_weighted_kappa": _cluster_bootstrap_interval(rows, lambda batch: _score_statistic(batch, "second_reviewer_scores", "linear_kappa")),
        "operations.assessment_ready_within_2m_rate": _cluster_bootstrap_interval(rows, lambda batch: _operational_rate(batch, "assessment_2m")),
        "operations.assessment_ready_within_5m_rate": _cluster_bootstrap_interval(rows, lambda batch: _operational_rate(batch, "assessment_5m")),
        "operations.digital_sanitized_ready_within_2m_rate": _cluster_bootstrap_interval(rows, lambda batch: _operational_rate(batch, "sanitized_2m")),
        "operations.upload_to_sanitized_ready_within_5m_rate": _cluster_bootstrap_interval(rows, lambda batch: _operational_rate(batch, "sanitized_5m")),
        "operations.scanned_ocr_extraction_within_5m_rate": _cluster_bootstrap_interval(rows, lambda batch: _operational_rate(batch, "ocr_5m")),
        "operations.extraction_failure_rate": _cluster_bootstrap_interval(rows, lambda batch: _operational_rate(batch, "extraction_failure")),
    }
    independent_cluster_count = len({row["evaluation_cluster_id"] for row in rows})
    return {
        "sample_count": len(rows),
        "uncertainty": {
            "independent_candidate_cluster_count": independent_cluster_count,
            "confidence_interval_method": "candidate-cluster bootstrap percentile 95%, 1000 replicates, deterministic seed 1729",
            "confidence_intervals_95": confidence_intervals,
        },
        "retrieval": {
            "evidence_query_count": len(evidence_queries),
            "recall_at_5": _mean(recalls5),
            "recall_at_10": _mean(recalls10),
            "sufficient_evidence_at_5_rate": _mean([int(value) for value in sufficient5]),
            "sufficient_evidence_at_10_rate": _mean([int(value) for value in sufficient10]),
        },
        "grounding": {
            "citation_validity": citation_valid / len(citations) if citations else None,
            "citation_count": len(citations),
            "scored_criterion_count": len(claims),
            "unsupported_criterion_count": unsupported,
            "unsupported_claim_rate": unsupported / len(claims) if claims else None,
        },
        "scoring": {
            "criterion_mae": criterion_mae(score_reference, score_predicted),
            "quadratic_weighted_kappa": quadratic_weighted_kappa(score_reference, score_predicted, scale=5),
            "linear_weighted_kappa": linear_weighted_kappa(score_reference, score_predicted, scale=5),
            "human_human_quadratic_weighted_kappa": quadratic_weighted_kappa(human_reference, human_second, scale=5),
            "human_human_linear_weighted_kappa": linear_weighted_kappa(human_reference, human_second, scale=5),
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
            "assessment_ready_within_2m_rate": _mean([int(value) for value in assessment_within_2m]),
            "assessment_ready_within_2m_count": sum(assessment_within_2m),
            "assessment_job_count": len(rows),
            "assessment_ready_within_5m_rate": _mean([int(value) for value in assessment_within_5m]),
            "assessment_ready_within_5m_count": sum(assessment_within_5m),
            "queue_wait_ms_p50": _percentile(queue_wait, 0.50),
            "queue_wait_ms_p95": _percentile(queue_wait, 0.95),
            "provider_latency_ms_p50": _percentile(provider_latency, 0.50),
            "provider_latency_ms_p95": _percentile(provider_latency, 0.95),
            "digital_sanitized_ready_within_2m_rate": len(digital_success) / len(digital) if digital else None,
            "digital_sanitized_ready_within_2m_count": len(digital_success),
            "digital_document_count": len(digital),
            "scanned_ocr_extraction_within_5m_rate": len(scanned_success) / len(scanned) if scanned else None,
            "scanned_ocr_extraction_within_5m_count": len(scanned_success),
            "scanned_document_count": len(scanned),
            "upload_to_sanitized_ready_within_5m_rate": _mean([int(value) for value in sanitized_within_5m]),
            "upload_to_sanitized_ready_within_5m_count": sum(sanitized_within_5m),
            "document_count": len(rows),
            "extraction_failure_rate": len(extraction_failures) / len(rows),
            "extraction_failure_count": len(extraction_failures),
            "sanitization_failure_count": len(sanitization_failures),
            "provider_failure_count": len(provider_failures),
            "provider_failure_manual_review_rate": sum(row["result_state"] == "manual_review" for row in provider_failures) / len(provider_failures) if provider_failures else None,
            "extraction_failure_manual_review_rate": sum(row["result_state"] == "manual_review" for row in extraction_failures) / len(extraction_failures) if extraction_failures else None,
            "sanitization_failure_manual_review_rate": sum(row["result_state"] == "manual_review" for row in sanitization_failures) / len(sanitization_failures) if sanitization_failures else None,
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


RAG_DESIGN_PROFILE = "rag_design_candidate_v1"
MVP_P1_PROFILE = "mvp_p1_candidate_v1"


def _slo_checks(summary: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    rag_names = (
        "retrieval_recall_at_5_at_least_0_85",
        "citation_validity_100_percent",
        "unsupported_claim_rate_zero",
        "criterion_mae_at_most_0_5",
        "quadratic_weighted_kappa_at_least_0_60",
        "assessment_ready_at_least_95_percent_within_2m",
        "digital_sanitized_ready_at_least_95_percent_within_2m",
        "scanned_ocr_at_least_95_percent_within_5m",
        "extraction_failure_below_5_percent",
        "provider_failures_route_to_manual_review",
        "extraction_failures_route_to_manual_review",
        "sanitization_failures_route_to_manual_review",
    )
    mvp_names = (
        "criterion_mae_at_most_0_75",
        "human_assessable_coverage_at_least_0_85",
        "linear_weighted_kappa_at_least_0_60",
        "assessment_ready_at_least_95_percent_within_5m",
        "upload_to_sanitized_ready_at_least_95_percent_within_5m",
        "scanned_ocr_at_least_95_percent_within_5m",
        "extraction_failure_below_5_percent",
        "provider_failures_route_to_manual_review",
        "extraction_failures_route_to_manual_review",
        "sanitization_failures_route_to_manual_review",
    )
    if summary is None:
        return {
            RAG_DESIGN_PROFILE: {name: "NOT_EVALUABLE" for name in rag_names},
            MVP_P1_PROFILE: {name: "NOT_EVALUABLE" for name in mvp_names},
        }
    operations = summary["operations"]
    route = {
        "provider_failures_route_to_manual_review": operations["provider_failure_manual_review_rate"],
        "extraction_failures_route_to_manual_review": operations["extraction_failure_manual_review_rate"],
        "sanitization_failures_route_to_manual_review": operations["sanitization_failure_manual_review_rate"],
    }
    rag = {
        "retrieval_recall_at_5_at_least_0_85": _slo(summary["retrieval"]["recall_at_5"], lambda x: x >= 0.85),
        "citation_validity_100_percent": _slo(summary["grounding"]["citation_validity"], lambda x: x == 1.0),
        "unsupported_claim_rate_zero": _slo(summary["grounding"]["unsupported_claim_rate"], lambda x: x == 0.0),
        "criterion_mae_at_most_0_5": _slo(summary["scoring"]["criterion_mae"], lambda x: x <= 0.5),
        "quadratic_weighted_kappa_at_least_0_60": _slo(summary["scoring"]["quadratic_weighted_kappa"], lambda x: x >= 0.60),
        "assessment_ready_at_least_95_percent_within_2m": _slo(operations["assessment_ready_within_2m_rate"], lambda x: x >= 0.95),
        "digital_sanitized_ready_at_least_95_percent_within_2m": _slo(operations["digital_sanitized_ready_within_2m_rate"], lambda x: x >= 0.95),
        "scanned_ocr_at_least_95_percent_within_5m": _slo(operations["scanned_ocr_extraction_within_5m_rate"], lambda x: x >= 0.95),
        "extraction_failure_below_5_percent": _slo(operations["extraction_failure_rate"], lambda x: x < 0.05),
        **{name: _slo(value, lambda x: x == 1.0) for name, value in route.items()},
    }
    mvp = {
        "criterion_mae_at_most_0_75": _slo(summary["scoring"]["criterion_mae"], lambda x: x <= 0.75),
        "human_assessable_coverage_at_least_0_85": _slo(summary["scoring"]["human_assessable_criterion_coverage"], lambda x: x >= 0.85),
        "linear_weighted_kappa_at_least_0_60": _slo(summary["scoring"]["linear_weighted_kappa"], lambda x: x >= 0.60),
        "assessment_ready_at_least_95_percent_within_5m": _slo(operations["assessment_ready_within_5m_rate"], lambda x: x >= 0.95),
        "upload_to_sanitized_ready_at_least_95_percent_within_5m": _slo(operations["upload_to_sanitized_ready_within_5m_rate"], lambda x: x >= 0.95),
        "scanned_ocr_at_least_95_percent_within_5m": _slo(operations["scanned_ocr_extraction_within_5m_rate"], lambda x: x >= 0.95),
        "extraction_failure_below_5_percent": _slo(operations["extraction_failure_rate"], lambda x: x < 0.05),
        **{name: _slo(value, lambda x: x == 1.0) for name, value in route.items()},
    }
    return {RAG_DESIGN_PROFILE: rag, MVP_P1_PROFILE: mvp}


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
    role_provider_checks = []
    suppressed_role_group_count = 0
    primary_fallback_scopes: list[dict[str, Any]] = []
    primary_provider_seen = False
    jev_profile_statuses: list[str] = []
    for (role, provider), group in sorted(groups.items()):
        if provider == "deepseek":
            primary_provider_seen = True
        summary = visible_summary(group)
        profiles = _slo_checks(summary)
        if summary is None:
            suppressed_role_group_count += 1
            group_reports.append({"suppressed": True, "reason": "below_minimum_group_size"})
            role_provider_checks.append({"suppressed": True, "reason": "below_minimum_group_size", "profiles": profiles})
        else:
            group_reports.append({"role_id": role, "provider_id": provider, **summary, "provisional_profiles": profiles})
            role_provider_checks.append({"role_id": role, "provider_id": provider, "profiles": profiles})
        if provider == "deepseek" and any(
            status != "PASS" for profile in profiles.values() for status in profile.values()
        ):
            fallback_scope: dict[str, Any] = {"provider_id": provider, "profiles": profiles}
            if summary is None:
                fallback_scope.update({"suppressed": True, "reason": "below_minimum_group_size"})
            else:
                fallback_scope["role_id"] = role
            primary_fallback_scopes.append(fallback_scope)
        if provider == "jev":
            jev_profile_statuses.extend(status for profile in profiles.values() for status in profile.values())

    provider_summaries: dict[str, dict[str, Any] | None] = {
        provider: visible_summary(group) for provider, group in sorted(provider_groups.items())
    }
    provider_checks = {
        provider: _slo_checks(summary)
        for provider, summary in provider_summaries.items()
    }
    manual_fallback = not primary_provider_seen or bool(primary_fallback_scopes)
    jev_shadow_status = (
        "NOT_RUN" if "jev" not in provider_groups
        else "COMPLETE_PROVISIONALLY" if jev_profile_statuses and all(status == "PASS" for status in jev_profile_statuses)
        else "INCOMPLETE"
    )
    return {
        "report_schema_version": 2,
        "benchmark_id": manifest["benchmark_id"] if not restricted else "restricted_evaluation",
        "dataset_sha256": manifest["dataset_sha256"],
        "version_context": manifest["version_context"],
        "version_context_status": "SYNTHETIC_PLACEHOLDERS" if manifest["data_scope"] == "synthetic_only" else "MANIFEST_ASSERTED_NOT_EXTERNALLY_VERIFIED",
        "split": split,
        "data_scope": manifest["data_scope"],
        "minimum_group_size": minimum_group_size,
        "manifest_sha256": _sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")),
        "role_provider_aggregates": group_reports,
        "provisional_slo_checks_by_role_provider": role_provider_checks,
        "overall": (
            {"sample_count": len(selected), "provider_count": len(provider_summaries), "provider_aggregates": provider_summaries}
            if len(selected) >= minimum_group_size
            else {"suppressed": True, "reason": "below_minimum_group_size"}
        ),
        "provisional_slo_checks_by_provider": provider_checks,
        "suppressed_role_provider_group_count": suppressed_role_group_count,
        "threshold_profiles": {
            RAG_DESIGN_PROFILE: {
                "state": "PROVISIONAL_NOT_APPROVED",
                "source": "docs/superpowers/specs/2026-10-06-rag-agent-talent-screen-design.md §10.3–10.4",
            },
            MVP_P1_PROFILE: {
                "state": "PROVISIONAL_NOT_APPROVED",
                "source": "docs/evaluation/legacy-mvp-evaluation-policy.md and legacy-mvp-operations-policy.md",
            },
        },
        "manual_fallback_recommended": manual_fallback,
        "manual_fallback_scopes": primary_fallback_scopes,
        "jev_shadow_status": jev_shadow_status,
        "failed_or_unevaluable_slo_count": sum(
            status != "PASS"
            for scope in role_provider_checks
            for profile in scope["profiles"].values()
            for status in profile.values()
        ),
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
