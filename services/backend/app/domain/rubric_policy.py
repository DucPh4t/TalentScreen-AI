"""Rubric validation policies, anti-discrimination invariant checks, and canonical schemas."""
from __future__ import annotations

import re
from typing import Any

VALID_CRITERION_IDS = {
    "python_backend",
    "api_design",
    "sql_data",
    "testing_debugging",
    "security_privacy",
    "delivery_ops",
}

FORBIDDEN_DISCRIMINATION_PATTERNS = [
    re.compile(r"\b(tuổi|năm sinh|ngày sinh|age|birth)\b", re.IGNORECASE),
    re.compile(r"\b(giới tính|nam/nữ|nam|nữ|gender|sex)\b", re.IGNORECASE),
    re.compile(r"\b(hôn nhân|gia đình|kết hôn|con cái|marital|family)\b", re.IGNORECASE),
    re.compile(r"\b(quê quán|dân tộc|tôn giáo|địa chỉ|origin|religion|ethnicity)\b", re.IGNORECASE),
    re.compile(r"\b(ngoại hình|ảnh|chân dung|chiều cao|cân nặng|photo|appearance)\b", re.IGNORECASE),
    re.compile(r"\b(danh tiếng trường|trường top|đại học top|bách khoa duy nhất|ivy league|school prestige)\b", re.IGNORECASE),
    re.compile(r"\b(năm tốt nghiệp|khoảng nghỉ|gap year|graduation year)\b", re.IGNORECASE),
]


class RubricValidationError(Exception):
    """Raised when a rubric violates business rules, scoring contracts, or anti-discrimination invariants."""
    pass


def scan_forbidden_criteria(text: str) -> str | None:
    """Check if text contains any forbidden demographic attribute. Returns matched string or None."""
    for pattern in FORBIDDEN_DISCRIMINATION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def validate_anti_discrimination(text: str, field_name: str) -> None:
    """Invariant: Check that no forbidden discriminatory attribute is evaluated in criteria or anchors."""
    match = scan_forbidden_criteria(text)
    if match:
        raise RubricValidationError(
            f"FORBIDDEN_CRITERION_DETECTED: Phát hiện tiêu chí/thuộc tính cấm phân biệt đối xử ('{match}') trong {field_name}."
        )


def validate_canonical_rubric(rubric_data: dict[str, Any]) -> None:
    """Validate a complete rubric structure against MVP business invariants:
    1. Exactly 6 criteria with canonical IDs.
    2. Sum of weights must equal exactly 100.
    3. Each criterion must have weights between 1 and 99.
    4. Each criterion must define anchors for scores 0, 1, 2, 3, 4.
    5. Anti-discrimination scan on label, description, and anchor descriptions.
    6. Recommendation policy must have threshold (default 70) and core minimum scores.
    """
    criteria = rubric_data.get("criteria", [])
    if not isinstance(criteria, list):
        raise RubricValidationError("Rubric phải chứa danh sách 'criteria'.")

    if len(criteria) != 6:
        raise RubricValidationError(f"Rubric bắt buộc có đúng 6 tiêu chí năng lực (hiện có {len(criteria)}).")

    seen_ids = set()
    total_weight = 0

    for crit in criteria:
        cid = crit.get("id") or crit.get("criterion_id")
        if not cid:
            raise RubricValidationError("Mỗi tiêu chí phải có trường 'id' hoặc 'criterion_id'.")
        if cid not in VALID_CRITERION_IDS:
            raise RubricValidationError(f"ID tiêu chí '{cid}' không nằm trong danh sách 6 tiêu chí hợp lệ: {VALID_CRITERION_IDS}")
        if cid in seen_ids:
            raise RubricValidationError(f"Trùng lặp tiêu chí '{cid}' trong rubric.")
        seen_ids.add(cid)

        # Weight validation
        weight = crit.get("weight")
        if not isinstance(weight, int) or weight <= 0 or weight >= 100:
            raise RubricValidationError(f"Trọng số của tiêu chí '{cid}' phải là số nguyên dương < 100 (nhận được: {weight}).")
        total_weight += weight

        # Anti-discrimination check on label and description
        label = crit.get("label") or crit.get("label_vi") or ""
        desc = crit.get("description") or crit.get("description_vi") or ""
        validate_anti_discrimination(label, f"tiêu chí '{cid}' (label)")
        validate_anti_discrimination(desc, f"tiêu chí '{cid}' (description)")

        # Scoring anchors validation (must have 0..4)
        anchors = crit.get("scoring_anchors") or crit.get("anchors")
        if not anchors:
            raise RubricValidationError(f"Tiêu chí '{cid}' thiếu định nghĩa scoring anchors 0..4.")

        anchor_scores = set()
        if isinstance(anchors, list):
            for anchor in anchors:
                score = anchor.get("score")
                if score is None or not isinstance(score, int) or score < 0 or score > 4:
                    raise RubricValidationError(f"Điểm anchor trong tiêu chí '{cid}' phải là số nguyên từ 0 đến 4.")
                anchor_scores.add(score)
                validate_anti_discrimination(anchor.get("description", ""), f"anchor {score} của '{cid}'")
        elif isinstance(anchors, dict):
            for k, v in anchors.items():
                try:
                    score = int(k)
                except ValueError:
                    raise RubricValidationError(f"Khóa anchor '{k}' không phải số nguyên hợp lệ.")
                if score < 0 or score > 4:
                    raise RubricValidationError(f"Điểm anchor {score} ngoài phạm vi 0..4.")
                anchor_scores.add(score)
                desc_text = v.get("description", "") if isinstance(v, dict) else str(v)
                validate_anti_discrimination(desc_text, f"anchor {score} của '{cid}'")
        else:
            raise RubricValidationError(f"Định dạng scoring anchors không hợp lệ trong tiêu chí '{cid}'.")

        expected_scores = {0, 1, 2, 3, 4}
        if anchor_scores != expected_scores:
            missing = expected_scores - anchor_scores
            raise RubricValidationError(f"Tiêu chí '{cid}' thiếu định nghĩa cho các mức điểm: {missing}.")

    if total_weight != 100:
        raise RubricValidationError(f"Tổng trọng số của 6 tiêu chí phải bằng đúng 100% (hiện tại: {total_weight}%).")

    # Policy validation
    policy = rubric_data.get("recommendation_policy") or rubric_data.get("threshold_config")
    if policy and isinstance(policy, dict):
        threshold = policy.get("threshold", 70)
        if not isinstance(threshold, (int, float)) or threshold <= 0 or threshold > 100:
            raise RubricValidationError("Ngưỡng điểm (threshold) trong policy phải từ 1 đến 100.")
