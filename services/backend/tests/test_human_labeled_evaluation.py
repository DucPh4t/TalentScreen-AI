from __future__ import annotations

import json
import math
import hashlib
from pathlib import Path

import pytest

from app.services.evaluation.metrics import quadratic_weighted_kappa
from app.services.evaluation.human_labeled import (
    EvaluationPackage,
    CriterionLabel,
    evaluate_assessment,
    evaluate_retrieval,
    load_verified_package,
)


@pytest.fixture(scope="session", autouse=True)
def test_engine():
    """These pure-metric tests must never connect to a database."""
    return None


def retrieval_package() -> EvaluationPackage:
    rubric = {
        "rubric_key": "rub_" + "1" * 24,
        "jd_key": "jd_" + "1" * 24,
        "approved_by_refs": ["approval_hr_1", "approval_it_1"],
        "criteria": [
            {"criterion_key": key, "description": description, "anchors": [
                {"score": score, "description": f"anchor {score}"} for score in range(5)
            ]}
            for key, description in (
                ("crit_api", "Design idempotent REST APIs"),
                ("crit_k8s", "Operate Kubernetes services"),
            )
        ],
    }
    rubric["sha256"] = hashlib.sha256(json.dumps(rubric, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    payload = {
        "schema_version": "human-evaluation.v1",
        "source": {
            "name": "local-authorized-sample",
            "snapshot": "snapshot-2026-10-09",
            "sha256": "a" * 64,
            "permission_ref": "approval-001",
            "text_extractor_version": "extractor-test-1",
            "redaction_version": "redaction-test-1",
        },
        "source_documents": [
            {"document_key": "cand_" + "1" * 24, "kind": "cv", "sha256": "c" * 64},
            {"document_key": "cand_" + "2" * 24, "kind": "cv", "sha256": "c" * 64},
            {"document_key": "jd_" + "1" * 24, "kind": "jd", "sha256": "d" * 64},
        ],
        "splits": [
            {"candidate_key": "cand_" + "1" * 24, "jd_key": "jd_" + "1" * 24, "split": "dev"},
            {"candidate_key": "cand_" + "2" * 24, "jd_key": "jd_" + "1" * 24, "split": "dev"},
        ],
        "rubrics": [rubric],
        "retrieval": [{
            "query_key": "qry_" + "1" * 24,
            "jd_key": "jd_" + "1" * 24,
            "criterion_key": "crit_api",
            "split": "dev",
            "query_source": "jd_criterion",
            "query_text": "Design idempotent REST APIs",
            "judgments": [
                {"candidate_key": "cand_" + "1" * 24, "relevance": 3, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
                {"candidate_key": "cand_" + "2" * 24, "relevance": 0, "evidence": []},
            ],
            "annotations": [
                {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True},
                {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True},
            ],
            "adjudication_reason": "Agreement after independent review.",
            "ranked_candidates": ["cand_" + "2" * 24, "cand_" + "1" * 24],
        }, {
            "query_key": "qry_" + "2" * 24,
            "jd_key": "jd_" + "1" * 24,
            "criterion_key": "crit_k8s",
            "split": "dev",
            "query_source": "jd_criterion",
            "query_text": "Operate Kubernetes services",
            "judgments": [
                {"candidate_key": "cand_" + "1" * 24, "relevance": 0, "evidence": []},
                {"candidate_key": "cand_" + "2" * 24, "relevance": 0, "evidence": []},
            ],
            "annotations": [
                {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True},
                {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True},
            ],
            "adjudication_reason": "No relevant evidence in this judged pool.",
            "ranked_candidates": ["cand_" + "2" * 24],
        }],
        "assessments": [],
    }
    for query in payload["retrieval"]:
        query["rubric_key"] = "rub_" + "1" * 24
        query["adjudicator_key"] = "ann_" + "3" * 24
        for index, annotation in enumerate(query["annotations"]):
            annotation["annotator_role"] = "hr" if index == 0 else "it"
            annotation["judgments"] = [dict(row) for row in query["judgments"]]
    return EvaluationPackage.model_validate(payload)


def test_retrieval_recall_ndcg_macro_and_no_positive_query() -> None:
    result = evaluate_retrieval(retrieval_package(), k=1, split="dev")
    # Query 1: top-1 is irrelevant, so Recall@1 = 0 and nDCG@1 = 0.
    # Query 2 has no relevant item, so it is excluded from metric means.
    assert result["recall_at_k"] == 0
    assert result["ndcg_at_k"] == 0
    assert result["metric_query_count"] == 1
    assert result["no_positive_query_count"] == 1
    assert result["no_positive_with_return_count"] == 1


def test_retrieval_reports_pre_adjudication_relevance_agreement() -> None:
    payload = retrieval_package().model_dump(mode="json")
    annotations = payload["retrieval"][0]["annotations"]
    annotations[0]["judgments"][0]["relevance"] = 3
    annotations[1]["judgments"][0]["relevance"] = 2
    annotations[1]["judgments"][0]["evidence"] = [{"start": 0, "end": 9, "quote": "REST APIs"}]
    annotations[0]["judgments"][1]["relevance"] = 0
    annotations[1]["judgments"][1]["relevance"] = 1
    annotations[1]["judgments"][1]["evidence"] = [{"start": 0, "end": 9, "quote": "REST APIs"}]
    result = evaluate_retrieval(EvaluationPackage.model_validate(payload), k=1, split="dev")
    agreement = result["human_human_relevance"]
    assert agreement["paired_count"] == 4
    assert agreement["query_count"] == 2
    assert agreement["quadratic_weighted_kappa"] == pytest.approx(
        quadratic_weighted_kappa([3, 0, 0, 0], [2, 1, 0, 0], scale=4)
    )
    assert agreement["undefined_reason"] is None


def test_retrieval_agreement_explicitly_marks_undefined_kappa() -> None:
    payload = retrieval_package().model_dump(mode="json")
    for query in payload["retrieval"]:
        for annotation in query["annotations"]:
            for judgment in annotation["judgments"]:
                judgment["relevance"] = 0
                judgment["evidence"] = []
    result = evaluate_retrieval(EvaluationPackage.model_validate(payload), k=1, split="dev")["human_human_relevance"]
    assert result["paired_count"] == 4
    assert result["quadratic_weighted_kappa"] is None
    assert result["undefined_reason"] == "DEGENERATE_EXPECTED_DISAGREEMENT"


def test_retrieval_metrics_use_judged_candidates_and_macro_average() -> None:
    package = retrieval_package().model_copy(deep=True)
    q1 = package.retrieval[0].model_copy(update={"ranked_candidates": ["cand_" + "1" * 24]})
    q2 = package.retrieval[1].model_copy(update={"ranked_candidates": []})
    package = package.model_copy(update={"retrieval": [q1, q2]})
    result = evaluate_retrieval(package, k=2, split="dev")
    assert result["recall_at_k"] == 1
    assert result["ndcg_at_k"] == 1
    assert result["metric_query_count"] == 1


def test_retrieval_metrics_are_scoped_to_requested_split() -> None:
    payload = retrieval_package().model_dump(mode="json")
    holdout_jd = "jd_" + "2" * 24
    holdout_candidate = "cand_" + "3" * 24
    holdout_negative = "cand_" + "4" * 24
    holdout_rubric_key = "rub_" + "2" * 24
    rubric = {
        "rubric_key": holdout_rubric_key,
        "jd_key": holdout_jd,
        "approved_by_refs": ["approval_hr_2", "approval_it_2"],
        "criteria": [{
            "criterion_key": "crit_api",
            "description": "Independent holdout API requirement",
            "anchors": [
                {"score": score, "description": f"anchor {score}"}
                for score in range(5)
            ],
        }],
    }
    rubric["sha256"] = hashlib.sha256(
        json.dumps(rubric, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["rubrics"].append(rubric)
    payload["source_documents"].extend([
        {"document_key": holdout_candidate, "kind": "cv", "sha256": "e" * 64},
        {"document_key": holdout_negative, "kind": "cv", "sha256": "f" * 64},
        {"document_key": holdout_jd, "kind": "jd", "sha256": "b" * 64},
    ])
    payload["splits"].extend([
        {"candidate_key": holdout_candidate, "jd_key": holdout_jd, "split": "holdout"},
        {"candidate_key": holdout_negative, "jd_key": holdout_jd, "split": "holdout"},
    ])
    judgments = [
        {
            "candidate_key": holdout_candidate,
            "relevance": 3,
            "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}],
        },
        {"candidate_key": holdout_negative, "relevance": 0, "evidence": []},
    ]
    payload["retrieval"].append({
        "query_key": "qry_" + "3" * 24,
        "jd_key": holdout_jd,
        "rubric_key": holdout_rubric_key,
        "criterion_key": "crit_api",
        "split": "holdout",
        "query_source": "jd_criterion",
        "query_text": "Independent holdout API requirement",
        "judgments": judgments,
        "annotations": [
            {
                "annotator_key": "ann_" + "1" * 24,
                "annotator_role": "hr",
                "blind_to_model": True,
                "judgments": [dict(row) for row in judgments],
            },
            {
                "annotator_key": "ann_" + "2" * 24,
                "annotator_role": "it",
                "blind_to_model": True,
                "judgments": [dict(row) for row in judgments],
            },
        ],
        "adjudicator_key": "ann_" + "3" * 24,
        "adjudication_reason": "Independent labels agree.",
        "ranked_candidates": [holdout_candidate],
    })

    package = EvaluationPackage.model_validate(payload)
    result = evaluate_retrieval(package, k=1, split="holdout")

    assert result["split"] == "holdout"
    assert result["query_count"] == 1
    assert result["metric_query_count"] == 1
    assert result["recall_at_k"] == 1
    assert result["ndcg_at_k"] == 1
    assert result["human_human_relevance"]["paired_count"] == 2


def test_retrieval_rejects_more_than_one_annotator_per_role() -> None:
    payload = retrieval_package().model_dump(mode="json")
    extra = {
        **payload["retrieval"][0]["annotations"][0],
        "annotator_key": "ann_" + "4" * 24,
    }
    payload["retrieval"][0]["annotations"].append(extra)
    with pytest.raises(ValueError, match="ANNOTATOR_REQUIREMENT"):
        EvaluationPackage.model_validate(payload)


def test_ndcg_uses_predeclared_graded_gain_and_rank_discount() -> None:
    package = retrieval_package().model_copy(deep=True)
    q1 = package.retrieval[0].model_copy(update={"ranked_candidates": ["cand_" + "2" * 24, "cand_" + "1" * 24]})
    package = package.model_copy(update={"retrieval": [q1]})
    result = evaluate_retrieval(package, k=2, split="dev")
    assert result["recall_at_k"] == 1
    assert result["ndcg_at_k"] == pytest.approx(1 / math.log2(3))


def test_retrieval_package_rejects_candidate_or_jd_split_leakage() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["splits"][1]["split"] = "holdout"
    with pytest.raises(ValueError, match="SPLIT_LEAKAGE"):
        EvaluationPackage.model_validate(payload)


def test_retrieval_requires_two_blind_distinct_annotators() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["retrieval"][0]["annotations"][1]["annotator_key"] = payload["retrieval"][0]["annotations"][0]["annotator_key"]
    with pytest.raises(ValueError, match="ANNOTATOR_REQUIREMENT"):
        EvaluationPackage.model_validate(payload)


def test_retrieval_requires_hr_it_pair_and_separate_adjudicator() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["retrieval"][0]["annotations"][1]["annotator_role"] = "hr"
    with pytest.raises(ValueError, match="ANNOTATOR_REQUIREMENT"):
        EvaluationPackage.model_validate(payload)


def test_retrieval_disagreement_requires_adjudication_reason() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["retrieval"][0]["annotations"][1]["judgments"][0]["relevance"] = 2
    payload["retrieval"][0]["adjudication_reason"] = " "
    with pytest.raises(ValueError, match="ADJUDICATION_REASON_REQUIRED"):
        EvaluationPackage.model_validate(payload)


def test_not_evidenced_must_not_be_converted_to_zero() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["assessments"] = [{
        "case_key": "case_" + "a" * 24,
        "candidate_key": "cand_" + "1" * 24,
        "jd_key": "jd_" + "1" * 24,
        "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_k8s",
        "split": "dev",
        "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "not_evidenced", "score": 0, "evidence": []},
        "annotations": [],
        "prediction": {"status": "not_evidenced", "score": None, "evidence": []},
    }]
    with pytest.raises(ValueError, match="NOT_EVIDENCED_SCORE_MUST_BE_NULL"):
        EvaluationPackage.model_validate(payload)


def test_conflicting_evidence_is_distinct_from_missing_and_contradicted() -> None:
    conflict = CriterionLabel.model_validate({
        "status": "conflicting_evidence",
        "score": None,
        "evidence": [
            {"start": 0, "end": 7, "quote": "Claim A"},
            {"start": 10, "end": 17, "quote": "Claim B"},
        ],
    })
    missing = CriterionLabel.model_validate({
        "status": "not_evidenced", "score": None, "evidence": [],
    })
    contradicted = CriterionLabel.model_validate({
        "status": "contradicted", "score": 0,
        "evidence": [{"start": 0, "end": 7, "quote": "Claim A"}],
    })

    assert conflict.status == "conflicting_evidence" and conflict.score is None and len(conflict.evidence) == 2
    assert missing.status == "not_evidenced" and missing.score is None and not missing.evidence
    assert contradicted.status == "contradicted" and contradicted.score == 0 and len(contradicted.evidence) == 1

    with pytest.raises(ValueError, match="CONFLICTING_EVIDENCE_REQUIRES_TWO_SPANS"):
        CriterionLabel.model_validate({
            "status": "conflicting_evidence", "score": None,
            "evidence": [{"start": 0, "end": 7, "quote": "Claim A"}],
        })


def test_score_disagreement_requires_reason_and_blind_two_person_review() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["assessments"] = [{
        "case_key": "case_" + "a" * 24,
        "candidate_key": "cand_" + "1" * 24,
        "jd_key": "jd_" + "1" * 24,
        "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_api",
        "split": "dev",
        "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        "annotations": [
            {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
            {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True, "status": "partial", "score": 3, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        ],
        "prediction": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
    }]
    with pytest.raises(ValueError, match="ADJUDICATION_REASON_REQUIRED"):
        EvaluationPackage.model_validate(payload)

def test_assessment_rejects_more_than_one_annotator_per_role() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["assessments"] = [{
        "case_key": "case_" + "a" * 24,
        "candidate_key": "cand_" + "1" * 24,
        "jd_key": "jd_" + "1" * 24,
        "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_api",
        "split": "dev",
        "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        "annotations": [
            {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
            {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
            {"annotator_key": "ann_" + "4" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        ],
        "prediction": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
    }]
    with pytest.raises(ValueError, match="ANNOTATOR_REQUIREMENT"):
        EvaluationPackage.model_validate(payload)


def test_assessment_metrics_are_separate_and_hand_calculated() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["assessments"] = [{
        "case_key": "case_" + "a" * 24,
        "candidate_key": "cand_" + "1" * 24,
        "jd_key": "jd_" + "1" * 24,
        "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_api",
        "split": "dev",
        "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        "annotations": [
            {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
            {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True, "status": "partial", "score": 3, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        ],
        "adjudication_reason": "Score anchor 4 requires demonstrated idempotency.",
        "prediction": {"status": "supported", "score": 2, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
    }, {
        "case_key": "case_" + "b" * 24,
        "candidate_key": "cand_" + "2" * 24,
        "jd_key": "jd_" + "1" * 24,
        "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_k8s",
        "split": "dev",
        "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "not_evidenced", "score": None, "evidence": []},
        "annotations": [
            {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "not_evidenced", "score": None, "evidence": []},
            {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True, "status": "not_evidenced", "score": None, "evidence": []},
        ],
        "prediction": {"status": "not_evidenced", "score": None, "evidence": []},
    }]
    package = EvaluationPackage.model_validate(payload)
    result = evaluate_assessment(package, split="dev")
    assert result["evidence"]["exact_span_precision"] == 1
    assert result["evidence"]["exact_span_recall"] == 1
    assert result["unsupported_claim_rate"] == 0
    assert result["score"]["mae"] == 2
    assert result["score"]["paired_score_count"] == 1
    assert result["status"]["agreement"] == 1
    assert "retrieval" not in result


def test_assessment_evidence_spans_are_scoped_to_jd() -> None:
    payload = retrieval_package().model_dump(mode="json")
    second_jd = "jd_" + "2" * 24
    second_rubric_key = "rub_" + "2" * 24
    second_rubric = {
        "rubric_key": second_rubric_key,
        "jd_key": second_jd,
        "approved_by_refs": ["approval_hr_2", "approval_it_2"],
        "criteria": [{
            "criterion_key": "crit_api",
            "description": "Design idempotent REST APIs",
            "anchors": [{"score": score, "description": f"anchor {score}"} for score in range(5)],
        }],
    }
    second_rubric["sha256"] = hashlib.sha256(
        json.dumps(second_rubric, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["rubrics"].append(second_rubric)
    payload["source_documents"].append({
        "document_key": second_jd, "kind": "jd", "sha256": "e" * 64,
    })
    payload["splits"].append({
        "candidate_key": "cand_" + "1" * 24, "jd_key": second_jd, "split": "dev",
    })
    first_case = {
        "case_key": "case_" + "a" * 24,
        "candidate_key": "cand_" + "1" * 24,
        "jd_key": "jd_" + "1" * 24,
        "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_api", "split": "dev", "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        "annotations": [
            {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
            {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        ],
        "prediction": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
    }
    second_case = {
        **first_case,
        "case_key": "case_" + "b" * 24,
        "jd_key": second_jd,
        "rubric_key": second_rubric_key,
        "adjudicated": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        "prediction": {"status": "not_evidenced", "score": None, "evidence": []},
    }
    payload["assessments"] = [first_case, second_case]
    result = evaluate_assessment(EvaluationPackage.model_validate(payload), split="dev")
    assert result["evidence"]["predicted_span_count"] == 1
    assert result["evidence"]["adjudicated_span_count"] == 2
    assert result["evidence"]["exact_span_match_count"] == 1
    assert result["evidence"]["exact_span_precision"] == 1
    assert result["evidence"]["exact_span_recall"] == 0.5


def test_assessment_reports_pre_adjudication_status_and_score_agreement() -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["assessments"] = [{
        "case_key": "case_" + "a" * 24, "candidate_key": "cand_" + "1" * 24,
        "jd_key": "jd_" + "1" * 24, "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_api", "split": "dev", "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        "annotations": [
            {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
            {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True, "status": "partial", "score": 3, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
        ],
        "adjudication_reason": "Anchor interpretation differed.",
        "prediction": {"status": "supported", "score": 4, "evidence": [{"start": 0, "end": 9, "quote": "REST APIs"}]},
    }, {
        "case_key": "case_" + "b" * 24, "candidate_key": "cand_" + "2" * 24,
        "jd_key": "jd_" + "1" * 24, "rubric_key": "rub_" + "1" * 24,
        "criterion_key": "crit_k8s", "split": "dev", "adjudicator_key": "ann_" + "3" * 24,
        "adjudicated": {"status": "not_evidenced", "score": None, "evidence": []},
        "annotations": [
            {"annotator_key": "ann_" + "1" * 24, "annotator_role": "hr", "blind_to_model": True, "status": "not_evidenced", "score": None, "evidence": []},
            {"annotator_key": "ann_" + "2" * 24, "annotator_role": "it", "blind_to_model": True, "status": "not_evidenced", "score": None, "evidence": []},
        ],
        "prediction": {"status": "not_evidenced", "score": None, "evidence": []},
    }]
    result = evaluate_assessment(EvaluationPackage.model_validate(payload), split="dev")
    agreement = result["human_human_agreement"]
    assert agreement["status"]["exact_agreement"] == 0.5
    assert agreement["status"]["paired_count"] == 2
    assert agreement["score"]["paired_count"] == 1
    assert agreement["score"]["quadratic_weighted_kappa"] == 0
    assert agreement["score"]["undefined_reason"] is None
    assert result["score"]["mae"] == 0


def write_verified_package(tmp_path: Path, package: dict | None = None, jd_text: bytes = b"Design idempotent REST APIs\nOperate Kubernetes services") -> bytes:
    import hashlib

    source_blobs = {
        b"REST APIs": hashlib.sha256(b"REST APIs").hexdigest(),
        jd_text: hashlib.sha256(jd_text).hexdigest(),
    }
    source_files = {f"sources/{digest}.blob": digest for digest in source_blobs.values()}
    source_manifest_hash = hashlib.sha256(json.dumps(source_files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "sources").mkdir()
    for blob, digest in source_blobs.items():
        (tmp_path / "sources" / f"{digest}.blob").write_bytes(blob)
    package = package or retrieval_package().model_dump(mode="json")
    package["source"]["sha256"] = source_manifest_hash
    package["source_documents"][0]["sha256"] = source_blobs[b"REST APIs"]
    package["source_documents"][1]["sha256"] = source_blobs[b"REST APIs"]
    package["source_documents"][2]["sha256"] = source_blobs[jd_text]
    raw = json.dumps(package, sort_keys=True, separators=(",", ":")).encode()
    (tmp_path / "annotations.json").write_bytes(raw)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "schema_version": "human-evaluation-package.v1",
        "source_name": "local-authorized-sample",
        "source_snapshot": "snapshot-2026-10-09",
        "source_sha256": source_manifest_hash,
        "permission_ref": "approval-001",
        "files": {"annotations.json": __import__("hashlib").sha256(raw).hexdigest()},
        "source_files": source_files,
    }))
    return source_blobs[b"REST APIs"]


def test_query_source_jd_must_be_in_pinned_jd(tmp_path: Path) -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["retrieval"][0]["query_source"] = "jd"
    payload["retrieval"][0]["query_text"] = "Design idempotent REST APIs"
    write_verified_package(tmp_path, payload)
    assert load_verified_package(tmp_path).retrieval[0].query_source == "jd"


def test_jd_criterion_query_matches_rubric_without_literal_jd_occurrence(tmp_path: Path) -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["retrieval"][0]["query_source"] = "jd_criterion"
    payload["retrieval"][0]["query_text"] = "Design idempotent REST APIs"
    write_verified_package(tmp_path, payload, b"API engineering responsibilities")
    assert load_verified_package(tmp_path).retrieval[0].query_text == "Design idempotent REST APIs"


def test_jd_criterion_query_must_match_pinned_rubric(tmp_path: Path) -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["retrieval"][0]["query_source"] = "jd_criterion"
    payload["retrieval"][0]["query_text"] = "Different criterion wording"
    with pytest.raises(ValueError, match="QUERY_CRITERION_MISMATCH"):
        EvaluationPackage.model_validate(payload)


def test_jd_query_missing_from_pinned_jd_is_rejected(tmp_path: Path) -> None:
    payload = retrieval_package().model_dump(mode="json")
    payload["retrieval"][0]["query_source"] = "jd"
    payload["retrieval"][0]["query_text"] = "A requirement not in this JD"
    write_verified_package(tmp_path, payload)
    with pytest.raises(ValueError, match="QUERY_NOT_IN_JD_SOURCE"):
        load_verified_package(tmp_path)


def test_verified_reader_checks_manifest_hash_and_emits_only_safe_error(tmp_path: Path) -> None:
    source_digest = write_verified_package(tmp_path)
    assert load_verified_package(tmp_path).source.name == "local-authorized-sample"
    blob_path = tmp_path / "sources" / f"{source_digest}.blob"
    blob_path.write_bytes(b"tampered source")
    with pytest.raises(ValueError, match="SOURCE_FILE_HASH_MISMATCH"):
        load_verified_package(tmp_path)
    blob_path.write_bytes(b"REST APIs")
    annotation_path = tmp_path / "annotations.json"
    annotation_path.write_bytes(annotation_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="PACKAGE_HASH_MISMATCH") as exc:
        load_verified_package(tmp_path)
    assert "cand_" not in str(exc.value)


def test_conflicting_evidence_remains_distinct_from_missing_and_contradicted() -> None:
    conflicting = CriterionLabel.model_validate({
        "status": "conflicting_evidence", "score": None,
        "evidence": [
            {"start": 0, "end": 9, "quote": "Built API"},
            {"start": 9, "end": 20, "quote": "Never built"},
        ],
    })
    missing = CriterionLabel.model_validate({
        "status": "not_evidenced", "score": None, "evidence": [],
    })
    contradicted = CriterionLabel.model_validate({
        "status": "contradicted", "score": 0,
        "evidence": [{"start": 0, "end": 11, "quote": "Never built"}],
    })
    assert conflicting.status == "conflicting_evidence" and conflicting.score is None
    assert missing.status == "not_evidenced" and missing.score is None and not missing.evidence
    assert contradicted.status == "contradicted" and contradicted.score == 0

    with pytest.raises(ValueError, match="CONFLICTING_EVIDENCE_REQUIRES_TWO_SPANS"):
        CriterionLabel.model_validate({
            "status": "conflicting_evidence", "score": None,
            "evidence": [{"start": 0, "end": 9, "quote": "Built API"}],
        })
    with pytest.raises(ValueError, match="CONFLICTING_EVIDENCE_SCORE_MUST_BE_NULL"):
        CriterionLabel.model_validate({
            "status": "conflicting_evidence", "score": 1,
            "evidence": [
                {"start": 0, "end": 9, "quote": "Built API"},
                {"start": 9, "end": 20, "quote": "Never built"},
            ],
        })
