"""Bounded, synthetic-only DeepSeek assessment prompt probe.

This exercises the production prompt builder and output validator without
creating applications, approving a real rubric or bypassing the application's
real-CV egress guard. It is not an end-to-end assessment or a real shadow run.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "backend"))

from app.config import get_settings
from app.services.assessment.prompt import (
    ASSESSMENT_PROMPT_VERSION,
    build_assessment_system_prompt,
    build_assessment_user_prompt,
    build_repair_user_prompt,
)
from app.services.assessment.validator import AssessmentValidationError, validate_assessment_output
from app.services.llm.cost import calculate_actual_cost, estimate_request_cost
from app.services.llm.provider import DeepSeekHTTPXProvider
from app.services.llm.types import CompletionRequest
from app.services.sanitizer import build_source_spans_from_canonical

DEFAULT_CASES = ("rehearsal_01", "rehearsal_19", "rehearsal_29")
ALL_CASES = tuple(f"rehearsal_{n:02d}" for n in range(1, 31))
DEFAULT_CAP_USD = Decimal("0.10")


def load_seed_criteria() -> list[SimpleNamespace]:
    seed = json.loads((ROOT / "talentscreen-mvp-plan/examples/rubric-backend-python.v1.json").read_text())
    return [
        SimpleNamespace(
            criterion_id=c["id"],
            label_vi=c["label"],
            description_vi=c["description"],
            weight=c["weight"],
            anchors=c["scoring_anchors"],
            jd_evidence_refs=c["source_requirements"],
        )
        for c in seed["criteria"]
    ]


def load_synthetic_case(case_id: str) -> dict:
    manifest = json.loads((ROOT / "fixtures/holdout_rehearsal/manifest.json").read_text())
    family = next((row for row in manifest["families"] if row["family_id"] == case_id), None)
    if family is None or manifest["origin_kind"] != "synthetic":
        raise ValueError(f"{case_id} is not a frozen synthetic rehearsal case")
    payload = json.loads((ROOT / "fixtures/holdout_rehearsal" / f"{case_id}.json").read_text())
    text = payload["raw_text"]
    if payload["origin_kind"] != "synthetic" or hashlib.sha256(text.encode()).hexdigest() != family["sha256"]:
        raise ValueError(f"{case_id} failed synthetic source/hash verification")
    return payload


def save_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    os.chmod(path, 0o600)


async def run(case_ids: tuple[str, ...], cap_usd: Decimal, dry_run: bool, progress_path: Path | None = None) -> dict:
    settings = get_settings()
    if not dry_run and not settings.DEEPSEEK_API_KEY:
        raise RuntimeError("DeepSeek key is not configured")
    if settings.DEEPSEEK_MODEL != "deepseek-flash":
        raise RuntimeError("The synthetic probe requires the verified deepseek-flash model")

    criteria = load_seed_criteria()
    system_prompt = build_assessment_system_prompt()
    cases = [load_synthetic_case(case_id) for case_id in case_ids]
    planned: list[tuple[dict, str, dict[str, SimpleNamespace], Decimal]] = []
    for case in cases:
        raw_text = case["raw_text"]
        version_id = uuid.uuid5(uuid.NAMESPACE_URL, f"synthetic:{case['family_id']}:{hashlib.sha256(raw_text.encode()).hexdigest()}")
        spans = build_source_spans_from_canonical(version_id, raw_text)
        user_prompt = build_assessment_user_prompt(criteria, spans)
        # UTF-8 bytes deliberately over-reserve tokens for this small rehearsal.
        repair_prompt = build_repair_user_prompt(user_prompt, ["CONTRACT_ERROR: regenerate valid output"])
        reserve = estimate_request_cost(
            input_tokens=max(
                len((system_prompt + user_prompt).encode("utf-8")),
                len((system_prompt + repair_prompt).encode("utf-8")),
            ),
            max_output_tokens=4096,
            model=settings.DEEPSEEK_MODEL,
        )
        planned.append((case, user_prompt, {span.span_id: span for span in spans}, reserve))

    # Each case can use one repair call. The estimate is deliberately pessimistic.
    maximum_reservation = sum((item[3] * 2 for item in planned), Decimal("0"))
    if maximum_reservation > cap_usd:
        raise RuntimeError(f"Estimated worst-case reservation {maximum_reservation} exceeds cap {cap_usd}")

    report = {
        "kind": "synthetic_assessment_prompt_probe",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "not_real_shadow": True,
        "not_application_budget_ledger": True,
        "provider_setting_unchanged": settings.LLM_PROVIDER,
        "model": settings.DEEPSEEK_MODEL,
        "prompt_version": ASSESSMENT_PROMPT_VERSION,
        "case_ids": list(case_ids),
        "system_prompt_sha256": hashlib.sha256(system_prompt.encode()).hexdigest(),
        "seed_rubric_sha256": hashlib.sha256((ROOT / "talentscreen-mvp-plan/examples/rubric-backend-python.v1.json").read_bytes()).hexdigest(),
        "estimated_worst_case_usd": str(maximum_reservation),
        "cost_cap_usd": str(cap_usd),
        "dry_run": dry_run,
        "cases": [],
    }
    if dry_run:
        return report
    if progress_path is not None:
        save_report(progress_path, report)

    provider = DeepSeekHTTPXProvider()
    total_observed = Decimal("0")
    for case, user_prompt, registry, reserve in planned:
        item = {
            "sample_id": case["family_id"],
            "language": case["language"],
            "source_sha256": hashlib.sha256(case["raw_text"].encode()).hexdigest(),
            "reserved_upper_bound_usd": str(reserve * 2),
            "attempts": [],
        }
        report["cases"].append(item)
        last_errors: list[str] = []
        for attempt in (1, 2):
            prompt = user_prompt if attempt == 1 else build_repair_user_prompt(user_prompt, last_errors)
            request = CompletionRequest(
                task_kind="assessment" if attempt == 1 else "repair",
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=settings.DEEPSEEK_MODEL,
                max_output_tokens=4096,
                timeout_seconds=90,
                temperature=0,
                thinking_mode="disabled",
            )
            try:
                result = await provider.complete(request)
                observed = calculate_actual_cost(
                    result.input_tokens or 0,
                    result.output_tokens or 0,
                    model=settings.DEEPSEEK_MODEL,
                )
                total_observed += observed
                attempt_record = {
                    "attempt": attempt,
                    "reported_model": result.reported_model,
                    "provider_request_id": result.provider_request_id,
                    "latency_ms": result.latency_ms,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "estimated_peak_cost_usd": str(observed),
                }
                item["attempts"].append(attempt_record)
                try:
                    parsed = validate_assessment_output(result.content or "", registry)
                    item["validation"] = "pass"
                    item["criterion_scores"] = {c.criterion_id: c.score for c in parsed.criteria}
                    item["criterion_statuses"] = {c.criterion_id: c.status.value for c in parsed.criteria}
                    item["validated_output"] = parsed.model_dump(mode="json")
                    break
                except AssessmentValidationError as exc:
                    last_errors = exc.errors[:5]
                    attempt_record["validation_error_codes"] = [err.split(":", 1)[0] for err in last_errors]
                    # This report is ignored by Git, mode 0600, and the runner
                    # accepts only hash-verified fictional fixtures. Preserve
                    # failed output to diagnose citation errors precisely.
                    attempt_record["invalid_synthetic_output"] = result.content
                    item["validation"] = "fail"
            except Exception as exc:
                item["validation"] = "provider_error"
                item["error_type"] = type(exc).__name__
                item["provider_billing_unknown"] = True
                break
        report["known_peak_spend_usd"] = str(total_observed)
        if progress_path is not None:
            save_report(progress_path, report)
        print(json.dumps({
            "sample_id": item["sample_id"],
            "validation": item["validation"],
            "attempts": len(item["attempts"]),
            "known_peak_spend_usd": str(total_observed),
        }), flush=True)
        # The request itself may have been billed despite a transport failure.
        # Stop before further calls when the observed ceiling reaches the cap.
        if item["validation"] == "provider_error":
            report["stopped_after_provider_error"] = True
            break
        if total_observed >= cap_usd:
            report["stopped_at_cost_cap"] = True
            break
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", choices=ALL_CASES, help="Repeat for selected synthetic cases")
    parser.add_argument("--all", action="store_true", help="Run all 30 frozen synthetic cases")
    parser.add_argument("--cap-usd", type=Decimal, default=DEFAULT_CAP_USD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.all and args.case:
        parser.error("Use either --all or --case, not both")
    case_ids = ALL_CASES if args.all else tuple(args.case or DEFAULT_CASES)
    if args.cap_usd <= 0 or len(set(case_ids)) != len(case_ids):
        parser.error("Cap must be positive and case IDs must be unique")
    output = ROOT / "private_storage/eval" / ("synthetic_assessment_probe_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    report = asyncio.run(run(case_ids, args.cap_usd, args.dry_run, None if args.dry_run else output))
    if args.dry_run:
        print(json.dumps({key: report[key] for key in ("case_ids", "estimated_worst_case_usd", "cost_cap_usd", "model", "dry_run")}))
        return
    save_report(output, report)
    print(json.dumps({
        "output": str(output),
        "case_count": len(report["cases"]),
        "valid_count": sum(case.get("validation") == "pass" for case in report["cases"]),
        "known_peak_spend_usd": report.get("known_peak_spend_usd", "0"),
        "provider_billing_unknown": any(case.get("provider_billing_unknown") for case in report["cases"]),
    }))


if __name__ == "__main__":
    main()
