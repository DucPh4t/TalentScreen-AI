# Benchmark v2 verification — 2026-10-09

Scope: approved roadmap steps 1–2, extending the existing benchmark. No UI, migration, dependency, live-provider or production-data change. Retrieval tuning/reranking and the portfolio demo remain future work.

## Changes and evidence

- Source provenance: real Git SHA, dirty flag and explicit unavailable state; metadata only, no paths/remotes/filenames. Inherited Git redirects are removed; optional index writes disabled; raw status bytes are not decoded.
- CLI `plan`/`run` share route, key presence, pricing freshness, model, embedding mode and pinned local-cache checks. No provider/database/network construction during planning. Successful planning does not attest API key validity or live request fit.
- Frozen v2: 60 synthetic long-context cases, three roles, same v1 design expectations, exact relocated citations and disjoint IDs. V1 manifest remains unchanged. New hash `3ce4710160259f8d8f2b2d75ef21ec7e07119add4d6cdc33eb4ebb92eee2d464`.
- Test-first evidence retained locally: initial prerequisite/provenance and absent-dataset failures, context separation/test expectation corrections before any ranking measurement, inherited Git redirection failure, raw filename decoding failure, then passing tests.
- Final full backend regression: **430 passed / 1 opt-in real-E5 skip**, exit 0, disposable PostgreSQL with migrations. Log SHA-256: `6792865f9be4351eb5a21e0c2c9e17ce8dd947c057d8cbc745a6c62d089a12d2`. The earlier full run was 429 passed before adding the raw-filename regression; the final related focused run passed 14 tests.
- Real E5 was exercised separately by the actual-service diagnostic: cached immutable revision, MPS, normalized 768d. The first verified-byte-bound attempt was partial (1 accepted, 1 failed, 22 skipped); the second zero-cost mock context diagnostic completed 24/24. Both journals reconciled, no held or uncertain funds, no missing records/integrity errors.
- **No paid API calls in this change.** Mock model accuracy and agent recovery remain unmeasured; zero tool executions are not a benefit claim. Six cases are not a full-60 or real-CV quality result.
- Frontend untouched; no new frontend build claim. Previous frontend verification is historical.

## Fresh code review

One read-only final reviewer checked the whole implementation/data diff against steps 1–2. No Critical/Important findings. One Minor raw Git filename decoding issue was reproduced with actual invalid-byte subprocess output, fixed at `0bbc952`, retested and confirmed by the same reviewer. Reviewer independently confirmed v1→v2 labels, quote groups, identity pairs and authoring hashes; retrieval journals/results were verified by the executor rather than independently by that reviewer.

## Material findings requiring next work

The reconstructed dense request exceeded the 65,536-byte bound despite its evidence character budget. Initial sufficient-group coverage was 0/30 dense, 2/30 hybrid and 12/30 truncated full-text in the mock context diagnostic. The current long-context stress results support improving serialized-aware packing and ranking, **not a real hiring readiness or HR replacement claim**.

See [results and reproducibility](../evaluation/ai-benchmark-v2-results-2026-10-09.md). Ignored logs/journals are preserved in the primary checkout before worktree cleanup; hashes and aggregate metrics are versioned.
