# RAG and evidence packing comparison — 2026-10-09

V2 substantially improved evidence availability on frozen synthetic stress CVs. This measures retrieval, not model scoring accuracy or readiness to replace HR.

## Controlled comparison

- Clean source commit: `cc15360c69576a1e3099d199646cbfc871b0eea6` for both experiments.
- Frozen dataset: 60 cases, SHA-256 `3ce4710160259f8d8f2b2d75ef21ec7e07119add4d6cdc33eb4ebb92eee2d464`. Inputs, rubrics, reference labels and prompts were not edited.
- Four profiles × 60 cases × two retrieval versions = **480/480 accepted actual-service runs**. E5/pgvector/LangGraph/validator/ledger ran; LLM was mock.
- E5 revision `d128750597153bb5987e10b1c3493a34e5a4502a`, MPS, normalized 768d; no new weights downloaded.
- Same verified UTF-8 bound, 65,536 serialized bytes; 24,000 unique evidence characters; 4,096 output tokens; prompt assessment-v1.6.0 + assessment-agent.v1; seed 20261008; one repetition, concurrency one.
- V1 here uses the **new packing fix**, isolating retrieval differences. The old 235de65 baseline and intermediate development journals are retained locally with their original metadata.
- Configuration was selected using development results, then frozen before the final public comparison. The public fixtures were already visible and are **not an unseen/protected holdout**.

## Initial sufficient-group coverage

A criterion is covered only when every span in at least one annotated sufficient evidence group is delivered after packing. Criteria without annotated groups are excluded from this denominator. Full-text is source ordered and has no ranking metric.

| Split | Profile | V1 covered / denominator | V2 covered / denominator | V1 Span Recall@10 | V2 Span Recall@10 |
|---|---|---:|---:|---:|---:|
| development | full_text | 42/135 (31.1%) | 42/135 (31.1%) | Unmeasured | Unmeasured |
| development | dense | 12/135 (8.9%) | 111/135 (82.2%) | 5.2% | 99.6% |
| development | hybrid | 21/135 (15.6%) | 124/135 (91.9%) | 5.2% | 100.0% |
| development | hybrid_agent | 21/135 (15.6%) | 124/135 (91.9%) | 5.2% | 100.0% |
| public_test | full_text | 66/87 (75.9%) | 66/87 (75.9%) | Unmeasured | Unmeasured |
| public_test | dense | 18/87 (20.7%) | 82/87 (94.3%) | 16.1% | 100.0% |
| public_test | hybrid | 24/87 (27.6%) | 86/87 (98.9%) | 15.5% | 100.0% |
| public_test | hybrid_agent | 24/87 (27.6%) | 86/87 (98.9%) | 15.5% | 100.0% |
| all | full_text | 108/222 (48.6%) | 108/222 (48.6%) | Unmeasured | Unmeasured |
| all | dense | 30/222 (13.5%) | 193/222 (86.9%) | 9.5% | 99.8% |
| all | hybrid | 45/222 (20.3%) | 210/222 (94.6%) | 9.2% | 100.0% |
| all | hybrid_agent | 45/222 (20.3%) | 210/222 (94.6%) | 9.2% | 100.0% |

Span Recall@10 flattens/deduplicates the ranked pre-pack chunk pool and counts its first ten spans; it is not chunk recall or final sufficient-group coverage. Retrieving only one half of a contradiction is still an uncovered group. V2 does not achieve complete delivery for every criterion.

## Request and financial verification

| Retrieval version | Calls measured | Maximum serialized bytes | Maximum unique evidence characters | Requests evicting spans |
|---|---:|---:|---:|---:|
| v1 | 240 | 65527 | 23684 | 60 |
| v2 | 240 | 65527 | 20500 | 60 |

Both complete journals reconcile: zero estimated spend, zero held funds, zero unresolved admissions and no integrity errors. All 480 mock calls have zero token usage. Tool executions and repairs were zero in these benchmark runs; separate actual-graph regression tests exercise bounded tool expansion, echoed evidence removal and repair. Financial admission gates were not relaxed.

## Limits and interpretation

- Public fixtures and labels were already visible; not independent HR/IT labels or unseen holdout.
- Development was used to choose the bounded indexing/query changes; final public slice was measured after code freeze.
- One repetition and concurrency one; timings are exploratory, index reuse and setup affect them.
- Mock made zero tools; model quality, live agent recovery, hiring fairness and hiring readiness remain unmeasured.
- Exact-dedup plus claim chunks plus query ordering and search-pool breadth changed together; no separate attribution ablation.
- No paid request or real CV processing in this change.
- Exact repeated text is deduplicated within a section. Semantically similar but differently worded planning prose can still compete; no learned reranker or contribution classifier was added.
- Remaining misses require development-only analysis and a separately authorized live-model probe; synthetic labels cannot establish real hiring quality.
- Frontend, production DB, `.env`, provider and model configuration were not changed.

## Reproduce

Use [prerequisites and isolation](ai-benchmark-reproducibility.md), including the pinned tokenizer artifacts in ignored `reports/ai-benchmark-cache/`, and the clean source commit above. Never reuse an output directory.

```bash
bash scripts/run_ai_benchmark_isolated.sh run \
  --dataset fixtures/ai_benchmark/v2 --provider mock --embedding-mode real \
  --split all --retrieval-version v1 --output reports/ai-benchmark/new-fixed-v1
bash scripts/run_ai_benchmark_isolated.sh run \
  --dataset fixtures/ai_benchmark/v2 --provider mock --embedding-mode real \
  --split all --retrieval-version v2 --output reports/ai-benchmark/new-claim-v2
.venv/bin/python scripts/run_ai_benchmark.py report \
  --dataset fixtures/ai_benchmark/v2 --input reports/ai-benchmark/new-claim-v2 \
  --output reports/ai-benchmark/new-claim-v2/report
```

[Aggregate JSON, split denominators and provenance](rag-packing-results-2026-10-09.json) · [Algorithm versions and rollback](rag-pipeline-versions.md). Local ignored journals/logs retain complete run metadata; their hashes are recorded in the aggregate JSON.
