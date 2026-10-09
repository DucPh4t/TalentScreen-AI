# TalentScreen AI: Jev evidence reranking and conservative gating

- **Date:** 2026-10-09
- **Baseline:** `190bf7d` on `main`
- **Status:** User approved the direction; this written specification awaits review.
- **Audience:** Product owner and implementation agent.
- **Authorization boundary:** This is a design artifact. Product implementation follows written-spec approval and review of a separate implementation plan.

## 1. Intended outcome

Improve the evidence supplied to DeepSeek when assessing an approved, redacted CV against a user-defined, approved rubric. Jev evaluates retrieved passages for usefulness; it does not select applicants, replace HR, calculate hiring scores, or generate explanations. Demonstrate the effect through reproducible retrieval and live-model experiments, including failures and cost.

The product remains a focused HR workspace without Copilot chat or an HR-facing developer trace panel. Support Vietnamese, English, mixed-language CVs and dynamic 2–12-criterion rubrics. Preserve immutable citations, nullable observations, authenticated human decisions and privacy controls.

## 2. Existing implementation and integration points

The baseline already has real E5/pgvector retrieval, lexical/vector RRF, V1/V2 index isolation, five LangGraph nodes, two scoped tools, complete request fitting, invocation ledgers and synthetic benchmarks. Hybrid V2 delivered 210/222 sufficient evidence groups in the recorded mock-LLM stress experiment. That is retrieval availability, not live scoring accuracy.

Relevant boundaries:

| Current code | Required extension |
|---|---|
| `services/backend/app/services/retrieval.py` | Separate candidate collection from diversity/packing; optional reranking before selection. |
| `services/backend/app/services/assessment/service.py` | Freeze reranking policy at enqueue; invoke the stage with job/snapshot authorization and provenance. |
| `services/backend/app/services/agent/tools.py` | Apply the same run-scoped reranking policy to additional retrieval. |
| `services/backend/app/services/jev/provider.py` | Explicit purpose authorization, bound request serialization, validate model identity and answer consistency. |
| `services/backend/app/services/llm/orchestrator.py` | Provider/stage-aware call limits and cost reservation, without a ledger bypass. |
| `services/backend/app/services/assessment/policy.py` | Versioned experimental policies while preserving old policy hashes. |
| `services/backend/app/services/evaluation/benchmark/` | Jev provenance, separate provider measurements, reranking ablations and budget preflight. |

Current Jev is a secondary shadow scorer after the primary assessment. Its adapter and orchestrator accept Jev only with `JEV_MODE=shadow`. This integration must not pretend that the existing shadow scorer is a retrieval reranker.

The current run ceiling is four external invocations, counted across providers. Adding per-passage calls without changing that policy would exhaust the agent budget. A bounded multi-provider policy is therefore part of this design, not an incidental override.

## 3. Alternatives and selected approach

| Approach | Advantage | Trade-off |
|---|---|---|
| Rerank only | Smallest semantic change; no threshold-based exclusion. | Still may deliver irrelevant passages; requires measuring ordering and packing effects. |
| Rerank, then evaluate conservative gating **(selected)** | Can improve ordering first and test context reduction separately. | More evaluation work; a filter can discard necessary evidence. |
| Jev directly scores candidate competency | Reuses the existing secondary scoring path. | Does not solve evidence selection; mixes retrieval judgment with applicant assessment. |

Ship the selected approach in stages: `shadow` measurements, explicit `rerank` activation, then sandbox-only `gate_experiment`. Do not enable hard filtering on real applicants merely because schema tests pass. Default remains `off`.

## 4. Pipeline and module boundaries

```text
Approved CV + rubric snapshot
  -> scoped dense / lexical candidates
  -> RRF order and exact source validation
  -> bounded criterion–passage pairs
  -> Jev typed judgments through the invocation ledger
  -> validated, deterministic reranked selection
  -> section diversity and whole-span request packing
  -> DeepSeek / bounded LangGraph agent
  -> existing citation validator and deterministic scoring
  -> HR evidence review and human decision
```

The five graph node names remain unchanged. Initial reranking is an assessment preparation stage; follow-up reranking runs within the authorized retrieval tool. Both use one policy and one run-level budget. `get_source_spans` remains an exact-text lookup, without a Jev call.

Introduce a focused `services/reranking/` module with strict policy/decision contracts, prompt construction, batch planning, selection and service orchestration. It receives authorized candidates plus an approved criterion; it cannot query arbitrary records or write hiring outcomes. Provider HTTP handling remains in the Jev adapter. Pure selection logic must be testable without DB or model calls.

## 5. Jev question and selection contract

Use **one Choice question per criterion–passage pair**, referring explicitly to indexed `state.pairs[i]`. Question IDs are transport keys; meanings must be in the instruction/criteria rather than assumed from those keys.

Options:

- `substantive_evidence`: describes a concrete activity/result relevant to the criterion.
- `mention_only`: names a relevant skill/tool without concrete activity or outcome.
- `limiting_evidence`: explicitly states a relevant lack, limitation or negative observation.
- `unrelated`: does not contribute evidence about this criterion.
- `unclear`: interpretation requires context not supplied by this pair.

These are passage categories, not the 0–4 competency rubric and not hiring recommendations. A limiting passage is useful evidence. Cross-passage contradiction remains an assessment task; Jev cannot claim to detect all contradictions from isolated pairs.

Input includes only the approved criterion definition, relevant anchor descriptions and exact retrieved passage text, with opaque pair identifiers. No raw CV, contact details, candidate name, school prestige, other applicants, assessment score or hiring outcome is sent.

Validate exact answer-key and option membership, finite probabilities in [0,1], sum tolerance, choice consistency with the maximum probability (allow exact ties), and finite confidence. Reject malformed, additional, omitted or cross-pair answers. Reject model identity outside the policy's explicit accepted-version set. Return no generated explanation text from Jev.

Initial ranking policy `jev-evidence-ranking.v1`:

1. Utility = `P(substantive_evidence) + P(limiting_evidence) + 0.35 * P(mention_only) + 0.15 * P(unclear)`.
2. Sort descending utility, then descending original RRF score, then chunk index and chunk ID. This utility orders context; it is not a probability of candidate suitability.
3. Within the existing four-slot selection, reserve one slot for the highest-utility `limiting_evidence` passage whose category probability is >=0.50, and one for the highest-RRF unscored passage, when present. Deduplicate overlapping choices, then fill the remaining slots with section-diverse scored passages; use the unscored RRF tail only when scored candidates cannot fill them. Record limiting passages omitted by the cap; do not claim complete conflict delivery.
4. Keep all valid pairs in the auditable candidate pool. Unscored/oversized pairs have no fabricated probabilities and retain a recorded baseline rank. Never compare RRF and Jev utility numerically. If no pair was scored because of planning bounds, return the identical baseline selection with an explicit `not_scored_bound` status; a provider/contract failure follows the mode-specific failure rule instead.

The weights and 0.50 selection rule are proposed development settings, not validated thresholds. Freeze any changes before public evaluation. Evaluate neutral and negative evidence explicitly to avoid rewarding only positive CV statements.

## 6. Modes, bounds and failure semantics

Add `JEV_RERANK_MODE=off|shadow|rerank|gate_experiment`, default `off`. It is server configuration, not an arbitrary public API parameter.

- **Off:** current retrieval/agent behavior and four-call ceiling; no new Jev network call.
- **Shadow:** record judgments and hypothetical selection, but pass the original RRF context to DeepSeek. A reranker failure is recorded and does not alter the primary context. Security/stale-input failures still terminate the run.
- **Rerank:** use the validated ranking. A provider/contract failure terminates with a specific failure code; no silent switch to baseline or another provider.
- **Gate experiment:** sandbox-only reranking plus exclusion of `unrelated` passages when both its probability >=0.95 and confidence >=0.80. Retain `unclear` and limiting evidence. These development thresholds are immutable experiment inputs; they cannot activate real-data filtering without a further reviewed policy.

Empty selected evidence means “insufficient evidence in the retrieved context.” It does not mean the entire CV contains no evidence or the applicant lacks the skill. Where recovery is available, allow the existing bounded evidence tool before a final insufficient observation. Existing `null` and human clarification behavior remain authoritative.

Proposed hard bounds for enabled reranking:

| Resource | Limit |
|---|---:|
| Candidates sent to Jev per criterion per retrieval stage | 8 |
| Questions per physical Jev request | 20 |
| Jev state UTF-8 bytes per request | 16,384 |
| Complete serialized Jev request UTF-8 bytes | 32,768 |
| Jev physical calls, including failures/retries, per assessment | 9 |
| Primary DeepSeek physical calls per assessment | Existing ceiling, at most 4 |
| Assessment-wide physical calls with reranking enabled | At most 13 |
| Jev request timeout | 15 seconds |
| Aggregate reranking wall-time allowance | 60 seconds |
| Tool executions | Existing maximum 2 |
| DeepSeek serialized request / unique evidence characters | Existing 65,536 / 24,000 |

At the largest supported rubric, initial retrieval has at most 96 pairs (12×8), nominally five batches; each of two tools may add 32 pairs (4×8), nominally two batches each. Byte limits can require smaller batches. A pair that alone exceeds the byte cap is left unscored with its text untouched, rather than truncated. Before egress, plan a stable, round-robin allocation across criteria that fits the remaining byte/call/time allowance, prioritizing requested focus criteria without starving the others. Record unscored pairs and actual batch sizes. The nine-call cap is a ceiling, not a promise to score all 160 pairs.

When the aggregate deadline is reached, stop admitting new batches, record pending pairs as unscored, and fit each admitted request timeout to the remaining time. Use original RRF position for unscored pairs with an explicit `not_scored_bound` diagnostic and the slot policy in section 5; additional evidence may be requested. Never silently assign zero relevance or remove a pair solely because it did not fit the budget.

No hidden SDK retries or automatic duplicate network calls after timeouts. HTTP failures, invalid responses and uncertain billing consume the physical call allowance. Unknown outcomes keep the reservation held and block further paid admissions until reconciled. Enforce limits under DB serialization/locking so concurrent jobs/retries cannot exceed them.

Legacy `JEV_MODE=shadow` and enabled `JEV_RERANK_MODE` are mutually exclusive in the first release, preventing an unbudgeted extra scorer. Do not increase the current four-call limit for ordinary/off runs. All new limits are pinned per run, not read from changed global configuration mid-run.

## 7. Provider configuration, budget and egress

Reuse the existing server-side Jev key, processing-approval and verified-rate fields. Configuration validation must distinguish authorized purposes: reranking, secondary scoring, or neither. Enabling reranking requires `RAG_MODE=hybrid` and `RAG_PIPELINE_VERSION=v2`. Reject invalid combinations at startup/enqueue.

The current repo uses the OpenRouter System One compatibility endpoint. Official OpenRouter examples now document `https://openrouter.ai/api/alpha/decisions` for `typesafe/jev-1.13`. Add this exact HTTPS endpoint to the allowlist and verify a synthetic contract probe before live benchmarks. Retain the existing explicitly configured compatibility route for legacy tests; do not try a second route automatically after a potentially billed call. Direct TypeSafe remains an explicit alternate configuration, not a fallback.

Freeze requested model, accepted reported versions, endpoint identity, question/policy hash and rate-card provenance. An API model family name alone is not proof that the served snapshot is unchanged.

All Jev calls go through reserve-before-call and settlement. Correct the serialized-request accounting to cover the exact outbound Jev body (`model`, `state`, `questions`), not an OpenAI chat-envelope surrogate. Provider/step routing must not let rerank calls escape the ledger or satisfy a DeepSeek-only strict reservation contract.

Byte caps control request size, not a proven tokenizer bound. For live financial admission, use a separately verified Jev provider/context bound and verified pricing; reserve a conservative full-context allowance (65,536 input tokens per allowed Jev call) unless a tighter tokenizer bound is independently proved. Do not reuse the DeepSeek UTF-8 tokenizer proof for Jev. Published context descriptions differ by endpoint; verify the chosen endpoint's constraints before admitting live experiments. Missing token/cost data remains unknown, never zero.

Global/requisition budgets remain binding across both providers. The first live synthetic experiment has a proposed aggregate USD 1 cap, including all reserved worst-case calls; reduce its sample count if preflight cannot admit it. No paid probe or real-CV processing is performed while this design awaits approval.

Recheck current approved document/rubric/generation before and after each network batch. Deletion, approval revocation and version drift stop the run and prevent applying the result. Validate residual contacts before egress. Do not broaden raw-document grants or data-processing permissions.

## 8. Versioning, persistence, privacy and UX

Freeze a strict `reranking_policy` plus digest in the enqueue snapshot. Include mode, policy/prompt versions, candidate/batch limits, selection weights, thresholds, models, endpoint, accepted reported identities, financial bounds and call/time ceilings. A missing field on a historical run means `off`, preserving historical snapshot and execution-policy hashes. A malformed explicit new field fails before egress.

Add a nullable `AssessmentRun.rerank_output` JSONB field through an additive Alembic migration; existing rows remain null. Store only bounded run-scoped metadata: stage, criterion/chunk/span IDs, original/reranked positions, validated distributions/categories, selected/unscored IDs, payload/policy hashes, call counters, timing, model identity and safe error codes. No copied passage, prompt, query, contact data or provider error body. Bound record counts/size and treat this derived applicant data as private.

Reuse successful decisions within the same assessment when a tool retrieves the identical criterion/passage/policy combination. Recheck authorization before reuse. Do not introduce a global cross-applicant cache. Include passage/criterion hashes and source scope in reuse keys. Purge rerank outputs with the existing candidate/run deletion lifecycle and test that behavior.

Persist diagnostics before a job can repeat billed work; a crash after an unknown network outcome requires reconciliation rather than automatic replay. Local journals for real applicants remain private and outside Git; public reports use synthetic data only.

LangSmith exports only allowlisted aggregate counts, mode/version, timings, provider identity and safe outcome codes. No pair text, criterion text, query, probability vectors tied to candidate identity or raw output. Add `jev_rerank` and gate subspans under the existing developer trace; no new HR trace page.

HR sees the existing observations, evidence and missing-information flow. If evidence was omitted by a bound, provide a concise review notice without exposing internal Jev probabilities as applicant scores. Include applied retrieval mode in the existing assessment details/exportable metadata. Do not add a new navigation tab or dashboard just for this integration.

## 9. Evaluation design and activation criteria

Do not change frozen V1/V2 cases, reference labels or historical result files. Add a separate versioned pair-relevance fixture for substantive, mention-only, limiting, irrelevant and unclear passages. Cover VI/EN/mixed, diverse IT roles, short/long CVs, negation, split contradictions, misleading keyword lists, instructions embedded in CVs and absent evidence. Synthetic design labels remain labeled as such; independent HR/IT labels are separate future evidence.

Use a common pre-rerank candidate pool to isolate ranking effects, then run the full assessment service to measure packing and tool consequences. Keep rubric, embedding revision, primary prompts, output limits and dataset hashes identical between comparison arms. Maintain old four-profile reports and CLI compatibility; add a versioned experiment selector rather than rewriting historical contracts.

Comparison arms:

1. Hybrid V2 without Jev.
2. Hybrid V2 plus Jev shadow (verify primary-context identity).
3. Hybrid V2 plus Jev rerank.
4. Hybrid V2 plus Jev gate experiment, sandbox only.

Run no-tool and agent-enabled comparisons separately. Report whether Jev is scripted or live independently of whether DeepSeek is mock or live. A mocked primary can measure actual Jev retrieval decisions, but cannot establish scoring quality. Paired live-primary runs are necessary for model-output claims.

Measurements:

- Pre-pool recall, reranked span Recall@5/10 and complete sufficient-group delivery before/after packing.
- NDCG only where independent graded passage relevance exists; do not invent grades from model outputs.
- Limiting-evidence retention, complete contradictory-pair retention, gate false-exclusion and false-abstention rates.
- Valid/missing/unscored pairs and failed assessments, with denominators and language/role breakdowns.
- Primary status agreement, numeric MAE/kappa, citation support and nullable behavior where labels permit.
- Tool recovery counts and outcomes; zero tool calls do not establish recovery benefit.
- Per-stage and end-to-end p50/p95, request/token counts, reservations, estimated/reported/invoiced costs and unresolved admissions separately.
- Paired per-CV uncertainty intervals; visible public synthetic cases are not a protected holdout.

Activation criteria for controlled rerank use: all scope/privacy/budget invariants pass; no additional loss of labeled limiting/contradictory evidence in the frozen set; paired sufficient-group coverage improves, or retains the baseline while materially reducing primary context/cost; observed p95 added reranking latency <=5 seconds on the selected workload; no unresolved financial admissions. If these are not established, retain shadow/off and publish the observed failure rather than claiming an improvement.

Real-applicant hard gating additionally requires independent adjudicated relevance labels, acceptable false-exclusion limits agreed with HR, multilingual validation and a separately reviewed activation policy. This spec does not authorize automated rejection or establish readiness for real hiring.

## 10. Verification and rollback

Test the pure rank/selection contract, exact per-pair scoping, no mutation of citations, malformed distributions, contradictory/limiting retention, fair budget allocation and byte-bound behavior. Adapter tests use HTTPX MockTransport and assert actual outgoing Jev serialization, no hidden retries and model-version validation.

Integration tests on disposable PostgreSQL verify per-provider and total call ceilings, all-provider requisition budgets, held unknown outcomes, retry/crash accounting, historical hashes, off-mode zero calls, shadow primary-context identity, active failure paths, tool reranking/reuse, stale/deleted inputs and derived-data deletion. Execute migration upgrade/downgrade with populated historical runs, full backend regression and affected frontend tests/build. Browser-check the unchanged HR flow and any small omission notice at phone/tablet/desktop widths.

Run offline/scripted checks first, then cached real E5, then the admitted small live synthetic Jev probe and paired DeepSeek experiment. Save code/config/dataset/rate provenance and journals without secrets. Do not send real CVs merely to test an endpoint.

Rollback sets `JEV_RERANK_MODE=off` for new runs and restarts API/worker. Existing snapshots keep their pinned policy; pause/cancel affected queued jobs explicitly rather than mutating them. An additive migration need not be rolled back to disable the feature; historical assessment/evidence remains interpretable. Update README only with measurements actually produced.

## 11. Evidence sources

Reviewed official documentation on 2026-10-09:

- [TypeSafe passage classification](https://docs.typesafe.ai/cookbooks/classifying_rag_passages): source routing includes evidence/conflict handling; an injection classifier is not a security boundary.
- [TypeSafe reranking](https://docs.typesafe.ai/cookbooks/rerank_typesafe): ranking only sees the retrieved candidate pool.
- [TypeSafe API](https://docs.typesafe.ai/api) and [fan-out](https://docs.typesafe.ai/patterns/fan-out): typed questions and explicit references to structured state; multiple questions can share a call.
- [TypeSafe models](https://docs.typesafe.ai/models) and [Jev limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13): versioning, context/language constraints and failure modes require workload-specific verification.
- [OpenRouter Jev guide](https://openrouter.ai/blog/insights/what-is-jev/) and [model page](https://openrouter.ai/typesafe/jev-1.13/api): Decisions endpoint and provider-specific model/cost/context information.
- Local baseline: retrieval, Jev adapter, assessment snapshots/policy, invocation orchestration and benchmark preflight inspected at `190bf7d`.

No implementation, model call, migration, runtime restart, production-data modification or benchmark result is claimed by this document.
