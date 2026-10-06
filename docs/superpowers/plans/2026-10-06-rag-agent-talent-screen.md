# TalentScreen AI RAG and Bounded Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add validated multilingual hybrid RAG and one bounded read-only agent to the existing HR assessment workflow, then prove its behavior on role-specific evaluation data before enabling recommendations for a real hiring round.

**Architecture:** Keep the current FastAPI worker and Next.js application. Replace mock vectors in the opt-in hybrid path with local multilingual E5; feed ranked source spans into the existing evidence validator; run a single LangGraph assessment workflow with at most two authorized retrieval tool executions; keep deterministic scoring, Jev shadow, HR review, and final decisions separate.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, PostgreSQL/pgvector, Pydantic v2, LangGraph, sentence-transformers (`intfloat/multilingual-e5-base`), DeepSeek Chat, existing Jev 1.13 adapter, Next.js 15, React 19, TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-06-rag-agent-talent-screen-design.md`

## Global Constraints

- Keep `LLM_PROVIDER=mock`, `RAG_MODE=full_text_baseline`, and `JEV_MODE=off` as safe defaults; enable hybrid RAG explicitly until its per-role holdout gate passes.
- Use local `intfloat/multilingual-e5-base`, the exact `query:` and `passage:` prefixes, 250–350 token target chunks, and a 480-token hard maximum.
- Retrieve at most 10 lexical and 10 dense results per criterion, fuse with RRF, and include at most four deduplicated evidence chunks per criterion in initial assessment context.
- Use approved sanitized CV versions only; all provider inputs and citations must resolve to immutable `SourceSpan` records.
- Scores use the approved 0–4 rubric anchors; missing or conflicting evidence is `null`, never an inferred zero.
- DeepSeek is primary. Jev is optional shadow only, off by default, separately reported, and never averaged into the primary score.
- The graph may execute at most two read-only evidence tool calls and at most three normal DeepSeek round trips; each `query_hint` is at most 256 characters, has control characters removed, and is rejected if it contains contact data or URLs. The whole assessment, including Jev, has at most four outbound attempts; permit only one extra transient retry or schema/citation repair, and skip Jev if the shared cap is exhausted.
- The model cannot choose candidate/requisition IDs, access another application, write data, change candidate state, contact applicants, browse the web, or make a hiring decision.
- Every accepted citation must resolve to the exact stored source span; any invalid citation or unauthorized tool call blocks the result.
- Keep actual applicant CVs, API keys, prompts containing applicant data, and raw model outputs out of Git fixtures, reports, and ordinary logs. Record the resolved E5 model revision in every evaluation manifest; locked holdout runs may not use a floating `main` revision.
- Keep the existing HR sanitization approval and final human decision gates. Do not restore the general Copilot chat.
- Target runtime is one developer and roughly one to two months; deployment remains a later stage.

## Review Focus

- Mixed Vietnamese/English text, section boundaries, and one span longer than the chunk maximum must remain retrievable with exact provenance; test in `test_chunking_preserves_sections_and_span_ids_for_mixed_language_cv` (Task 1).
- Empty or weak retrieval and conflicting evidence must remain unscored and must not be fabricated by the agent; test in `test_hybrid_assessment_uses_null_when_retrieval_has_no_reliable_evidence` (Tasks 2–3).
- Tool arguments naming an unknown criterion or attempting cross-application access must be rejected before querying data; test in `test_agent_tool_rejects_unknown_or_out_of_scope_criterion` (Task 5).
- Prompt injection, malformed tool JSON, invalid citations, provider timeout, and exhausted call budget must fail closed without a silent mock result; tests in `test_deepseek_tool_call_contract`, `test_agent_ignores_cv_instructions_and_blocks_unlisted_tools`, and `test_assessment_call_budget_includes_jev_and_repair` (Tasks 4–6).
- A deletion or version change while a job is running must block follow-up egress, discard late output, and purge traces; cover with `test_agent_stops_before_second_model_call_if_snapshot_changes`, `test_late_agent_result_is_discarded_after_application_tombstone`, and `test_purge_worker_execution_and_clean_verification_report` (Task 5).

---

## Repository File Map

- `services/backend/app/services/embedding.py` owns the cached local E5 runtime, token-aware section chunking, and indexing of approved sanitized spans.
- `services/backend/app/services/retrieval.py` owns criterion query construction, dense/lexical search, RRF, deduplication, and fallback signaling.
- `services/backend/app/services/assessment/` owns the rubric-bound prompt, exact-span validator, deterministic scoring, assessment job integration, and prompt-version registry.
- `services/backend/app/services/llm/types.py` and `provider.py` define and implement completion messages/tool calls; `orchestrator.py` enforces sanitization preconditions, call limits, and budget reservations.
- New `services/backend/app/services/agent/` owns the LangGraph state, validated read-only tools, and execution trace; it receives scope from the already validated `AssessmentRun`, never from model arguments.
- `services/backend/app/db/models/assessment.py` and `ops.py`, `services/backend/alembic/versions/`, and response schemas persist minimized trace/budget metadata.
- `services/backend/tests/` contains unit, provider-contract, security, migration, and worker integration tests; `scripts/run_rag_benchmark.py` evaluates only labeled benchmark manifests and writes aggregate reports under ignored `private_storage/eval/`.
- `apps/web/src/lib/api.ts`, `apps/web/src/components/AssessmentExecutionTrace.tsx`, and `apps/web/src/app/applications/[id]/page.tsx` connect agent actions and evidence traces to the current candidate workflow. Reuse the existing comparison matrix and sandbox.

The feature is one end-to-end assessment subsystem: each task has a separately testable result, but splitting RAG, agent, and evidence UI into independent product plans would leave each without a useful workflow. Implementation order follows their interfaces.

### Task 1: Real E5 embeddings and token-aware chunking

**Files:**
- Modify: `services/backend/pyproject.toml`
- Modify: `services/backend/requirements.lock`
- Modify: `services/backend/app/config.py`
- Modify: `services/backend/app/services/embedding.py`
- Test: `services/backend/tests/test_hybrid_retrieval.py`

**Interfaces:**
- Preserve `embed_texts(texts: list[str], prefix: str = "passage: ") -> list[list[float]]`.
- Replace the deterministic implementation in the runtime path with a lazily loaded, process-cached `SentenceTransformer(settings.EMBEDDING_MODEL, revision=settings.EMBEDDING_MODEL_REVISION, device=resolved_device)` and normalized 768-dimensional vectors.
- Add `build_chunks_from_spans(spans: list[SourceSpan], token_count: Callable[[str], int], target_tokens: int = 300, max_tokens: int = 480) -> list[dict[str, Any]]`; return `text`, `span_ids`, and `section_label`, without crossing sections.
- Keep deterministic vectors as an explicitly injected test double only. If the configured model cannot load while `RAG_MODE=hybrid`, raise a typed failure; do not silently fall back to hash vectors.

- [x] **Step 1: Write the failing tests** `test_embed_texts_uses_e5_prefix_and_returns_normalized_768d_vectors`, `test_embedding_model_is_loaded_once_per_process`, and `test_chunking_preserves_sections_and_span_ids_for_mixed_language_cv`. Include a long span above 480 tokens and assert it is split with exact source span coverage.
- [x] **Step 2: Run the focused tests**

Run: `make test-backend`
Expected: the isolated backend suite reports the new embedding/chunking tests failing because runtime vectors are currently deterministic hash vectors and chunking is character-based; the fixture uses a disposable pgvector database.

- [x] **Step 3: Implement cached E5 loading and token-aware chunking** in `embedding.py`; choose MPS on supported macOS, otherwise CPU unless `EMBEDDING_DEVICE` explicitly selects a supported device. Pin the model revision through existing config and include model/revision in `EMBEDDING_CONFIG_ID`.
- [x] **Step 4: Add `sentence-transformers` to project dependencies and regenerate `services/backend/requirements.lock` with `uv pip compile services/backend/pyproject.toml --all-extras --output-file services/backend/requirements.lock`; rerun the isolated backend suite with the deterministic test double.**

Run: `make test-backend`
Expected: PASS without downloading model weights during ordinary tests.

- [x] **Step 5: Run one opt-in local E5 smoke check** on Vietnamese, English, and mixed-language strings; assert dimensions, finite values, normalization, and that the real model path—not the test double—was used. Record only aggregate output.
- [x] **Step 6: Commit** the task as `feat: use multilingual e5 for cv retrieval`.

### Task 2: Rubric-aware hybrid retrieval and evidence pack

**Files:**
- Modify: `services/backend/app/services/retrieval.py`
- Test: `services/backend/tests/test_hybrid_retrieval.py`
- Reuse: `RubricCriterion.bilingual_terms` in `services/backend/app/db/models/requisition.py` and `CriterionDTO.bilingual_terms` in `services/backend/app/schemas/rubric.py`.

**Interfaces:**
- Preserve `hybrid_retrieve_for_criterion(db, sanitized_version_id, criterion_name, criterion_description, top_k=4, ...) -> list[RetrievedChunkScore]`; add optional `bilingual_terms: dict[str, Any] | None` and `anchor_terms: list[str] | None` keyword arguments.
- Preserve `build_hybrid_assessment_pack(db, sanitized_version_id, criteria, max_evidence_chars=24000) -> dict[str, Any]`; each criterion mapping may contain `id`, `name`, `description`, `anchors`, and `bilingual_terms`.
- The pack returns `strategy`, `criteria_retrieval_map`, `chunks`, `fallback_needed`, and an ordered list of source span IDs. Do not return applicant identity fields.

- [x] **Step 1: Write failing retrieval tests** `test_hybrid_retrieval_uses_approved_bilingual_terms_and_anchor_terms`, `test_rrf_is_deterministic_and_deduplicates_chunks`, `test_hybrid_assessment_uses_null_when_retrieval_has_no_reliable_evidence`, and `test_retrieval_is_scoped_to_sanitized_version`.
- [x] **Step 2: Run the focused tests**

Run: `make test-backend`
Expected: the isolated backend suite reports bilingual/anchor query expansion and empty-evidence tests failing; existing basic RRF tests continue to pass.

- [x] **Step 3: Implement normalized bilingual query assembly** from criterion label/description, approved anchor phrases, and stored `bilingual_terms`; cap terms to eight lexical tokens and enforce the spec's top-10 lexical/top-10 dense retrieval and top-four deduplicated evidence chunks per criterion.
- [x] **Step 4: Verify RRF rank fusion and scope tests** with `RRF k=60`, deterministic tie-break by `chunk_index`, and strict `sanitized_version_id` plus `embedding_config_id` filters.

Run: `make test-backend`
Expected: PASS, including empty-corpus fallback and version isolation.

- [x] **Step 5: Commit** as `feat: add rubric-aware hybrid evidence retrieval`.

### Task 3: Connect RAG to the assessment snapshot and prompts

**Files:**
- Modify: `services/backend/app/services/assessment/service.py`
- Modify: `services/backend/app/services/assessment/prompt.py`
- Modify: `services/backend/app/services/assessment/validator.py`
- Modify: `services/backend/app/schemas/assessment.py`
- Modify: `services/backend/tests/test_assessment.py`
- Modify: `services/backend/tests/test_assessment_prompt.py`

**Interfaces:**
- `AssessmentRun.snapshot` must freeze `assessment_prompt_version`, `agent_prompt_version`, `retrieval_strategy`, and any requested focus criterion IDs.
- Extend `AssessmentRunCreateRequest` with `focus_criterion_ids: list[str] | None = None`. Reject IDs outside the approved rubric before queuing; still produce a complete result for every rubric criterion.
- Use the existing `RAG_MODE` setting (`full_text_baseline | hybrid`) when creating a run; keep the default on the current full-text baseline.
- The prompt builder receives only the selected registered source spans. The validator remains `validate_assessment_output(raw_content, span_registry, expected_criterion_ids)` and must reject evidence not in the retrieved/approved span registry.

- [x] **Step 1: Write failing worker tests** `test_hybrid_assessment_sends_only_retrieved_source_spans`, `test_run_snapshot_freezes_prompt_and_retrieval_versions`, `test_focus_criterion_ids_must_belong_to_approved_rubric`, and `test_missing_retrieval_evidence_remains_null_not_zero`.
- [x] **Step 2: Run those tests**

Run: `make test-backend`
Expected: the isolated backend suite reports the new hybrid/snapshot/focus tests failing because the worker currently sends all sanitized spans and always records `strategy="fulltext"`.

- [x] **Step 3: Add prompt-version selection** in `assessment/prompt.py`: keep the current prompt as a named immutable version, add the retrieval-aware prompt as a new version, expose `get_assessment_prompt(version: str)`, and fail on unknown versions. Record the selected version and strategy in the run snapshot and audit metadata.
- [x] **Step 4: Integrate the hybrid pack in `execute_assessment_job`** only when the frozen strategy is `hybrid`; ensure the approved sanitized version is indexed idempotently with `index_sanitized_version` before retrieval, convert returned span IDs back to canonical `SourceSpan` rows, pass only those to the prompt and validator, and retain the current full-text baseline path when explicitly configured.
- [x] **Step 5: Run the focused tests and existing assessment regression suite**

Run: `make test-backend`
Expected: PASS; output schema still contains the complete approved rubric ID set and missing evidence remains `null`.

- [x] **Step 6: Commit** as `feat: ground assessment prompts in retrieved spans`.

### Task 4: DeepSeek tool-call protocol and mock contract

**Files:**
- Modify: `services/backend/app/services/llm/types.py`
- Modify: `services/backend/app/services/llm/provider.py`
- Modify: `services/backend/app/services/llm/orchestrator.py`
- Modify: `services/backend/tests/test_llm_adapter.py`

**Interfaces:**
- Add `ToolCall(id: str, name: str, arguments: dict[str, Any])` to `llm/types.py`.
- Extend `CompletionRequest` with optional `messages`, `tools`, and `tool_choice` fields while preserving the current system/user prompt interface for non-agent calls.
- Extend `CompletionResult` with `tool_calls: list[ToolCall]`; allow empty `content` only when valid tool calls are present.
- Preserve secret masking, provider error mapping, usage accounting, and no-silent-fallback behavior.

- [x] **Step 1: Write failing provider contract tests** `test_deepseek_tool_call_contract`, `test_deepseek_tool_call_malformed_arguments_are_rejected`, and `test_deepseek_empty_content_is_allowed_only_with_tool_calls` using `httpx.MockTransport`.
- [x] **Step 2: Run the focused tests**

Run: `make test-backend`
Expected: the isolated backend suite reports tool-call contract tests failing because the current adapter only accepts non-empty `message.content` and does not expose tool calls.

- [x] **Step 3: Implement typed tool-call parsing and message serialization** in `CompletionRequest`, `CompletionResult`, and `DeepSeekHTTPXProvider.complete`; reject malformed call IDs/names/JSON, keep raw request/response text out of logs, and calculate request hashes/token estimates from serialized messages and tool schemas in `execute_bounded_llm_call`.
- [x] **Step 4: Run provider and orchestration regressions**

Run: `make test-backend`
Expected: PASS for normal JSON completions, refusal/timeout/error mapping, and valid/invalid tool responses.

- [x] **Step 5: Commit** as `feat: support validated deepseek tool calls`.

### Task 5: Bounded LangGraph assessment agent and trace persistence

**Files:**
- Create: `services/backend/app/services/agent/__init__.py`
- Create: `services/backend/app/services/agent/schemas.py`
- Create: `services/backend/app/services/agent/tools.py`
- Create: `services/backend/app/services/agent/assessment_graph.py`
- Modify: `services/backend/pyproject.toml`
- Modify: `services/backend/requirements.lock`
- Modify: `services/backend/app/db/models/assessment.py`
- Modify: `services/backend/app/schemas/assessment.py`
- Modify: `services/backend/app/services/assessment/service.py`
- Create: `services/backend/alembic/versions/6f2c91a4d8e0_agent_execution_trace.py` (`down_revision = "a6b9031d8f42"`)
- Test: `services/backend/tests/test_assessment_agent.py`
- Test: `services/backend/tests/test_sec_regression.py`
- Modify: `services/backend/tests/test_deletion.py`

**Interfaces:**
- Add `AgentExecutionResult(output: AssessmentOutputSchema, trace: dict[str, Any], source_spans: dict[str, SourceSpan])` in `agent/schemas.py`.
- Add `async run_assessment_agent(*, db: AsyncSession, run: AssessmentRun, rubric_criteria: list[RubricCriterion], initial_pack: dict[str, Any], provider_override: BaseLLMProvider | None = None, focus_criterion_ids: list[str] | None = None) -> AgentExecutionResult` in `agent/assessment_graph.py`.
- Add `async retrieve_more_evidence(*, db: AsyncSession, run: AssessmentRun, rubric_criteria: list[RubricCriterion], criterion_ids: list[str], query_hint: str) -> list[RetrievedChunkScore]` and `async get_source_spans(*, db: AsyncSession, run: AssessmentRun, span_ids: list[str]) -> list[SourceSpan]` in `agent/tools.py`. The application, requisition, sanitized version, and rubric scope come only from `run`; the model may supply only criterion IDs, span IDs, and a bounded query hint.
- Persist only prompt/schema/retrieval versions, provider/model names, minimized tool names, criterion IDs, returned span IDs, counts, and outcomes in `AssessmentRun.execution_trace`; never persist raw CV text, query hints, prompts, or model arguments containing applicant text.
- Do not configure a LangGraph checkpointer in this iteration. The existing PostgreSQL job queue is durable; graph state is transient and must not outlive the job.

- [x] **Step 1: Write failing graph/tool tests** for missing and partially covered criteria, 2-tool/3-round bounds, unknown criterion and span scope, CV prompt injection, exact citation validation, initial evidence sets larger than the tool batch cap, stale snapshots, and deletion purge in `services/backend/tests/test_assessment_agent.py` and `services/backend/tests/test_deletion.py`.
- [x] **Step 2: Run the focused tests**

Run: `make test-backend`
Expected: the isolated backend suite reports graph/tool tests failing because the agent module and tool-call path do not exist.

- [x] **Step 3: Add the execution-trace migration and response field**; add `execution_trace JSONB NOT NULL DEFAULT '{}'` to `assessment_runs`, update the SQLAlchemy model and Pydantic response, and verify upgrade/downgrade/upgrade on isolated PostgreSQL.
- [x] **Step 4: Add LangGraph to `services/backend/pyproject.toml` and regenerate `services/backend/requirements.lock`**, constraining existing package versions to the committed lock while adding LangGraph dependencies.
- [x] **Step 5: Implement the StateGraph** with deterministic live-snapshot authorization, initial RAG pack, evidence coverage, structured assessment, zero-to-two tool executions, exact-span validation, deterministic scoring, and minimized trace. Count each model round trip through `execute_bounded_llm_call` with unique logical steps.
- [x] **Step 6: Integrate the graph into `execute_assessment_job`** and test with the mock provider; Jev remains a separate shadow call after validated primary output and never participates in the graph or score.
- [x] **Step 7: Run agent, assessment, security, deletion, and migration regressions**

Run: `make test-backend`
Expected: PASS; the agent cannot access or mutate data outside the run snapshot and the result is discarded when its source snapshot becomes stale or is deleted.

- [x] **Step 8: Commit** as `feat: add bounded evidence retrieval agent`.

### Task 6: Shared provider budget and per-requisition ceiling

**Files:**
- Modify: `services/backend/app/config.py`
- Modify: `services/backend/app/db/models/ops.py`
- Modify: `services/backend/app/services/llm/ledger.py`
- Modify: `services/backend/app/services/llm/orchestrator.py`
- Modify: `.env.example`
- Create: `services/backend/alembic/versions/43de8b507ac2_requisition_llm_budget.py` (`down_revision = "6f2c91a4d8e0"`)
- Test: `services/backend/tests/test_config.py`
- Test: `services/backend/tests/test_llm_adapter.py`
- Test: `services/backend/tests/test_jev_provider.py`

**Interfaces:**
- Add `REQUISITION_LLM_BUDGET_USD: Decimal | None = None`; in sandbox, inherit `DEV_EVAL_BUDGET_USD` (default `10.00`), and reject non-sandbox startup unless an explicit positive requisition cap is configured.
- Extend `BudgetReservation` with nullable `requisition_id` and index `(requisition_id, status)`.
- Extend `reserve_budget(db, job_id, amount_usd, scope=BudgetScope.PILOT, requisition_id: uuid.UUID | None = None) -> BudgetReservation`; enforce both the existing period cap and the configured requisition cap under PostgreSQL advisory transaction locks. Use the configured `ASSESSMENT_MAX_EXTERNAL_CALLS` (default 4, hard maximum 4) instead of a duplicated constant.
- In `execute_bounded_llm_call`, resolve the requisition from the `AssessmentRun` associated with `job_id` and pass it into the reservation. Count primary calls, tool-call round trips, repair/retry, and Jev against the same four-outbound-attempt cap.

- [x] **Step 1: Write failing ledger tests** `test_requisition_budget_reservation_refuses_over_limit`, `test_same_requisition_reservations_are_serialized`, `test_non_sandbox_requires_explicit_requisition_budget`, and `test_assessment_call_budget_includes_jev_and_repair`.
- [x] **Step 2: Run the focused tests**

Run: `make test-backend`
Expected: the isolated backend suite reports the new per-requisition budget tests failing because current reservations have only global development/pilot periods and no requisition attribution.

- [x] **Step 3: Add the reservation migration and typed setting**; existing reservations retain nullable `requisition_id` and remain covered by their global period cap.
- [x] **Step 4: Enforce the requisition reservation cap atomically** while preserving unknown-outcome holds and existing global cap settlement semantics. Skip Jev before egress if the shared call or budget cap is exhausted; never downgrade to mock.
- [x] **Step 5: Run budget, provider, Jev, and migration regression tests**

Run: `make test-backend`
Expected: PASS; concurrent reservations cannot exceed either ceiling and DeepSeek's accepted result remains intact if Jev is skipped/fails.

- [x] **Step 6: Commit** as `feat: cap model spend per requisition`.

### Task 7: Role-specific benchmark, agreement metrics, and readiness report

**Files:**
- Create: `services/backend/app/services/evaluation/__init__.py`
- Create: `services/backend/app/services/evaluation/metrics.py`
- Create: `services/backend/tests/test_evaluation_metrics.py`
- Create: `scripts/run_rag_benchmark.py`
- Create: `docs/evaluation/rag-agent-benchmark-protocol.md`
- Create: `docs/runbooks/rag-agent-readiness.md`
- Create: `fixtures/rag_benchmark/synthetic.jsonl`

**Interfaces:**
- Add pure functions `recall_at_k(expected_span_ids: set[str], retrieved_span_ids: list[str], k: int) -> float`, `criterion_mae(reference: list[int | None], predicted: list[int | None]) -> float | None` (ignore pairs missing on both sides; raise on one-sided missing labels), and `quadratic_weighted_kappa(reference: list[int], predicted: list[int], scale: int = 5) -> float | None`.
- Add CLI `python scripts/run_rag_benchmark.py --dataset PATH --output PATH`; report per-role retrieval, grounding, scoring, disagreement, latency, and estimated cost aggregates. Never put CV text, PII, prompt contents, or raw model responses into output.
- Benchmark manifest distinguishes development and locked holdout datasets by immutable IDs/hash. Only synthetic fixtures are committed; real CV/JD labels remain in approved private storage and reports are aggregate-only.

- [ ] **Step 1: Write failing metric tests** `test_recall_at_k_uses_span_intersection`, `test_criterion_mae_ignores_jointly_missing_and_rejects_one_sided_missing`, `test_quadratic_weighted_kappa_matches_known_ordinal_example`, and `test_counterfactual_assessment_is_invariant_to_name_pronoun_and_school_changes`.
- [ ] **Step 2: Run metric tests**

Run: `make test-backend`
Expected: the isolated backend suite reports metric and counterfactual tests failing because the evaluation module is not present.

- [ ] **Step 3: Implement metrics and synthetic benchmark schema** with validation for role IDs, criterion IDs, source span IDs, reviewer labels, and split. Reject any row that includes raw candidate identity fields.
- [ ] **Step 4: Implement the CLI and report template**; compute Recall@5/10, exact citation support, unsupported claim rate, criterion MAE, quadratic weighted kappa, human-human baseline, rank correlation diagnostic, counterfactual invariance, agent tool counts, P50/P95, extraction/OCR failures, and cost by role/provider. Report pass/fail against provisional SLOs from the spec and recommend manual fallback when an error budget is exceeded.
- [ ] **Step 5: Add an evaluation protocol** requiring HR/IT independent labels, adjudication, a locked holdout, thresholds selected from development and human-human baseline before holdout evaluation, and DeepSeek/Jev separation. Identify the roles represented by the locally authorized eight CVs, then source a current public JD per intended role; record source URL, retrieval date, role mapping, and derived job-related requirements, not full copyrighted posting text. State explicitly that eight mixed-role CVs are integration smoke data only, not sufficient role-specific validation, and must remain local/private.
- [ ] **Step 6: Test CLI privacy and deterministic report output**

Run: `make test-backend`
Expected: PASS; report contains aggregate metrics and no fixture CV text.

- [ ] **Step 7: Commit** as `feat: add role-specific rag evaluation harness`.

### Task 8: Evidence-first HR UI, readiness controls, and regression handoff

**Files:**
- Create: `apps/web/src/components/AssessmentExecutionTrace.tsx`
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/app/applications/[id]/page.tsx`
- Modify: `apps/web/src/app/globals.css`
- Modify: `apps/web/src/app/sandbox/page.tsx`
- Modify: `README.md`
- Modify: `docs/runbooks/rag-agent-readiness.md`

**Interfaces:**
- Extend `AssessmentRunData` with typed `strategy` and minimized `execution_trace` fields returned by the backend.
- Extend `api.triggerAssessment(applicationId, sanitizedVersionId, rubricVersionId, focusCriterionIds?: string[])` to pass `focus_criterion_ids`; backend still assesses the complete approved rubric.
- `AssessmentExecutionTrace` renders strategy, prompt/model versions, retrieval outcome, and tool count/criterion/span references; it never renders raw tool queries, full prompts, or raw CV text.
- “Tìm thêm bằng chứng” appears only for insufficient/conflicting criteria and creates a new complete assessment run focused on those criteria. Reuse the current evidence/candidate workspace, matrix, and interview actions; no general chat.

- [ ] **Step 1: Run the frontend build before UI changes**

Run: `cd apps/web && npm run build`
Expected: PASS on the approved baseline.

- [ ] **Step 2: Add `AssessmentExecutionTrace` and contextual retry action** in the current candidate assessment page; disable duplicate actions while a run is queued/running and show explicit provider failure/manual-review states.
- [ ] **Step 3: Add a short synthetic-only walkthrough in the sandbox** that explains evidence observation vs. ability, score vs. HR decision, and missing evidence vs. low score. Keep candidate identity fields hidden in queue/comparison views by default.
- [ ] **Step 4: Update README and readiness runbook** to describe real E5/hybrid RAG and bounded agent honestly, keep “not approved for live decisions” until gates pass, and document model weights, local setup, privacy controls, limits, and manual fallback.
- [ ] **Step 5: Run the full regression suite and local workflow smoke**

Run: `make test`
Expected: backend isolated tests and Next.js production build pass. Then run local Postgres/backend/worker/frontend with `RAG_MODE=hybrid`, mock provider, and synthetic CVs; verify intake → sanitization approval → retrieval/agent trace → evidence review → HR decision, plus mobile-width candidate page. Live provider calls are separate from `make test`: DeepSeek may use the already authorized, consented data; Jev remains off unless `JEV_DATA_PROCESSING_APPROVED=true` and its rate card is verified.

- [ ] **Step 6: Review the readiness report against every hard gate** in the spec. Do not enable AI-assisted recommendations for an actual hiring round if any data-quality, citation, scope, fairness, provider, deletion, or reviewer-agreement gate is unmet.
- [ ] **Step 7: Commit** as `feat: surface evidence agent in hr review workflow`.

## Final Verification

- [ ] Run `make test-backend`; it starts a throwaway PostgreSQL/pgvector container, applies `.venv/bin/alembic upgrade head` using the root `alembic.ini`, and runs the backend suite without touching the application database.
- [ ] Run `make test` after the final code change.
- [ ] Run the RAG benchmark separately on synthetic fixtures, then on authorized role-specific development data; keep locked holdout untouched until thresholds are written and reviewers approve.
- [ ] Run authorized DeepSeek primary and optional Jev shadow evaluation only after local mock/security tests pass; capture aggregate latency/cost and redact provider errors.
- [ ] Complete deletion/backup-purge and manual-fallback drills; verify all required go-live sign-offs in `docs/runbooks/rag-agent-readiness.md`.
- [ ] Confirm `git status --short` contains no CVs, API keys, benchmark reports with applicant data, model cache, or private storage artifacts.

## Execution Order and Review Gates

Tasks 1–3 establish genuine retrieval and keep the existing assessment contract. Tasks 4–6 add the bounded tool protocol, graph, trace, and cost controls. Task 7 proves quality on held-out role data. Task 8 exposes only reviewable behavior to HR and blocks real use until the documented readiness gates pass. Each task ends with its own commit and targeted tests; the full regression suite runs after integration.
