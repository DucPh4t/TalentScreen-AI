# Jev Evidence Reranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a measured, optional Jev passage-reranking stage before DeepSeek, including scoped agent retrieval, durable provenance, cost control and conservative sandbox gating.

**Architecture:** Keep retrieval/indexing and the five-node graph intact. A focused reranking module scores bounded criterion–passage pairs through the existing invocation ledger, returns deterministic selections and stores private run metadata. Versioned policies preserve historical behavior; the benchmark treats Jev and the primary model as separate experimental dimensions.

**Tech Stack:** Python 3.12, FastAPI/Pydantic v2, async SQLAlchemy/PostgreSQL/pgvector, existing HTTPX Jev adapter, LangGraph, Next.js/TypeScript, pytest and Docker.

**Spec:** [2026-10-09-jev-reranking-design.md](../specs/2026-10-09-jev-reranking-design.md), approved by the user after commit `f2450e1`.

**Execution:** Native implementation by the current agent, task-by-task; written plan approved by the user on 2026-10-09. This document is not an implementation-complete claim.

## Global Constraints

- Work only inside `/Users/nguyenducphat/TalentScreen AI/`; use an owned isolated worktree under `.worktrees/` at execution time. Do not modify the unrelated dirty `rag-agent` worktree.
- `JEV_RERANK_MODE=off|shadow|rerank|gate_experiment`, default `off`; enabled reranking requires `RAG_MODE=hybrid` and `RAG_PIPELINE_VERSION=v2`.
- Legacy `JEV_MODE=shadow` and enabled `JEV_RERANK_MODE` are mutually exclusive in the first release.
- Candidates sent to Jev per criterion per retrieval stage: 8. Questions per physical Jev request: 20.
- Jev state UTF-8 bytes per request: 16,384. Complete serialized Jev request UTF-8 bytes: 32,768.
- Jev physical calls, including failures/retries, per assessment: 9. Primary DeepSeek physical calls per assessment: at most 4. Assessment-wide physical calls with reranking enabled: at most 13. Ordinary/off runs retain their existing four-call ceiling.
- Jev request timeout: 15 seconds. Aggregate reranking wall-time allowance: 60 seconds. Tool executions: existing maximum 2.
- DeepSeek serialized request / unique evidence characters: existing 65,536 / 24,000. Citations and passage text are never shortened by the reranker.
- Ranking utility: `P(substantive_evidence) + P(limiting_evidence) + 0.35 * P(mention_only) + 0.15 * P(unclear)`; it is not an applicant score.
- Four selected chunks per criterion; reserve one eligible limiting passage with probability >=0.50 and one highest-RRF unscored passage, deduplicate, then fill by section diversity. Do not numerically compare RRF and Jev utility.
- Gate experiment is sandbox-only: exclude only `unrelated` with probability >=0.95 and confidence >=0.80. These are development thresholds, not proven operating thresholds.
- Rerank provider/contract failures terminate active runs; shadow retains original context. Stale/deleted/unapproved inputs stop all modes. Unknown billing keeps funds held and blocks paid admissions.
- Reserve a separately verified conservative Jev context allowance of 65,536 input tokens per allowed call; never reuse the DeepSeek tokenizer proof. Initial live synthetic experiment cap: USD 1 including worst-case reservations; reduce samples if not admitted.
- No deployment, automatic hiring action, new HR trace panel, paid call before reviewed execution, global candidate cache, frozen-fixture rewrite or unreviewed live-applicant hard gate.

## Review Focus

- A rubric has 12 criteria and Vietnamese passages fit fewer pairs per byte-bounded batch: allocate across criteria, record unscored pairs and never assign invented relevance (Task 2).
- A worker crashes after a billed call but before saving usable judgments: hold unknown/reserved admissions, stop replay and preserve call counts across restart (Tasks 3–4).
- Two workers try to admit the final allowed call concurrently: one durable admission succeeds, and the other cannot exceed either the provider or overall ceiling (Task 3).
- A tool returns the same passage under a changed query hint, criterion or document generation: reuse only an exact authorized judgment key; revalidate scope before reuse (Tasks 4–5).
- A historical run or unauthorized HR request reaches the new response field: preserve historical hashes and expose only an authorized summary, never distributions or copied CV text (Tasks 1 and 7).

## File structure and sequencing

Create `services/backend/app/services/reranking/` with `contracts.py` (strict data), `policy.py` (snapshots/config), `prompt.py` (typed questions), `planner.py` (byte/call allocation), `selection.py` (pure ranking), `service.py` (authorized orchestration) and `journal.py` (bounded private persistence). Keep provider transport in `services/jev/provider.py`; keep invocation admission/settlement in `services/llm/`.

Add `services/llm/call_policy.py` for the provider/stage ceilings and strict Jev financial policy. Add a nullable `assessment_runs.rerank_output` migration, not a parallel data store. Use an experimental `services/evaluation/benchmark/reranking.py` extension plus separate relevance fixtures; preserve existing V1 contracts when the extension is off. Frontend receives a small typed summary through the current assessment endpoint.

Dependencies: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8. Do not start a later task until the earlier task's targeted tests pass. Steps below refer to exact contracts produced by earlier tasks.

For DB tests use `bash scripts/test_backend_isolated.sh <test paths>` from the worktree root. Its disposable PostgreSQL fixture is required even for most pure tests because the existing autouse fixture initializes app configuration. Do not run pytest against the app's `.env` database. Configure local dependency paths before execution without downloading optional E5 weights.

---

### Task 1: Strict reranking policy and historical snapshot compatibility

**Files:** Create `services/backend/app/services/reranking/{__init__,contracts,policy}.py`; modify `services/backend/app/config.py`, `services/backend/app/services/assessment/policy.py`, `.env.example`, `scripts/test_backend_isolated.sh`, `.github/workflows/ci.yml`; create `services/backend/tests/test_rerank_policy.py`.

**Interfaces:**
- Produce frozen Pydantic `RerankPolicy` with `mode`, `policy_version='jev-evidence-ranking.v1'`, `prompt_version='jev-passage-choice.v1'`, requested/accepted models, endpoint, rate-card provenance and the exact Global Constraints. `enabled` means mode != off.
- Produce `freeze_rerank_policy(settings: Settings) -> RerankPolicy` and `load_rerank_policy(snapshot: dict) -> RerankPolicy`. Absent policy/digest returns off; explicit malformed/mismatched digest raises `ValueError('RERANK_POLICY_INVALID')`.
- Produce `ApprovedCriterion(criterion_id: str, label: str, description: str, anchors: tuple[str, ...], bilingual_terms: dict)`, `PassagePair(pair_id: str, criterion: ApprovedCriterion, chunk_id: str, chunk_index: int, text: str, span_ids: tuple[str, ...], section: str | None, rrf_score: float)`.
- Produce `PairJudgment(pair_id, choice, probabilities, confidence, reported_model)` with the five spec categories, and `RerankStageResult(stage, mode, ordered_pair_ids_by_criterion, selected_pair_ids_by_criterion, judgments, unscored_pair_ids, omitted_limiting_count, status, elapsed_ms)`. Both ID maps hold tuples of pair IDs.

- [ ] **Step 1: Write failing tests** named `test_absent_policy_is_off_without_changing_legacy_digest`, `test_explicit_policy_hash_mismatch_fails`, `test_enabled_policy_requires_v2_hybrid_and_verified_provider`, `test_gate_rejected_outside_sandbox` and `test_old_shadow_and_reranker_are_mutually_exclusive`. Assert the exact limits/modes and reject bool/nonfinite/unknown enum values.
- [ ] **Step 2: Verify RED.** Run `bash scripts/test_backend_isolated.sh services/backend/tests/test_rerank_policy.py`; expect missing new contracts or unsupported fields, not an environment failure.
- [ ] **Step 3: Implement the contracts/functions above.** Add `JEV_RERANK_MODE` and `JEV_RERANK_ACCEPTED_MODELS` (explicit list of reported versions, required when enabled). Reuse verified provider/rate fields. New policy digest uses compact, sorted JSON; do not inject off fields into old execution-policy snapshots. Generic test helper and CI explicitly set new mode off and clear optional live credentials. No primary-model dependency/version change.
- [ ] **Step 4: Verify GREEN and compatibility.** Run the new file plus `test_config.py`, `test_assessment_ablation_policy.py` and `test_ai_benchmark_provenance.py`; expected all pass with historical hashes unchanged.
- [ ] **Step 5: Commit** only the listed files with `feat: define versioned Jev reranking policy`.

### Task 2: Typed pair questions, bounded batches and deterministic selection

**Files:** Create `services/backend/app/services/reranking/{prompt,planner,selection}.py` and `services/backend/tests/test_rerank_kernel.py`; modify the new contracts only for types defined below.

**Interfaces:**
- Consume Task 1 types.
- Produce `build_jev_payload(pairs: tuple[PassagePair, ...], policy: RerankPolicy) -> dict`; one Choice per pair explicitly references `state.pairs[i]`. Include exact passage text and approved criterion descriptions in the state, never applicant identity.
- Produce `plan_batches(pairs_by_criterion: dict[str, tuple[PassagePair, ...]], policy: RerankPolicy, *, remaining_calls: int, focus_ids: tuple[str, ...]) -> BatchPlan`; Define `PlannedBatch(payload: dict, pairs: tuple[PassagePair, ...])` with derived ordered `pair_ids`; `BatchPlan(batches: tuple[PlannedBatch, ...], unscored_pair_ids: tuple[str, ...])` contains exact wire bodies. Every question key maps to precisely one ordered pair.
- Produce `validate_pair_judgments(body: dict, pairs: tuple[PassagePair, ...], policy: RerankPolicy) -> tuple[PairJudgment, ...]`, `rank_and_select(pairs: tuple[PassagePair, ...], judgments: tuple[PairJudgment, ...], policy: RerankPolicy, *, stage: Literal['initial','tool_1','tool_2'], elapsed_ms: int = 0) -> RerankStageResult`.

- [ ] **Step 1: Write failing tests.** Pin utility for a distribution, e.g. substantive=.40, limiting=.20, mention=.20, unclear=.10, unrelated=.10 -> .685. Assert deterministic tie ordering, one limiting/unscored reserved slot, at most four selections, exact quote preservation, zero scores for unrelated relevance never converted to competency zero, and all-unscored baseline identity. Assert gate thresholds at and just below .95/.80, limiting/unclear retention, swapped pairs/questions and exact answer membership. The 12-criterion VI test must prove stable round-robin allocation, no starvation while an eligible slot exists, <=20 questions, <=16,384 state bytes and <=32,768 body bytes. Oversized pairs are unscored, not truncated. Reject extra/missing keys, NaN/inf, inconsistent choice and invalid distributions.
- [ ] **Step 2: Verify RED.** Run `bash scripts/test_backend_isolated.sh services/backend/tests/test_rerank_kernel.py`; expect missing kernel functions/selection behavior.
- [ ] **Step 3: Implement the exact interfaces.** Use local indexed state, stable pair IDs bound to criterion/content/source hashes, exact five-option descriptions and stable deterministic sorting. An active gate removes only confident unrelated scored pairs. Select protected slots before diversity; fill remaining unscored candidates as an RRF-only tail. Batch planning reduces pair allocation before adding calls beyond the cap. Freeze question strings/weights in versioned constants.
- [ ] **Step 4: Verify GREEN.** Run both new test files; all tests pass without provider I/O. Inspect the resulting synthetic payload to ensure no field named candidate/email/name/school or copied raw CV is included.
- [ ] **Step 5: Commit** with `feat: add bounded Jev evidence ranking kernel`.

### Task 3: Provider-aware durable admission and exact Jev transport

**Files:** Create `services/backend/app/services/llm/call_policy.py`; modify `services/backend/app/services/llm/{types,orchestrator,cost}.py`, `services/backend/app/services/jev/provider.py`, existing secondary-scorer call construction in `services/backend/app/services/assessment/service.py`; create `services/backend/tests/{test_rerank_admission,test_jev_rerank_transport}.py`.

**Interfaces:**
- Produce `InvocationBudgetPolicy(primary_limit: int, rerank_limit: int, total_limit: int)` from an authorized run snapshot; off uses the old total limit and rerank_limit=0. Enabled uses primary<=4, rerank<=9, total<=13.
- Produce `JevReservationPolicy(budget_period_id: UUID, cap_usd: Decimal, max_input_tokens: int, rate_per_million_usd: Decimal, rate_verified_at: str, accepted_models: frozenset[str], provider_endpoint: str)`; verified full-context allowance is 65,536. It validates a Jev body rather than using `StrictReservationPolicy` for DeepSeek.
- Extend `CompletionRequest` with optional `purpose: Literal['primary','jev_secondary','jev_rerank'] | None` and `jev_reservation_policy: JevReservationPolicy | None`, preserving legacy defaults. Purpose is not added to the physical provider body.
- Produce `async admit_invocation(db: AsyncSession, *, job_id: UUID, request: CompletionRequest, logical_step: str, attempt_no: int, sanitized_version_id: UUID | None) -> AdmittedInvocation`; Define `AdmittedInvocation(invocation_id: UUID, reservation_id: UUID | None, reserved_usd: Decimal, input_upper_tokens: int, input_rate_per_million_usd: Decimal, output_rate_per_million_usd: Decimal, accepted_models: frozenset[str])`; these financial values are frozen at admission. Reserve and persist admission in one locked transaction before network I/O.
- Extend `get_jev_provider(*, policy: RerankPolicy | None = None)` and the provider's evaluation path to honor frozen request model/endpoint. No implicit route fallback.

- [ ] **Step 1: Write failing tests.** Off cannot admit a fifth call; enabled cannot admit the tenth rerank, fifth primary or fourteenth total. Verify counters include failures and admissions and cannot be bypassed by a mislabeled provider/step. Two async sessions racing the last slot must yield exactly one network admission. Failure after reservation/invocation commit leaves a durable record. Missing usage, timeout, model drift and malformed output retain unknown funds and block further paid calls; successful usage=0 remains 0. HTTPX MockTransport must assert exact transmitted `model/state/questions` body hash and one physical request, with no raw error echoed into logs. Reject a body one byte above caps before transport.
- [ ] **Step 2: Verify RED.** Run the two new tests; establish specific admission/serialization failures rather than changing financial gates to make them pass.
- [ ] **Step 3: Implement admission and transport.** Lock job row before call-count check, then budget-period/requisition rows in consistent order; persist reservation and invocation atomically, commit, perform HTTP outside the transaction. Use authenticated namespaces `jev_rerank_initial_N`, `jev_rerank_tool_1_N`, `jev_rerank_tool_2_N` (<50 chars) for classification and uniqueness; primary/secondary requests cannot use rerank namespaces. Serialized Jev material is exactly its wire envelope. Settlement uses frozen rates and accepted identities, not changed global rates. Add the exact HTTPS OpenRouter `/api/alpha/decisions` allowlist entry, retaining explicit legacy route support. Classify post-egress ambiguous failures as unknown; do not automatically retry them. Validate every billing usage count against the financial bound.
- [ ] **Step 4: Verify GREEN.** Run the new tests plus existing `test_jev_provider.py`, `test_ai_benchmark_budget.py` and applicable ledger/cost tests identified with `rg --files services/backend/tests`. Verify ordinary calls and existing shadow-scoring tests still pass. No live request here.
- [ ] **Step 5: Commit** with `feat: admit Jev rerank calls within frozen budgets`.

### Task 4: Private durable reranking journal, scoped reuse and migration

**Files:** Create `services/backend/app/services/reranking/{journal,service}.py`; modify `services/backend/app/db/models/assessment.py`, `services/backend/app/services/deletion.py`, `services/backend/app/services/observability.py`; create `services/backend/alembic/versions/b6d12f84a901_jev_rerank_output.py`, `services/backend/tests/{test_rerank_journal,test_rerank_migration}.py`; update `test_jev_shadow_migration.py`'s current-head assertion.

**Interfaces:**
- Produce `async rerank_candidates(*, db: AsyncSession, run: AssessmentRun, policy: RerankPolicy, stage: Literal['initial','tool_1','tool_2'], candidates_by_criterion: dict[str, tuple[PassagePair, ...]], focus_ids: tuple[str, ...] = (), provider_override: BaseLLMProvider | None = None, financial_policy: JevReservationPolicy | None = None) -> RerankStageResult`.
- Produce `async load_rerank_journal(db: AsyncSession, run: AssessmentRun) -> RerankJournal` and `async persist_rerank_stage(db: AsyncSession, run: AssessmentRun, stage: RerankStageResult, *, policy: RerankPolicy) -> None`. Define `RerankJournal(version: Literal['v1'], policy_digest: str, stages: tuple[RerankStageResult, ...], successful_judgments: dict[str, PairJudgment], cumulative_calls: int, cumulative_elapsed_ms: int, admission_ids: tuple[str, ...], pending_admission_ids: tuple[str, ...], truncated_rows: int)`; successful judgment keys hash criterion definition, source/version, content and policy. Persist metadata only, never source text.
- Add nullable JSONB `AssessmentRun.rerank_output`; cap serialized journal at 256 KiB and stage/pair counts to the Global Constraints, omitting excess diagnostic rows with a truncation count rather than changing assessment selection.

- [ ] **Step 1: Write failing tests.** Assert nullable JSONB and populated-old-row roundtrip; a successful exact judgment is reused without another invocation. Changing criterion/content/source/policy prevents reuse. Deleting/revoking/changing the snapshot during a synthetic network batch discards its selection and halts later batches. A restarted run with a pending admission does not repeat its billed call. Cumulative time from persisted stages cannot reset to 60s on each tool call. Journals contain no passage/prompt/contact/error body, stay size-bounded, and are removed with candidate/run deletion.
- [ ] **Step 2: Verify RED.** Run new journal/migration tests on a disposable DB; expect missing column/service or missing crash guard.
- [ ] **Step 3: Implement service/persistence.** Migration down_revision is the inspected current head `0c84e9d57a62`; upgrade adds only nullable JSONB, downgrade removes only that column. Before each batch/reuse invoke existing `snapshot_failure_code`; validate candidate/span membership against the exact sanitized version. Load remaining allowance from persisted admissions/journal. Stop new batches when 60s expires, fit request timeout to min(15s, remaining), and record pending pairs as unscored. On success recheck scope and persist sanitized metadata before allowing repeat work. Unknown billing aborts further paid work in every mode. Shadow may continue the unchanged primary only for failures with reconciled/non-unknown outcomes.
- [ ] **Step 4: Verify GREEN.** Run Task 3–4 tests, existing deletion tests and explicit isolated upgrade/downgrade/upgrade with historical rows. Add only approved aggregate trace keys and safe codes `JEV_RERANK_FAILED`, `RERANK_POLICY_INVALID`, `RERANK_BOUND_EXCLUDED`; compare exported LangSmith metadata against a canary private passage.
- [ ] **Step 5: Commit** with `feat: persist private run-scoped reranking provenance`.

### Task 5: Initial retrieval and agent-tool integration

**Files:** Modify `services/backend/app/services/retrieval.py`, `services/backend/app/services/assessment/service.py`, `services/backend/app/services/assessment/policy.py`, `services/backend/app/services/agent/{tools,assessment_graph}.py`, `services/backend/app/services/assessment/diagnostics.py`; create `services/backend/tests/test_rerank_assessment_flow.py`; extend `test_assessment_agent.py` and `test_agent_request_budget.py`.

**Interfaces:**
- Produce `async collect_hybrid_candidates(db: AsyncSession, sanitized_version_id: UUID, criterion_name: str, criterion_description: str, *, bilingual_terms: dict[str, Any] | None = None, anchor_terms: list[str] | None = None, channels: frozenset[str] = frozenset({'dense','lexical'}), pipeline_version: str = 'v1') -> list[RetrievedChunkScore]`. Return the existing full RRF pool (V1 10, V2 30); public `hybrid_retrieve_for_criterion` delegates and preserves its existing `top_k` slicing.
- Extend existing `build_hybrid_assessment_pack` with keyword-only `candidates_by_criterion: dict[str, list[RetrievedChunkScore]] | None = None` and `rerank_result: RerankStageResult | None = None`. A supplied scoped pool prevents duplicate retrieval; map selected pair IDs through Task 2's deterministic ID function. Unknown/mismatched IDs fail closed. Off/shadow packs use the original full pool and selection, active packs use reranked selections with canonical-span/whole-chunk bounds.
- Produce `pairs_from_candidates(criteria: list[ApprovedCriterion], candidates: dict[str, list[RetrievedChunkScore]], *, sanitized_version_id: UUID, rubric_version_id: UUID) -> dict[str, tuple[PassagePair, ...]]` in `reranking/prompt.py`.
- Extend `retrieve_more_evidence` with keyword-only `rerank_stage: Literal['tool_1','tool_2'] | None = None`, `rerank_provider_override: BaseLLMProvider | None = None` and `rerank_financial_policy: JevReservationPolicy | None = None`; default remains compatible. The graph derives stage from its existing tool counter, never client arguments. Inside the tool retain a `dict[str, list[RetrievedChunkScore]]` keyed by requested criterion throughout collection/reranking; flatten only the final deduplicated selections for the existing return type. Never infer a criterion association from the flattened list.

- [ ] **Step 1: Write failing tests.** Off has zero Jev admissions and unchanged original evidence map; shadow has hypothetical rerank metadata but byte-identical primary context. Active rerank changes selection on a predetermined script without changing quotes/IDs; empty/gated evidence remains nullable, not a zero competency score. Exercise two evidence tools plus repair and assert <=9 Jev, <=4 primary, <=13 overall and unchanged final request bounds. Assert all four scoped criteria are reranked when a tool requests four IDs and that a changed hint never reuses a mismatched input. Active contract failure must surface `JEV_RERANK_FAILED`; stale/deleted failure uses existing specific safe codes rather than generic provider error.
- [ ] **Step 2: Verify RED.** Run new flow tests and the extended actual-graph tests. Failures must demonstrate missing policy/stage integration.
- [ ] **Step 3: Implement the pipeline.** Freeze/digest enabled rerank policy during `create_assessment_run`, before snapshot hashing. For off snapshots preserve the existing payload shape. Collect exact scoped RRF candidates once, construct at most eight pairs per criterion, call Task 4 service, then select/pack. Preserve both initial RRF and post-rerank ranking in diagnostics. Pass a tool-specific stage to the same service and shared allowance; `get_source_spans` makes no Jev call. Continue using whole-span eviction and current allowlist validation after every tool/repair. No graph node renaming, prompt schema widening or automatic recommendation override.
- [ ] **Step 4: Verify GREEN.** Run new flow tests plus existing hybrid retrieval, assessment, agent and request-budget tests through the isolated helper. Confirm historical snapshots retain their digest and old version behavior; no failure path widens to full CV or another provider.
- [ ] **Step 5: Commit** with `feat: integrate Jev reranking into scoped RAG and agent retrieval`.

### Task 6: Controlled multi-provider experiments and separate relevance labels

**Files:** Create `services/backend/app/services/evaluation/benchmark/reranking.py`, `fixtures/rerank_benchmark/v1/{manifest,pairs,references}.json`, `services/backend/tests/{test_rerank_benchmark,test_rerank_metrics}.py`; modify benchmark `{runner,contracts,preflight,metrics,reporting,artifacts}.py`, `scripts/run_ai_benchmark_isolated.sh`, `scripts/run_ai_benchmark.py`; add `docs/evaluation/jev-provider-bounds.json` with official source/verification metadata before live admission.

**Interfaces:**
- Produce `load_pair_references(root: Path) -> PairReferenceDataset` Define `PairReferenceDataset(input_pairs: tuple[PassagePair, ...], design_labels: dict[str, str], independent_grades: dict[str, int] | None, sufficient_groups: dict[str, tuple[tuple[str, ...], ...]], limiting_pair_ids: tuple[str, ...], contradictory_pair_groups: tuple[tuple[str, str], ...], hashes: dict[str, str])`; reference category/grades stay outside `input_pairs`. Use disjoint input/reference loading, five-category design labels and optional independently authored graded relevance. Hash all inputs; reference files never enter model state.
- Extend run CLI with `--rerank-mode off|shadow|rerank|gate_experiment` (default off) and `--reranker-provider scripted|jev` (default scripted). One mode per experiment avoids changing legacy case/profile record keys. Non-off experiments use a strict versioned manifest extension recording both providers; off retains V1 JSON/schema compatibility.
- Produce `plan_rerank_budget(primary_plan: BudgetPlan, selection: RunSelection, *, policy: RerankPolicy, reranker_provider: Literal['scripted','jev'], cap_usd: Decimal, probe_calls: int = 0) -> MultiProviderBudgetPlan`. Define `MultiProviderBudgetPlan(primary: BudgetPlan, rerank_upper_by_combination: dict[str, Decimal], probe_upper_usd: Decimal, total_upper_usd: Decimal, cap_usd: Decimal, admitted: bool)`; combination keys are stable case/profile JSON strings. Primary mock and scripted Jev have zero paid reservation, while physical-call ceilings still apply. Combine existing primary worst-case reservation with at most nine separately verified Jev reservations for every selected case/profile plus explicitly admitted probe calls. No model I/O in preflight.
- Produce `evaluate_rerank_records(dataset: PairReferenceDataset, records: list[dict], *, seed: int) -> dict` with exact counts, sufficient-group retention, optional graded NDCG, ranking recall, omission/error rates and paired per-CV intervals. Add separate Jev recording provider, not an alias of DeepSeek's recorder.

- [ ] **Step 1: Write failing tests.** Old CLI/manifest records remain accepted and unchanged when off. Scripted Jev + mock primary is explicitly contract-only; live Jev + mock primary reports measured reranking but unmeasured primary quality. Assert four comparison arms, no-tool/agent separation, model identities pinned per provider, exact reuse/admission reconciliation, pending/failed denominators and no automatic zero cost. Preflight must reject a plan above USD 1 before network; it must reject model/endpoint/pricing/context uncertainty without borrowing the DeepSeek proof. NDCG is null without grades; the canary label file never appears in prompts. A reordered or edited frozen input causes a hash failure.
- [ ] **Step 2: Verify RED.** Run new benchmark/metrics tests plus targeted old CLI/reporting tests, observing unsupported extension failures.
- [ ] **Step 3: Implement experiments.** Keep frozen `fixtures/ai_benchmark/v1` and `v2` immutable. Add separate VI/EN/mixed relevance examples for 12-criterion allocation, negation, mention-only skills, paired contradictions, oversized context and CV instructions. Reuse owned disposable-DB/artifact utilities. Add separate `rerank.jsonl` and provider-specific admissions, latencies and financial records; record byte caps, policy hashes and actual served models. Extend metrics before and after packing, not only top-1 choice. Wrapper defaults new mode off; explicit experimental arguments configure test providers safely without reading the app DB or exporting secrets. Context/rate source artifact identifies endpoint-specific evidence and conservative 65,536-token reservation as an upper financial allowance, not a proved tokenizer estimate.
- [ ] **Step 4: Verify GREEN.** Run all benchmark-related tests through the isolated helper. Run `bash scripts/run_ai_benchmark_isolated.sh run --dataset fixtures/ai_benchmark/v2 --provider mock --profiles hybrid,hybrid_agent --cases v2-node-01,v2-ai-01,v2-android-01 --embedding-mode scripted --retrieval-version v2 --rerank-mode rerank --reranker-provider scripted --max-cost-usd 1 --output reports/ai-benchmark/jev-scripted-smoke-20261009` once into a previously absent output directory; expect completed and fully reconciled mock journals, not measured model-quality claims. Repeat a small cached-real-E5 run without a paid primary.
- [ ] **Step 5: Commit** with `feat: evaluate Jev reranking with controlled provider ablations`.

### Task 7: Minimal HR notice and private developer observability

**Files:** Modify `services/backend/app/schemas/assessment.py`, `services/backend/app/services/assessment/service.py`, `services/backend/app/services/observability.py`, `apps/web/src/lib/api.ts`, `apps/web/src/app/applications/[id]/page.tsx`; create `services/backend/tests/test_rerank_visibility.py` and `apps/web/tests/reranking-summary.test.mjs`.

**Interfaces:**
- Produce optional `AssessmentRunResponse.reranking_summary` / TypeScript `RerankingSummaryData` with `mode`, `applied`, `omitted_count`, `needs_evidence_review` and `error_code`, default null. Derive it from authorized journal/snapshot; never expose raw `rerank_output` through generic ORM serialization.
- Add allowlisted aggregate developer spans `jev_rerank` and `jev_gate`, with mode/version, counts, timing and safe outcome codes only.

- [ ] **Step 1: Write failing tests.** An unauthorized user cannot get summary data; old rows return null; shadow shows applied=false even when hypothetical ranking differs; rerank/gate omissions produce a review notice. Distributions/pair/source text and provider errors never appear in API or trace exports. Frontend must render exact copy only when `needs_evidence_review` is true: “Một số bằng chứng chưa được đưa vào đánh giá. Hãy đối chiếu CV hoặc yêu cầu AI tìm thêm trước khi quyết định.” No new navigation or probabilities labeled as applicant fit.
- [ ] **Step 2: Verify RED.** Run the backend visibility file and `npm test` in `apps/web`; observe missing summary behavior.
- [ ] **Step 3: Implement the summary and notice.** Use existing assessment details/card styles, semantic status text and a link to the existing evidence action. Existing failures remain actionable. Native API authorization stays unchanged; telemetry remains best-effort and metadata-only.
- [ ] **Step 4: Verify GREEN.** Run visibility and frontend tests/build. Browser QA with synthetic data at 390, 820 and 1440 px checks no horizontal overflow, notice readability and successful CV/evidence/decision flow. If no omission exists, the usual HR screen remains unchanged.
- [ ] **Step 5: Commit** with `feat: surface bounded evidence-review notices without exposing reranker internals`.

### Task 8: Regression, admitted live synthetic experiment and honest release evidence

**Files:** Update `README.md`, `docs/architecture.md`, `docs/evaluation/ai-benchmark-reproducibility.md`; create `docs/runbooks/jev-reranking.md` and dated review/result artifacts under `docs/reviews/` and `docs/evaluation/`. Raw private journals stay ignored under `reports/`.

**Interfaces:** Consume completed Tasks 1–7. Produce a measured report with code/config/data/model/rate provenance, activation recommendation, explicit limitations and rollback instructions; no new runtime API.

- [ ] **Step 1: Run regression.** Execute `make test` in the owned worktree, migration upgrade/downgrade/upgrade on disposable PostgreSQL, and all new privacy/concurrency/crash tests. Expected: no failures, frontend production build success, skips named honestly. Do not rerun unchanged checks after they pass unless later edits justify it.
- [ ] **Step 2: Freeze the implementation commit and experiment inputs.** Record clean Git SHA, hash unchanged frozen fixtures, store the scripted/cached-real results and selected synthetic live cases before model I/O. Verify local key presence without printing values and exact endpoint/model/rate preflight. Add a synthetic endpoint-contract probe as a budgeted admission, not an unaccounted ping.
- [ ] **Step 3: Run only an admitted live experiment.** Through the isolated wrapper, compare hybrid V2 off/shadow/rerank/gate with live Jev and mock primary first; use a fresh output and combined USD 1 cap including the probe. Then use identical preselected cases/prompts for paired live DeepSeek where the remaining worst-case reservation permits it. Never increase the cap automatically, relabel references, add real CVs or hide failed cases. If credentials, model version, pricing/context verification or budget block admission, document the concrete blocker and finish offline verification without inventing a live result.
- [ ] **Step 4: Evaluate and document.** Report limiting/contradictory evidence retention, complete group coverage, omission/error rates, actual tool use, p50/p95 and financial reconciliation. Apply the spec's activation criteria: no new labeled negative/conflict losses, improvement or equal coverage with material cost/context reduction, added rerank p95 <=5s, no unresolved funds. Keep mode off/shadow when unmet. Real-data gate remains disabled regardless of synthetic success. Update README/architecture with only observed results and the exact distinction between optional secondary scoring and pre-primary reranking.
- [ ] **Step 5: Finish and integrate.** Obtain whole-branch code review using the execution skill's review workflow; reproduce/fix material findings and rerun affected checks. Preserve ignored reports before cleanup. Integrate the owned branch into primary `main` only when the primary checkout is clean and checks pass, push according to the user's standing instruction, verify local/remote SHA equality. Do not remove the unrelated worktree or mutate running `.env`/app DB merely to merge. Report what is implemented, what was actually run, and the remaining activation limits.

## Preparation and handoff checklist

- [ ] User reviews this written plan and confirms it captures the approved spec; Native execution method is preserved.
- [ ] At execution, read `executing-plans`, `using-git-worktrees` and applicable TDD/verification skills. Inspect attached artifacts and prefer an owned suitable worktree; if none, create `codex/jev-evidence-reranking` under `.worktrees/jev-evidence-reranking` from approved main. Do not infer that the existing dirty `rag-agent` worktree is safe to reuse.
- [ ] Configure isolated test dependencies/env; confirm the baseline suite before product edits. No paid API calls during baseline verification.
- [x] Self-review completed: all spec sections map to Tasks 1–8, types/signatures match across tasks, five Review Focus items have named test requirements, and no placeholder implementation decision remains.

This plan was approved for implementation. It does not authorize model-quality claims, real-applicant hard gating, or declaring implementation complete before the recorded checks.
