"""Pure metric and fairness-regression tests for role-specific evaluation."""
from __future__ import annotations

import pytest

from app.services.evaluation.metrics import (
    criterion_mae,
    counterfactual_invariance_rate,
    linear_weighted_kappa,
    quadratic_weighted_kappa,
    recall_at_k,
)


def test_recall_at_k_uses_span_intersection() -> None:
    assert recall_at_k(
        expected_span_ids={"span_a", "span_c"},
        retrieved_span_ids=["span_b", "span_a", "span_c"],
        k=2,
    ) == 0.5


def test_criterion_mae_ignores_jointly_missing_and_rejects_one_sided_missing() -> None:
    assert criterion_mae([0, None, 4], [1, None, 2]) == 1.5
    with pytest.raises(ValueError, match="one-sided missing"):
        criterion_mae([1, None], [1, 2])


def test_quadratic_weighted_kappa_matches_known_ordinal_example() -> None:
    # Standard squared disagreement weights over five ordered categories.
    assert quadratic_weighted_kappa([0, 1, 2, 3], [1, 2, 2, 3], scale=5) == pytest.approx(3 / 4)


def test_linear_weighted_kappa_matches_known_ordinal_example() -> None:
    assert linear_weighted_kappa([0, 1, 2, 3], [1, 2, 2, 3], scale=5) == pytest.approx(5 / 9)


def test_counterfactual_assessment_is_invariant_to_name_pronoun_and_school_changes() -> None:
    paired_evaluations = [
        {
            "counterfactual_pair_id": "synthetic_pair_01",
            "counterfactual_variant": "base",
            "changed_attributes": [],
            "predicted_scores": [3, None, 2, 4],
        },
        {
            "counterfactual_pair_id": "synthetic_pair_01",
            "counterfactual_variant": "identity_changed",
            "changed_attributes": ["name", "pronoun", "school"],
            "predicted_scores": [3, None, 2, 4],
        },
    ]
    assert counterfactual_invariance_rate(paired_evaluations) == 1.0


def test_counterfactual_pair_requires_same_rubric_and_human_label() -> None:
    paired_evaluations = [
        {
            "counterfactual_pair_id": "synthetic_pair_02",
            "counterfactual_variant": "base",
            "changed_attributes": [],
            "predicted_scores": [3, 2],
            "criterion_ids": ["python_backend", "api_design"],
            "reference_scores": [3, 2],
        },
        {
            "counterfactual_pair_id": "synthetic_pair_02",
            "counterfactual_variant": "identity_changed",
            "changed_attributes": ["school"],
            "predicted_scores": [3, 2],
            "criterion_ids": ["python_backend", "security"],
            "reference_scores": [3, 2],
        },
    ]
    with pytest.raises(ValueError, match="criterion_ids fixed"):
        counterfactual_invariance_rate(paired_evaluations)
