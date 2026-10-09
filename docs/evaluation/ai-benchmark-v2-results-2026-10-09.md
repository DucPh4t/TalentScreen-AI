# Benchmark v2: long-context retrieval stress diagnostic — 2026-10-09

The frozen collection exposed a serialized-request admission limit and substantial initial evidence misses. This is useful failure evidence for retrieval/packing work, **not proof of model scoring accuracy or readiness to replace HR**.

## Frozen inputs and scope

- Dataset: [synthetic v2 collection](../../fixtures/ai_benchmark/v2/README.md), 60 cases, three role families, 30 repetitive team-planning distractors per CV. The deliberately repetitive construction is adversarial and not representative of real CVs.
- Manifest SHA-256: `3ce4710160259f8d8f2b2d75ef21ec7e07119add4d6cdc33eb4ebb92eee2d464`. V1 is unchanged. All scores/statuses/sufficient quote groups were inherited from frozen v1 design expectations and relocated exactly.
- Selection declared before measurement: `v2-node-10,v2-node-13,v2-ai-10,v2-ai-13,v2-android-10,v2-android-13`; all four profiles, seed 20261008, one repetition, concurrency 1. These six cases test separated conflicts and buried evidence; the other 54 were **not measured**.
- Actual assessment service, LangGraph, pgvector and cached multilingual E5 ran. Revision `d128750597153bb5987e10b1c3493a34e5a4502a`, normalized 768d vectors, device `mps:0`. LLM was mock; cloud tracing disabled. No real CV or production database was used.
- Every experiment began from a clean committed source checkout. Git SHA/dirty state, prompt/schema/policy/input-bound metadata and invocation journals are retained in [aggregate JSON](ai-benchmark-v2-results-2026-10-09.json).

## First attempt: verified UTF-8 bound

Source commit `5b5df015705416c7c23ea32ff1449a171e0a6586`. The existing 65,536-byte serialized request limit admitted one hybrid-agent mock run, then the dense run failed before invocation; remaining 22 combinations were skipped. Result: **1 accepted / 1 failed / 22 skipped**, status partial. This failed attempt is preserved and not merged with the next experiment's metrics.

Offline reconstruction from the saved dense initial pack IDs and frozen canonical/role inputs produced **66,930 bytes** and `BENCHMARK_REQUEST_BYTE_LIMIT`. This is a reconstruction, not a captured raw request. A 24,000-character evidence limit does not guarantee a 65 KB JSON request: UTF-8, span IDs, rubric and criterion maps add overhead. The journal's minimized failure code is `PreconditionViolationError`; the reconstruction identifies the exact guard.

No live request admission, provider key validity or scoring quality was established. The financial journal reconciles with zero spend, zero held funds and zero unresolved admissions.

## Second attempt: zero-cost mock context diagnostic

Source commit `0bbc95247c7d1c220e9977605004690f47732523`. The same frozen cases, selection, evidence policy and prompt were used with the existing conservative `model_context` reservation bound. The pinned tokenizer proof cache was moved aside only in this isolated worktree, causing the existing CLI fallback; production code and the paid/live byte gate were not weakened. This explicitly different input-bound strategy is recorded in its manifest.

The mock context diagnostic completed **24/24 service runs**. It measures actual retrieval availability and pipeline contracts; it does **not** establish that these requests fit the live 65 KB gate. All 24 mock model calls report zero tokens/cost; no paid API request was made. Both journals have no integrity errors, no missing records, reconciled financial state and no unresolved funds.

| Profile | Accepted / planned | Initial sufficient-group coverage | Span Recall@10 | Size-truncated runs | Tool executions |
|---|---:|---:|---:|---:|---:|
| full_text | 6/6 | 12/30 (40.0%) | Unmeasured | 6 | 0 |
| dense | 6/6 | 0/30 (0.0%) | 0% | 0 | 0 |
| hybrid | 6/6 | 2/30 (6.7%) | 0% | 0 | 0 |
| hybrid_agent | 6/6 | 2/30 (6.7%) | 0% | 0 | 0 |

Group coverage requires **all spans in at least one annotated sufficient group** for a criterion. Each profile's denominator is 30 criteria across six cases. Span Recall@10 flattens/deduplicates the ranked pre-pack chunk pool and takes its first ten spans; it is not chunk Recall@10. Two groups can be delivered later in a pack while no relevant span appears in those first ten spans. Full-text has no ranking metric.

All six full-text runs were cut by the 24,000-character bound. RAG packs excluded relevant evidence through ranking/selection even when their character budget did not report size truncation. The keyword-rich planning paragraphs competed successfully with genuine contribution/correction spans in this stress setup.

Mock returned an insufficient-evidence contract response and made **zero tool calls**. Its null outputs do not count as human agreement, scoring accuracy, counterfactual fairness or agent recovery. Final coverage equals initial coverage; recovery effectiveness remains unmeasured. No confidence interval or generalization claim over real applicants is justified by this six-case diagnostic.

## Reproduce without paid calls

Use an isolated checkout and follow [prerequisites and isolation](ai-benchmark-reproducibility.md). Do not change the application's `.env` or remove its proof cache.

```bash
# Check the frozen data.
.venv/bin/python scripts/run_ai_benchmark.py validate --dataset fixtures/ai_benchmark/v2

# In a fresh worktree without reports/ai-benchmark-cache, mock planning uses
# the conservative model_context fallback. Inspect the JSON: provider=mock,
# model=mock, bound.strategy=model_context, admitted=true, total_upper_usd=0.
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python scripts/run_ai_benchmark.py plan \
  --dataset fixtures/ai_benchmark/v2 --provider mock --embedding-mode real \
  --profiles all --cases v2-node-10,v2-node-13,v2-ai-10,v2-ai-13,v2-android-10,v2-android-13 \
  --max-cost-usd 5

bash scripts/run_ai_benchmark_isolated.sh run \
  --dataset fixtures/ai_benchmark/v2 --provider mock --embedding-mode real \
  --profiles all --cases v2-node-10,v2-node-13,v2-ai-10,v2-ai-13,v2-android-10,v2-android-13 \
  --max-cost-usd 5 --output reports/ai-benchmark/new-v2-context-diagnostic

.venv/bin/python scripts/run_ai_benchmark.py report \
  --input reports/ai-benchmark/new-v2-context-diagnostic \
  --output reports/ai-benchmark/new-v2-context-diagnostic --dataset fixtures/ai_benchmark/v2
```

Replaying the first attempt additionally requires the pinned tokenizer proof artifacts in the isolated checkout's ignored cache. Expect a partial result until serialized-aware packing is improved. Changing to a paid provider requires a separate authorized/admitted experiment; neither mock result establishes that condition.

## Work identified by this historical diagnostic

Items 1–2 were subsequently implemented and measured in the [controlled packing/retrieval comparison](rag-packing-results-2026-10-09.md). This historical journal and its failures remain unchanged; items 3–4 remain unmeasured.

1. Make evidence packing aware of the complete serialized request budget, without relaxing financial or citation constraints.
2. Improve ranking on the development split through section/contribution-aware chunks, queries and optional reranking; keep current stress fixtures frozen. Separate public-test diagnostic reuse from any genuinely unseen holdout.
3. Run a separately authorized bounded live probe of missing-evidence cases to measure whether tools improve coverage and valid scoring. Mock tool counts cannot establish this benefit.
4. Obtain independent HR/IT labels and representative authorized CVs before claiming real hiring quality. Synthetic inherited labels cannot substitute for those judgments.
