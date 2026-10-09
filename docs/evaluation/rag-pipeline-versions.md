# Versioned retrieval and serialized evidence packing

The assessment service has two retrieval pipelines over the same immutable canonical CV spans and approved rubric. Pipeline selection is an internal configuration, not an HR-editable experiment flag.

| Property | `v1` | `v2` |
|---|---|---|
| Index suffix | `section-token-v1` | `span-evidence-v2` |
| Chunk unit | Adjacent spans within one source section, target 300 tokens | One source span/claim, exact repeated text deduplicated within the same source section |
| Maximum chunk | 480 tokens, lossless splitting | 480 tokens, lossless splitting |
| Query | Up to 4,000 characters, legacy ordering | Up to 800 characters; approved bilingual skill phrases first |
| Lexical vocabulary | At most 8 terms, length >2 | At most 16 terms, length >=2 (retains AI/ML) |
| Search pool | 10 candidates per channel | 30 candidates per channel |
| Fusion | RRF k=60 | RRF k=60 |
| Initial selection | Up to four section-diverse chunks per criterion | Same policy |

Both pipelines use the existing pinned multilingual E5 model, normalized 768-dimensional vectors, and `query: `/`passage: ` prefixes. There is no new reranker, model download, label-aware query, inferred contribution classifier or language penalty. A canonical span may contain multiple sentences; V2 does not claim to semantically separate every sentence. Exact deduplication keeps the earliest representative in a section; distinct negations, corrections and text in another section remain distinct.

## Configuration and replay

Defaults stay `RAG_MODE=full_text_baseline` and `RAG_PIPELINE_VERSION=v1`. To opt into the new retrieval for newly enqueued app runs, set `RAG_MODE=hybrid` and `RAG_PIPELINE_VERSION=v2`, then restart API and worker. No existing `.env` is modified by the implementation or benchmark. Switch the pipeline setting back to `v1` to roll back retrieval for new runs.

New run snapshots record `rag_pipeline_version`, the full model/revision/chunk configuration ID, and `request_packing_version`. Index rows for V1/V2 coexist; search filters by exact sanitized version and configuration ID. Unsupported explicit packing versions and changed embedding configuration fail before external execution. Older snapshots without these fields retain V1 retrieval. Legacy benchmark V1 policy serialization/hash omits the new default field; V2 explicitly declares it and receives a distinct policy hash.

`--retrieval-version v1|v2` controls the isolated benchmark's policies and manifest. Dataset version and retrieval version are independent: either algorithm can run on the same frozen dataset. Replaying the historical byte-packing implementation additionally requires its original Git commit; V1 here preserves retrieval, not every historical execution detail.

## Full serialized request bound

Before each graph model call—initial, after tools and repair—the fitter counts the complete compact JSON request encoded as UTF-8, including model parameters, system instructions, rubric, evidence IDs/maps, tool schemas, tool arguments and message history. The canonical accounting includes optional null fields and conservatively bounds the HTTP payload (which omits absent optional fields). A mock-transport test checks that relationship against the actual provider adapter.

The fitter enforces **65,536 bytes** and **24,000 unique evidence characters** without increasing the financial reservation or provider call limits. If necessary it drops whole lowest-priority spans from every evidence-bearing message and criterion map, and removes those IDs from the graph registry and validation scope. Quotes are never shortened. Newly resolved tool evidence has priority over old evidence. The assistant's tool-call prose is discarded while its call IDs/arguments remain; invalid output is not replayed in repair history. This avoids retaining removed evidence through unvalidated model echoes.

If rubric/system/protocol overhead alone cannot fit, execution stops with a fixed budget error before provider admission. Missing evidence stays unscored; neither retrieval nor packing permits invented citations or automatic hiring decisions. Existing full-text selection remains source ordered; byte-aware fitting does not search the full document for evidence it excluded earlier.

Diagnostics retain counts/bytes and initial/tools/repair phases, never raw quotes or model text. Optional telemetry failure must not change the assessment result. Tests cover actual graph tool expansion and repair, exact quote retention, oversized multilingual spans, fixed overhead rejection, index reuse/coexistence, SQL snapshot scoping and legacy policy compatibility.

## Evaluation limits

Develop on the frozen development split; freeze code before evaluating the public split. Public synthetic references are already visible and are not independent HR/IT judgments or protected holdout. E5 + mock measures retrieval availability and integration contracts; it cannot measure DeepSeek scoring accuracy, live agent recovery or real hiring fairness. Retain failed/partial experiments and identify dirty versus clean source provenance. No paid call, real applicant processing or production migration is necessary for this local comparison.
