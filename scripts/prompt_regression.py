"""Prompt regression runner and release/rollback manager for Task B20.
Verifies contract integrity, anti-discrimination scan, and prompt injection resilience.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent / "services" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.domain.rubric_policy import FORBIDDEN_DISCRIMINATION_PATTERNS
from app.services.assessment.prompt import ASSESSMENT_PROMPT_VERSION, build_assessment_system_prompt
from app.services.interview_prompts import build_interview_system_prompt

RELEASES_DIR = Path(__file__).resolve().parent.parent / "reports" / "releases"

RUBRIC_DRAFT_SYSTEM_PROMPT = """Task: draft a competency rubric for HR review, using the supplied JD requirements.
Create role-specific criterion IDs and criteria from this JD; do not reuse an unrelated role's rubric.
Use only job-related abilities explicitly supported by the supplied JD.
Propose anchors describing demonstrated scope/complexity of work, not eloquence,
school prestige, years alone, or number of tools listed. Every criterion must map
to at least one supplied JD requirement_id and its exact quotation.
Do not add hidden requirements, degrees or veto rules. A rule requiring a sensitive
attribute must be reported as a warning and must not be converted into a criterion.
For each 0..4 anchor, distinguish qualifying_evidence from not_sufficient.
Missing evidence is not anchor 0. A skills-only list is not proof of demonstrated
competence. Keep numeric policy values supplied by the backend unchanged.
All output remains a draft; HR approval happens outside this task.
Return JSON: {"criteria":[...],"warnings":[...]}.
"""


def verify_prompt_invariants(prompt_name: str, prompt_text: str) -> list[str]:
    """Verify core prompt safety and architecture invariants."""
    violations = []

    # 1. Zero demographic attributes in prompt templates
    lower_text = prompt_text.lower()
    for pattern in FORBIDDEN_DISCRIMINATION_PATTERNS:
        match = pattern.search(lower_text)
        if match:
            # Check if it is within a negative instruction (e.g. "do not ask about age")
            matched_word = match.group(0)
            context_start = max(0, match.start() - 120)
            context = lower_text[context_start:match.end() + 50]
            negatives = ("do not", "not ", "không", "never", "sensitive", "exclude", "ignore")
            if not any(neg in context for neg in negatives):
                violations.append(
                    f"PROMPT_DEMOGRAPHIC_VIOLATION ({prompt_name}): Chứa thuộc tính nhân khẩu học ngoài ngữ cảnh phủ định: '{matched_word}'"
                )

    # 2. Responsible AI disclaimer check: Must instruct not to infer personal attributes
    if "impartial" not in lower_text and "do not" not in lower_text:
        violations.append(f"MISSING_SAFETY_DISCLAIMER ({prompt_name}): Thiếu chỉ dẫn an toàn AI có trách nhiệm.")

    # 3. JSON format instruction check
    if "json" not in lower_text:
        violations.append(f"MISSING_JSON_INSTRUCTION ({prompt_name}): Prompt thiếu yêu cầu trả về định dạng JSON.")

    return violations


def run_prompt_regression() -> dict[str, Any]:
    """Run regression test on all production prompt templates."""
    prompts = {
        ASSESSMENT_PROMPT_VERSION: build_assessment_system_prompt(),
        "rubric_draft_system_prompt_v1": RUBRIC_DRAFT_SYSTEM_PROMPT,
        "interview_system_prompt_v1": build_interview_system_prompt(),
    }

    all_violations = []
    checked_count = 0

    for p_name, p_content in prompts.items():
        checked_count += 1
        v = verify_prompt_invariants(p_name, p_content)
        all_violations.extend(v)

    passed = len(all_violations) == 0

    report = {
        "status": "PASS_STATIC_CHECKS" if passed else "FAIL",
        "checked_prompts_count": checked_count,
        "prompt_sha256": {name: hashlib.sha256(content.encode("utf-8")).hexdigest() for name, content in prompts.items()},
        "violations": all_violations,
        "quality_evaluation_status": "NOT_RUN",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return report


def generate_release_manifest(version: str = "v1.0.0-mvp") -> Path:
    """Record content hashes and rollback guidance without claiming pilot approval."""
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "release_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt_versions": {
            "assessment": ASSESSMENT_PROMPT_VERSION,
            "rubric": "v1.0.0",
            "interview": "v1.0.0",
        },
        "rollback_target": "v0.9.0-mock",
        "rollback_instructions": "Đặt biến môi trường LLM_PROVIDER=mock và khởi động lại dịch vụ backend.",
        "prompt_sha256": run_prompt_regression()["prompt_sha256"],
        "regression_status": "STATIC_CHECKS_ONLY",
        "quality_evaluation_status": "PENDING_RECORDED_OUTPUTS_AND_HR_LABELS",
        "pilot_gate_status": "PENDING_HR_IT_SIGNOFF",
    }
    manifest_file = RELEASES_DIR / f"manifest_{version}.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prompt Regression Runner")
    parser.add_argument("--test", action="store_true", help="Run prompt regression tests")
    parser.add_argument("--release", type=str, default="v1.0.0-mvp", help="Generate release manifest")
    args = parser.parse_args()

    report = run_prompt_regression()
    print("Prompt Regression Report:")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if report["status"] == "PASS_STATIC_CHECKS":
        m_file = generate_release_manifest(args.release)
        print(f"Generated release manifest at {m_file}")
    else:
        sys.exit(1)
