# AI Evaluation and RAG/Agent Ablation Implementation Plan

> Archived 10 October 2026. The v1/v2 datasets and old case IDs described below were removed. The active synthetic regression set is `fixtures/ai_benchmark/synthetic_100_multi_role`; the earlier Backend Python-only `golden_100` remains a legacy fixture. The references are AI-authored design expectations, not independent HR/IT labels.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible developer benchmark that measures the actual TalentScreen assessment pipeline across four evidence/agent profiles and publishes honest portfolio evidence.

**Architecture:** A synthetic dataset feeds a disposable PostgreSQL instance and the existing assessment service. A private execution policy controls only retrieval channels and tool availability; shared graph, validators, scoring and budget ledger remain authoritative. Typed result journals drive offline metrics and HTML/Markdown reports.

**Tech Stack:** Existing Python 3.12, Pydantic 2, SQLAlchemy, PostgreSQL/pgvector, multilingual E5, LangGraph, httpx, LangSmith, pytest; Python standard-library CLI/reporting. Existing python-docx and LibreOffice generate document fixtures. No new frontend route or core runtime dependency.

**Spec:** [2026-10-08-ai-evaluation-ablation-design.md](../specs/2026-10-08-ai-evaluation-ablation-design.md), approved by the user on 2026-10-08.

**Execution status:** Approved for Native sequential execution on 2026-10-08; see focused commits and execution ledger. Suggested method: Native, sequentially in this session. Estimated effort: 8–12 focused developer days, including annotation review and live verification; provider/model/setup issues may extend verification.

## Global Constraints

- Work only under `/Users/nguyenducphat/TalentScreen AI`; preserve secrets, real CVs and production records.
- **60 synthetic CVs**, twenty each for `backend_node`, `ai_ml`, `android`.
- **36 development / 24 public test cases**; twelve/eight per role; public test is not a protected HR holdout.
- Four profiles: `full_text`, `dense`, `hybrid`, `hybrid_agent`; one repetition, concurrency one.
- Same CV/JD/rubric/source IDs/model/common prompt/configuration across profiles.
- Tools: zero for the first three profiles; **at most two executions** for `hybrid_agent`.
- Normal model turns **at most three**, repairs **at most one**, outbound calls **at most four**.
- Scores **0–4**; `insufficient_evidence` and `conflicting_evidence` require `null`, never zero.
- Gold origin is `design_expected`; gold files never enter provider inputs, tools or graph state.
- **USD 5 cumulative cap for the initial live experiment**, across all roles/profiles; reject an unaffordable plan before calls.
- No silent mock/full-text fallback, paid resume, budget increase, profile removal or unknown-outcome retry.
- LangSmith exports metadata only; no CV/JD/prompt/response/quote/tool-argument/credential/gold content.
- Twelve separate document-ingestion smoke fixtures: **six PDF and six DOCX**; do not merge their timings with the assessment benchmark.
- Preserve existing offline benchmark v2/Jev compatibility and existing HR workflow. No Jev activation, automated hiring/email, deployment or unrelated refactoring.

## Review Focus

1. NFC/NFD Vietnamese, CRLF and repeated bilingual evidence must resolve to stable exact spans without duplicate credit — Task 1 tests.
2. A correct-looking database name or environment flag without an owned-container marker must not authorize writes — Task 2 tests.
3. Tool responses, repair history and Unicode can exceed a naive token estimate; live admission must account for complete requests — Task 5 tests.
4. Duplicate journal records, a torn final JSONL line and unmatched profile coverage must not inflate quality or conceal incomplete runs — Tasks 6 and 7 tests.
5. CV-derived HTML, provider error text or secret-shaped metadata must never become executable report content or exported traces — Tasks 7 and 8 tests.

## File and dependency map

| Area | Create/modify | Responsibility |
| --- | --- | --- |
| Data/contracts | `app/services/evaluation/benchmark/{__init__,contracts,dataset}.py`; `fixtures/ai_benchmark/v1/{manifest,roles}.json`, `cases.jsonl`, `references.jsonl` | Frozen synthetic inputs, labels and report types |
| Isolation/seed/docs | `benchmark/{isolation,seed,documents}.py`; `scripts/run_ai_benchmark_isolated.sh` | Owned database/storage, synthetic application entities, PDF/DOCX smoke |
| Policy | `app/services/assessment/policy.py`; existing assessment service/prompt and agent graph | Internal profile seam; production defaults unchanged |
| Retrieval | Existing `app/services/retrieval.py` | Explicit channels using the same scoped ranking/packing code |
| Diagnostics | `app/services/assessment/diagnostics.py`; existing service/graph/orchestrator | Allowlisted local measurements before and after validation |
| Preflight/cost | `benchmark/preflight.py`; existing LLM types/provider/orchestrator/cost | Conservative planning, usage collection and ledger enforcement |
| Runner/artifacts | `benchmark/{runner,artifacts,mock_provider}.py`; `scripts/run_ai_benchmark.py` | Actual assessment execution and durable journals |
| Metrics/report | `benchmark/{metrics,reporting}.py`; existing evaluation metric primitives | Offline reference comparisons and static reports |
| Verification/docs | New benchmark test files; existing regression tests; CI; README; `docs/evaluation/independent-human-evaluation-design.md` | Offline CI, real-E5/live evidence and truthful presentation |

`app/services/...` resolves under `services/backend/app/services/...`; `assessment/...`, `agent/...` and `llm/...` resolve under that services directory. `benchmark/...` resolves under `services/backend/app/services/evaluation/benchmark/...`; tests resolve under `services/backend/tests`. Scripts run from the repository root. Use existing `.venv/bin/python`; run pytest through the disposable database script because backend conftest requires isolation even for otherwise pure tests.

Dependency order: **1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9**. Every task has a RED/GREEN cycle and a focused commit. Do not change a downstream interface without updating its tests and this plan.

## Shared types and artifact contract

Task 1 defines strict Pydantic models with `extra="forbid"`; reject booleans where numeric scores/tokens are expected and reject NaN/infinity. Use `Decimal` for financial decisions and JSON decimal strings for monetary output.

- `ProfileName = Literal["full_text", "dense", "hybrid", "hybrid_agent"]`.
- `CaseInput`: case/cluster/role IDs, language (`vi|en|mixed`), tags, split, raw synthetic CV, JD/rubric references.
- `RoleInput`: JD text/hash and approved-rubric-compatible criteria/policy. Use existing rubric DTO validation; criterion weights total 100.
- `DatasetInputs`: immutable case tuple, role map, root path, manifest and input hashes; contains **no gold labels**.
- `CriterionReference`: expected application status, nullable score, sufficient-evidence groups of exact span IDs/quotes, clarification expectation, annotation explanation and completeness flag.
- `CaseReference`: case ID, `origin="design_expected"`, criterion-reference map.
- `RunSelection`: ordered case IDs, profile tuple, seed `20261008`, concurrency/repetitions fixed at one.
- `InvocationRecord`: logical step, requested/reported model, invocation status, nullable input/output/cache tokens, reserved/estimated cost, nullable measured latency; excludes request/response bodies.
- `RunRecord`: schema version `ai-benchmark.v1`, case/profile/job/run IDs, terminal status/code, normalized criterion observations and evidence IDs, ranked/initial/final evidence maps, numeric diagnostics, timings, invocation records, provenance and trace ID.
- `RunManifest`: experiment UUID, schema/version hashes, selected combinations, policies, provider/model, setup/device, rate-card verification, cap and final completion status.
- `MetricsReport`: version, manifest identity, planned/attempted/accepted/failed/skipped totals, profile/role/language statistics, comparable-pair counts and paired intervals; nullable measurements remain null.
- `IsolationContext`: experiment UUID, owned container ID, loopback port, expected database name/nonce, temporary root and storage root. No password/key is serialized.
- `SeededCase`: case ID, application/document/sanitized/rubric UUIDs and synthetic `AuthenticatedContext`.
- `BudgetPlan`: selected combinations, defensible input-bound provenance, per-combination worst-case reservations, total bound, cap and admission status.

Only `DatasetInputs` travels into runner/seeding. `load_references` is used for upfront validation and post-run evaluation, never passed to assessment execution.

### Task 1: Frozen dataset, reference resolution and contracts

**Files:** Create `benchmark/contracts.py`, `dataset.py`, `__init__.py`, four dataset files and `tests/test_ai_benchmark_dataset.py`.

**Interfaces:** Produce `load_inputs(root: Path) -> DatasetInputs`, `load_references(root: Path, inputs: DatasetInputs) -> dict[str, CaseReference]`, `canonical_case(case: CaseInput) -> tuple[UUID, str, list[SourceSpan]]`, `select_runs(inputs: DatasetInputs, *, split: Literal["development", "public_test", "all"] | None, case_ids: tuple[str, ...], profiles: tuple[ProfileName, ...], seed: int) -> RunSelection`.

- [ ] **Step 1 — Write failing tests.** `test_dataset_shape_and_cluster_split` asserts 60 total, 20/role, 36/24 split, 12/8 per role, 7/7/6 languages per role, all languages in both splits, and no cluster crossing splits. `test_gold_references_are_exact_and_dynamic` asserts gold criterion sets equal their rubric, every quote matches its canonical span, assessed scores are integers 0..4, conflicts have null plus at least two contradictory spans, insufficient cases have null. `test_unicode_canonicalization_and_duplicate_bilingual_claim` asserts NFC/NFD and LF/CRLF equivalents yield identical canonical hashes/IDs and repeated statements do not create a second expected achievement. Reject dangling references, duplicate cases, bool scores and mislabeled zero.
- [ ] **Step 2 — Run RED.** `bash scripts/test_backend_isolated.sh services/backend/tests/test_ai_benchmark_dataset.py`; expect missing benchmark imports/fixtures, not dependency failures.
- [ ] **Step 3 — Implement contracts and loader.** Canonicalization uses `sanitize_text`, `normalize_text_nfc_lf`, `build_source_spans_from_canonical`; version UUID is UUID5 of a fixed namespace plus `ai-benchmark.v1/<case_id>`. Compile gold from exact canonical quotes and freeze the generated IDs. Loader validates manifest SHA-256 values and rejects symlinks/path traversal outside the dataset root.
- [ ] **Step 4 — Author the dataset.** IDs `node-01..20`, `ai-01..20`, `android-01..20`. Per role: development 01–12 has four vi/four en/four mixed; public test 13–20 has three vi/three en/two mixed. Counterfactual cases 11/12 share one cluster and identical competency evidence. Use distinct scenarios/projects for other clusters, including direct anchor 0..4, absent/skills/team claims, partial/conflicting evidence, buried facts and injection. Specialize each role's anchors and JD source requirements from existing multi-role samples; do not use generic Python IDs or infer scores from years/school/name.
- [ ] **Step 5 — Run GREEN and annotation review.** Same command; inspect each case/reference against its JD/anchor, fixing ambiguous annotations before freezing hashes. Record label authorship as synthetic design, never HR-independent.
- [ ] **Step 6 — Commit.** `feat: add multi-role synthetic benchmark contracts and references`.

### Task 2: Owned isolation, synthetic seeding and document smoke

**Files:** Create `benchmark/isolation.py`, `seed.py`, `documents.py`, wrapper script; `tests/test_ai_benchmark_isolation.py`, `test_ai_benchmark_documents.py`. Reuse `intake.py`, `provenance.py`, `sanitizer.py`, models and service guards.

**Interfaces:** Consume Task 1 inputs. Produce `assert_isolated_database(db: AsyncSession, context: IsolationContext) -> None`, `seed_cases(db: AsyncSession, inputs: DatasetInputs, selection: RunSelection, context: IsolationContext) -> dict[str, SeededCase]`, `materialize_documents(inputs: DatasetInputs, output: Path) -> list[Path]`, `run_document_smoke(db: AsyncSession, inputs: DatasetInputs, context: IsolationContext, output: Path) -> dict[str, Any]`.

- [ ] **Step 1 — Write failing tests.** `test_fake_isolation_flag_cannot_authorize_writes` checks wrong nonce/name/storage and asserts no seed/migration/write occurred. `test_cleanup_only_stops_owned_container` uses mocked Docker commands to reject a mismatched ownership label. `test_seed_is_synthetic_approved_and_snapshot_consistent` checks memberships, current document/rubric links, deterministic spans and audit provenance. `test_twelve_documents_preserve_technical_evidence_and_remove_pii` checks six PDF/six DOCX across all roles/languages, original synthetic contact/name absence after redaction, and expected technical snippets preserved.
- [ ] **Step 2 — Run RED.** Run the two new files through `scripts/test_backend_isolated.sh`.
- [ ] **Step 3 — Implement wrapper and isolation checks.** Start `pgvector/pgvector:pg16` with an experiment ownership label and ephemeral `127.0.0.1` port, database `talentscreen_benchmark`, random password and nonce. Create extensions/migrate only through this owned container. Store nonce in a database comment; runner verifies `current_database()`, the comment, explicit DSNs and resolved temporary storage before writes. Never print DSNs containing passwords. EXIT/INT/TERM cleanup compares exact container ID/label and removes only owned temporary storage.
- [ ] **Step 4 — Implement seed/document helpers.** Core assessment cases use valid synthetic approved ORM fixtures with memberships, approvals and audit origin; they are not human attestations. Distinct profile jobs share each case's sanitized UUID. Document smoke invokes actual `upload_application_document` then `ingest_and_parse_document` in separate smoke applications, without starting a live worker or triggering paid assessments. Build DOCX with python-docx; convert six to PDF with existing LibreOffice using a private temporary user profile. Generate under ignored report/temp paths; record generator/version/file hashes. Missing LibreOffice is an explicit prerequisite failure, not a substituted fake PDF.
- [ ] **Step 5 — Run GREEN.** Isolated tests pass; confirm unrelated containers and source files remain intact. Add a wrapper command smoke with mocked Docker to exercise interruption cleanup.
- [ ] **Step 6 — Commit.** `feat: isolate benchmark data and document ingestion smoke`.

### Task 3: Shared execution policy and dense/hybrid ablation

**Files:** Create `assessment/policy.py`; modify `assessment/service.py`, `assessment/prompt.py`, `agent/assessment_graph.py`, `retrieval.py`; add `tests/test_assessment_ablation_policy.py`; extend existing prompt/retrieval/agent tests.

**Interfaces:** `AssessmentExecutionPolicy` is frozen and validates profile, channels, tools, max evidence characters 24000, prompt versions, temperature 0, thinking disabled and output limit 4096. Produce `benchmark_policy(profile: ProfileName) -> AssessmentExecutionPolicy`. Extend `create_assessment_run(..., *, execution_policy: AssessmentExecutionPolicy | None = None)`; executor loads frozen optional snapshot policy. Add keyword-only `channels: frozenset[str]` to existing retrieval/pack functions with current dense+lexical default. Extend `run_assessment_agent(..., execution_policy: AssessmentExecutionPolicy | None = None)`.

- [ ] **Step 1 — Write failing tests.** `test_four_profiles_share_prompt_and_source_snapshot` asserts equal effective prompt/model/schema hashes and same CV/rubric IDs; the test captures the complete effective system text including agent instructions. `test_dense_does_not_execute_lexical_query` and `test_hybrid_preserves_rrf_and_scope` check queries/ranks, exact version/config filtering and unchanged default results. `test_disabled_tools_cannot_execute` injects a tool call into each non-agent profile and expects rejection. `test_agent_empty_initial_pack_can_recover_evidence` scripts retrieve/get-source calls, then validates supported output within two tools/three normal turns. `test_old_snapshots_and_public_api_ignore_experimental_profiles` checks old strategy behavior and that API request DTOs cannot introduce the policy. `test_graph_repair_and_outbound_limits_are_enforced` pins three normal turns, one repair, two tools and four total requests, including repair exhaustion.
- [ ] **Step 2 — Run RED.** Isolated policy/prompt/retrieval/agent tests; identify intended missing seam behavior.
- [ ] **Step 3 — Implement the narrow seam.** Register immutable `assessment-v1.6.0` for experiments, with neutral provided-evidence wording and per-criterion span constraints; preserve v1.4/v1.5 and default production choice. Same agent prompt across all four. Snapshot `assessment_execution_policy` and its hash only for internal calls. Existing stored strategy remains `full_text_baseline` for full text and `hybrid` for the others; effective experimental channel/profile comes from policy. Dense disables only the lexical query in shared retrieval. Cap each profile's supplied evidence consistently at 24000 characters and expose truncation/oversize outcomes. Do not widen failed retrieval to full text.
- [ ] **Step 4 — Preserve graph bounds and lifecycle checks.** Derive tool declarations/eligibility from the frozen policy; keep existing authorization, generation/current-snapshot checks, tool allowlist, repair and outbound ceilings. Leave default production empty-hybrid recovery intact. No graph checkpointer or new API switch.
- [ ] **Step 5 — Run GREEN.** New plus existing assessment, agent, prompt and hybrid retrieval suites pass; verify old prompt hashes did not change.
- [ ] **Step 6 — Commit.** `feat: add internal assessment ablation profiles`.

### Task 4: Local diagnostics with raw-error visibility

**Files:** Create `assessment/diagnostics.py`; modify service/graph/validator integration as needed; add `tests/test_assessment_diagnostics.py`.

**Interfaces:** Produce `AssessmentDiagnostics.record_stage(name: str, elapsed_ms: float) -> None`, `record_retrieval(criterion_id: str, ranked_chunks: list[list[str]], delivered_span_ids: list[str]) -> None`, `record_validation(*, rejected_citations: int, normalized_criteria: int, schema_failures: int) -> None`, `record_final_evidence(mapping: dict[str, list[str]]) -> None`, `snapshot() -> dict[str, Any]`. Optional recorder arguments on service/graph preserve behavior when absent. Each recorder is scoped to one run, never a module-global shared mutable object.

- [ ] **Step 1 — Write failing tests.** `test_candidate_pool_and_delivered_pack_are_distinct` uses ten ranked chunks but four packed chunks and checks both retained. `test_validator_does_not_hide_raw_model_errors` scripts an unsupported score normalized to null and a quote mismatch requiring repair; counters remain nonzero after successful validation. `test_recorder_excludes_text_and_is_run_scoped` passes secret/CV markers and verifies snapshots contain no raw text and another run's measurements remain separate.
- [ ] **Step 2 — Run RED.** Isolated diagnostics and agent tests.
- [ ] **Step 3 — Implement allowlisted diagnostics.** Capture candidate rank before diversity/packing; record stable span IDs and selected evidence, not chunk text. Measure indexing, retrieval, graph, validation/scoring and total assessment with monotonic timers; failed stages have elapsed time or explicit unmeasured null. Capture initial/final per-criterion evidence and pre-normalization counters. Validation failures export fixed categories/counts, never Pydantic messages containing candidate strings. Instrumentation failure cannot convert a valid assessment into success/failure differently.
- [ ] **Step 4 — Run GREEN.** Diagnostic fixtures prove structural validity and semantic-gold agreement remain distinct measurements; no-recorder regression behavior matches baseline.
- [ ] **Step 5 — Commit.** `feat: record privacy-safe assessment experiment diagnostics`.

### Task 5: Preflight, conservative admission and measured token usage

**Files:** Create `benchmark/preflight.py` and `docs/evaluation/deepseek-token-bound.json`; modify `llm/types.py`, `provider.py`, `orchestrator.py`, `cost.py` only where required; thread optional `strict_reservation_policy` through the assessment executor and graph; add `tests/test_ai_benchmark_budget.py`; extend `test_llm_adapter.py`.

**Interfaces:** Produce `plan_budget(inputs: DatasetInputs, selection: RunSelection, policies: dict[ProfileName, AssessmentExecutionPolicy], *, model: str, cap_usd: Decimal, bound: InputBound) -> BudgetPlan` and `validate_live_preflight(plan: BudgetPlan, *, provider_host: str, pricing_verified_at: str, model_available_locally: bool) -> None`. `InputBound` is defined in `benchmark/contracts.py` with strategy (`verified_utf8|model_context`), positive maximum input tokens, nullable maximum serialized UTF-8 bytes, nullable framing allowance, nullable tokenizer artifact SHA-256, proof reference and rate-card identity. For verified UTF-8 mode, fix the request ceiling at 65536 serialized bytes and framing allowance at 4096 tokens; verify the tokenizer byte bound and justify the framing assumption before enabling it. If those assumptions cannot be defended for the requested model, select model-context fallback instead. Context fallback reads the verified context ceiling from the rate-card/model metadata and does not guess it from the model name. Add optional benchmark-only strict reservation policy to `CompletionRequest`, `execute_assessment_job` and `run_assessment_agent`; legacy default unchanged. Add nullable `cached_input_tokens` to `CompletionResult`; parse and validate it against total input usage.

- [ ] **Step 1 — Write failing tests.** `test_three_roles_share_one_experiment_cap` reserves across requisitions and refuses total spent+held above 5. `test_plan_includes_unicode_tool_history_and_repairs` verifies all four possible requests and max output, including UTF-8/tool schema/history, are included. `test_over_budget_plan_makes_no_provider_calls` rejects unaffordable scope with profiles intact. `test_unknown_or_missing_usage_retains_reservation` covers timeout, post-admission server/transport errors and absent input/output usage in strict mode; no second call occurs. `test_cache_usage_and_model_change_are_explicit` checks invalid cache counts rejected, missing cache reported null, actual model changes stop comparability, and zero actual usage is not replaced by an estimate.
- [ ] **Step 2 — Run RED.** Isolated budget/adapter tests.
- [ ] **Step 3 — Implement planning without paid calls.** Bound whole conversation, at most two tool results and one repair; no chars/3 approximation or assumed cache savings. A verified byte-bounded tokenizer may use serialized UTF-8 length plus a documented chat-framing allowance; require artifact/proof in `InputBound`. Without defensible tokenizer/framing verification, use the provider's verified maximum input context as the conservative bound; if that exceeds USD 5, reject and report the reason, never relax the rule silently. Enforce the planned input/output limits on every actual request. Check pinned E5 files locally with offline cache inspection; do not download on `plan`. Validate supported requested model/rate card and explicit direct-DeepSeek hostname.
- [ ] **Step 4 — Reuse the database ledger for the experiment cap.** One disposable database per experiment means its single DEVELOPMENT `BudgetPeriod` is the experiment-wide reservation ledger. Child-process `DEV_EVAL_BUDGET_USD=5` (or the explicit lower cap) applies across all roles; existing per-requisition guards still apply. Validate the period ID/cap before admission and put it in the manifest. No additional budget table/migration and no live ledger reset. Commit reservation before network, retain unknown funds, record settled peak-rate estimates separately from provider invoice unavailable. Strict benchmark outcomes stop on server/transport ambiguity or missing usage; preserve legacy defaults outside strict policy. Set rate-card version on new invocation records. Parse cache usage when supplied, otherwise use conservative miss pricing and report cache usage unmeasured.
- [ ] **Step 5 — Verify official pricing and bound provenance.** Before live execution, check [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/) and [token usage](https://api-docs.deepseek.com/quick_start/token_usage/). Those docs treat usage returned by the API as authoritative; a character ratio is not proof of an upper bound. Record verification date/source, pin the applicable tokenizer artifact or reject the byte-bound shortcut. Existing rates matched the retrieved pricing page on 2026-10-08; recheck at execution and version any changed card rather than relabeling old spend.
- [ ] **Step 6 — Run GREEN.** New budget plus adapter/ledger tests pass; verify all strict benchmark exceptions leave a recoverable sanitized financial record.
- [ ] **Step 7 — Commit.** `feat: enforce isolated benchmark admission and usage accounting`.

### Task 6: Actual pipeline runner, CLI and interruption journal

**Files:** Create `benchmark/runner.py`, `artifacts.py`, `mock_provider.py`, CLI script; extend wrapper; add `tests/test_ai_benchmark_runner.py`, `test_ai_benchmark_cli.py`.

**Interfaces:** Produce `run_experiment(db: AsyncSession, inputs: DatasetInputs, selection: RunSelection, context: IsolationContext, *, provider: BaseLLMProvider, budget_plan: BudgetPlan, output: Path) -> RunManifest`, `append_record(path: Path, record: RunRecord) -> None`, `read_records(path: Path) -> list[RunRecord]`, and CLI `main(argv: list[str] | None = None) -> int`. `BenchmarkMockProvider.complete(request: CompletionRequest) -> CompletionResult` implements the existing provider interface, deriving criterion IDs from supplied rubric only and returning explicit insufficient-evidence responses; it never reads labels.

- [ ] **Step 1 — Write failing tests.** `test_runner_invokes_real_assessment_service_and_ledger` checks all profile runs persisted criteria/invocations via `create_assessment_run` and `execute_assessment_job`, with shared input versions. `test_mock_is_labeled_not_model_quality` checks provider/model/embedding provenance and no quality claim. `test_gold_never_enters_provider_or_tools` spies on all provider messages/graph state/tool arguments and asserts an annotation-only sentinel is absent. `test_changed_snapshot_halts_before_next_tool_or_score` mutates the application generation during a scripted tool turn and expects stale-input failure with no persisted scores. `test_dataset_hash_change_stops_run` detects modified frozen input files before further requests. `test_interrupt_and_duplicate_journal_records_are_explicit` interrupts between combinations and verifies planned totals, no duplicates and no silent rerun. `test_cli_plan_and_report_never_call_provider` covers all subcommands and rejects unknown profiles, cases, provider, existing output directory and missing isolation context.
- [ ] **Step 2 — Run RED.** Isolated runner/CLI files.
- [ ] **Step 3 — Implement deterministic selection and execution.** CLI subcommands: `validate --dataset`; `plan --dataset --provider --profiles --split|--cases --max-cost-usd`; `run` with same selection flags plus `--output --embedding-mode real|scripted`; `report --input --output`. Default split development (also support public_test/all), profiles all, seed 20261008; provider explicit. `--split` and `--cases` are mutually exclusive. Live mode requires real embeddings; scripted mode is mock/test only. Provider mock uses model `mock` in the child process for zero-priced tests; live provider/model are actual configured DeepSeek values. Set isolated settings before importing cached application configuration; never edit `.env`.
- [ ] **Step 4 — Implement durable artifacts and stopping.** Create a new output directory exclusively, write manifest atomically, append/fsync records, retain owned ledger/invocation summaries before cleanup. Journal a sanitized admission record before each outbound request so interrupted calls remain uncertain, not free. SIGINT/TERM stops further calls and produces partial status; hard kill leaves journal/manifest sufficient to flag incomplete admission, without claiming reconciliation. Stop batch for auth/quota/model/server/ambiguous errors, changed actual model or violated bounds; deterministic schema/citation failures remain in results and may continue. Exit codes: 0 complete contract/run/report; 2 invalid input/preflight; 3 partial or failed experiment; 130 interruption. Reports can still be generated for partial runs. No automatic paid resume.
- [ ] **Step 5 — Run GREEN and wrapper smoke.** Through wrapper, execute three synthetic cases × four profiles with mock/scripted embeddings; assert twelve result combinations, durable manifest and no external calls. Existing report directories remain untouched unless `report` explicitly replaces generated report outputs atomically.
- [ ] **Step 6 — Commit.** `feat: run assessment benchmarks through the production pipeline`.

### Task 7: Offline metrics, paired comparisons and report safety

**Files:** Create `benchmark/metrics.py`, `reporting.py`; reuse existing evaluation metrics; add `tests/test_ai_benchmark_metrics.py`, `test_ai_benchmark_reporting.py`; CLI `report` integration.

**Interfaces:** Produce `evaluate_records(inputs: DatasetInputs, references: dict[str, CaseReference], manifest: RunManifest, records: list[RunRecord]) -> MetricsReport`, `paired_cluster_interval(pairs: list[tuple[str, float, float]], *, seed: int, samples: int = 1000) -> tuple[float, float] | None`, `write_reports(report: MetricsReport, output: Path) -> None`.

- [ ] **Step 1 — Write failing tests.** `test_null_conflicts_and_failures_do_not_inflate_agreement` asserts comparable numeric denominator, separate conflict/abstention statistics, null kappa for degenerate data and all failures in reliability totals. `test_recall_uses_ranked_pool_not_top_four_pack` pins span recall@5/@10 before packing, sufficient-group coverage after packing and full-text ranking unmeasured. `test_pairing_requires_same_case_and_cluster_bootstrap` checks overlap counts and seeded intervals without pretending unmatched cases are comparable. `test_report_rejects_duplicate_or_torn_records` rejects duplicate combinations and malformed JSONL with explicit incomplete-journal status rather than truncating silently. `test_html_escapes_candidate_and_error_strings` uses script/HTML markers and checks inert escaped output.
- [ ] **Step 2 — Run RED.** Isolated metric/report tests; run existing metric and offline benchmark tests as compatibility checks.
- [ ] **Step 3 — Implement metrics.** Reuse MAE/kappa primitives on numeric comparable pairs; calculate status/conflict agreement, false-zero/unsupported-score/correct-abstention denominators explicitly. Flatten ranked chunk spans with deduplication for span recall; sufficient-group coverage requires all spans in an alternative group. Capture initial vs final recovery, prevalidation rejection/normalization, scope violations, counterfactual complete pairs, p50/p95 and measured/held cost. Report all-planned and accepted-only statistics separately. Bootstrap paired profile deltas by `cluster_id`, 1000 resamples, seed recorded; unavailable or too-small comparisons are null/exploratory, never a global winner.
- [ ] **Step 4 — Implement static artifacts.** Output `metrics.json`, `report.md`, `report.html` using standard library and HTML escaping. Include provenance, n/coverage/errors, language/role tables, four-profile comparison, timing/cost and failure catalogue; queue time/invoice/unmeasured values are explicitly unavailable. No executable CV-derived script, external assets, API call or automatic claims of HR agreement. Same journal/manifest/labels regenerate equivalent aggregates; report creation timestamp may differ.
- [ ] **Step 5 — Run GREEN.** Numeric hand-calculated fixtures match expected metrics, XSS probes remain inert, and existing v2/Jev report tests pass unchanged.
- [ ] **Step 6 — Commit.** `feat: report paired RAG and agent benchmark results`.

### Task 8: Metadata-only LangSmith correlation and offline CI

**Files:** Modify `observability.py`, new benchmark recorder integration and `.github/workflows/ci.yml`; extend `test_langsmith_observability.py`; add `tests/test_ai_benchmark_tracing.py`, `test_ai_benchmark_real_embedding.py`.

**Interfaces:** Trace UUID `experiment_id`; fixed profile enum; case identifier exported as a SHA-256 value validated by regex, never arbitrary name text. Extend safe counters for normalization/rejected citations and cache tokens. Real embedding test requires `TALENTSCREEN_REAL_E5_SMOKE=1`; otherwise skipped with explicit reason.

- [ ] **Step 1 — Write failing tests.** `test_trace_allowlist_rejects_sensitive_and_secret_shaped_values` checks payload markers absent at every exported span. `test_langsmith_outage_does_not_change_assessment` compares persisted result with tracing failure vs tracing off. `test_real_e5_smoke_is_explicit_and_uses_actual_device` verifies true pinned model encoding/768-dimension normalized vectors, pgvector retrieval on three roles and observed device when explicitly enabled; default CI cannot download weights or call providers.
- [ ] **Step 2 — Run RED.** Isolated tracing tests with fake LangSmith client and model stubs; E5 test remains opt-in.
- [ ] **Step 3 — Implement correlation and CI.** Manual SDK spans only, automatic state tracing remains suppressed. Capture safe trace correlation IDs locally. CI sets mock, Jev off, generic retrieval baseline and cloud tracing/key off; run new offline contract/fault tests as part of the backend suite. Leave real weights/download/live provider out of push CI.
- [ ] **Step 4 — Run GREEN.** Secret/CV markers absent in captured exports; outage outcomes unchanged. Separately run `TALENTSCREEN_REAL_E5_SMOKE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 bash scripts/test_backend_isolated.sh services/backend/tests/test_ai_benchmark_real_embedding.py`. Missing cached weights are a reported prerequisite, not a successful semantic test; explicitly set up pinned embedding dependencies/cache before retrying.
- [ ] **Step 5 — Commit.** `feat: correlate benchmark traces and add offline regression coverage`.

### Task 9: Bounded live verification, regression and portfolio evidence

**Files:** Create `docs/evaluation/independent-human-evaluation-design.md` and a dated measured-result summary after actual execution; update README evaluation/architecture references. Save full run artifacts under ignored `reports/ai-benchmark/`.

**Interfaces:** Consume all prior tasks and frozen hashes. Publish only verified synthetic aggregates plus reproducible commands; live reports declare origin and actual scope.

- [ ] **Step 1 — Verify dataset and document smoke.** Run `validate`, twelve-document smoke and real-E5 smoke. Freeze inputs/references before live tuning. Confirm all core case/profile outputs share prompt and snapshot hashes as designed.
- [ ] **Step 2 — Plan the live scope.** Select `node-01,ai-01,android-01` before observing output; run `plan --provider deepseek --profiles all --cases node-01,ai-01,android-01 --max-cost-usd 5`. Check provider/model, current official price, bound proof and cached model availability without printing keys. If admission fails, save the preflight failure and continue regression/docs; do not run a narrower paid scope or raise the cap implicitly.
- [ ] **Step 3 — Execute the admitted probe.** `bash scripts/run_ai_benchmark_isolated.sh run --dataset fixtures/ai_benchmark/v1 --provider deepseek --profiles all --cases node-01,ai-01,android-01 --embedding-mode real --max-cost-usd 5 --output reports/ai-benchmark/live-probe-2026-10-08`. Actual execution date replaces the date suffix if later. Capture actual model/tool/token/latency/ledger evidence and metadata-only LangSmith correlation where configured. API rejection, unknown cost or invalid output is a recorded outcome, not a reason to substitute mock results.
- [ ] **Step 4 — Respect cumulative spend.** This task permits one initial live experiment with total USD 5. Do not start a second fresh USD-5 database after the probe and call it the same cap. Full 60 × four measurement is a subsequent explicitly budgeted experiment, undertaken only if the first probe is valid and its full preflight fits the authorized remaining/next budget. Code supports all 60 now; report whether that full live measurement was actually run. Never call a 12-combination probe a 240-combination benchmark.
- [ ] **Step 5 — Run regression and build.** `PRIVATE_STORAGE_ROOT=/tmp/talentscreen-ai-benchmark-regression bash scripts/test_backend_isolated.sh services/backend/tests`; `npm test` and `npm run build` in `apps/web`. Check no paid live tests were collected by generic pytest, no new migration is necessary, and existing HR UI/workflow remains unchanged. Resolve meaningful failures with new RED/GREEN tests.
- [ ] **Step 6 — Review the whole change.** Follow the approved execution method's review workflow; verify policy defaults, isolation, gold separation, raw-error metrics and financial uncertainty. Fix important findings before publishing claims.
- [ ] **Step 7 — Write verified portfolio evidence.** Describe E5 + pgvector, lexical/vector RRF, five-node LangGraph with two read-only tools, strict citation validation, experiment ledger and safe LangSmith tracing. Include commands, data origin, actual n/results, measured benefit or lack thereof, confidence limitations and failures. Label mock contracts/real-E5/live DeepSeek separately. Make an architecture diagram in repository Markdown; no HR automation claims or invented improvement percentages.
- [ ] **Step 8 — Commit and integrate.** `docs: publish reproducible AI benchmark evidence`; inspect staged diff for secrets/private artifacts and verify status. Preserve user preference for one coherent improved main version; push only verified changes under the existing authorization and execution environment.

## Final acceptance checklist

- [ ] Spec sections 1–5: actual service reuse, immutable policies/common prompt, dynamic multi-role fixtures and label separation — Tasks 1–4.
- [ ] Spec sections 6–7: owned isolation, no live fallback, CLI, partial status, request admission, cumulative cap and safe traces — Tasks 2, 5, 6, 8, 9.
- [ ] Spec section 8: ranked/packed/final evidence distinction, synthetic-reference metrics, honest denominators and paired intervals — Tasks 4 and 7.
- [ ] Spec section 9: versioned JSON/Markdown/HTML, regenerated aggregates, ignored private artifacts and README — Tasks 6, 7, 9.
- [ ] Spec section 10: fault/scope/snapshot/privacy/cost tests, real-E5 evidence, actual-or-explicitly-failed live probe, regression/build — Tasks 3–9.
- [ ] No tests or model-quality results are claimed before commands run and artifacts confirm them. Missing live evidence is stated in final status and README.
