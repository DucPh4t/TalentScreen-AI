# TalentScreen AI: production-pipeline evaluation and RAG/agent ablation

> Superseded as the benchmark corpus on 10 October 2026. The old v1/v2, standalone RAG and pairwise rerank fixtures were removed. The active software-regression set is `fixtures/ai_benchmark/synthetic_100_multi_role`; the Backend Python-only `golden_100` remains legacy. Its AI-authored references follow unapproved draft rubrics and are not HR/IT gold or hiring-quality evidence. Real quality evaluation still requires independent human labels.

- Date: 2026-10-08
- Design status: written spec approved by the user on 2026-10-08; implementation awaits plan review.
- Selected approach: B — a developer evaluation runner that exercises application services.
- Baseline: main at ca62f56.

## 1. Intent and boundaries

The user wants stronger, demonstrable AI Engineering work: actual RAG, bounded agents, measured quality and cost, and a reproducible explanation for recruiters. The deliverable is an evaluation subsystem with executable experiments and honest results. Adding another HR screen, or reporting fixture metrics as live model performance, would not meet that intent.

The existing application remains an advisory recruiting assistant. This work does not authorize automatic rejection, hiring, sending email, changing real recruitment data, or claiming equivalence to independent HR judgment. Use only newly authored synthetic CVs in a disposable database. Existing real CVs and Downloads are outside this experiment.

The core benchmark starts with an approved, sanitized CV and approved rubric and ends with the persisted assessment. A separate document-ingestion smoke test covers PDF/DOCX upload and extraction. Keep their denominators and timings separate.

### Alternatives considered

| Approach | Benefit | Trade-off |
| --- | --- | --- |
| A: extend the current offline metric scripts | Smallest change; fast report generation | Does not prove retrieval, model, tools or budget enforcement ran |
| **B: isolated runner using production services** | Measures actual pipeline behavior and supports controlled comparisons | Requires a narrow execution-policy seam and curated reference labels |
| C: add reranking, new agents or fine-tuning first | More potential research directions | More variables, cost and implementation before establishing a baseline |

B is selected. Establish a baseline before considering C.

## 2. Verified starting point

The backend already provides pgvector retrieval, multilingual E5 embeddings, source-span citations, a bounded LangGraph, output validation, deterministic scoring, budget reservations and metadata-only LangSmith traces. Reuse these components.

The current application graph contains `authorize`, `model`, `tools`, `validate` and `repair`. Allowed evidence tools are `retrieve_more_evidence` and `get_source_spans`. They read approved evidence within the application snapshot; they do not browse, send messages or make hiring decisions.

The former standalone RAG benchmark CLI and its dataset were retired. The active 100-case synthetic Backend Python set exercises the application pipeline for regression only; it does not establish hiring performance.

Local configuration was observed using the direct DeepSeek endpoint, model `deepseek-flash`, hybrid retrieval and `intfloat/multilingual-e5-base`. Preserve that configuration unless the user separately requests a provider change. Jev is disabled and is not a dependency of this work. Existing offline report contracts that mention Jev remain compatible.

## 3. Architecture and integration contract

Use five small components:

1. **Dataset loader:** validates synthetic inputs, labels, split membership and source references before any paid call.
2. **Isolated runner:** creates benchmark actors, requisitions, approved rubrics and sanitized versions; invokes the application assessment job; writes incremental results.
3. **Execution policy:** immutable internal configuration for evidence source and tool availability; supplies only the deliberate experimental differences.
4. **Evaluator:** joins recorded outputs to reference labels after execution, computes metrics, and retains failures.
5. **Reporter:** produces JSON, Markdown and standalone HTML, plus a publishable aggregate summary.

Data flow:

`synthetic input → approved snapshot → shared indexing/retrieval → assessment graph → production validator/scorer/ledger → recorded output → gold-label evaluator → reports`

Integrate with these existing boundaries:

- `app/services/assessment/service.py`: job creation/execution and snapshot checks.
- `app/services/retrieval.py` and `embedding.py`: shared query building, filtering, embeddings and context packing.
- `app/services/agent/assessment_graph.py` and `tools.py`: graph and evidence-tool execution.
- `app/services/assessment/prompt.py`: immutable prompt registration.
- `app/services/llm/orchestrator.py`, `ledger.py` and `cost.py`: outbound-call guards, reservation and settlement.
- `app/services/evaluation/metrics.py`: reusable metric primitives.
- `app/services/observability.py`: explicit trace metadata allowlist.

The runner must execute `execute_assessment_job`, including the graph, validators and ledger. Calling a provider directly and separately approximating application behavior is not acceptable.

Add an optional internal execution policy with production defaults preserved. Experimental profiles are not public API inputs, environment-wide production modes or HR controls. Do not add experimental database enum values solely to select a profile. Persist the effective policy in the existing run snapshot, without reinterpreting old snapshots. Extract shared logic only where the benchmark needs it; avoid unrelated application refactoring.

## 4. Four controlled profiles

| Profile | Initial evidence | Tools | Purpose |
| --- | --- | --- | --- |
| `full_text` | All approved CV spans, subject to the recorded input limit | Disabled | Full-CV baseline |
| `dense` | E5 cosine retrieval only | Disabled | Semantic retrieval baseline |
| `hybrid` | E5 + lexical retrieval, RRF fusion | Disabled | Measure lexical contribution |
| `hybrid_agent` | Identical initial hybrid pack | At most two executions | Measure additional evidence recovery |

All profiles use the same CV snapshot, JD, approved rubric, source-span IDs, actual provider/model, output schema, scoring rules, common prompt text, temperature and reasoning configuration. Pin chunking and embedding revisions. Record all effective values and hashes.

Use one common assessment prompt, registered immutably as an experiment-compatible version if required. Do not compare the existing full-text prompt v1.4 against hybrid v1.5 and attribute their differences solely to retrieval. Supply the same agent instructions; tool declarations and evidence packs are the intentional differences. For full text, every criterion's allowed evidence map includes all delivered CV spans.

Reuse query construction, scope filters, candidate limits, section diversity and packing for dense/hybrid. Dense switches off the lexical channel; it does not introduce a separate ranking implementation. Record pool sizes, selected chunk counts and truncation. Full-text truncation or an oversize guard is visible as a limitation/outcome, never silently dropped from the comparison.

Retain graph ceilings: normal model turns at most three, at most one repair, at most four outbound requests in total. Tools are optional: zero tool calls is a valid agent outcome. Preserve the ability to search when the initial hybrid evidence is empty; enforce existing snapshot/scope guards throughout.

Each case/profile combination receives a distinct run/job but references the same approved CV version. Randomize profile order per case with a recorded seed. Run with concurrency one on the MacBook Air; distinguish embedding warm-up/indexing from assessment execution. A first release uses one repetition per combination. It measures that run, not model variance across repeated sampling.

## 5. Dataset and reference labels

Author version `fixtures/ai_benchmark/v1` with **60 synthetic CVs**, twenty each for:

- `backend_node`: Node.js/NestJS backend intern.
- `ai_ml`: AI/ML intern.
- `android`: Android intern.

Use the repository's multi-role JD/rubric material as a starting point. Freeze one sample JD and rubric per family, with criterion-specific 0–4 anchors. These are sample vacancies, not vacancies approved by the school. The runner accepts dynamic criterion IDs and must not assume Backend Python criteria.

Target language coverage per role: seven Vietnamese, seven English, six mixed-language cases. Cover explicit anchor-level evidence, absent evidence, skills lists, team-only claims, partial evidence, contradictory statements, buried evidence and CV prompt injection. Include at least one two-case identity counterfactual pair per role, with unchanged competency evidence and changed synthetic identity attributes.

Split into **36 development / 24 public test cases**, twelve/eight per role. Preserve counterfactual pairs and any closely related variants in a single cluster/split. Every role/split contains all three language categories. Generate and freeze a seeded manifest before tuning. Public test data is a fixed reproducibility set, not a protected holdout; earlier exposure and any tuning on it must be disclosed. Independent HR-labeled holdout collection remains a separate future activity.

### Input and label contracts

The public input record contains `case_id`, `cluster_id`, `role_family`, `language`, `scenario_tags`, `split`, `cv_text`, and JD/rubric references. All personal information is invented. Reuse normal canonicalization, sanitization and source-span generation.

Gold records are separate files accessible only to the evaluator, not model messages, retrieval queries, graph state or tools. Each criterion label contains:

- Expected status exactly `assessed`, `insufficient_evidence` or `conflicting_evidence`, matching the application contract.
- Expected numeric score 0–4 for `assessed`; `null` for insufficient or conflicting evidence. Conflict labels require at least two contradictory supporting spans and an explicit clarification expectation.
- One or more alternative sufficient-evidence groups referencing exact canonical spans.
- A short annotation explanation and origin `design_expected`.

Resolve labels against shared canonical spans before execution. Every cited reference must exist and its exact text must match; reject inconsistent labels before API calls. Derive deterministic benchmark version IDs so span references are stable across profiles. Declare relevant span annotations complete for the curated criterion where retrieval precision is reported; otherwise precision is unmeasured.

Do not synthesize predictions from gold labels and call that model quality. Human review of synthetic labels can improve them, but AI-authored labels are not independent HR labels.

Generate **twelve document smoke fixtures**, six PDF and six DOCX, distributed across roles/languages, using twelve development cases. Exercise existing extraction/redaction and verify evidence preservation and PII removal. Scanned OCR and arbitrary PDF layouts are not comprehensively evaluated by these twelve fixtures.

## 6. Isolation, CLI and operating behavior

Provide `scripts/run_ai_benchmark.py` and an isolated PostgreSQL wrapper, with `validate`, `plan`, `run`, and `report` commands. The wrapper starts an owned disposable pgvector container on an ephemeral local port, migrates it, creates synthetic benchmark entities, and removes only its own container/storage on exit.

Never fall back to the application's `.env` database or storage. A run validates an isolation marker, expected benchmark database and private-storage scope before writes. Load provider credentials without printing them. Reading credentials does not authorize reusing the live application database.

The provider is explicit: `mock` for contract/failure tests or `deepseek` for real model measurements. A live run cannot silently fall back to mock. Mock output is reported as **model quality not measured**. Scripted embeddings and tools likewise carry explicit test-only provenance. Real retrieval results require the pinned E5 model and pgvector.

Example intended interface:

```sh
python scripts/run_ai_benchmark.py validate --dataset fixtures/ai_benchmark/v1
python scripts/run_ai_benchmark.py plan --dataset fixtures/ai_benchmark/v1 --provider deepseek --profiles all --split development --max-cost-usd 5
# Through the isolated wrapper:
python scripts/run_ai_benchmark.py run --dataset fixtures/ai_benchmark/v1 --provider mock --profiles all --split development --output reports/ai-benchmark/contracts
python scripts/run_ai_benchmark.py run --dataset fixtures/ai_benchmark/v1 --provider deepseek --profiles all --cases node-01,ai-01,android-01 --max-cost-usd 5 --output reports/ai-benchmark/live-probe
```

The exact command entry point is finalized in the implementation plan; the above flags and behavior are required. `plan` makes no model request. It validates current provider/model support, rate-card availability, local model availability and worst-case request reservations. Downloading an embedding model is explicit setup, not hidden inside a cost-only dry run.

Begin live verification with three development cases across all four profiles. Advance to the full dataset only after that probe is valid and the reservation plan fits the configured cap. Do not remove difficult cases based on observed scores. Any limited subset is selected before requests and recorded as a subset benchmark.

Write the result journal after each run and produce a partial report on interruption. Report complete/partial/failed status and planned/completed counts. First release has no automatic paid resume or automatic retry of ambiguous requests.

## 7. Cost, failures and traces

Propose a **USD 5 cumulative cap for the initial live experiment**, shared across roles and profiles. This is a design choice for user review, not evidence that all 240 assessments fit within USD 5. Existing application ledger safeguards remain active; an experiment-level reservation additionally prevents each requisition from independently consuming the entire cap.

Calculate conservative serialized-input and maximum-output allowances, including tool messages and repair turns. Do not treat the current characters-divided-by-three estimator as a proven token upper bound. If a defensible bound is unavailable, the live preflight fails. Check the supported provider's current official pricing and synchronize the versioned rate card before live execution. Cache discounts are not assumed in the reservation bound.

If the complete plan exceeds the cap, refuse before paid execution and report the affordable preselected scope. Never silently raise the cap or drop profiles. Record input/output/cache tokens from actual usage and distinguish estimated cost, reserved cost and invoice cost unavailable. An unknown provider outcome keeps its reservation and aborts the batch; it is not recorded as zero cost.

Stop the live batch for authentication/quota errors, provider-wide unavailability, isolation failure or ambiguous outbound outcomes. Determinate per-case schema, citation or model failures are recorded and may allow the next planned case while budget remains. Preserve production preconditions; do not weaken them to obtain a passing benchmark.

LangSmith stays a developer tool. Export only allowlisted experiment/profile IDs, versions, timings, counters and sanitized error codes. No CV/JD text, quotes, prompts, responses, tool arguments, keys or gold labels. Do not enable automatic graph-state export. Tracing is optional and tracing failure must not change assessment results. Local result records provide timing/counter evidence when cloud tracing is absent.

## 8. Metrics and interpretation

Every table includes its denominator, language/role breakdown and data origin. Separate the following:

| Area | Required measurements |
| --- | --- |
| Retrieval | Gold-span recall at 5/10 from the ranked candidate pool; sufficient-evidence coverage of the delivered pack; annotated precision where defined; scope violations |
| Agent contribution | Initial versus final evidence coverage; criteria recovered; actual tool/model calls; budget stops; net change against the same hybrid cases |
| Output contract | Accepted citation validity; pre-validation rejected citations/normalizations; schema failures; repair and terminal failure rates |
| Reference agreement | Score MAE and linear/quadratic weighted kappa where both scores are numeric; status agreement; correct abstention; false zero and unsupported-score rates |
| Counterfactuals | Pairwise score/status invariance after sanitization, reported per profile and complete pair |
| Performance/cost | Assessment latency p50/p95; indexing/warm-up separately; measured usage and estimated/reserved cost; costs of failures included |
| Completeness | Planned/attempted/accepted/failed/skipped counts and explicit partial-run status |

Gold evidence groups define sufficient support: all spans in at least one accepted group must be available. Compute recall at 5/10 before the top-four packing limit; never label four delivered chunks as a recall-at-ten experiment. Full text has pack coverage but no retrieval-ranking recall. Report final agent evidence separately from initial retrieval.

Numeric agreement metrics use only comparable numeric pairs and report the eligible fraction. Report conflict detection separately; a conflict is not an ordinary missing-evidence abstention. Never turn `null` into zero, omit abstentions from all quality statistics or interpret an undefined kappa as perfect agreement. Reference metrics indicate agreement with synthetic design labels, not HR agreement or demonstrated hiring accuracy.

Exact span validity is a structural guarantee. Semantic support is measured separately against annotated gold evidence; it is not established by a valid quote alone. Record raw rejected/normalized output counters so validators do not conceal model errors.

For profile comparisons, use paired case results and cluster bootstrap intervals with a recorded seed. Keep failures in reliability totals and show success-only versus all-planned denominators explicitly. Show the overlap count; do not choose a global winner from unequal coverage. A single run with sixty synthetic cases supports exploratory evidence, not broad statistical or hiring claims.

The synchronous runner does not measure queue delay. Document extraction smoke timing is distinct from assessment latency. Model/device telemetry records the observed CPU/MPS device; Mac GPU availability is not proof the embedding workload used it.

## 9. Artifacts and portfolio presentation

Each run directory contains:

- `manifest.json`: schema version, git revision/dirty state, dataset/label/JD/rubric/prompt hashes, embedding revision, execution policies, provider/model, seed, cap and selected cases.
- `results.jsonl`: sanitized case/profile outcomes, assessment records, citation IDs, stage durations, usage, reservations and trace identifiers.
- `metrics.json`, `report.md`, `report.html`: reproducible aggregates, paired comparisons and sanitized failure catalogue.

Report inputs are validated and versioned. The reporter supports regenerating aggregates without provider calls. Use a new versioned experiment contract; preserve compatibility with the existing offline benchmark's v2/Jev contract.

Keep run directories ignored by Git. Publish only reviewed synthetic/aggregate evidence under `docs/evaluation`, including commands, environment, limitations and actual results. Update README architecture and evaluation links after verification. Distinguish measured numbers, fixture demonstrations and future independent-HR evaluation. Do not invent improvement percentages.

No new HR tab, trace panel, chat copilot, model picker, reranker, fine-tuning, Jev cleanup, cloud deployment or real-candidate reprocessing is included.

## 10. Verification and acceptance

Implementation is acceptable when:

1. The four profiles run against the same valid dynamic rubrics and stable source snapshots, with common prompt/configuration hashes and only documented evidence/tool differences.
2. The isolation wrapper rejects live storage/DB configuration and cleans up only owned resources. No real recruitment records are modified.
3. Gold labels cannot enter retrieval, graph or provider inputs. Corpus/split validation rejects invalid spans, leaking clusters and invalid nullable scores.
4. Deterministic tests cover explicit tool execution, zero-tool completion, invalid citations, repair exhaustion, empty evidence, scope violations, changed snapshots, cost exhaustion, unknown outcomes and interruption reports.
5. Mock and scripted embedding tests are clearly test-only. A separate real-E5 smoke establishes indexing/retrieval behavior without claiming LLM quality.
6. The live probe either yields recorded real-provider outcomes or an explicit failed/blocked report. A real comparison is published only after the selected scope has actually executed; no fixture substitute is allowed.
7. The report includes all planned outcomes, comparable numeric coverage, paired comparison coverage, null/undefined values and failed-request cost handling. Rebuilding it produces equivalent aggregates.
8. Trace/export tests prove sensitive payloads and credentials are excluded. Trace availability does not affect business results.
9. Existing backend/frontend checks and build pass after the integration changes. CI runs offline contract/fault tests without paid calls; full semantic and live runs remain explicit developer commands.
10. README and a short reproducibility guide explain what was measured and how to repeat it. AI score support remains advisory.

There is no preset quality percentage required for a favorable portfolio claim. A technically correct experiment that exposes poor agent benefit is useful evidence. Decide subsequent retrieval/agent changes from measured failure analysis, not by tuning public-test labels until they match outputs.

## 11. Handoff after written-spec approval

Create a separate implementation plan covering dataset/contracts, isolation, the shared policy seam, runner/ledger integration, metrics/reporting, traces, regression tests, real-E5 verification and bounded live verification. Estimate those tasks before execution. The plan must preserve the current HR workflow and identify the technical evidence required before documenting completion.
