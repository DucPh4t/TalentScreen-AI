# Jev evidence reranking — 9 October 2026

**Activation recommendation: keep `JEV_RERANK_MODE=off`.** The implementation is optional; this experiment does not meet the activation gates. Jev and DeepSeek were actually called. No real CVs or hiring decisions were used.

## Recorded experiment

- Paid contract probe: one call, served `typesafe/jev-1.13-20260917`, 831 input / 120 output tokens; estimated cost USD 0.00003490. Clean product SHA `e739d8b`.
- Paired arm implementation SHA `2db463c` (clean at launch), frozen V2 dataset hash `3ce4710160259f8d8f2b2d75ef21ec7e07119add4d6cdc33eb4ebb92eee2d464`; cached real E5 and actual PostgreSQL/pgvector.
- Jev endpoint `https://openrouter.ai/api/alpha/decisions`, requested `typesafe/jev-1.13`, served `typesafe/jev-1.13-20260917`. Primary direct DeepSeek endpoint, requested `deepseek-flash`; no OpenRouter primary-route comparison.
- Probe + seven preselected arms admitted at a conservative combined USD **0.93585370** upper bound within a USD 1 cap. An earlier fractional-cap preflight failed before HTTP; corrected with a regression test. The paid probe was reused, not repeated.
- Mock-primary arms: Node.js, AI/ML, Android cases `v2-node-01,v2-ai-01,v2-android-01`, each with `hybrid` and `hybrid_agent`. Live-primary arms: the same Node.js case with `hybrid`, four modes. These selected cases contain explicit limiting statements, not representative strong-applicant CVs.

| Arm | Accepted / planned | Complete evidence groups | Jev p95 ms* | Settled peak estimate USD | Held USD |
| --- | ---: | ---: | ---: | ---: | ---: |
| mock-shadow | 6 / 6 | 18 / 30 | 4897.25 | 0.00626276 | 0E-8 |
| mock-rerank | 6 / 6 | 24 / 30 | 4436.0 | 0.00625870 | 0E-8 |
| mock-gate_experiment | 6 / 6 | 26 / 30 | 4024.75 | 0.00626230 | 0E-8 |
| deepseek-off | 1 / 1 | 3 / 5 | unmeasured | 0.00229468 | 0E-8 |
| deepseek-shadow | 1 / 1 | 3 / 5 | 3865.0 | 0.00255821 | 0E-8 |
| deepseek-rerank | 1 / 1 | 5 / 5 | 4176.0 | 0.00285693 | 0E-8 |
| deepseek-gate_experiment | 0 / 1 | 0 / 0 | unmeasured | 0.00028379 | 0.00275251 |

*Stage elapsed time over completed assessments; the one-case live-primary values are single observations, not stable production p95 estimates. Embedding setup is excluded. All completed arms used zero model-requested tools; the separate scripted integration test exercises two retrieval tools and one repair.

## What the evidence establishes

21/22 assessment runs were accepted, plus the successful paid probe. The final live-primary gate arm stopped before a DeepSeek call: the second Jev admission had an unknown provider outcome (`JEV_RERANK_FAILED` at application level). Its USD 0.00275251 reservation remains held; no replay, retry, or free-cost assumption was made. Settled peak estimates across all arms and probe: **USD 0.02681227**; total held: **USD 0.00275251**. These are rate-card/usage estimates, not an invoice. Invocation and admission artifacts preserve the unresolved request ID/hash for reconciliation.

Compared with the matching shadow pool, mock-primary rerank increased total limiting-group delivery from 18/30 to 24/30, but lost previously delivered Node.js negative evidence for `backend_implementation` and `security` in both profiles (four criterion/profile losses). Gate delivered 26/30 but also lost two previously delivered negative groups. Higher aggregate recall does not justify these losses. One stage reported an omitted limiting passage.

The live DeepSeek rerank arm delivered 5/5 reference groups versus shadow 3/5 on its single Node.js case. This small result does not establish general improvement, and mock/live Jev responses differ across separate requests. There were **no annotated conflicting groups in the selected slice**; contradictory retention and general positive-applicant quality remain unmeasured. Pair-fixture independent NDCG remains null.

## Comparison defect discovered and fixed

The live experiment exposed different initial anchor-query construction for off versus enabled reranking. Enabled retrieval omitted disqualifying anchor text and changed phrase order. Also, a supplied full pool in shadow could include a section beyond the baseline top-30 scope. Both defects now have failing-then-passing integration tests: `test_initial_rerank_pool_uses_identical_baseline_anchor_query` and `test_shadow_supplied_full_pool_keeps_baseline_top30_scope`.

Consequently, **the recorded off/enabled comparison is confounded** and is not a valid causal estimate of Jev benefit. Shadow/rerank mock arms shared ranked pools, so their observed negative-group losses remain a useful warning, not an activation certificate. The corrected implementation has not been paid-rerun: unresolved funds require stopping further paid experimentation. Original outcomes and labels are preserved, without changing references after seeing results.

## Release gate

| Requirement | Result |
| --- | --- |
| No new annotated limiting/conflict losses | Failed: negative losses observed; conflicts unmeasured |
| Improved/equal coverage with meaningful cost/context gain | Inconclusive: single live case and off/enabled query confound |
| Added Jev p95 ≤5s | Exploratory completed-stage values below 5s; insufficient production sample |
| No unresolved funds | Failed: one held admission |
| Representative independent HR/IT holdout | Not available in this experiment |

**Default remains off; hard gate stays internal synthetic-only.** Do not replace HR assessment or enable automatic hiring actions. Next paid evaluation must first reconcile the unknown invocation, then use identical post-fix pools with positive, limiting, and contradictory cases and independently reviewed references. The current branch has a tested implementation, not a measured production-quality reranker.

## Evidence location

Local private artifacts remain ignored under `reports/ai-benchmark/`: `jev-contract-probe-20261009`, `jev-live-suite-20261009` (first no-I/O failure), `jev-live-suite-resumed-20261009` (allocations and release-analysis), and the seven `jev-live-<provider>-<mode>-20261009` directories. They contain metadata/IDs, not a tracked raw CV corpus. Scripted smoke: 6/6; cached-real-E5 + scripted Jev smoke: 1/1, both zero-cost and quality unmeasured.

[Runbook and rollback](../runbooks/jev-reranking.md) · [Reproduction protocol](ai-benchmark-reproducibility.md) · [Provider proof](jev-provider-bounds.json)
