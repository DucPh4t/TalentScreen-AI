"""Small, dependency-free metrics used by the reproducible RAG benchmark."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def recall_at_k(expected_span_ids: set[str], retrieved_span_ids: list[str], k: int) -> float:
    """Return the fraction of labeled relevant spans present in the top ``k``."""
    if k < 1:
        raise ValueError("k must be positive")
    if not expected_span_ids:
        raise ValueError("expected_span_ids must not be empty")
    if any(not isinstance(span_id, str) or not span_id for span_id in expected_span_ids):
        raise ValueError("expected span IDs must be nonempty strings")
    if any(not isinstance(span_id, str) or not span_id for span_id in retrieved_span_ids):
        raise ValueError("retrieved span IDs must be nonempty strings")
    return len(expected_span_ids.intersection(retrieved_span_ids[:k])) / len(expected_span_ids)


def criterion_mae(
    reference: list[int | None], predicted: list[int | None]
) -> float | None:
    """MAE on paired 0..4 labels; jointly missing scores are excluded."""
    if len(reference) != len(predicted):
        raise ValueError("reference and predicted must have equal length")
    pairs: list[tuple[int, int]] = []
    for expected, actual in zip(reference, predicted, strict=True):
        if expected is None and actual is None:
            continue
        if expected is None or actual is None:
            raise ValueError("one-sided missing label")
        if type(expected) is not int or type(actual) is not int or not (0 <= expected <= 4 and 0 <= actual <= 4):
            raise ValueError("criterion scores must be integer anchors 0..4 or null")
        pairs.append((expected, actual))
    if not pairs:
        return None
    return sum(abs(expected - actual) for expected, actual in pairs) / len(pairs)


def quadratic_weighted_kappa(
    reference: list[int], predicted: list[int], scale: int = 5
) -> float | None:
    """Quadratic weighted Cohen's kappa for integer categories ``0..scale-1``.

    Returns ``None`` for empty input or a degenerate expected-disagreement
    denominator. ``scale`` is the number of ordered categories, not a max score.
    """
    if len(reference) != len(predicted):
        raise ValueError("reference and predicted must have equal length")
    if type(scale) is not int or scale < 2:
        raise ValueError("scale must be an integer >= 2")
    if not reference:
        return None
    if any(type(value) is not int or not 0 <= value < scale for value in reference + predicted):
        raise ValueError(f"scores must be integer categories 0..{scale - 1}")

    n = len(reference)
    observed_disagreement = sum(
        ((expected - actual) / (scale - 1)) ** 2
        for expected, actual in zip(reference, predicted, strict=True)
    ) / n
    reference_counts = Counter(reference)
    predicted_counts = Counter(predicted)
    expected_disagreement = sum(
        reference_counts[i] * predicted_counts[j] * ((i - j) / (scale - 1)) ** 2
        for i in range(scale)
        for j in range(scale)
    ) / (n * n)
    if expected_disagreement == 0:
        return None
    return 1.0 - observed_disagreement / expected_disagreement


def counterfactual_invariance_rate(evaluations: list[dict[str, Any]]) -> float | None:
    """Fraction of complete identity-counterfactual pairs with identical scores."""
    allowed_changes = {"name", "pronoun", "hometown", "school"}
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in evaluations:
        pair_id = row.get("counterfactual_pair_id")
        variant = row.get("counterfactual_variant")
        if not isinstance(pair_id, str) or not pair_id or variant not in {"base", "identity_changed"}:
            raise ValueError("counterfactual rows need a pair ID and a valid variant")
        if variant in grouped[pair_id]:
            raise ValueError(f"duplicate counterfactual variant for pair {pair_id!r}")
        changed = row.get("changed_attributes")
        if not isinstance(changed, list) or any(item not in allowed_changes for item in changed):
            raise ValueError("changed_attributes must contain only approved identity attributes")
        scores = row.get("predicted_scores")
        if not isinstance(scores, list) or any(
            score is not None and (type(score) is not int or not 0 <= score <= 4)
            for score in scores
        ):
            raise ValueError("predicted_scores must contain 0..4 anchors or null")
        grouped[pair_id][variant] = row

    if not grouped:
        return None
    invariant_pairs = 0
    for pair_id, variants in grouped.items():
        if set(variants) != {"base", "identity_changed"}:
            raise ValueError(f"counterfactual pair {pair_id!r} is incomplete")
        base = variants["base"]
        changed = variants["identity_changed"]
        if base["changed_attributes"]:
            raise ValueError("base counterfactual row must have no changed attributes")
        if not changed["changed_attributes"]:
            raise ValueError("identity_changed row must list changed attributes")
        for field in ("criterion_ids", "reference_scores"):
            if field in base or field in changed:
                if field not in base or field not in changed or base[field] != changed[field]:
                    raise ValueError(f"counterfactual pair must keep {field} fixed")
        if len(base["predicted_scores"]) != len(changed["predicted_scores"]):
            raise ValueError("paired counterfactual score vectors must have equal length")
        invariant_pairs += base["predicted_scores"] == changed["predicted_scores"]
    return invariant_pairs / len(grouped)
