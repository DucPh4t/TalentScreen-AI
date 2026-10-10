"""Local-only metrics for independently human-labeled evaluation packages.

This module has no model/provider integrations. It accepts only validated,
annotated local records and returns aggregate metrics without identifiers/text.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from app.services.evaluation.metrics import criterion_mae, quadratic_weighted_kappa


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class EvidenceSpan(Contract):
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    quote: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def valid_range(self) -> "EvidenceSpan":
        if self.start >= self.end or len(self.quote) != self.end - self.start:
            raise ValueError("INVALID_EVIDENCE_OFFSETS")
        return self


class RetrievalJudgment(Contract):
    candidate_key: str = Field(pattern=r"^cand_[a-f0-9]{24}$")
    relevance: StrictInt = Field(ge=0, le=3)
    evidence: tuple[EvidenceSpan, ...] = ()

    @model_validator(mode="after")
    def evidence_matches_relevance(self) -> "RetrievalJudgment":
        if (self.relevance == 0) != (not self.evidence):
            raise ValueError("RELEVANCE_EVIDENCE_MISMATCH")
        return self


class RetrievalAnnotation(Contract):
    annotator_key: str = Field(pattern=r"^ann_[a-f0-9]{24}$")
    annotator_role: Literal["hr", "it"]
    blind_to_model: Literal[True]
    judgments: tuple[RetrievalJudgment, ...] = Field(min_length=1)


class ScoreAnchor(Contract):
    score: StrictInt = Field(ge=0, le=4)
    description: str = Field(min_length=1, max_length=1000)


class RubricCriterion(Contract):
    criterion_key: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    anchors: tuple[ScoreAnchor, ...] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def complete_anchors(self) -> "RubricCriterion":
        if {anchor.score for anchor in self.anchors} != {0, 1, 2, 3, 4} or any(not anchor.description.strip() for anchor in self.anchors):
            raise ValueError("RUBRIC_ANCHORS_INVALID")
        return self


class RubricSnapshot(Contract):
    rubric_key: str = Field(pattern=r"^rub_[a-f0-9]{24}$")
    jd_key: str = Field(pattern=r"^jd_[a-f0-9]{24}$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_by_refs: tuple[str, ...] = Field(min_length=2)
    criteria: tuple[RubricCriterion, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def frozen_approved_rubric(self) -> "RubricSnapshot":
        keys = [c.criterion_key for c in self.criteria]
        if len(set(keys)) != len(keys) or len(set(self.approved_by_refs)) < 2:
            raise ValueError("RUBRIC_SNAPSHOT_INVALID")
        content = self.model_dump(exclude={"sha256"}, mode="json")
        digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if digest != self.sha256:
            raise ValueError("RUBRIC_HASH_MISMATCH")
        return self


class RetrievalQuery(Contract):
    query_key: str = Field(pattern=r"^qry_[a-f0-9]{24}$")
    jd_key: str = Field(pattern=r"^jd_[a-f0-9]{24}$")
    rubric_key: str = Field(pattern=r"^rub_[a-f0-9]{24}$")
    criterion_key: str = Field(min_length=1, max_length=100)
    split: Literal["train", "dev", "holdout"]
    query_source: Literal["jd", "jd_criterion"]
    query_text: str = Field(min_length=5, max_length=4000)
    judgments: tuple[RetrievalJudgment, ...] = Field(min_length=1)
    annotations: tuple[RetrievalAnnotation, ...] = Field(min_length=2)
    adjudicator_key: str = Field(pattern=r"^ann_[a-f0-9]{24}$")
    adjudication_reason: str = Field(min_length=1, max_length=2000)
    ranked_candidates: tuple[str, ...] = ()

    @model_validator(mode="after")
    def complete_blind_double_annotation(self) -> "RetrievalQuery":
        annotators = [a.annotator_key for a in self.annotations]
        if (len(annotators) != 2 or len(set(annotators)) != 2
            or {a.annotator_role for a in self.annotations} != {"hr", "it"}
            or self.adjudicator_key in annotators):
            raise ValueError("ANNOTATOR_REQUIREMENT")
        gold = {j.candidate_key: j.model_dump() for j in self.judgments}
        for annotation in self.annotations:
            rows = {j.candidate_key: j.model_dump() for j in annotation.judgments}
            if rows.keys() != gold.keys():
                raise ValueError("ANNOTATION_POOL_INCOMPLETE")
        annotation_labels = [
            {j.candidate_key: (j.relevance, tuple((s.start, s.end, s.quote) for s in j.evidence)) for j in a.judgments}
            for a in self.annotations
        ]
        if any(labels != annotation_labels[0] for labels in annotation_labels[1:]) and not self.adjudication_reason.strip():
            raise ValueError("ADJUDICATION_REASON_REQUIRED")
        if len(set(self.ranked_candidates)) != len(self.ranked_candidates):
            raise ValueError("DUPLICATE_RETRIEVED_CANDIDATE")
        if set(self.ranked_candidates) - gold.keys():
            raise ValueError("UNJUDGED_RETRIEVED_CANDIDATE")
        return self


AssessmentStatus = Literal[
    "supported", "partial", "not_evidenced", "contradicted", "conflicting_evidence"
]


class CriterionLabel(Contract):
    status: AssessmentStatus
    score: StrictInt | None = Field(ge=0, le=4)
    evidence: tuple[EvidenceSpan, ...] = ()

    @model_validator(mode="after")
    def status_score_evidence_consistency(self) -> "CriterionLabel":
        # These states intentionally remain distinct: not_evidenced means no
        # assessable CV evidence; contradicted means an explicit scoped negative
        # claim; conflicting_evidence means both directions have cited evidence
        # and therefore cannot receive one ordinal score without adjudication.
        if self.status == "not_evidenced":
            if self.score is not None:
                raise ValueError("NOT_EVIDENCED_SCORE_MUST_BE_NULL")
            if self.evidence:
                raise ValueError("NOT_EVIDENCED_CANNOT_HAVE_EVIDENCE")
        elif self.status == "conflicting_evidence":
            if self.score is not None:
                raise ValueError("CONFLICTING_EVIDENCE_SCORE_MUST_BE_NULL")
            if len(self.evidence) < 2:
                raise ValueError("CONFLICTING_EVIDENCE_REQUIRES_TWO_SPANS")
        elif self.score is None or not self.evidence:
            raise ValueError("EVIDENCE_AND_SCORE_REQUIRED")
        return self


class IndependentCriterionAnnotation(CriterionLabel):
    annotator_key: str = Field(pattern=r"^ann_[a-f0-9]{24}$")
    annotator_role: Literal["hr", "it"]
    blind_to_model: Literal[True]


class AssessmentCase(Contract):
    case_key: str = Field(pattern=r"^case_[a-f0-9]{24}$")
    candidate_key: str = Field(pattern=r"^cand_[a-f0-9]{24}$")
    jd_key: str = Field(pattern=r"^jd_[a-f0-9]{24}$")
    rubric_key: str = Field(pattern=r"^rub_[a-f0-9]{24}$")
    criterion_key: str = Field(min_length=1, max_length=100)
    split: Literal["train", "dev", "holdout"]
    adjudicator_key: str = Field(pattern=r"^ann_[a-f0-9]{24}$")
    adjudicated: CriterionLabel
    annotations: tuple[IndependentCriterionAnnotation, ...] = Field(min_length=2)
    adjudication_reason: str | None = Field(default=None, max_length=2000)
    prediction: CriterionLabel

    @model_validator(mode="after")
    def independent_review_and_adjudication(self) -> "AssessmentCase":
        annotators = [a.annotator_key for a in self.annotations]
        if (len(annotators) != 2 or len(set(annotators)) != 2
            or {a.annotator_role for a in self.annotations} != {"hr", "it"}
            or self.adjudicator_key in annotators):
            raise ValueError("ANNOTATOR_REQUIREMENT")
        compared = [
            (a.status, a.score, tuple((s.start, s.end, s.quote) for s in a.evidence))
            for a in self.annotations
        ]
        if len(set(compared)) > 1 and not (self.adjudication_reason or "").strip():
            raise ValueError("ADJUDICATION_REASON_REQUIRED")
        return self


class SplitAssignment(Contract):
    candidate_key: str = Field(pattern=r"^cand_[a-f0-9]{24}$")
    jd_key: str = Field(pattern=r"^jd_[a-f0-9]{24}$")
    split: Literal["train", "dev", "holdout"]


class SourceProvenance(Contract):
    name: str = Field(min_length=1, max_length=160)
    snapshot: str = Field(min_length=1, max_length=300)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    permission_ref: str = Field(min_length=1, max_length=200)
    text_extractor_version: str = Field(min_length=1, max_length=100)
    redaction_version: str = Field(min_length=1, max_length=100)


class SourceDocument(Contract):
    document_key: str = Field(pattern=r"^(cand|jd)_[a-f0-9]{24}$")
    kind: Literal["cv", "jd"]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def key_matches_kind(self) -> "SourceDocument":
        if (self.kind == "cv") != self.document_key.startswith("cand_"):
            raise ValueError("SOURCE_DOCUMENT_KIND_MISMATCH")
        return self


class PackageManifest(Contract):
    schema_version: Literal["human-evaluation-package.v1"]
    source_name: str = Field(min_length=1, max_length=160)
    source_snapshot: str = Field(min_length=1, max_length=300)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    permission_ref: str = Field(min_length=1, max_length=200)
    files: dict[str, str]
    source_files: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_pins(self) -> "PackageManifest":
        if set(self.files) != {"annotations.json"} or not re.fullmatch(r"[a-f0-9]{64}", self.files["annotations.json"]):
            raise ValueError("PACKAGE_MANIFEST_SCHEMA_INVALID")
        for relative, digest in self.source_files.items():
            path = PurePosixPath(relative)
            if (path.is_absolute() or len(path.parts) != 2 or path.parts[0] != "sources"
                or not re.fullmatch(r"[a-f0-9]{64}\.blob", path.parts[-1])
                or path.parts[-1][:-5] != digest
                or not re.fullmatch(r"[a-f0-9]{64}", digest)):
                raise ValueError("PACKAGE_SOURCE_PATH_INVALID")
        if _source_manifest_hash(self.source_files) != self.source_sha256:
            raise ValueError("SOURCE_MANIFEST_HASH_MISMATCH")
        return self


class EvaluationPackage(Contract):
    schema_version: Literal["human-evaluation.v1"]
    source: SourceProvenance
    source_documents: tuple[SourceDocument, ...] = Field(min_length=2)
    rubrics: tuple[RubricSnapshot, ...] = Field(min_length=1)
    splits: tuple[SplitAssignment, ...] = Field(min_length=1)
    retrieval: tuple[RetrievalQuery, ...] = ()
    assessments: tuple[AssessmentCase, ...] = ()

    @model_validator(mode="after")
    def validate_split_integrity_and_unique_units(self) -> "EvaluationPackage":
        rubrics = {rubric.rubric_key: rubric for rubric in self.rubrics}
        if len(rubrics) != len(self.rubrics):
            raise ValueError("DUPLICATE_RUBRIC")
        documents = {doc.document_key: doc for doc in self.source_documents}
        if len(documents) != len(self.source_documents):
            raise ValueError("DUPLICATE_SOURCE_DOCUMENT")
        candidate_splits: dict[str, str] = {}
        jd_splits: dict[str, str] = {}
        pairs: dict[tuple[str, str], str] = {}
        for row in self.splits:
            if documents.get(row.candidate_key) is None or documents[row.candidate_key].kind != "cv":
                raise ValueError("CANDIDATE_SOURCE_MISSING")
            if documents.get(row.jd_key) is None or documents[row.jd_key].kind != "jd":
                raise ValueError("JD_SOURCE_MISSING")
            for mapping, key in ((candidate_splits, row.candidate_key), (jd_splits, row.jd_key)):
                prior = mapping.setdefault(key, row.split)
                if prior != row.split:
                    raise ValueError("SPLIT_LEAKAGE")
            pair = (row.candidate_key, row.jd_key)
            prior = pairs.setdefault(pair, row.split)
            if prior != row.split:
                raise ValueError("SPLIT_LEAKAGE")
        seen_queries: set[str] = set()
        for query in self.retrieval:
            if query.query_key in seen_queries:
                raise ValueError("DUPLICATE_QUERY")
            seen_queries.add(query.query_key)
            if jd_splits.get(query.jd_key) != query.split:
                raise ValueError("QUERY_SPLIT_MISMATCH")
            rubric = rubrics.get(query.rubric_key)
            if rubric is None or rubric.jd_key != query.jd_key or query.criterion_key not in {c.criterion_key for c in rubric.criteria}:
                raise ValueError("QUERY_RUBRIC_MISMATCH")
            if query.query_source == "jd_criterion":
                criterion = next(c for c in rubric.criteria if c.criterion_key == query.criterion_key)
                if query.query_text != criterion.description:
                    raise ValueError("QUERY_CRITERION_MISMATCH")
            if documents.get(query.jd_key) is None or documents[query.jd_key].kind != "jd":
                raise ValueError("JD_SOURCE_MISSING")
            if any(candidate_splits.get(j.candidate_key) != query.split for j in query.judgments):
                raise ValueError("RETRIEVAL_SPLIT_MISMATCH")
        seen_assessments: set[tuple[str, str]] = set()
        for case in self.assessments:
            key = (case.case_key, case.criterion_key)
            if key in seen_assessments:
                raise ValueError("DUPLICATE_ASSESSMENT")
            seen_assessments.add(key)
            if candidate_splits.get(case.candidate_key) != case.split or jd_splits.get(case.jd_key) != case.split:
                raise ValueError("ASSESSMENT_SPLIT_MISMATCH")
            rubric = rubrics.get(case.rubric_key)
            if rubric is None or rubric.jd_key != case.jd_key or case.criterion_key not in {c.criterion_key for c in rubric.criteria}:
                raise ValueError("ASSESSMENT_RUBRIC_MISMATCH")
        return self


def _discounted_gain(grades: list[int], k: int) -> float:
    return sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(grades[:k]))


def evaluate_retrieval(
    package: EvaluationPackage, *, k: int, split: Literal["train", "dev", "holdout"]
) -> dict:
    """Macro Recall@K and nDCG@K over queries with >=1 relevant judged candidate.

    Relevance is graded 0..3; any grade >0 is relevant for recall. nDCG uses
    gain 2**grade-1 and log2(rank+2). A no-positive query has undefined recall
    and nDCG and is excluded from both means, but counted separately.
    """
    if type(k) is not int or k < 1:
        raise ValueError("INVALID_K")
    if split not in {"train", "dev", "holdout"}:
        raise ValueError("INVALID_SPLIT")
    queries = [query for query in package.retrieval if query.split == split]
    recalls: list[float] = []
    ndcgs: list[float] = []
    no_positive = 0
    no_positive_with_return = 0
    human_relevance_reference: list[int] = []
    human_relevance_other: list[int] = []
    human_relevance_pair_count = 0
    human_relevance_query_count = 0
    for query in queries:
        grades = {row.candidate_key: row.relevance for row in query.judgments}
        relevant_count = sum(grade > 0 for grade in grades.values())
        if not relevant_count:
            no_positive += 1
            no_positive_with_return += bool(query.ranked_candidates[:k])
        else:
            top = list(query.ranked_candidates[:k])
            recalls.append(sum(grades[key] > 0 for key in top) / relevant_count)
            dcg = _discounted_gain([grades[key] for key in top], k)
            ideal = _discounted_gain(sorted(grades.values(), reverse=True), k)
            ndcgs.append(dcg / ideal if ideal else 0.0)

        hr = [annotation for annotation in query.annotations if annotation.annotator_role == "hr"]
        it = [annotation for annotation in query.annotations if annotation.annotator_role == "it"]
        query_pair_count = 0
        for hr_annotation in hr:
            hr_labels = {row.candidate_key: row.relevance for row in hr_annotation.judgments}
            for it_annotation in it:
                it_labels = {row.candidate_key: row.relevance for row in it_annotation.judgments}
                for candidate_key in sorted(hr_labels.keys() & it_labels.keys()):
                    human_relevance_reference.append(hr_labels[candidate_key])
                    human_relevance_other.append(it_labels[candidate_key])
                    query_pair_count += 1
        human_relevance_pair_count += query_pair_count
        human_relevance_query_count += bool(query_pair_count)
    human_relevance_kappa = quadratic_weighted_kappa(
        human_relevance_reference, human_relevance_other, scale=4
    )
    return {
        "k": k,
        "split": split,
        "query_count": len(queries),
        "metric_query_count": len(recalls),
        "no_positive_query_count": no_positive,
        "no_positive_with_return_count": no_positive_with_return,
        "recall_at_k": sum(recalls) / len(recalls) if recalls else None,
        "ndcg_at_k": sum(ndcgs) / len(ndcgs) if ndcgs else None,
        "human_human_relevance": {
            "quadratic_weighted_kappa": human_relevance_kappa,
            "paired_count": human_relevance_pair_count,
            "query_count": human_relevance_query_count,
            "undefined_reason": (
                "NO_PAIRED_LABELS" if not human_relevance_pair_count
                else "DEGENERATE_EXPECTED_DISAGREEMENT" if human_relevance_kappa is None
                else None
            ),
        },
    }


def _span_key(jd_key: str, case_key: str, span: EvidenceSpan) -> tuple[str, str, int, int]:
    return jd_key, case_key, span.start, span.end


def _overlap(a: EvidenceSpan, b: EvidenceSpan) -> bool:
    return max(a.start, b.start) < min(a.end, b.end)


def _source_manifest_hash(files: dict[str, str]) -> str:
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_exact_source_spans(package: EvaluationPackage, source_files: dict[str, str], root: Path) -> None:
    by_hash = {digest: root / "sources" / f"{digest}.blob" for digest in source_files.values()}
    texts: dict[str, str] = {}
    for document in package.source_documents:
        if document.sha256 not in by_hash:
            raise ValueError("SOURCE_DOCUMENT_NOT_PINNED")
        try:
            texts[document.document_key] = by_hash[document.sha256].read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            raise ValueError("SOURCE_DOCUMENT_NOT_UTF8") from None
    for query in package.retrieval:
        if query.query_source == "jd" and query.query_text not in texts[query.jd_key]:
            raise ValueError("QUERY_NOT_IN_JD_SOURCE")
        for judgement in query.judgments:
            text = texts[judgement.candidate_key]
            if any(text[span.start:span.end] != span.quote for span in judgement.evidence):
                raise ValueError("EVIDENCE_SPAN_SOURCE_MISMATCH")
        for annotation in query.annotations:
            for judgement in annotation.judgments:
                text = texts[judgement.candidate_key]
                if any(text[span.start:span.end] != span.quote for span in judgement.evidence):
                    raise ValueError("EVIDENCE_SPAN_SOURCE_MISMATCH")
    for case in package.assessments:
        text = texts[case.candidate_key]
        labels = [case.adjudicated, case.prediction, *case.annotations]
        if any(text[span.start:span.end] != span.quote for label in labels for span in label.evidence):
            raise ValueError("EVIDENCE_SPAN_SOURCE_MISMATCH")


def evaluate_assessment(package: EvaluationPackage, *, split: Literal["train", "dev", "holdout"]) -> dict:
    """Return separate evidence, unsupported-claim, status, and score metrics."""
    rows = [row for row in package.assessments if row.split == split]
    reference_keys = {
        (row.candidate_key, row.criterion_key, *_span_key(row.jd_key, row.case_key, span))
        for row in rows for span in row.adjudicated.evidence
    }
    predicted_keys = {
        (row.candidate_key, row.criterion_key, *_span_key(row.jd_key, row.case_key, span))
        for row in rows for span in row.prediction.evidence
    }
    exact_matches = len(reference_keys & predicted_keys)
    scored_claims = [row for row in rows if row.prediction.score is not None]
    unsupported = sum(
        not any(
            _overlap(predicted, gold)
            for predicted in row.prediction.evidence
            for gold in row.adjudicated.evidence
        )
        for row in scored_claims
    )
    status_pairs = [(row.adjudicated.status, row.prediction.status) for row in rows]
    score_pairs = [
        (row.adjudicated.score, row.prediction.score)
        for row in rows
        if row.adjudicated.score is not None and row.prediction.score is not None
    ]
    references = [int(a) for a, _ in score_pairs]
    predictions = [int(b) for _, b in score_pairs]
    human_status_pairs: list[tuple[str, str]] = []
    human_score_reference: list[int] = []
    human_score_other: list[int] = []
    jointly_null_score_pairs = 0
    one_sided_null_score_pairs = 0
    for row in rows:
        hr = [annotation for annotation in row.annotations if annotation.annotator_role == "hr"]
        it = [annotation for annotation in row.annotations if annotation.annotator_role == "it"]
        for hr_annotation in hr:
            for it_annotation in it:
                human_status_pairs.append((hr_annotation.status, it_annotation.status))
                if hr_annotation.score is not None and it_annotation.score is not None:
                    human_score_reference.append(hr_annotation.score)
                    human_score_other.append(it_annotation.score)
                elif hr_annotation.score is None and it_annotation.score is None:
                    jointly_null_score_pairs += 1
                else:
                    one_sided_null_score_pairs += 1
    human_score_kappa = quadratic_weighted_kappa(
        human_score_reference, human_score_other, scale=5
    )
    human_status_pair_count = len(human_status_pairs)
    return {
        "split": split,
        "case_count": len(rows),
        "evidence": {
            "exact_span_precision": exact_matches / len(predicted_keys) if predicted_keys else None,
            "exact_span_recall": exact_matches / len(reference_keys) if reference_keys else None,
            "exact_span_f1": (2 * exact_matches / (len(predicted_keys) + len(reference_keys)))
            if predicted_keys or reference_keys else None,
            "exact_span_match_count": exact_matches,
            "predicted_span_count": len(predicted_keys),
            "adjudicated_span_count": len(reference_keys),
        },
        "unsupported_claim_rate": unsupported / len(scored_claims) if scored_claims else None,
        "unsupported_claim_count": unsupported,
        "scored_claim_count": len(scored_claims),
        "human_human_agreement": {
            "status": {
                "exact_agreement": (
                    sum(a == b for a, b in human_status_pairs) / human_status_pair_count
                    if human_status_pair_count else None
                ),
                "paired_count": human_status_pair_count,
                "undefined_reason": "NO_PAIRED_LABELS" if not human_status_pair_count else None,
            },
            "score": {
                "quadratic_weighted_kappa": human_score_kappa,
                "paired_count": len(human_score_reference),
                "jointly_null_count": jointly_null_score_pairs,
                "one_sided_null_count": one_sided_null_score_pairs,
                "undefined_reason": (
                    "NO_PAIRED_SCORES" if not human_score_reference
                    else "DEGENERATE_EXPECTED_DISAGREEMENT" if human_score_kappa is None
                    else None
                ),
            },
        },
        "status": {
            "agreement": sum(a == b for a, b in status_pairs) / len(status_pairs) if status_pairs else None,
            "paired_count": len(status_pairs),
        },
        "score": {
            "mae": criterion_mae(references, predictions),
            "quadratic_weighted_kappa": quadratic_weighted_kappa(references, predictions, scale=5),
            "paired_score_count": len(score_pairs),
            "adjudicated_score_count": sum(row.adjudicated.score is not None for row in rows),
            "prediction_score_count": sum(row.prediction.score is not None for row in rows),
        },
    }


def load_verified_package(directory: str | Path) -> EvaluationPackage:
    """Read one local annotation package after SHA-256 verification.

    The manifest pins the exact annotation artifact and the upstream source
    snapshot/hash. File names are restricted to one basename; no path can escape
    the chosen directory. Errors intentionally omit local path, ID and content.
    """
    root = Path(directory).resolve(strict=True)
    manifest_path = root / "manifest.json"
    try:
        if manifest_path.is_symlink() or manifest_path.resolve(strict=True).parent != root:
            raise ValueError("PACKAGE_PATH_INVALID")
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        try:
            manifest = PackageManifest.model_validate(manifest_payload)
        except ValidationError:
            raise ValueError("PACKAGE_MANIFEST_SCHEMA_INVALID") from None
        source_files = manifest.source_files
        for relative, expected_hash in sorted(source_files.items()):
            rel = PurePosixPath(relative)
            source_path = root.joinpath(*rel.parts)
            if any(part.is_symlink() for part in (root / "sources", source_path)):
                raise ValueError("PACKAGE_SOURCE_PATH_INVALID")
            if source_path.resolve(strict=True).parent != (root / "sources").resolve(strict=True):
                raise ValueError("PACKAGE_SOURCE_PATH_INVALID")
            if _sha256_file(source_path) != expected_hash:
                raise ValueError("SOURCE_FILE_HASH_MISMATCH")
        name = "annotations.json"
        candidate = root / name
        if candidate.is_symlink() or candidate.resolve(strict=True).parent != root:
            raise ValueError("PACKAGE_PATH_INVALID")
        raw = candidate.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest.files[name]:
            raise ValueError("PACKAGE_HASH_MISMATCH")
        payload = json.loads(raw)
        try:
            package = EvaluationPackage.model_validate(payload)
        except ValidationError:
            raise ValueError("PACKAGE_SCHEMA_INVALID") from None
        # The package's declared provenance must agree with the pinned manifest.
        if (package.source.snapshot != manifest.source_snapshot
            or package.source.sha256 != manifest.source_sha256
            or package.source.permission_ref != manifest.permission_ref
            or package.source.name != manifest.source_name):
            raise ValueError("PACKAGE_PROVENANCE_MISMATCH")
        _validate_exact_source_spans(package, source_files, root)
        expected_names = {"manifest.json", "annotations.json", "sources"}
        if {item.name for item in root.iterdir()} != expected_names:
            raise ValueError("PACKAGE_UNEXPECTED_FILES")
        actual_blobs = {f"sources/{item.name}" for item in (root / "sources").iterdir() if item.is_file()}
        if actual_blobs != set(source_files):
            raise ValueError("PACKAGE_UNEXPECTED_FILES")
        return package
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("PACKAGE_READ_FAILED") from None
