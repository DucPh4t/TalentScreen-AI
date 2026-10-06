# RAG and bounded-agent readiness gates

**Status: NOT READY for AI-assisted live hiring decisions.** This is a release checklist, not an approval record. A code path, synthetic test, or successful provider smoke call is not evidence that candidate scoring is suitable for a live hiring round.

## Required gates

| Gate | Evidence required before the gate can pass | Status |
|---|---|---|
| G1 — Vacancy and rubric | HR and an IT reviewer approve the real JD, role-specific dynamic rubric, job-related anchors, weights, and permitted missing-evidence behavior. Record immutable versions. | PENDING — no live vacancy package in this benchmark. |
| G2 — Data handling | Institution's data owner confirms lawful/institutional processing, applicant notice/consent as required, provider/subprocessor scope, cross-border terms if applicable, retention, deletion, and backup-purge process. Record approvals outside public Git. | PENDING — repository controls do not establish institutional approval. |
| G3 — Dataset and labels | Per-family development and protected holdout cohorts, with HR and IT blind independent criterion labels, evidence spans, adjudication, inclusion/exclusion log, and human-human baseline. No raw applicant data in Git. | PENDING — seven mixed-role local CVs are smoke data only. |
| G4 — Retrieval and grounding | Per-family Recall@5/10, citation span validity, unsupported-claim audit, duplicate/coverage analysis, multilingual checks, and prompt-injection/security tests meet reviewer-approved thresholds on development and then untouched holdout. | PENDING — only synthetic fixture included. |
| G5 — Scoring, fairness, and HITL | Criterion MAE/agreement/coverage compared with human-human baseline; inspect every high-impact disagreement and HR override. Counterfactual name/pronoun/school/hometown invariance is 100% or any failure is explained and fixed. HR UI keeps evidence, uncertainty, provider disagreement, override reason, and final human decision visible. | PENDING — no qualified independent labels or protected holdout. |
| G6 — Provider, cost, and failure behavior | DeepSeek primary workflow tested with approved data and budget; Jev tested separately only after its specific institutional provider approval. Verify prompt/model versions, per-requisition hard cap, four-call assessment ceiling, rate-card/invoice reconciliation, explicit error/manual-review states, circuit-breaker behavior, and no silent mock fallback. | PENDING — synthetic benchmark does not validate provider calls or invoice cost. |
| G7 — Operations, privacy, and rollback | Measure SLOs under representative load; rehearse user onboarding, manual fallback, deletion plus backup purge, restore-and-repurge, audit review, credential rotation, incident response, and rollback. Named owners sign and date each artifact. | PENDING — runbook text alone is not a completed drill. |

No aggregate “overall score” can bypass an unmet gate. Any missing or unreviewed evidence remains `PENDING` / `NOT_EVALUABLE`, not `PASS`.

## Local synthetic check

Run this only to verify the benchmark code and schema:

```bash
python scripts/run_rag_benchmark.py \
  --dataset fixtures/rag_benchmark/synthetic.jsonl \
  --output /tmp/talentscreen-rag-benchmark.json
```

The report should say `data_scope: synthetic_only`, `readiness: NOT_AUTHORIZED_FOR_LIVE_DECISIONS`, and may recommend manual fallback when synthetic provisional checks fail or lack data. Its visible `locked_holdout` entries are deliberately synthetic and public; the holdout flag is not access control. Never present their metric values as evidence for a role or a provider.

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
