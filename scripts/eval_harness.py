"""Compare recorded AI predictions with independent reviewer labels.

Input files are JSON arrays or JSONL and must not contain CV text. This command
never invents predictions or treats synthetic expectations as HR annotations.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any


CRITERION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,49}$")
MIN_CRITERIA = 2
MAX_CRITERIA = 12
RECOMMENDATIONS = frozenset({
    "consider_next_round", "needs_clarification", "review_required",
})
LANGUAGES = frozenset({"vi", "en", "mixed"})
SPLITS = frozenset({"smoke", "dev", "holdout", "real_shadow"})


def compute_mae(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return round(sum(abs(pred - gold) for pred, gold in pairs) / len(pairs), 3)


def compute_cohens_kappa(pairs: list[tuple[str, str]], categories: list[str]) -> float | None:
    """Return None when class variation is insufficient to estimate agreement."""
    if len(pairs) < 2:
        return None
    n = len(pairs)
    pred_counts = Counter(pred for pred, _ in pairs)
    gold_counts = Counter(gold for _, gold in pairs)
    observed = sum(pred == gold for pred, gold in pairs) / n
    expected = sum(pred_counts[cat] * gold_counts[cat] for cat in categories) / (n * n)
    if expected >= 1:
        return None
    return round((observed - expected) / (1 - expected), 3)


def compute_linear_weighted_kappa(pairs: list[tuple[float, float]]) -> float | None:
    """Ordinal 0..4 agreement, with linear disagreement weights."""
    if len(pairs) < 2:
        return None
    n = len(pairs)
    pred_counts = Counter(int(pred) for pred, _ in pairs)
    gold_counts = Counter(int(gold) for _, gold in pairs)
    observed = sum(abs(pred - gold) / 4 for pred, gold in pairs) / n
    expected = sum(
        pred_counts[pred] * gold_counts[gold] * abs(pred - gold) / 4
        for pred in range(5) for gold in range(5)
    ) / (n * n)
    if expected == 0:
        return None
    return round(1 - observed / expected, 3)


def _read_records(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Input file does not exist: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Input file is empty: {path}")
    rows = json.loads(content) if content.startswith("[") else [json.loads(line) for line in content.splitlines() if line.strip()]
    if not isinstance(rows, list):
        raise ValueError(f"Expected JSON array or JSONL: {path}")
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("sample_id"), str) or not row["sample_id"].strip():
            raise ValueError(f"Every record needs a nonempty sample_id: {path}")
        sample_id = row["sample_id"]
        if sample_id in indexed:
            raise ValueError(f"Duplicate sample_id {sample_id!r}: {path}")
        indexed[sample_id] = row
    return indexed


def _validate_row(row: dict[str, Any], *, is_label: bool) -> None:
    sample_id = row["sample_id"]
    rubric_id = row.get("rubric_id")
    if not isinstance(rubric_id, str) or not CRITERION_ID_PATTERN.fullmatch(rubric_id):
        raise ValueError(f"{sample_id}: rubric_id must be a stable lowercase slug")
    scores = row.get("criterion_scores")
    if not isinstance(scores, dict) or not MIN_CRITERIA <= len(scores) <= MAX_CRITERIA:
        raise ValueError(f"{sample_id}: criterion_scores must contain {MIN_CRITERIA}..{MAX_CRITERIA} rubric criteria")
    if any(not isinstance(key, str) or not CRITERION_ID_PATTERN.fullmatch(key) for key in scores):
        raise ValueError(f"{sample_id}: criterion IDs must be stable lowercase slugs")
    if any(value is not None and (type(value) is not int or not 0 <= value <= 4) for value in scores.values()):
        raise ValueError(f"{sample_id}: scores must be integer anchors 0..4 or null")
    if row.get("recommendation") not in RECOMMENDATIONS:
        raise ValueError(f"{sample_id}: unknown recommendation")
    if is_label:
        if row.get("language") not in LANGUAGES or row.get("split") not in SPLITS:
            raise ValueError(f"{sample_id}: label requires valid language and split")
        if row.get("label_origin") not in {"hr_blind", "design_expected"}:
            raise ValueError(f"{sample_id}: label_origin must be hr_blind or design_expected")
        if row["label_origin"] == "hr_blind" and not row.get("reviewer_id"):
            raise ValueError(f"{sample_id}: blind HR label requires reviewer_id")
    elif not row.get("run_id") or not row.get("prompt_version") or not row.get("model"):
        raise ValueError(f"{sample_id}: prediction requires run_id, prompt_version and model")


def run_evaluation(predictions_path: Path, labels_path: Path, split: str | None = None) -> dict[str, Any]:
    """Measure only matched, independently stored predictions and labels."""
    if split is not None and split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")
    predictions = _read_records(predictions_path)
    labels = _read_records(labels_path)
    for row in predictions.values():
        _validate_row(row, is_label=False)
    for row in labels.values():
        _validate_row(row, is_label=True)
    selected = {sid: row for sid, row in labels.items() if split is None or row["split"] == split}
    if not selected:
        raise ValueError("No labels in selected split; cannot evaluate")
    matched_ids = sorted(selected.keys() & predictions.keys())
    missing_ids = sorted(selected.keys() - predictions.keys())
    if not matched_ids:
        raise ValueError("No predictions match selected labels; cannot evaluate")

    score_pairs: list[tuple[float, float]] = []
    hr_assessable = 0
    ai_abstained_on_hr_assessable = 0
    ai_scored_without_hr_score = 0
    criterion_pairs: dict[tuple[str, str], list[tuple[float, float]]] = defaultdict(list)
    rubric_pairs: dict[str, list[tuple[float, float]]] = defaultdict(list)
    rubric_recommendations: dict[str, list[tuple[str, str]]] = defaultdict(list)
    recommendation_pairs: list[tuple[str, str]] = []
    by_language: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "scores": [], "recommendations": []})
    by_role_family: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "scores": [], "recommendations": []})
    origins: Counter[str] = Counter()
    token_input = token_output = 0
    observed_cost = 0.0
    cost_rows = 0
    models: Counter[str] = Counter()

    for sid in matched_ids:
        label, pred = selected[sid], predictions[sid]
        if label["rubric_id"] != pred["rubric_id"]:
            raise ValueError(f"{sid}: prediction rubric_id does not match expected label")
        rubric_id = label["rubric_id"]
        label_criteria = set(label["criterion_scores"])
        prediction_criteria = set(pred["criterion_scores"])
        if label_criteria != prediction_criteria:
            raise ValueError(
                f"{sid}: prediction criterion IDs do not match rubric '{rubric_id}' "
                f"(missing={sorted(label_criteria - prediction_criteria)}, "
                f"unexpected={sorted(prediction_criteria - label_criteria)})"
            )
        lang = label["language"]
        role_family = label.get("role_family") or rubric_id
        origins[label["label_origin"]] += 1
        models[pred["model"]] += 1
        recommendation_pairs.append((pred["recommendation"], label["recommendation"]))
        rubric_recommendations[rubric_id].append((pred["recommendation"], label["recommendation"]))
        by_language[lang]["count"] += 1
        by_language[lang]["recommendations"].append((pred["recommendation"], label["recommendation"]))
        by_role_family[role_family]["count"] += 1
        by_role_family[role_family]["recommendations"].append((pred["recommendation"], label["recommendation"]))
        for criterion in sorted(label_criteria):
            gold, value = label["criterion_scores"][criterion], pred["criterion_scores"][criterion]
            if gold is not None:
                hr_assessable += 1
                if value is None:
                    ai_abstained_on_hr_assessable += 1
            elif value is not None:
                ai_scored_without_hr_score += 1
            if gold is not None and value is not None:
                pair = (float(value), float(gold))
                score_pairs.append(pair)
                criterion_pairs[(rubric_id, criterion)].append(pair)
                rubric_pairs[rubric_id].append(pair)
                by_language[lang]["scores"].append(pair)
                by_role_family[role_family]["scores"].append(pair)
        token_input += int(pred.get("input_tokens") or 0)
        token_output += int(pred.get("output_tokens") or 0)
        if pred.get("observed_cost_usd") is not None:
            observed_cost += float(pred["observed_cost_usd"])
            cost_rows += 1

    categories = sorted(RECOMMENDATIONS)
    kappa = compute_cohens_kappa(recommendation_pairs, categories)
    summary = {
        "total_labeled": len(selected),
        "total_evaluated": len(matched_ids),
        "missing_prediction_count": len(missing_ids),
        "missing_prediction_ids": missing_ids,
        "comparable_score_pairs": len(score_pairs),
        "mean_absolute_error_score": compute_mae(score_pairs),
        "human_assessable_coverage": round(len(score_pairs) / hr_assessable, 3) if hr_assessable else None,
        "ai_abstained_on_hr_assessable": ai_abstained_on_hr_assessable,
        "ai_scored_without_hr_score": ai_scored_without_hr_score,
        "linear_weighted_kappa_score": compute_linear_weighted_kappa(score_pairs),
        "cohens_kappa": kappa,
        "recommendation_accuracy": round(sum(a == b for a, b in recommendation_pairs) / len(recommendation_pairs), 3),
        "input_tokens_recorded": token_input,
        "output_tokens_recorded": token_output,
        "observed_cost_usd": round(observed_cost, 6) if cost_rows == len(matched_ids) else None,
    }
    disaggregated = {
        lang: {
            "total_samples": values["count"],
            "mean_score_error": compute_mae(values["scores"]),
            "recommendation_accuracy": round(sum(a == b for a, b in values["recommendations"]) / values["count"], 3),
            "cohens_kappa": compute_cohens_kappa(values["recommendations"], categories),
        }
        for lang, values in sorted(by_language.items())
    }
    role_disaggregated = {
        role: {
            "total_samples": values["count"],
            "mean_score_error": compute_mae(values["scores"]),
            "recommendation_accuracy": round(
                sum(a == b for a, b in values["recommendations"]) / values["count"], 3
            ),
            "cohens_kappa": compute_cohens_kappa(values["recommendations"], categories),
        }
        for role, values in sorted(by_role_family.items())
    }
    warnings = []
    if missing_ids:
        warnings.append("Some labeled samples have no AI prediction")
    if kappa is None:
        warnings.append("Kappa unavailable: too few samples or insufficient class variation")
    if not score_pairs:
        warnings.append("MAE unavailable: no comparable scored criteria")
    if summary["human_assessable_coverage"] is None:
        warnings.append("Coverage unavailable: HR did not assign any comparable anchors")
    if summary["linear_weighted_kappa_score"] is None:
        warnings.append("Weighted score kappa unavailable: insufficient ordinal variation")
    if origins.get("design_expected"):
        warnings.append("Synthetic design labels are not independent HR ratings")
    if models.get("mock"):
        warnings.append("Mock predictions cannot establish provider quality")
    if split == "holdout" and len(matched_ids) < 30:
        warnings.append("Holdout has fewer than 30 matched families")
    if split == "real_shadow" and len(matched_ids) < 30:
        warnings.append("Real shadow sample is too small for the planned quality gate")
    if split in {"holdout", "real_shadow"} and set(by_language) != LANGUAGES:
        warnings.append("Missing at least one language group: vi, en or mixed")
    return {
        "evaluation_summary": summary,
        "per_criterion_mae": {
            f"{rubric_id}/{criterion}": compute_mae(pairs)
            for (rubric_id, criterion), pairs in sorted(criterion_pairs.items())
        },
        "per_rubric": {
            rubric_id: {
                "comparable_score_pairs": len(rubric_pairs[rubric_id]),
                "mean_absolute_error_score": compute_mae(rubric_pairs[rubric_id]),
                "recommendation_accuracy": round(
                    sum(a == b for a, b in rubric_recommendations[rubric_id])
                    / len(rubric_recommendations[rubric_id]), 3
                ),
                "sample_count": len(rubric_recommendations[rubric_id]),
            }
            for rubric_id in sorted(rubric_recommendations)
        },
        "macro_mean_absolute_error_by_rubric": (
            round(sum(value for value in (compute_mae(pairs) for pairs in rubric_pairs.values()) if value is not None)
                    / sum(compute_mae(pairs) is not None for pairs in rubric_pairs.values()), 3)
            if any(compute_mae(pairs) is not None for pairs in rubric_pairs.values()) else None
        ),
        "disaggregated_by_language": disaggregated,
        "disaggregated_by_role_family": role_disaggregated,
        "label_origins": dict(origins),
        "draft_threshold_observations": {
            "conditional_mae_le_0_75": summary["mean_absolute_error_score"] <= 0.75 if summary["mean_absolute_error_score"] is not None else None,
            "human_assessable_coverage_ge_0_85": summary["human_assessable_coverage"] >= 0.85 if summary["human_assessable_coverage"] is not None else None,
            "linear_weighted_kappa_ge_0_60": summary["linear_weighted_kappa_score"] >= 0.60 if summary["linear_weighted_kappa_score"] is not None else None,
        },
        "gate_status": "PENDING_HUMAN_SIGNOFF",
        "gate_eligible": not warnings and origins == Counter({"hr_blind": len(matched_ids)}) and split in {"holdout", "real_shadow"},
        "warnings": warnings,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate recorded AI output against independent reviewer labels")
    parser.add_argument("--predictions", type=Path, required=True, help="JSONL/JSON array of recorded AI predictions")
    parser.add_argument("--labels", type=Path, required=True, help="JSONL/JSON array of HR-blind or synthetic labels")
    parser.add_argument("--split", choices=sorted(SPLITS))
    parser.add_argument("--output", type=Path, help="Write report to this file (keep private for real CVs)")
    args = parser.parse_args()
    result = run_evaluation(args.predictions, args.labels, args.split)
    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
