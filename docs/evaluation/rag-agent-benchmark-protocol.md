# TalentScreen AI RAG and agent evaluation protocol

**Version:** 1.0  
**Prepared:** 2026-10-07  
**State:** Protocol draft for HR/IT review. It is not a result report or go-live approval.

## Purpose and limits

This protocol tests whether the system retrieves CV evidence for approved, job-related rubric criteria, cites only evidence that exists in the retrieved snapshot, keeps scores grounded, behaves consistently under irrelevant identity changes, fails safely, and stays within latency and cost limits. It does not authorize automated screening, rejection, advancement, or ranking decisions. HR remains accountable for each decision.

The committed fixture at `fixtures/rag_benchmark/synthetic.jsonl` contains invented IDs, scores, spans, timing, and cost only. Its `locked_holdout` split exists to test the CLI guard and reporting path. Because it is committed and visible to developers, it is **not a statistically or operationally protected holdout** and must never be cited as validation evidence. The companion SHA-256 manifest detects accidental changes; it does not prevent a maintainer from replacing the data and recomputing the hashes.

The previously reviewed local download set contained seven CVs across Backend Node/NestJS (2), AI/ML (2), .NET Full-stack (1), Android (1), and Java/Spring Backend (1). The eighth PDF was a Product Owner job description, not a CV. These are routing and integration-smoke counts only. They do not provide enough examples per role to validate accuracy, agreement, fairness, ranking, or real hiring use. The PDFs and any labels derived from them must remain in approved private storage; never add them, extracted text, embeddings, evidence spans, provider payloads, or per-person outputs to Git.

## Public role-family context

The public TopCV pages below were checked on 2026-10-07. Search-category pages are market snapshots and can include a mixture of levels or postings whose individual closing dates differ; they are not a substitute for the actual approved requisition JD. The benchmark uses only the following derived, job-related capability areas. It does not reproduce employer text or use school, age, gender, photograph, hometown, or other protected/irrelevant attributes.

| Intended CV role family | Public source snapshot | Derived capability areas for rubric review |
|---|---|---|
| Backend Node/NestJS | [TopCV Backend Intern listings](https://www.topcv.vn/tim-viec-lam/backend-intern), page updated 2026-10-06 | Individual backend contribution; HTTP/API behavior; data persistence; tests, debugging, and delivery. |
| AI/ML Intern | [TopCV AI Intern listings](https://www.topcv.vn/tim-viec-lam/intern-ai), page updated 2026-09-16 | Python/data work; model or experiment implementation; appropriate evaluation; reproducibility and integration. |
| .NET Full-stack Intern | [TopCV .NET Intern listings](https://www.topcv.vn/tim-viec-lam/net-intern), page updated 2026-09-13 | C#/.NET implementation; API/data integration; UI-to-service flow; testing and Git delivery. |
| Android Intern | [TopCV Android Intern listings](https://www.topcv.vn/tim-viec-lam/intern-android), page updated 2026-07-09 | Kotlin/Java mobile feature work; lifecycle/navigation; API or local persistence; testing and debugging. |
| Java/Spring Backend Intern | [TopCV Java Intern listings](https://www.topcv.vn/tim-viec-lam/java-intern?exp=4), page updated 2026-10-06 | Java/Spring implementation; REST/API behavior; SQL/data access; testing and debugging. |

These sources guide the role-family vocabulary only. Before evaluation of a real vacancy, HR and the technical reviewer must use the university's actual approved JD, remove non-job-related criteria, approve a role-specific rubric and anchors, and record the source JD version. Do not infer the candidate's intended role from a CV where the application/requisition has not established it.

## Dataset, labels, and split governance

For each enabled job family, create a separate versioned dataset with an immutable manifest. Store private datasets and reports in institution-approved storage with least-privilege access and an auditable access trail. The Git repository may contain synthetic data only.

1. Freeze the approved JD, rubric, criterion anchors, extraction/redaction version, chunker/retriever/embedding versions, prompts, model identifiers, and tool policy before collecting predictions.
2. Create development and holdout cohorts at the requisition/family level. Keep related documents, duplicate CV versions, and counterfactual pairs in one split to prevent leakage. Record inclusion/exclusion counts and reasons without applicant identifiers in exported reports.
3. Have HR and an IT/domain reviewer label the same CV/JD/rubric independently, criterion by criterion, while blind to model output and each other's labels. Each score requires a source-span reference and a written reason; use `null` when evidence is absent. Record disagreement and adjudicate with a third reviewer or a documented joint review. Preserve the independent labels for the human-to-human baseline.
4. Select thresholds from development results and the human-human baseline. Put the thresholds, dataset hash, reviewer protocol, and analysis plan in a dated approval record **before** opening the protected holdout. Do not tune prompts, retrieval, rubric anchors, or thresholds against holdout results.
5. Holdout access belongs to a named evaluation custodian. Release it for one pre-registered evaluation, retain the report and hash, then treat it as consumed. Any material change to model, prompt, extraction, retrieval, rubric schema, or tool behavior requires a new holdout cohort or an explicitly approved revalidation design.
6. Record the exact `DeepSeek` and `Jev` provider/model/prompt versions separately. DeepSeek is the primary path. Jev 1.13 is an optional shadow scorer, off by default; it receives only an explicitly approved cohort and budget. Never average outputs or let Jev change the primary assessment or a hiring state. Compare each provider separately to human labels and each other only as a disagreement diagnostic.

For real datasets, the CLI needs a separate private synthetic-compatible adapter only after a privacy review. Do not weaken its schema or add raw text fields. Reports may include only counts, aggregate metrics, group/role/provider labels, and dataset hashes. Small groups should be suppressed or combined under the institution's disclosure policy.

## Metrics and interpretation

`python scripts/run_rag_benchmark.py --dataset PATH --output PATH` evaluates the development split by default. The committed synthetic fixture demonstrates the shape, not expected production performance. The CLI requires `--split locked_holdout --allow-locked-holdout` to evaluate that split. This flag is a procedural friction point, not an authorization system; access control must be enforced by storage and the evaluation custodian.

The companion file at `PATH.with_suffix(".manifest.json")` records the `data_scope`, dataset and split hashes, immutable split IDs, and a version context for approved rubric, extraction, retrieval, embedding, prompt, and model versions. The row schema accepts only stable opaque IDs, criteria and score anchors/nulls, source-span IDs and reviewer citation labels, counterfactual metadata, measured latency/cost/tool counts, and explicit status fields. Unknown fields—including raw CV text, names, email, prompt bodies, and model response bodies—are rejected. For an authorized private run, set `data_scope` to `restricted_evaluation`, use the institution-approved path and permissions, and keep both the input and generated aggregate report in that private storage. Private reports suppress overall or role/provider groups under five examples by default; set `--minimum-group-size` to the stricter threshold required by the institution's disclosure policy. The threshold cannot be lowered below five for restricted runs.

The aggregate report contains:

- Retrieval Recall@5 and Recall@10 against reviewer-labeled source span IDs.
- Citation span validity (citation ID appears in the exact retrieved evidence set) and unsupported-claim rate (reviewer marked claim unsupported).
- Criterion MAE and quadratic weighted kappa against the primary human label, the same agreement against the second human reviewer, scorable coverage, and Spearman rank correlation as a diagnostic only. Scores and SLO checks stay separate by provider and role; there is no cross-provider score average. Rank correlation uses the mean of comparable criterion anchors and is diagnostic only, not a candidate decision rule.
- Counterfactual score invariance when synthetic variants change name, pronoun, hometown, or school while qualifications stay fixed.
- Agent tool-call count, P50/P95 assessment, queue-wait, and provider latency; extraction/OCR time-budget rates; extraction/provider failure rates; manual-review routing; and estimated cost by role and provider.
- Provisional SLO statuses and a manual-fallback recommendation. Missing data is `NOT_EVALUABLE`, never a pass.

Initial targets from the approved architecture spec are proposals to discuss against human-human consistency, not certified thresholds: Recall@5 ≥ 0.85, citation validity 100%, unsupported claims 0%, criterion MAE ≤ 0.5 on 0–4 anchors, quadratic weighted kappa ≥ 0.60, ≥95% assessments within 2 minutes, ≥95% digital extraction/redaction within 2 minutes, ≥95% scanned OCR/extraction within 5 minutes, and supported-format extraction failures <5%. Queue wait, provider latency, and end-to-end assessment latency are reported separately. Every failure, timeout, invalid output, or extraction error must land in explicit manual review; no score is fabricated. The assessment worker also has a per-requisition budget and an outbound-attempt ceiling; report provider spend separately and verify actual provider invoices against estimates.

Agreement is not a truth measure. If HR and IT reviewers disagree materially, first clarify the rubric or evidence standard; do not tune AI merely to reproduce one reviewer's pattern. Review per-criterion errors, abstentions, unsupported citations, adverse/outlier cases, language and file-class differences, overrides, and confidence calibration before any threshold decision.

## Run commands and privacy checks

```bash
python scripts/run_rag_benchmark.py \
  --dataset fixtures/rag_benchmark/synthetic.jsonl \
  --output /tmp/talentscreen-rag-benchmark.json
```

Do not commit generated reports from real data. Before any authorized private-data run, verify consent/notice and institutional/provider authorization, redaction, the exact data scope, separate provider approval for Jev, cost ceilings, and deletion/retention rules. Use one provider at a time for primary quality comparisons; enable Jev only as a separate, explicitly approved shadow run.

## Current evidence status

- Synthetic evaluator/fixture: harness and regression only; the model IDs and prompt versions in the manifest are placeholders, and this fixture makes no DeepSeek or Jev API calls.
- Role-specific CV counts: local integration smoke only; not per-role validation.
- HR/IT independent blind labels and protected role-specific holdout: **NOT PROVIDED / NOT EVALUABLE** in this repository.
- Threshold approval before holdout: **PENDING**.
- DeepSeek and Jev evaluation through the final application workflow: **NOT ESTABLISHED BY THIS BENCHMARK**.
- Recommendation for real hiring use: **not authorized by this protocol** until the institution's reviewers complete the readiness gates in `docs/runbooks/rag-agent-readiness.md`.
