# Measured AI benchmark — 2026-10-09

This release adds a developer benchmark that calls the application's actual assessment services. It measures retrieval, model observations, safety failures, timing and ledger cost separately. It does not authorize autonomous hiring.

## Executed scope

| Experiment | Scope | Observed outcome |
| --- | --- | --- |
| Pipeline contract smoke | 3 synthetic CVs × 4 profiles; mock LLM + scripted embeddings | 12/12 completed; no external model calls |
| Document ingestion | 6 generated PDFs + 6 DOCX, three roles/languages | 12/12 passed actual intake/extraction/redaction; technical evidence preserved |
| Real E5 smoke | Cached immutable E5 weights + scoped pgvector over three roles | Passed on Apple GPU `mps:0`; normalized 768d vectors |
| Offline real retrieval | All 60 synthetic CVs × 4 profiles; real E5 + mock LLM | 240/240 accepted service runs; **LLM quality unmeasured** |
| Live DeepSeek probe | Predetermined `node-01,ai-01,android-01` × 4 profiles; real E5 + DeepSeek | 12/12 accepted; 12 model calls; 0 tools; 0 repairs |

The live provider was direct `api.deepseek.com`, requested/reported model `deepseek-flash`. No Jev or OpenRouter call was made. E5 revision: `d128750597153bb5987e10b1c3493a34e5a4502a`; dataset manifest SHA-256: `55bc89a5c94022b7312a1dd56703a215ac1974f873cf177d5e4a6b3f9b62515a`.

Each case's four runs used the same input versions, neutral prompt/schema and scoring policy. The order was shuffled with seed 20261008; one repetition, concurrency 1. The full 240-combination **live** experiment was not run: its conservative admission bound exceeds the authorized USD5 cap. No second paid experiment was started.

## Live model results: integration probe only

| Profile | Accepted/planned | Comparable numeric anchors | MAE | Status agreement | Kappa | Tools | Peak-rate cost estimate USD |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| full_text | 3/3 | 15 | 0 | 100% | unavailable | 0 | 0.00336810 |
| dense | 3/3 | 15 | 0 | 100% | unavailable | 0 | 0.00640146 |
| hybrid | 3/3 | 15 | 0 | 100% | unavailable | 0 | 0.00488898 |
| hybrid_agent | 3/3 | 15 | 0 | 100% | unavailable | 0 | 0.00886646 |

All three predetermined cases describe explicit unsuccessful tasks and have design-expected anchor 0. Correct zeros in this probe **do not measure** how well the model distinguishes missing information, conflicts or higher anchors. Kappa and paired confidence intervals are null for degenerate outcomes; these are 15 repeated rubric observations per profile from **three cases**, not 60 independent applicants. The zero-tool result provides no live evidence-recovery benefit.

Reported usage: 75,182 input tokens, 11,032 output tokens, 41,728 cached input tokens. Settled peak-rate estimate: **USD 0.02352500**; held funds: **USD 0**, unresolved invocations: **0**. Provider invoice is unavailable; off-peak billing may differ. Preflight maximum for the permitted probe was USD 1.23863040, within the shared USD5 period cap.

Measured total-time medians for full_text/dense/hybrid/hybrid_agent were approximately 3.40/3.29/3.50/4.02 seconds. E5 setup was recorded separately (about 8.72 seconds). Cache effects, warm indexing and n=3 prevent a stable performance comparison; these are observations of this run.

## Real retrieval over 60 synthetic CVs

| Profile | Labeled evidence criteria | Span Recall@5 | Span Recall@10 | Initial sufficient-group coverage |
| --- | ---: | ---: | ---: | ---: |
| full_text | 222 | unmeasured | unmeasured | 100% |
| dense | 222 | 19.14% | 59.46% | 100% |
| hybrid | 222 | 16.44% | 54.95% | 100% |
| hybrid_agent | 222 | 16.44% | 54.95% | 100% |

The mock LLM returns explicit insufficient-evidence observations, so its MAE/status accuracy/fairness are unmeasured. These retrieval figures use actual E5 vectors and PostgreSQL searches, joined to authored evidence groups offline.

Span Recall@k flattens ranked chunk span IDs before cutting off at k; it is not chunk Recall@k. Many short CVs fit in a small number of chunks. A relevant span can appear after the first 10 IDs while still reaching the prompt. This explains the lower span recall alongside complete packed-group coverage.

Hybrid did **not** outperform dense on this dataset's span ranking. All profiles delivered the sufficient groups; the data does not establish a selective-retrieval or tool-recovery advantage. No improvement percentage or global winner is claimed. A future version should include longer CVs with more than four competing project chunks per criterion and independently adjudicated labels; freeze it before tuning.

## Post-review report reconciliation

The evaluator was rerun **offline on the original journals**, without further paid calls. All 12 live and 240 offline combinations have complete result/admission journals, no integrity errors, and reconciled peak-rate estimates. Annotated citation precision and cited sufficient-group coverage are 15/15 per live profile for these three anchor-0 cases; this is authored-reference support, not independently adjudicated semantic accuracy. Mock citation quality remains unmeasured.

These original runs predate durable context-size instrumentation. Their context/truncation measurements are explicitly **unmeasured**; they were not reconstructed after database cleanup. New service regressions verify partial truncation and a zero-call context-limit outcome. A later experiment must collect these fields before making context-coverage claims.

## Safety, trace and validation evidence

Regression covers immutable policies/legacy prompts, source/criterion scope, stale snapshots, gold separation, unknown spend, usage bounds, missing/zero/cache usage, duplicate/torn journals, interrupted runs, evaluator denominators, paired clusters, escaping and tracing outages. Synthetic approvals are explicitly machine-authored fixtures, never independent HR attestations.

LangSmith received metadata-only trace roots for the live probe. Cloud verification uses read-only HTTP and checks empty inputs/outputs plus experiment/profile correlation. The short-timeout SDK read initially failed; this did not affect assessments. Exact confirmed counts are in the aggregate JSON.

Frontend: **22/22 tests passed**, production Next.js build passed. No HR UI screen or public experimental profile selector was added. **417 backend tests passed**; one real-E5 test is opt-in and its separate smoke passed. Backend regression and default-off real-E5 collection were verified in disposable PostgreSQL; CI clears provider/trace keys and never downloads weights or calls a paid model. No migration is required by this benchmark.

## Limits and next evidence

Labels are synthetic design expectations authored with templates, not independent HR/IT labels. The public-test split is visible, not protected holdout. The paid probe contains only anchor-0 cases, and one run does not measure model variance. None of these numbers proves hiring accuracy, production fairness or readiness to replace HR.

The next quality experiment should evaluate representative roles/anchors, insufficient and conflicting evidence on a protected independently labeled set, with a separately approved cumulative budget. Investigate chunk/span ranking and longer-context cases before claiming hybrid or agent benefits. Preserve failures, annotation disagreement and unmeasured values.

[Reproduction commands and metric definitions](ai-benchmark-reproducibility.md) · [Machine-readable verified aggregates](ai-benchmark-results-2026-10-09.json)
