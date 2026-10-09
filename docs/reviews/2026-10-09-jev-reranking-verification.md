# Jev evidence reranking verification — 9 October 2026

## Scope

Reviewed implementation includes frozen opt-in policy, bounded pair classification/selection, provider-aware atomic admission, private resumable journal, additive migration, initial and agent-tool retrieval integration, explicit synthetic benchmark extension, and the minimal HR evidence-review notice. The five LangGraph nodes and HR decision ownership are unchanged.

## Verification

- Disposable PostgreSQL/pgvector regression; no application's database used. Current full suite: **506 passed, 1 opt-in real-E5 test skipped**, zero errors/failures. Cached real E5 was actually used in separate synthetic live experiments. Existing Starlette 413 deprecation warning remains.
- Frontend: 23 workflow/helper tests passed; Next.js production build compiled and typechecked all eight routes.
- Migration: populated legacy row survives downgrade/upgrade; new journal null for historical rows; deletion purges the run/journal.
- Admission/privacy: last-slot race, provider ceilings, held ambiguous usage, crash without journal, async rollback, resumed ordinal, transport drift, revoked scope, historical hash and authorized-only summary checks passed.
- Actual scripted graph integration exercised two multi-criterion retrieval tools and one repair inside ≤4 primary / ≤9 Jev / ≤13 total ceilings.
- Browser QA: disposable synthetic login → assessment → notice → approved redacted CV → mark all five criteria reviewed → HR request-information conclusion persisted. No console errors observed. At 390×844, 820×1180, and 1440×900, document width matched viewport; no horizontal overflow.

The omission count in browser QA was injected into a disposable synthetic journal to exercise the notice. It is not a model-quality measurement. The screenshot contains synthetic records only.

![Synthetic assessment evidence-review notice](jev-evidence-notice-2026-10-09.jpg)

## Live experiment and limitations

Jev actually served `typesafe/jev-1.13-20260917`; direct DeepSeek also ran. 21/22 assessment runs accepted plus one successful paid probe. Negative-group losses and one unknown provider outcome prevent activation. Off/enabled query comparison was confounded before the post-run fix, now covered by new regression tests. No paid retries after unresolved spend. See [full results](../evaluation/jev-reranking-results-2026-10-09.md).

Default remains off, gate remains internal synthetic-only, no deployment or running application database migration was performed. Real hiring accuracy, fairness, independent holdout, conflicting-evidence retention and production SLOs are not established.

## Independent whole-branch review

One fresh read-only reviewer examined `f33b7c9..6224f60`. No critical issue was found; four important findings entered one consolidated fix pass. Two initially minor findings were treated as important because they affect reproducibility and future CI.

- Full dense/lexical union supports up to 60 candidates per criterion, 12 criteria, without increasing eight judged pairs/criterion or call/body/journal bounds. Actual PostgreSQL tests exercise 12×31 and 12×60 pools.
- Allocation is pinned to the stage's first eight pairs **before** filtering cached judgments; unchanged completed-stage restart does not admit another paid tail. Partial-stage recovery and admission ordinals remain covered.
- An unscored initial stage uses the baseline top-30 section-diverse selection; unscored tool stages retain the baseline top four. The complete pool remains auditable.
- Exported metrics use `ai-benchmark-metrics.rerank.v1` only when enabled, preserving mode, provider kind, policy/hash, budget and separate model-quality interpretation in JSON, Markdown and HTML. Off reports keep their V1 schema.
- Focus ordering follows stable criterion order rather than Python set iteration. Hash-seed0 reproduces the old defect; post-fix seeds0 and1 agree.
- Offline financial fixtures derive current test dates; a future-clock test passes while a stale real financial policy still fails. No live freshness check was weakened.

Each fix has a test observed failing before the fix and passing afterwards. All four important findings and both regraded items were addressed in one pass; no second review was dispatched.

The reviewer set aside real-data quality/readiness, unknown-invoice resolution, and whether a held Jev call must also universally pause ordinary off-mode jobs. Rulings: maintain default off/synthetic-only gating; retain unresolved funds without replay pending external records; preserve legacy off admission behavior while held spend remains binding on the shared budget. The last choice allows legacy work only within remaining budget rather than imposing a new universal pause.

Final post-review full suite: **506 backend passed / 1 named opt-in E5 skip, 23 frontend passed, eight-route production build successful**. Raw live experiment outcomes were not rerun or relabeled.
