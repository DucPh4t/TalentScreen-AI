# Jev Primary Rubric Scoring Implementation Plan

> **For agentic workers:** Implement this plan task-by-task with test-first changes. The owner has directed implementation of the selected Jev-primary architecture; keep HR as the final decision-maker.

**Goal:** Add an opt-in Jev-primary scoring path that scores each eligible approved rubric criterion from cited CV evidence while DeepSeek drafts rubrics, operates the bounded retrieval agent, and explains validated results.

**Architecture:** Pin `assessment_scorer_mode` in each run snapshot. In Jev mode, LangGraph returns a validated evidence-only contract, then one bounded TypeSafe System One call batches score questions for eligible criteria. The backend validates source provenance, preserves Jev's fractional expected scores and probabilities separately from legacy DeepSeek integer scores, calculates deterministic totals, and DeepSeek may explain only validated results. Jev mode remains opt-in; failures never fall back to DeepSeek scoring.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy/Alembic, PostgreSQL JSONB/Numeric, LangGraph, TypeSafe Jev 1.13 direct, DeepSeek direct, Next.js/TypeScript, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-jev-primary-scoring-design.md`

## Global Constraints

- Use only `https://api.typesafe.ai/v1/systemone` and pinned `jev-1.13.0` for Jev; no OpenRouter route.
- Keep Jev primary opt-in with `ASSESSMENT_SCORER_MODE=deepseek` by default; require Jev key, approved provider processing, and a verified positive input rate before `jev` mode starts.
- Freeze scorer mode, provider/model, rubric, sanitized document, prompt versions, and retrieval version in the run snapshot.
- Jev gets only approved rubric anchors and source spans retrieved from that run's approved sanitized CV; do not send identity attributes or raw CV data.
- DeepSeek must not emit competency scores in Jev-primary mode; it may search the bounded evidence tools and explain validated Jev output afterward.
- Criteria without evidence, with conflicting evidence, or with low confidence remain unscored and cannot get an automatic shortlist recommendation.
- Keep existing DeepSeek integer score values and old run behavior intact; persist Jev fractional score, probabilities, confidence, and disposition in separate fields.
- Reserve and settle provider spend with the existing invocation/budget ledger; hold ambiguous paid outcomes and never automatically replay them.
- No application code may treat Jev confidence as probability of correctness or as a hiring decision.

## Review Focus

- Empty retrieval, one missing criterion, and all-missing evidence must remain `null` and avoid a Jev call; test no evidence and partial coverage.
- A fabricated/foreign citation, duplicate criterion, malformed answer, or wrong model must fail closed; test exact span subset and model identity.
- Fractional boundaries (0, 0.01, 3.59, 4) must remain unrounded through deterministic aggregation; test score and threshold boundary.
- Jev timeout, 401/402/429, usage missing/over limit, and ambiguous outcome must not trigger DeepSeek score fallback or an automatic paid retry; test ledger status and run result.
- A rubric/document/sanitized-version change during Jev egress must discard results; test the existing late-arrival snapshot check after both provider calls.

---

## File Map

- `services/backend/app/config.py`: scorer mode and Jev activation validation.
- `services/backend/app/db/models/assessment.py`: run-level mode metadata plus nullable Jev score/probability/confidence/disposition columns.
- `services/backend/alembic/versions/`: additive migration; existing `score` values remain unchanged.
- `services/backend/app/schemas/assessment.py`: evidence-only agent contract and API response fields.
- `services/backend/app/services/assessment/validator.py`: validate evidence-only outputs against rubric and exact source-span set.
- `services/backend/app/services/agent/assessment_graph.py`: mode-specific prompt, validation, and final result type; same bounded tools and no checkpoint.
- `services/backend/app/services/assessment/service.py`: snapshot scorer mode, one Jev score batch, no-evidence/abstention handling, persistence, stale snapshot check.
- `services/backend/app/services/assessment/scoring.py`: deterministic Decimal scores from legacy integer or Jev fractional values.
- `services/backend/app/services/llm/types.py` and `services/backend/app/services/llm/orchestrator.py`: typed `jev_primary` purpose, call bounds, pinned served model, usage validation, reservations and settlement.
- `services/backend/app/schemas/assessment.py`, `services/backend/app/api/` (existing assessment routes), `apps/web/src/lib/api.ts`, `apps/web/src/app/applications/[id]/page.tsx`: expose and present score source, fractional score, confidence/distribution, and abstention reason.
- `services/backend/tests/test_jev_primary_scoring.py`, existing assessment-agent/orchestrator/schema tests: regression coverage.
- `README.md`, `docs/architecture.md`, `.env.example`: distinguish current default from opt-in Jev-primary mode.

## Task 1: Pin Scorer Mode and Persist Jev Result Separately

**Interfaces:** Add `ASSESSMENT_SCORER_MODE: Literal["deepseek", "jev"] = "deepseek"`. Every new `AssessmentRun.snapshot` receives `scorer_mode`, requested Jev endpoint/model when mode is `jev`, and the existing prompt/retrieval snapshots. Add `CriterionAssessment.jev_score: Numeric(5,4)`, `jev_probabilities: JSONB`, `jev_confidence: Numeric(5,4)`, and `score_disposition: String(32)`. Add `AssessmentRun.scorer_mode` response from its snapshot. Preserve `CriterionAssessment.score` as nullable `SmallInteger` for DeepSeek historical and current DeepSeek runs.

- [x] Add config tests: default remains `deepseek`; `jev` rejects missing key, missing data approval, missing/unverified rate, non-TypeSafe endpoint, and non-pinned model; Jev and rerank/shadow modes cannot conflict.
- [x] Run those tests and observe expected failures.
- [x] Add snapshot tests: deepseek and jev runs freeze distinct modes and Jev direct model/endpoint without secret values.
- [x] Add Alembic migration with nullable Jev result columns; upgrade/downgrade against isolated PostgreSQL and assert existing integer scores survive unchanged.
- [x] Run config, snapshot, and migration tests; expected: all pass and historical score column is not rewritten.

## Task 2: Add Evidence-Only Agent Output for Jev Mode

**Interfaces:** Add `EvidenceCriterionSchema` with `criterion_id`, status `assessed|insufficient_evidence|conflicting_evidence`, exact evidence spans, rationale, and missing information, but no score fields. Add `EvidenceOnlyAssessmentSchema`; validator takes expected rubric criteria and allowed span IDs and returns a complete unique criterion set. `AgentExecutionResult.output` becomes the explicit union `AssessmentOutputSchema | EvidenceOnlyAssessmentSchema` selected by `run.snapshot["scorer_mode"]`.

- [x] Add tests that Jev-mode prompt schema rejects any `score`, `recommendation`, or unknown span ID while DeepSeek mode retains the existing assessment-output contract.
- [x] Run the new tests to observe failure.
- [x] Add a versioned evidence-only prompt. Keep current criterion-scoped read-only retrieval tools and limits; identify CV text as untrusted; require evidence sufficiency/conflict and quotes only.
- [x] Route initial and repair validation through the evidence-only validator when the run snapshot says `jev`; preserve current validator path for `deepseek`.
- [x] Add tests for tool-returned spans, missing/duplicate criteria, prompt-injection text in CV, and no score emission; expected: graph returns validated evidence-only output and never a DeepSeek score.

## Task 3: Invoke Jev Once, Validate/Abstain, and Score Deterministically

**Interfaces:** Add `CompletionRequest.purpose="jev_primary"` and a run-frozen primary policy with maximum request bytes/state bytes, accepted model `jev-1.13.0`, input rate, and per-run call ceiling 1. `admit_invocation` admits only the `jev_primary_score` namespace for the Jev provider, reserves a maximum-input cost, validates approval and snapshot policy, and blocks replay of reserved/unknown outcomes. Jev receives one typed Score question per sufficient, non-conflicting criterion, each with exactly five approved 0..4 anchors and only that criterion's delivered spans. A postprocessor returns criterion-linked fractional score, probabilities, confidence, disposition and used span IDs.

- [x] Write tests for one batched call with 2..12 questions, omitted evidence criteria, foreign answer IDs, wrong served model, invalid probability sets, request/usage bounds, and required per-call purpose.
- [x] Run tests to observe failure.
- [x] Implement the immutable Jev-primary admission, cost reservation, provider call, settlement and explicit no-retry-on-unknown behavior using existing ledger tables.
- [x] Add tests for a stale/tombstoned snapshot during Jev egress, and for Jev errors producing `provider_error`/HR review with no DeepSeek score fallback.
- [x] Add Decimal deterministic scoring that reads `jev_score` without rounding, keeps old integer path identical, and returns `comparable_score=null` for any abstention/conflict.
- [x] Persist Jev raw scores/probabilities/confidence/disposition and evidence only from the exact subset sent; keep `CriterionAssessment.score` null for Jev-primary rows.
- [x] Run Jev-primary service, ledger, snapshot and legacy scoring tests; expected: one score call per eligible run, no call for all-missing evidence, exact budget journal and unchanged DeepSeek historical semantics.

## Task 4: Explain Validated Scores and Update HR Review UI

**Interfaces:** API criterion response adds optional `jev_score`, `jev_probabilities`, `jev_confidence`, `score_disposition`, and `score_source`; run response adds `scorer_mode`. DeepSeek narrative takes only the validated score/evidence DTO, cannot mutate scores or citations, and is omitted safely on failure. HR UI shows Jev expected level with 2 decimal places, anchor probability distribution and confidence label (“độ tập trung phân phối, không phải xác suất đúng”), exact evidence, missing/conflicting state, and “AI tham khảo — HR quyết định”; DeepSeek score rows remain unchanged.

- [x] Add API schema and frontend contract/UI tests before implementation; cover Jev vs DeepSeek, `null` score states, and old response payloads.
- [x] Run the tests to observe failure.
- [x] Add a strict DeepSeek narrative contract that accepts only backend-validated criterion IDs, scores, and source span IDs; reject unsupported IDs/quotes and keep output separate from scoring data.
- [x] Render Jev distribution and fractional expected score in the existing evidence-first assessment panel; show clear abstention and provider failure states.
- [x] Update README, architecture and `.env.example` with safe opt-in instructions; keep `ASSESSMENT_SCORER_MODE=deepseek` as default and explicitly state Jev is not enabled for real CVs until institutional processor approval.
- [x] Run targeted backend suite, migration suite, frontend typecheck/build, and synthetic end-to-end scorer-mode tests; expected: both modes render correctly, Jev remains off by default, no score fallback, and no secrets in tracked files.

## Self-Review

- Spec coverage: scorer mode, evidence-only retrieval agent, one batched Jev Score request, exact citation provenance, fractional storage, deterministic Decimal aggregation, HITL display, separate provider budgets, failure abstention, rollback, and labeled holdout gate map to Tasks 1–4.
- Interface consistency: Task 1 owns run snapshot/columns; Task 2 consumes `scorer_mode` and produces evidence-only DTO; Task 3 consumes that DTO and produces persisted Jev result; Task 4 consumes the response fields from Tasks 1/3.
- High-risk inputs are listed in Review Focus and assigned tests in Tasks 1–4.
- The opt-in mode remains DeepSeek by default because user/provider approval for TypeSafe on real applicant CVs is not established by synthetic API testing.
