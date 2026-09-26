"""Compare recorded prompt variants on exactly the same labeled cases.

Generating the model outputs is a separate, budget-controlled operation. This
offline tool never contacts a provider and never promotes a variant to pilot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .eval_harness import _read_records, run_evaluation
except ImportError:  # direct `python scripts/prompt_compare.py` execution
    from eval_harness import _read_records, run_evaluation


def compare_variants(labels_path: Path, variants: dict[str, Path], split: str) -> dict:
    if len(variants) < 2:
        raise ValueError("Compare at least two prompt variants")
    labels = _read_records(labels_path)
    selected_ids = {sid for sid, row in labels.items() if row.get("split") == split}
    if not selected_ids:
        raise ValueError("No labels in selected split")
    reports = {}
    for name, path in variants.items():
        predictions = _read_records(path)
        if selected_ids != selected_ids & predictions.keys():
            raise ValueError(f"{name}: missing predictions; variants must cover the same labeled cases")
        versions = {predictions[sid].get("prompt_version") for sid in selected_ids}
        if versions != {name}:
            raise ValueError(f"{name}: prompt_version in prediction rows does not match variant name")
        reports[name] = run_evaluation(path, labels_path, split)
    return {
        "split": split,
        "same_sample_count": len(selected_ids),
        "variants": reports,
        "selection_status": "PENDING_ERROR_REVIEW_AND_HR_SIGNOFF",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare prompt outputs on the same labeled inputs")
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--split", required=True, choices=["smoke", "dev", "holdout", "real_shadow"])
    parser.add_argument("--variant", action="append", required=True, help="PROMPT_VERSION=predictions.jsonl; repeat for each variant")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    variants = {}
    for value in args.variant:
        name, separator, path = value.partition("=")
        if not separator or not name or not path or name in variants:
            parser.error("Each --variant needs a distinct PROMPT_VERSION=path")
        variants[name] = Path(path)
    report = compare_variants(args.labels, variants, args.split)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
