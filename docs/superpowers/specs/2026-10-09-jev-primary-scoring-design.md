# Jev Primary Rubric Scoring Design

**Status:** Draft for owner review  
**Date:** 2026-10-09  
**Scope:** Make Jev the primary model for per-criterion scores, while retaining DeepSeek for JD-to-rubric drafting, bounded evidence-search agent behavior, and human-readable explanations/interview questions.

## Goal and non-goals

TalentScreen should produce a rubric-grounded, evidence-linked Jev score proposal for each approved competency. HR remains the decision maker. The implementation must keep unsupported criteria unscored, expose uncertainty to HR, and make the model/version/evidence snapshot auditable.

This change does not automate hiring decisions, alter rubric ownership, enable Jev passage reranking by default, or claim Jev is more accurate than DeepSeek. No production applicant CVs are to be used in provider smoke tests; use synthetic fixtures until the school approves TypeSafe as a processor for that data.

## Model responsibilities

- DeepSeek remains the generative model for proposing rubric drafts from a JD, bounded agent turns that decide whether scoped retrieval is needed, and final explanations/interview follow-up questions.
- Hybrid RAG remains E5 dense retrieval plus PostgreSQL lexical retrieval with RRF, scoped to the current approved sanitized CV and rubric snapshot.
- Jev becomes the primary typed decision model for one-dimensional 0..4 rubric scores. It receives the approved criterion anchors and only the exact retrieved sanitized source spans allocated to that criterion.
- Backend code owns scope, citation provenance, abstention gates, score normalization/weighting, recommendation policy, and audit persistence. Jev confidence is a signal, never a correctness guarantee or hiring decision.
- Jev reranking stays `off` for this first scoring implementation. It is a separate experiment, and the current reranking evidence does not meet its activation gate.

## Assessment flow

1. HR approves the JD-derived rubric and the sanitized CV version.
2. The worker freezes the application, document, sanitized-version, rubric, retrieval configuration, and prompt versions on an assessment run.
3. Hybrid retrieval forms a criterion-specific evidence pack with canonical source-span IDs. Retrieval results are not treated as proof of competence.
4. DeepSeek's bounded agent may call only the existing read-only tools to retrieve more text from the same approved CV for listed rubric criteria. It returns an evidence-search outcome and span IDs; it must not produce competency scores or recommendations in Jev-primary mode.
5. Before scoring, the backend excludes criteria with no eligible source spans. The Jev request contains one Score question per eligible criterion, each with exactly the approved ordered anchors 0..4 and that criterion's quoted evidence. Each question explicitly references only its criterion-specific state fields. Jev Score returns a probability-weighted expected level, which can be fractional; preserve its expected value and per-anchor probability distribution. Add a separate typed evidence-state question only if its contract can reliably distinguish sufficient, mention-only/insufficient, and conflicting evidence; otherwise uncertain/conflicting evidence is sent to HR and not treated as a scored competency. Every assessment remains a proposal for HR review.
6. The backend validates every response field and model/version, maps Jev's expected score and probability distribution to an observation, associates citations only with source spans actually sent for that criterion, and applies an explicit confidence/abstention policy calibrated on labeled holdout data. Missing evidence is `null`, never zero. Do not round before weighted score/threshold calculations.
7. DeepSeek may generate a short explanation and interview questions from the validated Jev observations and exact cited spans. It cannot change scores, add evidence, or produce a hiring recommendation. The output validator rejects unknown span IDs and unsupported quotations.
8. The backend calculates coverage and weighted score using the approved rubric policy, records complete provenance and model invocations, and presents the evidence, Jev score/probabilities/confidence, LLM explanation, and HR override controls. HR's decision is separate and final.

## Output contract and persistence

Per criterion, persist: criterion ID and approved rubric version; Jev requested and served model/version; ordered anchor version/hash; raw 0..4 expected score; probability by anchor; reported confidence; disposition (`scored`, `insufficient_evidence`, `conflicting_evidence`, `low_confidence`, or `provider_error`); exact source-span IDs/hash; retrieval strategy/index version; LLM explanation/question artifact version; and HR override value/reason/actor/time. Never use model confidence as a numeric multiplier on the rubric score.

Do not overwrite the existing DeepSeek assessment fields or silently reinterpret their historical integer score meaning. Introduce an explicit scorer-mode snapshot and persist Jev expected score (decimal), per-anchor probabilities, confidence, disposition, citations, and exact model/version separately. Update response schemas and UI to distinguish Jev's fractional expected level from any discrete HR score/override. A run pins the scorer mode at creation; later environment changes do not mutate in-flight/history results. Preserve a rollback to DeepSeek-primary for new runs.

## Provider configuration and cost controls

The supplied `apikey_…` credential is for the direct TypeSafe API; configure `JEV_BASE_URL=https://api.typesafe.ai/v1/systemone`, pin the direct model ID `JEV_MODEL=jev-1.13.0`, and store the key only in the ignored local `.env`/secret manager. Do not put it in docs, test fixtures, traces, console output, or Git. Keep a per-run admission limit and budget reservation for Jev and DeepSeek separately; fail closed on unknown provider outcomes and never auto-replay an ambiguous paid call. Verify the direct provider's current rate card before setting a production budget. The existing `.env` rate value and accepted-model allowlist were for the prior OpenRouter rerank route and must not be assumed to govern direct TypeSafe scoring. Expand the invocation ledger to admit and reserve Jev-primary score calls as a distinct purpose with pinned provider, endpoint, model, rate card, per-run ceiling, and idempotency key; maintain independent Jev and DeepSeek reservations and reconciliation for unknown outcomes.

## Error handling and fallback

- Jev unavailable, malformed, truncated, or budget-rejected: mark Jev score as unavailable and route the profile to HR review. No silent DeepSeek score fallback in a Jev-primary run.
- DeepSeek evidence agent unavailable: score only the initial validated retrieval pack if policy permits; otherwise return insufficient evidence for HR.
- No spans: do not call Jev; persist `insufficient_evidence` with null score.
- Low confidence, uncertain evidence state, conflicting passages, stale/tombstoned application, revoked sanitized version, or rubric drift: do not create a comparable score or shortlist rank; preserve trace and request HR review.
- Re-run requires an explicit new run and a fresh bounded budget admission; never replay a provider call with unknown outcome.

## Evaluation and activation gates

Before any assisted real-applicant use, compare Jev-primary with DeepSeek-primary on the same frozen synthetic benchmark and an independently HR/IT-labeled, permissioned holdout. Include Vietnamese, English, mixed-language CVs; positive, sparse, contradictory, and limiting evidence; all rubric anchors; and perturbations for forbidden identity fields. Measure per-criterion exact/adjacent agreement, weighted kappa, MAE, abstention/coverage, unsupported-citation rate, negative/conflict evidence retention, HR override rate, calibration/Brier score, latency, and total cost including both providers and retries. Report confidence intervals and slice results. Promotion requires predeclared thresholds and zero identity-feature influence; lack of labels means stay in shadow/synthetic mode.

## Rollback

Set the pinned assessment scorer mode back to DeepSeek-primary for newly created runs; retain Jev artifacts for completed runs. Keep Jev reranking off. Do not rewrite completed records. Rollback must not clear budget reservations, alter historical snapshots, or change approved rubric versions.

## Known questions to settle in implementation plan

- Whether TypeSafe's direct endpoint supports all current request/response fields and multiple Score questions under current project limits; verify with a minimal synthetic contract probe before model integration.
- Exact abstention/conflict thresholds must come from local labeled holdout results, not vendor confidence guidance. Initially show the full distribution and require HR review for every result; do not use confidence as a probability of correctness or to auto-advance candidates.
- The existing `CriterionAssessment.score` is an integer SmallInteger. Migration/API/UI design must preserve historical values while storing Jev's fractional expected score and distribution without lossy rounding.
- Final UI should distinguish the model's expected score from a discrete HR-approved score and explain that confidence describes distribution sharpness, not probability of correctness.
