# Synthetic DeepSeek assessment rehearsal — 2026-09-27

This is an engineering prompt and validator check on 30 fictional, hash-frozen Backend Python CV scenarios. It is **not** a real-candidate shadow run, an independent HR evaluation, or a G5 sign-off. The JD and rubric remain draft seed versions.

## Execution and provenance

- Runner: `scripts/run_synthetic_assessment_probe.py --all --cap-usd 1.00`.
- Private result: `private_storage/eval/synthetic_assessment_probe_20260926T180028Z.json` (ignored by Git; mode 0600). It contains output and source text only for the synthetic cases.
- One-line source cases: `fixtures/holdout_rehearsal/manifest.json`, 10 Vietnamese, 10 English, 10 mixed-language. The runner verifies each fixture's source hash before any call.
- Model: `deepseek-flash`, Chat Completions JSON mode, thinking disabled for the bounded scoring task. The app's `LLM_PROVIDER` was left at `mock`; this runner directly exercised the production prompt builder, DeepSeek adapter and output validator, but **not** the application database/job/budget workflow.
- Prompt version: `assessment-v1.1.0`; its system-prompt hash and rubric hash are in the private result. The initial version silently omitted list-shaped seed anchors; v1.1.0 sends all 0–4 anchors and JD source references, explicitly requires `rationale`, and treats CV text as untrusted.
- Rate model: conservative peak-price estimate using provider-reported tokens. This is not a DeepSeek invoice. The [official model/pricing page](https://api-docs.deepseek.com/quick_start/pricing/) lists the model and rates; the [thinking-mode guide](https://api-docs.deepseek.com/guides/thinking_mode/) describes the default thinking behavior and disable switch.

## Measured result

| Check | Result |
|---|---:|
| Synthetic cases sent | 30 / 30 |
| Valid six-criterion JSON with exact registered-span citations | 27 / 30 |
| Valid on first call | 24 |
| Valid after one bounded repair call | 3 |
| Failed after two calls | 3 |
| Reported input / output tokens across this batch | 277,243 / 33,197 |
| Peak-rate spend estimate for this batch | USD 0.12300930 |
| Pre-run two-attempt upper estimate / configured cap | USD 0.81153360 / USD 1.00 |

The separate first exploratory call with default thinking mode was truncated. Its provider billing is unknown, **not zero**. It is recorded in `private_storage/eval/synthetic_assessment_probe_20260926T175443Z.json`. After explicitly disabling thinking, a one-case trial passed on the first call. No real candidate data was sent in any of these probes.

The three failures are actionable:

1. `rehearsal_18`: the CV contains two contradictory claims in a **single** source span. The contract requires two distinct evidence items while also forbidding duplicate span IDs and partial quotes, so the truthful conflict cannot be represented. This is a schema/span-design defect, not merely bad model wording.
2. `rehearsal_21` and `rehearsal_28`: the model returned modified or partial evidence quotes after repair. The validator correctly rejected them as `QUOTE_MISMATCH`. Do not relax the exact-quote check; consider extracting citation text deterministically from validated span IDs or providing narrower canonical spans.

### Follow-up regression on the three known failures

The source-span builder now divides each non-empty paragraph at sentence boundaries while retaining exact offsets into the canonical text. This lets two contradictory claims on one CV line have distinct, verifiable span IDs and gives the model shorter verbatim quotes. The synthetic probe now calls that same production span builder. On `rehearsal_18`, `21`, and `28`, all three responses passed the unchanged schema and exact-quote validator on the first call. The result is in `private_storage/eval/synthetic_assessment_probe_20260926T182739Z.json`; conservative peak-rate estimate: USD 0.01002660. The test runner ran only hash-verified fictional CVs, and `LLM_PROVIDER` remains `mock`.

This is **regression testing on cases already inspected**, not a new holdout result. Valid JSON also does not imply a correct competency judgment: on `rehearsal_21`, the model marked Python backend, API design and SQL/data as insufficient despite concrete implementation claims. The simulated IT role assigned level 2 to all three. A real IT reviewer must adjudicate the anchor interpretation before any quality gate can pass. Existing stored sanitized versions retain their previous source spans; new versions use the revised builder.

## Comparison with the delegated role-play

The role-play file was recorded before these DeepSeek outputs, but it came from **one AI assistant acting in two roles**, not independent people. It is useful to locate disagreements, not to estimate hiring accuracy or AI–HR agreement.

Across the 27 valid cases there are 162 criterion cells. Both sides supplied a 0–4 anchor on only 35 cells; 24 of those anchors match exactly and conditional mean absolute difference is 0.343 points. There are 19 score/status differences in total, including seven cells the model marked unknown while the role-play assigned a score, and one cell the model scored while the role-play marked unknown. The other 119 jointly unknown cells dominate any naive overall agreement percentage, so no such percentage should be used as a quality claim.

Review examples:

- `rehearsal_11`: DeepSeek gave API design 4 from “kept the old API contract during rollout.” The CV does not state that the candidate designed a multi-client/version transition or checked edge cases. This appears to infer missing anchor requirements.
- `rehearsal_14`: DeepSeek described a bug as fixed although the CV only says it was reproduced, traced to a missing check, and covered by a regression test.
- `rehearsal_16` and `22`: DeepSeek treated a single negative/edge-case test as though normal behavior was also tested; the level-2 testing anchor requires both branches or a complete reproduce-fix-regression chain.
- `rehearsal_07` and `23`: the role-play assigned operations 3 and DeepSeek assigned 2. These cases need a human adjudicator to decide whether the described rollback and health check meet the anchor's failure/recovery verification requirement.
- `rehearsal_12`: DeepSeek assigned SQL 3 after a query and index were described; the role-play assigned 1 because no post-index result was stated. This is an anchor interpretation question, not a validated model error.

Do not tune the prompt on these 30 cases and report a rerun on the same file as untouched holdout performance. A new, separately frozen set is needed after structural fixes. Real G5 still requires actual-vacancy applications, independent HR/IT labels recorded before AI reveal, and source-level error adjudication.

## Engineering fixes made during this rehearsal

- Assessment prompt now transmits list- or dictionary-shaped anchors plus JD source quotes and fails closed if all five anchors are absent.
- JSON instructions now require every schema field; the assessment request explicitly disables DeepSeek thinking mode. The prompt version is stored in the assessment snapshot.
- Truncated/empty/malformed/refused provider responses are no longer treated as free in the application ledger. The error is raised **after** the transaction committing the unknown-cost state.
- New budget periods use configured development/pilot caps; sandbox calls reserve against the development scope.
- Pytest now requires an explicitly isolated DB URL. `make test-backend` creates, migrates, tests against and removes a disposable pgvector container. All 130 backend tests passed on that isolated database, and the container was removed.

The earlier adapter tests in this local checkout ran before the isolation guard was added and created 14 synthetic `LLM Test Requisition` records in the local application database. They were removed in one serializable transaction after checking the exact creation window, `test.pdf`/`dummy_key`, one application and one job per requisition, no candidate identities or decisions, no shared candidates, and no non-test budget reservations. The transaction deleted the 14 synthetic requisitions/applications/candidates/jobs and their single mock budget period. Read-only verification found zero remaining records in that window and zero remaining mock period. No candidate CV content was read for cleanup. Future `make test-backend` runs use the disposable database; the follow-up suite passed 131 backend tests.

G1 remains partial until account limits, billable usage and operating caps are reconciled. G4 remains partial: the three known contract failures pass on rerun, but scoring disagreements and the real-CV workflow still need resolution. G5 remains pending independent human data and real shadow.
