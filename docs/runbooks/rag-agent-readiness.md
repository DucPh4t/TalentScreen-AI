# RAG and bounded-agent readiness gates

**Status: NOT READY for AI-assisted live hiring decisions.** This is a release checklist, not an approval record. A code path, synthetic test, or successful provider smoke call is not evidence that candidate scoring is suitable for a live hiring round.

## Required gates

| Gate | Evidence required before the gate can pass | Status |
|---|---|---|
| G1 — Vacancy and rubric | HR and an IT reviewer approve the real JD, role-specific dynamic rubric, job-related anchors, weights, and permitted missing-evidence behavior. Record immutable versions. | PENDING — no approved live vacancy package is attached. |
| G2 — Data handling | Institution's data owner confirms lawful/institutional processing, applicant notice/consent as required, provider/subprocessor scope, cross-border terms if applicable, retention, deletion, and backup-purge process. Record approvals outside public Git. | PENDING — repository controls do not establish institutional approval. |
| G3 — Dataset and labels | Authorized, source-pinned development and protected holdout cohorts; independent JD/criterion queries; HR/IT blind labels, exact evidence, adjudication, sampling log, and human-human baseline. No raw applicant data in Git. | PENDING — no independent JD set or new labels collected. |
| G4 — Retrieval and grounding | Macro Recall@K/nDCG@K on fully judged JD-derived pools; exact citation span accuracy, unsupported-claim audit, multilingual checks, and prompt-injection/security tests meet reviewer-approved thresholds on development and then untouched holdout. | PENDING — the 100-case AI-authored synthetic set is only a software regression fixture, not independent hiring-quality evidence. |
| G5 — Scoring, fairness, and HITL | Criterion MAE/agreement/coverage compared with human-human baseline; inspect every high-impact disagreement and HR override. Counterfactual name/pronoun/school/hometown invariance is 100% or any failure is explained and fixed. HR UI keeps evidence, uncertainty, provider disagreement, override reason, and final human decision visible. | PENDING — no qualified independent labels or protected holdout. |
| G6 — Provider, cost, and failure behavior | DeepSeek primary workflow tested with approved data and budget; Jev tested separately only after its specific institutional provider approval. Verify prompt/model versions, per-requisition hard cap, four-call assessment ceiling, rate-card/invoice reconciliation, explicit error/manual-review states, circuit-breaker behavior, and no silent mock fallback. | PENDING — synthetic benchmark does not validate provider calls or invoice cost. |
| G7 — Operations, privacy, and rollback | Measure SLOs under representative load; rehearse user onboarding, manual fallback, deletion plus backup purge, restore-and-repurge, audit review, credential rotation, incident response, and rollback. Named owners sign and date each artifact. | PENDING — runbook text alone is not a completed drill. |

No aggregate “overall score” can bypass an unmet gate. Any missing or unreviewed evidence remains `PENDING` / `NOT_EVALUABLE`, not `PASS`.

## Synthetic regression set

The active synthetic dataset is `fixtures/ai_benchmark/synthetic_100_multi_role_v2`: 100 generated CVs, with 20 each for Senior AI Engineer (Computer Vision/NLP/LLM), Software Development Manager, Java Backend Developer, Mobile/Web Tester (QA/QC), and Agentic Engineer. Each role has a separate draft JD and six role-specific criteria; references contain 600 deterministic design expectations with score/status outcomes and evidence spans. Cases include 80 development and 20 `public_test` records, Vietnamese/English/mixed text, counterfactual identity pairs, insufficient-evidence cases, conflicting evidence, keyword-only distractors, long context, and prompt-injection text. These are AI-authored synthetic expectations, not HR/IT-reviewed labels, and `public_test` is not a protected holdout.
Revision v2 preserves the 100 CVs and draft rubrics from v1 and corrects one documented cross-criterion expectation: Java case 001's post-release client-error monitoring is also evidence for delivery/reliability anchor 1. The v1 dataset remains unchanged. Evidence-agent prompt v5 distinguishes keyword-only/team-only statements from individual work, avoids extending a project-specific denial into a career-wide claim, and requires direct same-scope individual claims before using `conflicting_evidence`.


Validate the pinned inputs and exact evidence spans without calling a model:

```bash
python scripts/run_ai_benchmark.py validate
```

Model comparisons require an isolated disposable database, a cached pinned embedding model, provider configuration, and an explicit cost cap. Mock mode verifies wiring only; it cannot measure model quality. No result from this dataset establishes hiring validity or authorizes live decisions.

For a Jev-primary sandbox run, set `ASSESSMENT_SCORER_MODE=jev` for that isolated process; primary scoring is separate from `JEV_MODE` and `JEV_RERANK_MODE`, which remain off unless Jev reranking is independently under test. The isolation wrapper forwards `JEV_API_KEY` only when Jev is the primary scorer or an explicitly selected reranker. Confirm the run contains `jev_primary_score` invocations before attributing Jev token usage. The scorer requires the four validated score fields and ignores additional unconsumed answer metadata. `runs.jsonl` records only the Jev primary outcome, requested model, eligible criterion count, fractional Jev scores, and stable error code; it does not store provider responses or CV text. An evidence-agent validation failure before Jev invocation means Jev was not called. Under the default four-call ceiling, the evidence agent may use at most three model turns (two normal turns plus one JSON-mode repair), while always reserving a call for Jev scoring. If the repair consumes the third turn, the post-score DeepSeek explanation is marked failed by the existing call-budget guard; no fifth provider call is made. Otherwise, the explanation uses the remaining call slot. The evidence-only prompt requires rationale and clarification questions to stay job-related and omit personal/demographic details. Never print provider credentials.

In Jev evidence-only mode, model-written rationale/questions that mention prohibited personal attributes are replaced with generic job-related wording before strict validation. This changes no status or cited evidence; the execution trace records `sanitized_narrative_field_count`. Schema, criterion-set, retrieval-scope, and exact-span checks still fail closed.

The post-score explanation is a separate DeepSeek call with reasoning disabled and a bounded JSON output; it is distinct from Jev scoring and is charged to the DeepSeek budget. If it truncates or times out, its reservation remains held as outcome-unknown until reconciled.

The explanation request now explicitly asks the DeepSeek provider for JSON-object mode as well as validating the response schema and cited evidence; malformed or schema-invalid narratives still fail closed without exposing provider output.

The verified Jev rate card prices output tokens at USD 0/M, but Jev still reports generated output tokens. Bounded primary-scoring and reranking calls record those reported tokens and accept at most `MAX_JEV_OUTPUT_TOKENS=1024`; this is a local post-response usage bound, not a provider-side generation cap. If a response exceeds it, the invocation remains outcome-unknown and its reservation is held for reconciliation.

The offline report selects the score field pinned by `assessment_scorer_mode`: fractional `jev_score` for Jev-primary runs and integer `score` for DeepSeek. MAE compares Jev expected scores with the synthetic integer anchors; quadratic weighted kappa is omitted for Jev because it is defined over discrete categories. Use cost totals only when the report has no journal integrity errors and `journal.financial_reconciled=true`; every DeepSeek and Jev invocation must have a matching admission record.



The independent human-labeled protocol remains a separate future evaluation path; its reviewers must create and adjudicate labels independently of the system being evaluated.

For a protected private holdout, only the named evaluation custodian should grant access after thresholds and analysis plan are signed. Keep its records, CV/JD, labels, evidence spans, embeddings, provider payloads, and row-level predictions out of Git and public reports. Use the benchmark output for aggregates only and suppress low-count group results per institutional policy.

## Error-budget response

If extraction/OCR failure, latency, citation, provider, or cost error budgets exceed the approved limit, stop queueing AI assessments for the affected provider/file class, display the manual-review state, and continue recruitment with the approved human process. Do not relax evidence validation, retry ceilings, privacy controls, or budget guards to recover throughput. Resume only after the cause is fixed, regression and security tests pass, and the owner records the decision.

## Sign-off record template

Keep completed approvals and restricted evidence in the institution-approved system; do not commit signed applicant-data reports here.

| Gate | Evidence URI/hash | Owner | Decision | Date |
|---|---|---|---|---|
| G1 |  | HR + IT reviewers | PENDING |  |
| G2 |  | Data owner / privacy / legal | PENDING |  |
| G3 |  | Evaluation custodian + reviewers | PENDING |  |
| G4 |  | RAG owner + reviewers | PENDING |  |
| G5 |  | HR + IT reviewers | PENDING |  |
| G6 |  | Platform/provider owner | PENDING |  |
| G7 |  | Operations/security owner | PENDING |  |

The author of this document must not self-sign as HR, legal, security, or an institutional data owner. Each named university owner records their own decision after reviewing evidence.
