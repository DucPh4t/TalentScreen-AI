import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
import tempfile
import pytest

from scripts.eval_harness import compute_cohens_kappa, compute_mae, run_evaluation
from scripts.fixture_factory import generate_fixtures
from scripts.prompt_regression import run_prompt_regression, verify_prompt_invariants


def test_fixture_generation_in_temp_dir():
    """B18: Fixture factory produces smoke, dev, and holdout splits with deterministic manifests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        counts = generate_fixtures(Path(tmpdir))
        assert counts["smoke"] >= 10
        assert counts["dev"] >= 1
        assert counts["holdout"] >= 1

        manifest = Path(tmpdir) / "manifest.json"
        assert manifest.exists()


def test_eval_metrics_mae_and_kappa():
    """B19: MAE and Cohen's Kappa math calculations are verified with known assertions."""
    # MAE
    pairs = [(3.0, 3.0), (2.0, 3.0), (4.0, 2.0)]
    # diffs: 0, 1, 2 -> avg = 1.0
    assert compute_mae(pairs) == 1.0

    # Kappa perfect agreement
    perfect_pairs = [("consider_next_round", "consider_next_round"), ("review_required", "review_required")]
    assert compute_cohens_kappa(perfect_pairs, ["consider_next_round", "review_required"]) == 1.0

    # Kappa partial agreement
    mixed_pairs = [
        ("consider_next_round", "consider_next_round"),
        ("review_required", "needs_clarification"),
    ]
    kappa_val = compute_cohens_kappa(mixed_pairs, ["consider_next_round", "needs_clarification", "review_required"])
    assert kappa_val is not None
    assert kappa_val < 1.0


def test_full_evaluation_harness():
    """B19: Evaluation harness aggregates metrics across language splits and estimates costs."""
    res = run_evaluation()
    summary = res["evaluation_summary"]
    assert summary["total_evaluated"] >= 12
    assert summary["recommendation_accuracy"] >= 0.8
    assert summary["estimated_cost_usd"] > 0
    assert "vi" in res["disaggregated_by_language"]
    assert "en" in res["disaggregated_by_language"]


def test_prompt_regression_clean():
    """B20: Production prompts pass zero demographic violations and contain JSON contracts."""
    report = run_prompt_regression()
    assert report["status"] == "PASS"
    assert len(report["violations"]) == 0


def test_prompt_regression_catches_violations():
    """B20: Regression runner flags forbidden demographic bias inserted into prompts."""
    bad_prompt = "You are an assistant. Consider candidate gender and age when ranking."
    violations = verify_prompt_invariants("bad_test_prompt", bad_prompt)
    assert len(violations) > 0
    assert any("PROMPT_DEMOGRAPHIC_VIOLATION" in v for v in violations)
