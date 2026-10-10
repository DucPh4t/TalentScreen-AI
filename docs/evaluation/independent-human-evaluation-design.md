# Independent human-labeled evaluation design

**Status:** protocol and evaluator implemented; no new quality evaluation has been run. A real run requires an independently authored JD/criteria set, approved data source, and completed blinded HR/IT labels.

This protocol evaluates two different tasks. It deliberately does not combine their metrics into a single quality score and does not predict hiring outcomes.

## 1. Data and provenance

Use only CVs and job descriptions for which the university has documented authority to process and evaluate the data. Keep source files, extracted text, annotation packages, identity maps, and outputs on an approved local system. Do not send CV text, excerpts, identifiers, or labels to DeepSeek, Jev, LangSmith, or any other external service for this evaluation. Source blobs contain only canonical sanitized extracted text. The package carries the exact HR/IT-approved rubric snapshot, all five score anchors per criterion, and a SHA-256 over its canonical serialized form.

Pin each source export/revision and a SHA-256 digest of a canonical, sorted local source-file manifest. Pin the exact annotation package bytes separately in `manifest.json`. The manifest also carries a local approval/consent reference. Candidate/JD keys must be random opaque keys or keyed HMACs; the identity mapping and HMAC key stay outside the evaluation package. Never use source row IDs as keys. Do not put CV text, PII, row IDs, or opaque record keys into logs or aggregate reports.

The reader accepts `manifest.json`, `annotations.json`, and the source blobs listed in `manifest.json`. Each source blob uses `sources/<sha256>.blob`; the manifest pins each blob hash and a canonical sorted hash of that mapping. The source-document index binds opaque candidate/JD keys to those hashes. Before metrics, the reader verifies every blob, checks each evidence quote at its zero-based Unicode character offsets, and checks that each query occurs in its pinned JD text. It rejects symlinks/path traversal and undeclared files, validates the package schema and source provenance, and emits only stable error codes. Keep original filenames and the identity map outside this package. The package records extractor/redaction version identifiers; detailed configuration belongs in the controlled source snapshot and never in logs.

## 2. Retrieval task

### Query and unit

A query is copied from an approved JD or one of its competency criteria, independent of every CV being judged. Record `query_source` as `jd` or `jd_criterion`, the exact query text, JD key, criterion key, and hash-pinned approved rubric. A reviewer must confirm that the query was not authored by reading the target CV. Never derive a query from `Primary Keyword`, `Position`, or any field of a CV.

The unit is one JD/criterion query against a declared candidate pool. The pool is judged completely by two independent annotators: at least one HR and one IT reviewer. Each candidate receives relevance grade 0–3 and exact supporting evidence spans for grades 1–3; grade 0 has no evidence. The adjudicated grade/evidence is stored in `judgments`; both blinded annotators' own labels are retained in `annotations`. A separate adjudicator key records who resolved differences; write `adjudication_reason` when the two sets differ. All retrieved candidates must belong to the judged pool; otherwise the evaluator rejects the package instead of silently treating unjudged items as irrelevant.

### Metrics

For query `q`, relevant means adjudicated grade greater than 0. Let `R_q` be the count of relevant candidates in its complete judged pool and `Rel_q@K` the relevant candidates in the first K results.

`Recall@K_q = |Rel_q@K| / R_q`.

nDCG uses gain `2^grade - 1` and discount `log2(rank + 1)` (rank is one-based). `DCG@K` sums discounted gains for returned candidates; `IDCG@K` uses the same formula after sorting all candidates in that judged pool by adjudicated grade. `nDCG@K = DCG@K / IDCG@K`.

Report each metric as a **macro-average over queries with at least one relevant candidate**; each query has equal weight. For a query with no relevant candidate, Recall and nDCG are undefined and excluded from the metric mean. Report `no_positive_query_count` and `no_positive_with_return_count` beside the metric so abstention/false-return behavior on those queries is visible. If there are no positive queries, the metric value is `null`, never zero. An empty result on a positive query has Recall@K and nDCG@K equal to zero.

Compute retrieval ranking and HR–IT relevance agreement on exactly one explicit split (`train`, `dev`, or `holdout`) at a time. Do not aggregate splits in a reported result. Report the selected split and query count.

Before adjudication, report HR–IT relevance quadratic weighted kappa over paired candidate judgments, with pair/query counts and an explicit undefined reason when it cannot be computed. This measures label reliability, not model quality.

This is a judged-pool retrieval measurement. It is not candidate–job suitability, ranking quality over an unjudged corpus, or hiring effectiveness.

## 3. Rubric assessment task

The unit is one candidate–JD–criterion tuple, with the criterion and scoring anchors frozen before annotation. One HR and one IT annotator independently record one status, an exact evidence span (except for `not_evidenced`), and a 0–4 rubric score or `null`. `blind_to_model` must be true: annotators cannot view any model output before their labels are frozen. A separate adjudicator resolves differences and is recorded by an opaque key.

- `supported`: evidence in the CV supports the stated competency at the selected rubric anchor.
- `partial`: evidence supports only part of the competency/scope.
- `not_evidenced`: the supplied CV does not state assessable evidence; score must be `null`. This means **unknown from this CV**, not that the applicant lacks the skill.
- `contradicted`: explicit CV evidence conflicts with the criterion claim; cite the exact conflicting text and score only according to the preapproved rubric.
- `conflicting_evidence`: the same criterion has at least two exact spans that support materially incompatible interpretations; score must be `null` until a human adjudicator resolves the conflict. This is distinct from `not_evidenced` (no assessable evidence) and `contradicted` (an explicit negative statement with no competing positive evidence in the scoped record). Do not silently map one state to another.

An adjudicator reviews disagreement after both independent labels are saved. Retain both original labels, final status/evidence/score, and a reason when status, score, or evidence spans differ. No LLM creates or adjudicates gold labels.

Report pre-adjudication annotator reliability separately from model agreement: exact HR–IT status agreement and quadratic weighted kappa for paired non-null rubric scores, including paired, jointly-null, one-sided-null, and undefined counts/reasons.

Report these separately against the adjudicated label:

- **Evidence accuracy:** exact-span precision, recall, and F1 over distinct `(candidate, JD, case, criterion, start, end)` spans. Exact boundaries are required. Offsets are zero-based Unicode code-point offsets in the pinned canonical sanitized text; the quote must equal the source substring.
- **Unsupported-claim rate:** among model criterion predictions with a non-null score, the fraction whose cited evidence has no character overlap with adjudicated evidence for the same candidate–JD–case–criterion. Also report numerator and denominator.
- **Status agreement:** exact status match rate.
- **Score agreement:** MAE and quadratic weighted kappa on pairs where both adjudicated and model scores are non-null, plus paired and total score counts. No-evidence/null coverage stays visible via adjudicated and predicted score counts.

Do not compute one composite. These measure agreement with the adjudicated rubric labels, not prediction of hiring success.

## 4. Sampling and split discipline

Create a sampling frame before looking at model output. Include positive examples, clear negatives, hard negatives (lexical/topic overlap without the required competency), and cases with insufficient CV evidence. Sample from the eligible authorized population without conditioning inclusion on a matching keyword or existing evidence. Record selection method and counts in the controlled study notes.

Assign splits before any prompt/model/threshold tuning. Use connected components of the candidate–JD bipartite graph so neither a candidate nor a JD appears in more than one of `train`, `dev`, and `holdout`. Keep the holdout package inaccessible to prompt authors until configuration is frozen. Do not tune on holdout. If the available data cannot satisfy disjoint candidate and JD splits, report that constraint and do not call the split a holdout.

One HR and one IT reviewer work independently with an agreed rubric and exact-span instructions. Calibrate the rubric on a separate dev set, record rubric changes, then freeze it before holdout annotation. Resolve disagreements in adjudication, not by changing the original labels. Keep the adjudicator blind to model output too.

## 5. Run procedure and privacy

1. Approve and locally stage a source export; record the authority/consent reference and immutable source revision. Create the authorized HR/IT-approved rubric snapshot and compute its canonical SHA-256 as `sha256(json.dumps(snapshot_without_sha256, sort_keys=True, separators=(",", ":")).encode("utf-8"))` before annotators begin.
2. Extract canonical sanitized CV text locally, pin extractor and redaction versions, and create opaque keys. Do not store the identity map in the annotation package.
3. Author independent JD/criterion queries and rubric anchors. Freeze query, rubric, and sampling manifests before annotators start.
4. Assign candidate/JD connected components to splits, then two annotators to each unit. Freeze individual labels before adjudication.
5. Create the package from the [annotation template](templates/annotations.example.json) and [manifest template](templates/manifest.example.json); compute exact hashes and have an authorized owner review it for PII and split leakage locally. Schemas are [here](../../schemas/evaluation/human-evaluation-v1.schema.json) and [here](../../schemas/evaluation/human-evaluation-manifest-v1.schema.json).
6. Run the local CLI. Store aggregate output in the approved local evaluation location. The CLI has no provider, network, LangSmith, or application-database integration.
7. Preserve package, source-manifest reference, evaluator version, command arguments, and aggregate output under access control and retention policy.

## 6. Current readiness and non-claims

The repository currently has no newly collected independent HR/IT labels and no independent JD set for this protocol. Therefore no retrieval or assessment quality metric is reported by the new evaluator. Existing synthetic fixtures may continue to test software contracts but are not ground truth. No result from this protocol establishes fairness, legal compliance, or hiring validity by itself; those require separate reviewed studies and governance.

Run only after the package is complete and approved:

```bash
PYTHONPATH=services/backend .venv/bin/python scripts/evaluate_human_labels.py \
  --package /approved/local/path/evaluation-package --retrieval-k 5 --retrieval-split holdout \
  --output /approved/local/path/retrieval-aggregate.json

PYTHONPATH=services/backend .venv/bin/python scripts/evaluate_human_labels.py \
  --package /approved/local/path/evaluation-package --assessment-split holdout \
  --output /approved/local/path/assessment-aggregate.json
```

An empty task returns `NO_HUMAN_LABELS`; the CLI does not emit a placeholder quality report when independent annotations are missing.
