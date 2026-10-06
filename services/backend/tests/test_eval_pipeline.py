import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
import tempfile
import json
import pytest

from scripts.eval_harness import compute_cohens_kappa, compute_linear_weighted_kappa, compute_mae, run_evaluation
from scripts.fixture_factory import generate_fixtures
from scripts.prompt_regression import run_prompt_regression, verify_prompt_invariants
from scripts.prompt_compare import compare_variants


def test_fixture_generation_in_temp_dir():
    """B18: Smoke is a dev subset; initial fixtures must not masquerade as holdout."""
    with tempfile.TemporaryDirectory() as tmpdir:
        counts = generate_fixtures(Path(tmpdir))
        assert counts["smoke"] >= 10
        assert counts["dev"] == 12
        assert counts["holdout"] == 0

        manifest = Path(tmpdir) / "manifest.json"
        assert manifest.exists()
        rows = json.loads(manifest.read_text(encoding="utf-8"))["families"]
        assert all(row["split"] == "dev" for row in rows)
        assert sum(row["smoke"] for row in rows) == 10
        assert not list(Path(tmpdir).glob("*.pdf"))
        sample = json.loads((Path(tmpdir) / rows[0]["json_file"]).read_text(encoding="utf-8"))
        assert sample["source_registry"]["label_origin"] == "unlabeled_synthetic"
        assert "expected_scores" not in sample


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
    assert compute_cohens_kappa(
        [("review_required", "review_required"), ("review_required", "consider_next_round")],
        ["consider_next_round", "review_required"],
    ) == 0.0
    assert compute_linear_weighted_kappa([(1, 1), (4, 4)]) == 1.0
    assert compute_linear_weighted_kappa([(2, 2), (2, 2)]) is None


def test_full_evaluation_harness():
    """B19: Mixed role rubrics are compared only within their approved rubric."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        labels = [
            {"sample_id": "a", "rubric_id": "backend_node_intern", "role_family": "backend_node", "split": "dev", "language": "vi", "label_origin": "hr_blind", "reviewer_id": "hr1", "criterion_scores": {"backend_build": 2, "api_design": 2}, "recommendation": "consider_next_round"},
            {"sample_id": "b", "rubric_id": "android_intern", "role_family": "android", "split": "dev", "language": "en", "label_origin": "hr_blind", "reviewer_id": "hr1", "criterion_scores": {"android_build": 1, "mobile_data": 1, "testing": None}, "recommendation": "review_required"},
        ]
        predictions = [
            {"sample_id": "a", "rubric_id": "backend_node_intern", "run_id": "run-a", "prompt_version": "v1", "model": "mock", "criterion_scores": {"backend_build": 3, "api_design": 2}, "recommendation": "consider_next_round"},
            {"sample_id": "b", "rubric_id": "android_intern", "run_id": "run-b", "prompt_version": "v1", "model": "mock", "criterion_scores": {"android_build": 1, "mobile_data": 1, "testing": None}, "recommendation": "needs_clarification"},
        ]
        labels_path, predictions_path = root / "labels.json", root / "predictions.json"
        labels_path.write_text(json.dumps(labels), encoding="utf-8")
        predictions_path.write_text(json.dumps(predictions), encoding="utf-8")
        res = run_evaluation(predictions_path, labels_path, "dev")
    summary = res["evaluation_summary"]
    assert summary["total_evaluated"] == 2
    assert summary["mean_absolute_error_score"] == 0.25
    assert summary["human_assessable_coverage"] == 1.0
    assert summary["linear_weighted_kappa_score"] is not None
    assert summary["recommendation_accuracy"] == 0.5
    assert summary["observed_cost_usd"] is None
    assert "vi" in res["disaggregated_by_language"]
    assert "en" in res["disaggregated_by_language"]
    assert res["per_rubric"]["backend_node_intern"]["comparable_score_pairs"] == 2
    assert res["per_rubric"]["android_intern"]["comparable_score_pairs"] == 2
    assert res["disaggregated_by_role_family"]["android"]["total_samples"] == 1
    assert res["gate_eligible"] is False


def test_eval_rejects_missing_predictions_and_invalid_dynamic_criteria(tmp_path):
    label = {"sample_id": "a", "rubric_id": "ai_intern", "split": "holdout", "language": "mixed", "label_origin": "design_expected", "criterion_scores": {"python": None, "model_evaluation": None}, "recommendation": "review_required"}
    label_path, prediction_path = tmp_path / "labels.jsonl", tmp_path / "predictions.jsonl"
    label_path.write_text(json.dumps(label) + "\n", encoding="utf-8")
    prediction_path.write_text(json.dumps({"sample_id": "a", "rubric_id": "ai_intern", "run_id": "r", "prompt_version": "v1", "model": "mock", "criterion_scores": {"python": None, "model_evaluation": None}, "recommendation": "review_required"}) + "\n", encoding="utf-8")
    report = run_evaluation(prediction_path, label_path, "holdout")
    assert report["gate_eligible"] is False
    assert report["evaluation_summary"]["mean_absolute_error_score"] is None
    assert report["evaluation_summary"]["cohens_kappa"] is None
    bad = json.loads(prediction_path.read_text(encoding="utf-8"))
    bad["criterion_scores"] = {"technical_competence": 4}
    prediction_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="criterion_scores must contain 2..12"):
        run_evaluation(prediction_path, label_path, "holdout")


def test_eval_rejects_prediction_from_wrong_role_rubric(tmp_path):
    label = {"sample_id": "a", "rubric_id": "backend_node", "split": "dev", "language": "vi", "label_origin": "design_expected", "criterion_scores": {"api": 2, "database": 1}, "recommendation": "review_required"}
    prediction = {"sample_id": "a", "rubric_id": "backend_python", "run_id": "r", "prompt_version": "v1", "model": "mock", "criterion_scores": {"api": 2, "database": 1}, "recommendation": "review_required"}
    labels_path, predictions_path = tmp_path / "labels.json", tmp_path / "predictions.json"
    labels_path.write_text(json.dumps([label]), encoding="utf-8")
    predictions_path.write_text(json.dumps([prediction]), encoding="utf-8")
    with pytest.raises(ValueError, match="rubric_id does not match"):
        run_evaluation(predictions_path, labels_path, "dev")


def test_prompt_variants_use_identical_cases(tmp_path):
    keys = ["backend_build", "api_design"]
    labels = [
        {"sample_id": sid, "rubric_id": "backend_node", "role_family": "backend_node", "split": "dev", "language": lang, "label_origin": "hr_blind", "reviewer_id": "hr1", "criterion_scores": {key: score for key in keys}, "recommendation": rec}
        for sid, lang, score, rec in [("a", "vi", 2, "review_required"), ("b", "en", 3, "consider_next_round")]
    ]
    label_path = tmp_path / "labels.json"
    label_path.write_text(json.dumps(labels), encoding="utf-8")
    paths = {}
    for name, score in [("v1", 2), ("v2", 3)]:
        path = tmp_path / f"{name}.json"
        rows = [{"sample_id": row["sample_id"], "rubric_id": row["rubric_id"], "run_id": f"run-{name}-{row['sample_id']}", "prompt_version": name, "model": "mock", "criterion_scores": {key: score for key in keys}, "recommendation": row["recommendation"]} for row in labels]
        path.write_text(json.dumps(rows), encoding="utf-8")
        paths[name] = path
    comparison = compare_variants(label_path, paths, "dev")
    assert comparison["same_sample_count"] == 2
    assert comparison["variants"]["v1"]["evaluation_summary"]["mean_absolute_error_score"] == 0.5
    paths["v2"].write_text(json.dumps(json.loads(paths["v2"].read_text(encoding="utf-8"))[:1]), encoding="utf-8")
    with pytest.raises(ValueError, match="missing predictions"):
        compare_variants(label_path, paths, "dev")


def test_prompt_regression_clean():
    """B20: Production prompts pass zero demographic violations and contain JSON contracts."""
    report = run_prompt_regression()
    assert report["status"] == "PASS_STATIC_CHECKS"
    assert len(report["violations"]) == 0
    assert len(report["prompt_sha256"]) == 3
    assert report["quality_evaluation_status"] == "NOT_RUN"


def test_prompt_regression_catches_violations():
    """B20: Regression runner flags forbidden demographic bias inserted into prompts."""
    bad_prompt = "You are an assistant. Consider candidate gender and age when ranking."
    violations = verify_prompt_invariants("bad_test_prompt", bad_prompt)
    assert len(violations) > 0
    assert any("PROMPT_DEMOGRAPHIC_VIOLATION" in v for v in violations)
