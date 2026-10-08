# AI benchmark implementation and final verification — 2026-10-09

## Scope and reviewed revisions

Implemented the approved [design](../superpowers/specs/2026-10-08-ai-evaluation-ablation-design.md) and [nine-task plan](../superpowers/plans/2026-10-08-ai-evaluation-ablation.md) sequentially in a project-local worktree. Base `b3086f7`; independent fresh-context review covered `b3086f7..3433dd3`; the single reviewed-findings fix pass is `661c0a5`. No second reviewer or additional paid experiment was used.

The benchmark calls the actual assessment creation/execution service, LangGraph, scoped retrieval, output validator, deterministic scorer and invocation ledger. It is a developer evaluation tool; HR workflow/UI defaults and decision authority remain unchanged. All benchmark inputs/approvals are explicitly synthetic fixtures, never independent human attestations.

## Independent review and verified fixes

No Critical finding. Six Important/P2 findings were confirmed by focused reproductions before changes. Thirteen new regression cases failed on the reviewed implementation, then passed after one fix pass:

| Finding | Verified behavior | Regression |
| --- | --- | --- |
| Raw score coercion | Boolean, numeric string and float anchors fail before scoring/persistence; raw schema errors stay counted | `test_raw_score_types_fail_at_provider_to_service_boundary`, 3 cases |
| Served-model drift | First reported identifier is pinned across all combinations, tool/repair calls; a change is journaled, holds uncertain funds and stops the batch | `test_alternating_served_models_stop_the_experiment`, 2 cases |
| Lost context-size evidence | Durable allowlisted original/delivered/excluded initial spans/characters and packing counters; zero-call context-limit outcome exported | `test_context_diagnostics_survive_disposable_database`, 2 cases |
| Contradictory completed reports | Missing result/admission evidence downgrades completion and prevents financial reconciliation; interrupted/running reports remain supported | `test_complete_manifest_requires_complete_journal_evidence`, 3 cases |
| Irrelevant valid citations | Annotation-complete citation precision and cited sufficient-group coverage are separate from delivered-pack availability and structural scope | `test_valid_but_irrelevant_citations_fail_annotated_support`; mock support remains unmeasured |
| Unexecuted retrieval counted as zero | Unmeasured evidence is null and excluded from quality denominators; measured-empty evidence is zero; failures remain in reliability totals | `test_unexecuted_retrieval_excluded_from_quality_denominators` |

There were no declined-to-judge items in this fresh review. The reviewer performed read-only reproductions, not paid provider experiments or a full regression rerun; the executor ran the regression gates below.

## Verification evidence

- Full backend: **417 passed, 1 opt-in real-E5 skip, 0 failed**, disposable PostgreSQL with all migrations applied. Existing Starlette HTTP413 deprecation warning remains.
- Focused fix gates: **17/17 runner/diagnostics** and **17/17 metrics/reporting** passed.
- Cached real E5 smoke separately passed: scoped pgvector retrieval for three roles, normalized 768d vectors, immutable revision `d128750597153bb5987e10b1c3493a34e5a4502a`, Apple GPU `mps:0`.
- Frontend: **22/22 passed**, Next.js production build passed before final review; the fix pass changes no frontend files.
- Document smoke: **6 PDFs + 6 DOCX**, all three roles/languages, through real intake/extraction/redaction.
- One live DeepSeek probe: **12/12 accepted**, 12 calls, 0 tools, 0 repairs, peak-rate estimate **USD0.02352500**, no held/unresolved funds. Direct DeepSeek `deepseek-flash`; no Jev/OpenRouter calls in this benchmark.
- Full real-E5/mock experiment: **240/240 accepted**, zero paid LLM calls; LLM quality unmeasured.
- Read-only remote LangSmith check confirmed **12/12 metadata-only roots**, empty inputs/outputs and experiment/profile correlation. The short-timeout SDK read initially failed; direct HTTP confirmation succeeded.
- Existing journals regenerated offline after review: all result/admission records present, no integrity errors, financial reconciliation true. Original journal files were preserved. Their context-size diagnostics predate the fix and remain **unmeasured**, not reconstructed.
- Diff whitespace check passed; changed-file secret-pattern scan found no real API-key pattern and no tracked `.env`.

Measured figures and their limits are in [the results](../evaluation/ai-benchmark-results-2026-10-09.md) and [aggregate JSON](../evaluation/ai-benchmark-results-2026-10-09.json). Synthetic anchor-0 live cases do not establish representative hiring accuracy; hybrid did not improve span ranking over dense here, and no live agent-recovery gain was measured. Independent representative labels and longer selective-retrieval cases remain future evidence requirements.

## Rulings I made

- Ruling: native worktree tool cannot select the required project-local path and this chat's cwd is a different directory; use git worktree add in the user's explicit project root — no current checkout/data touched; cost if wrong: app would run an old version until verified integration.
- Ruling: skill helper files lack executable bits; copy helpers into this plan's ignored workspace with executable permissions — preserves original skills and allows exact task-start/task-done behavior; cost if wrong: bookkeeping only, verified with the ledger.
- Task5 Ruling: thread the strict reservation object through optional executor/graph arguments, beyond the original Task5 file list — needed to enforce the planned budget on actual assessment requests; legacy default remains None; cost if wrong: a narrow internal argument change, covered by graph and adapter tests. Plan interface/file map updated.
- Task6 Ruling: plan report implementation depends on Task7; implement CLI report routing now and complete successful report tests in Task7 — keeps evaluator labels outside the runner — cost if wrong: report unavailable at intermediate Task6 commit only.
- Task8 Ruling: local .env uses mutable E5 revision main; resolve and pin the cached snapshot SHA only in the benchmark child, record setup/device and keep user config unchanged — reproducibility requires immutable weights — cost if wrong: missing cache rejects a real benchmark rather than silently downloading/changing weights.
- Task9 Ruling: execution skill places fresh whole-branch review after all task completion records, while Task9 lists it before final documentation — commit measured artifacts and finish regression first, then perform fresh review before main integration/push — cost if wrong: review occurs later, but still before publication.

## Deferred minors

- Final: minor (deferred): source-code revision and dirty state are absent from manifests; published experiment code is identified by the committed results/review record.
- Final: minor (deferred): CLI plan checks budget admission before live prerequisites; actual run still rejects invalid provider/cache/pricing configuration before calls.
