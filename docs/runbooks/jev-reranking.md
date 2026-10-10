# Optional Jev evidence reranking

Jev evaluates the relevance of a **CV passage to an approved rubric criterion** before the primary model reads its evidence pack. It does not produce applicant scores or hiring decisions. This is different from the older optional Jev secondary scoring shadow. The two modes cannot be enabled together.

## Execution

Approved redacted CV → pinned E5 + lexical retrieval → RRF pool → optional Jev pair judgments → bounded evidence pack → DeepSeek / bounded LangGraph agent → schema and exact-citation validation → deterministic scoring → HR review.

The same reranking service is used for initial retrieval and up to two agent retrieval stages. The five graph nodes remain `authorize`, `model`, `tools`, `validate`, and `repair`; Jev is a service inside retrieval rather than a new hiring agent.

| Mode | Behavior | Availability |
| --- | --- | --- |
| `off` | Existing RRF selection and packing | Default; historical snapshots also resolve to off |
| `shadow` | Record Jev judgments while preserving the baseline evidence pack | Explicit configuration after rate/model/egress checks |
| `rerank` | Reorder and select evidence using Jev judgments | Opt-in only after quality and latency gates |
| `gate_experiment` | Additionally exclude high-confidence unrelated passages | Internal synthetic sandbox execution policy only; not real applicant filtering |

Five passage categories: substantive evidence, skill mention only, limiting evidence, unrelated, unclear. Missing or unrelated evidence never becomes competency zero. Selection protects a labeled limiting passage and the highest-ranked unscored passage where available; an omission still requires HR review. These protections do not guarantee all negative or contradictory evidence reaches the final request.

## Configuration

Keep secrets in the untracked `.env`; never in scripts, fixtures, screenshots, or Git. Current verified model/rate facts are recorded in [provider bounds](../evaluation/jev-provider-bounds.json), with source URLs and date. Refresh the proof after seven days; reject an unrecognized served snapshot rather than silently trusting an alias change.

```dotenv
RAG_MODE=hybrid
RAG_PIPELINE_VERSION=v2
JEV_MODE=off
JEV_RERANK_MODE=off
JEV_MODEL=jev-1.13.0
JEV_BASE_URL=https://api.typesafe.ai/v1/systemone
JEV_API_KEY=<local-typesafe-key>
JEV_RERANK_ACCEPTED_MODELS=["jev-1.13.0"]
JEV_DATA_PROCESSING_APPROVED=true
JEV_INPUT_PRICE_PER_MILLION_USD=0.042
JEV_RATE_CARD_VERIFIED_AT=2026-10-09
```

Approval is a deployment-specific assertion about permitted data processing, not proof of applicant consent. Before choosing `shadow` or `rerank`, verify organizational approval, current bounds, matching embedding index, and the intended spend period. Restart API and worker together after configuration changes. A queued run uses its frozen policy, not a later mode change.

## Limits and billing

- The auditable dense/lexical union contains up to 60 candidates per criterion (720 for 12 criteria). At most eight judged pairs per criterion per stage and 20 questions per batch. Oversized pairs stay unscored; text is never silently truncated.
- State ≤16,384 UTF-8 bytes, full body ≤32,768 bytes. Primary context remains ≤65,536 bytes / 24,000 unique evidence characters.
- At most nine Jev and four primary calls per assessment, thirteen total, including failed/admitted calls. At most two tools and one repair.
- Jev request timeout 15 seconds, cumulative reranking allowance 60 seconds. This is a stop budget, not a promise of added p95 latency ≤5 seconds.
- Reserve-before-call uses a conservative 65,536 input-token financial allowance, separately from the provider's documented 64,000-token context. Output can report tokens even when the verified output price is zero.
- Unknown usage, transport ambiguity, or served-model drift retain the reservation and block more paid work. Do not mark such calls free or replay them. Reconcile against provider records using the admission ID/request hash; preserve the original record.

A crash after admission but before the ranking journal is committed fails with `RERANK_RECONCILIATION_REQUIRED`. Completed exact judgments can be reused only within the same run/source/rubric/configuration scope. There is no cross-candidate cache.

## Observation and privacy

A private run journal stores opaque pair/admission IDs, probabilities, policy digest, status, and durations, without passage text or prompts. It is size-bounded and follows assessment deletion. HR receives only a small evidence-review notice when applicable; probabilities and developer traces are not exposed. LangSmith gets allowlisted aggregate metadata only.

## Evaluation and activation

Use the [independent human-labeled evaluation protocol](../evaluation/independent-human-evaluation-design.md) before making any quality claim or considering activation. Synthetic fixtures and provider contract tests establish software behavior only. No current independent HR/IT quality result is available; keep Jev disabled for real applicant decisions until the approved evaluation and governance gates pass.

Activate reranking only when paired evaluation shows no new annotated limiting/conflicting evidence losses, improved coverage or equivalent coverage with meaningful cost/context reduction, added rerank p95 ≤5 seconds, and no unresolved funds. Passing schema validation alone is insufficient. Hard gating remains synthetic-only even if these conditions pass.

## Rollback

1. Pause new assessment scheduling; inspect running/admitted jobs and unresolved spend. Do not replay unknown calls.
2. Set `JEV_RERANK_MODE=off`, leaving legacy `JEV_MODE=off`; restart API and worker together.
3. Existing snapshots keep their frozen policy. Revoke/cancel affected pending work through normal workflow; create a fresh assessment with a new off snapshot if needed.
4. Keep additive migration `b6d12f84a901` and journals for diagnosis. Downgrade is a separate maintenance operation that removes this column; it is not needed for feature rollback.
5. Confirm new runs have baseline packing, no Jev admissions, normal HR access, and the expected period cap.
