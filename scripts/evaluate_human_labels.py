#!/usr/bin/env python3
"""Evaluate one locally pinned, human-labeled package. Never calls a provider."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/backend"))
from app.services.evaluation.human_labeled import evaluate_assessment, evaluate_retrieval, load_verified_package


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path, help="Local directory with manifest.json and annotations.json")
    task = parser.add_mutually_exclusive_group(required=True)
    task.add_argument("--retrieval-k", type=int, help="Compute macro Recall@K and nDCG@K")
    parser.add_argument("--retrieval-split", choices=("train", "dev", "holdout"), help="Evaluate retrieval on exactly one split")
    task.add_argument("--assessment-split", choices=("train", "dev", "holdout"), help="Compute separate assessment metrics for one split")
    parser.add_argument("--output", type=Path, help="Optional local aggregate-only JSON output")
    args = parser.parse_args()
    if args.retrieval_k is not None and args.retrieval_split is None:
        parser.error("--retrieval-split is required with --retrieval-k")
    if args.retrieval_k is None and args.retrieval_split is not None:
        parser.error("--retrieval-split can only be used with --retrieval-k")
    try:
        package = load_verified_package(args.package)
        if args.retrieval_k is not None:
            if not any(query.split == args.retrieval_split for query in package.retrieval):
                raise ValueError("NO_HUMAN_LABELS")
            result = {"task": "retrieval", **evaluate_retrieval(
                package, k=args.retrieval_k, split=args.retrieval_split
            )}
        else:
            if not any(row.split == args.assessment_split for row in package.assessments):
                raise ValueError("NO_HUMAN_LABELS")
            result = {"task": "assessment", **evaluate_assessment(package, split=args.assessment_split)}
        rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.output:
            output_path = args.output.resolve()
            try:
                output_path.relative_to(args.package.resolve())
            except ValueError:
                pass
            else:
                raise ValueError("OUTPUT_MUST_BE_OUTSIDE_PACKAGE")
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except ValueError as exc:
        code = str(exc)
        if not code or len(code) > 80 or any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789" for ch in code):
            code = "EVALUATION_FAILED"
        sys.stderr.write(json.dumps({"error": code}) + "\n")
        return 2
    except Exception:
        sys.stderr.write('{"error":"EVALUATION_FAILED"}\n')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
