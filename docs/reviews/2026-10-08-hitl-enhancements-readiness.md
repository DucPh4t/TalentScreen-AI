# TalentScreen AI — HITL enhancements readiness review

Review date: 2026-10-08 (Asia/Ho_Chi_Minh)

**Verdict: do not release this checkout for live recruitment decision support yet.** The feature surfaces exist, but the full regression suite and additional security/business probes expose blocking defects. No evidence in this review authorizes autonomous candidate rejection or selection.

## Scope and verification

Reviewed the dirty `main` checkout at `/Users/nguyenducphat/TalentScreen AI`, based on commit `d47db0c`. The seven new enhancements are uncommitted in this checkout. OpenRouter integration, Jev retirement and updated hybrid RAG defaults are uncommitted in the separate `.worktrees/rag-agent` checkout. Both checkouts share the same committed base; their working changes have not been integrated and tested together.

No live model API calls or real candidate CVs were used in this review. All additional probes used synthetic fixtures, disposable PostgreSQL/pgvector, and temporary private storage.

| Verification | Observed outcome | What it establishes |
| --- | --- | --- |
| `DEV_EVAL_BUDGET_USD=10 PILOT_MONTHLY_BUDGET_USD=10 bash scripts/test_backend_isolated.sh` | 5 failures; fresh collection contains 247 tests, leaving 242 passing | The full checkout is not regression clean. All five failures are assessment end-to-end variants. |
| `npm run build` in `apps/web` | Exit 0; production compilation/type checking completed | Frontend builds. This does not establish browser workflow, accessibility, responsiveness or AI accuracy. |
| Alembic upgrade during isolated tests | Upgraded through `7a1e8c9d0b2f` | Fresh-database upgrade works. Production-data upgrade, downgrade and rollback drills were not tested. |
| Additional audit probes | Summary gaps crash; retained email after purge; revoked-source fixture exposed; blind reviewer bypass; unsupported Backend criteria in Frontend JD | Concrete edge cases missing from the selected happy-path test set. |
| Deterministic scoring/shortlist probe | Approved scorer: `consider_next_round`; new shortlist: `core_fail`; same score 62.5 and threshold 60 | Two components implement different hiring policies. |
| Email composition probe | A synthetic `missing_information` string containing `3/4` appears in the email body | The claimed no-internal-score invariant is not enforced at the correspondence boundary. |

The audit probe file is temporarily available at `/tmp/talentscreen-review-20261008/test_review_regressions.py`; it is intentionally outside the repository and is not part of the passing regression suite. Fixtures that explicitly set a revoked source or shadow policy test endpoint defenses; they are not claims that the normal revocation handler fails to clear current pointers.

## Findings that block release

### F1 — P1: Sanitization approval crashes in the auto-assessment path

Location: `services/backend/app/services/sanitization.py:525–527`.

`logger` is not defined in this module. The new success logging call raises `NameError`, then the exception handler also references the same undefined name. Five existing end-to-end assessment variants fail while approving the sanitized CV. This is a failure of a core user action, not an optional feature.

Correction: initialize module logging; separate expected enqueue failures from programming/database failures; preserve clear approval/enqueue transaction behavior. Verify approval with and without an approved rubric, retries, failed enqueue, and both relevant approval orders.

### F2 — P1: Executive Summary crashes on missing/weak evidence

Location: `services/backend/app/services/candidate_summary.py:133`.

The comprehension iterates `s` but reads `g`. A nonempty `gaps` list raises `NameError`. The new test exercises only candidates whose criteria all score 3, so it misses this common recruitment case. The audit probe reproduces the exception with an insufficient-evidence criterion.

Correction: fix the variable and test insufficient, conflicting, assessed-low, all-unknown and mixed evidence. Unknown comparable scores must remain null; line 122 currently converts them to 0. Templates must not infer basic capability, absence of leadership or full evidence coverage from the absence of a strength/gap entry.

### F3 — P1: New derived views bypass source/policy checks

Locations: `candidate_summary.py:43–92`; `shortlist.py:50–68`; existing reference policy: `api/v1/independent_review.py:246`.

The new summary/shortlist endpoints do not enforce shadow-blind review. In the audit fixture, the existing assessment endpoint correctly returns 403 to a reviewer who has not submitted independent labels, while both new views return 200 and reveal AI-derived information. This contaminates supposedly independent evaluation labels.

Summary also checks only whether the pointed assessment succeeded. It does not verify the current document, sanitized version, application generation or rubric. A controlled revoked-source fixture returns 410 from the existing assessment endpoint but 200 from summary. The normal revoke handler clears current pointers, which mitigates that normal path; the new endpoint itself has no quarantine guard. Replacement CV uploads leave the previous assessment pointer until a new run succeeds, and rubric approval can likewise make a pointed assessment stale.

Correction: reuse centralized access, blind-review and source-freshness guards for every derived view. Resolve a current effective assessment/HR revision once, then use it in summary, shortlist and correspondence. Cache against immutable source/version identifiers and reject stale or quarantined sources.

### F4 — P1: Successful candidate purge leaves email content in the database

Locations: `services/backend/app/services/deletion.py:368–449`; `db/models/email_draft.py:18–27`.

The purge routine deletes existing child entities but does not inventory or remove `EmailDraft`. Applications are tombstoned rather than physically deleted, so the new FK `ON DELETE CASCADE` never fires. An integration audit created an email draft, requested deletion through the API, executed the actual purge worker, and still found the draft afterward.

Correction: include email drafts and all derived communication data in deletion inventory, purge and verification. Add a regression with email subject/body/variables, plus restored-backup re-purge coverage. Do not report a clean purge while derived personal data remains.

### F5 — P1: JD drafter is a fixed Backend template with unrelated quotations

Location: `services/backend/app/services/rubric.py:58–154`.

The function always emits `technical_core`, `system_and_api`, `data_persistence` and `delivery_and_quality` with fixed Backend descriptions, weights and anchors. Keywords choose quotations; if none match, an arbitrary JD line is used. A Frontend-only JD still gets server API/gRPC and database criteria. Every quote can be a true substring while failing to support the associated criterion.

Several zero-score anchors define lack of evidence as zero capability, contradicting the project's null-for-insufficient-evidence requirement.

Correction: generate only criteria supported by actual job requirements, with requirement/span identifiers. Validate quotation fidelity and semantic relevance separately. Treat absent evidence as unknown. Require HR approval of the proposed role-specific rubric; test Frontend, Backend, Data, QA, DevOps and insufficient/ambiguous JDs. If the implementation remains a template, label it accordingly.

### F6 — P1: Shortlist silently overrides the approved policy

Location: `services/backend/app/services/shortlist.py:96–109, 216–224`.

The shortlist promotes any criterion with weight >= 25 to core with floor 2, even when the approved rubric's `core_minimum_scores` does not specify it. The existing deterministic scoring engine follows the approved explicit policy. A synthetic example with two equally weighted criteria scored 1 and 4, threshold 60 and no core requirements scores 62.5 and is recommended by the approved scorer, but becomes `core_fail` in shortlist.

The new views also read AI runs directly rather than reflecting a selected finalized HR revision. A threshold query is not validated as finite or bounded and is not an approved versioned policy change.

Correction: use the same authoritative scoring policy and effective-result semantics everywhere. Remove weight-based core inference. Make temporary threshold exploration visibly hypothetical; persist consequential policy changes only as approved rubric versions. Keep unrankable/unknown cases distinct from below-threshold capability.

### F7 — P1: The release does not contain the tested provider/RAG combination

Location: `services/backend/app/config.py:65,105` in this checkout.

`main` still accepts only mock/direct DeepSeek, defaults to full-text baseline, and contains the Jev integration. The OpenRouter/hybrid-default/Jev-removal working changes are elsewhere. A passing build of the seven enhancements therefore does not prove the requested OpenRouter + RAG + agent application works as a combined release.

Correction: integrate the intended changes while preserving the current work, select an immutable release commit, and rerun the full suite, migration and production-browser journey on that exact version. Keep provider-specific real-data approval and fail-closed behavior; do not copy a provider key into tracked files.

## Business/operational improvements before live use

1. **Auto-trigger on a new rubric:** `rubric.py:742` considers only applications with no current assessment pointer. Existing assessments become stale under a new rubric but are not requeued. Queue all eligible stale snapshots with deduplication and bounded cost; expose why an item was skipped or failed. Do not silently swallow every exception.
2. **Duplicate detection:** `workflow.py:64–73` counts applications already linked to the same `candidate_id`. Normal intake creates a new candidate if an ID is not supplied (`intake.py:80–102`), so this is application history, not automatic identity resolution for independently uploaded duplicate CVs. Add scoped exact-file hashes and permitted normalized-contact fingerprints, with human merge/review and no contribution to capability scores.
3. **SLA semantics:** `workflow.py:99–108` falls back to application age for every other stage, including completed applications. Stop the decision timer when a decision is complete; track stage entry and configured working/calendar hours. Warn separately about extraction, AI processing and HR review delays.
4. **Email draft workflow:** composition is template-based, not an LLM/tool agent. Preserve this economical approach if suitable, but describe it accurately. Use explicit POST for generation, validate template/status values, record actor/version/source/approval, avoid overwriting approved drafts, and invalidate drafts after a decision or source changes. `missing_information` is currently copied verbatim into outgoing content without a boundary filter. The rejection template also promises Talent Pool retention without establishing that retention/consent workflow. Sending remains a separate explicit human action.
5. **UX meaning:** display score as a rubric-based advisory result, not a probability of success or an absolute measure of ability. Show coverage/unknowns, evidence links, source version and HR override next to recommendations. Test the complete browser journey at mobile/tablet/desktop widths, keyboard navigation, long Vietnamese text and error/manual-review states. A production build is not a usability test.
6. **Migration and operations:** test upgrade from the actual previous release with existing records, restore/re-purge, rollback, worker restarts, timeout/rate-limit responses, hard budget caps and representative batch load. Record outcomes, rather than marking a runbook as an executed drill.

## What is still required to trust AI-assisted screening

The repository already has evaluation and readiness scaffolding. The missing part is qualified evidence and release sign-off, not another dashboard module.

- Freeze actual JD/rubric/prompt/model versions for supported role families.
- Collect permitted representative development data and a protected held-out set. Obtain independent HR and IT judgments and an adjudicated reference. AI role-play expected labels are useful regression fixtures, not independent human validation.
- Measure criterion status accuracy, score MAE/agreement, shortlist recall/false exclusion, rank stability, evidence relevance and unsupported assertions. Report by role and language with uncertainty and a human-human baseline; do not hide weak roles behind an aggregate.
- Evaluate retrieval Recall@k, multilingual/mixed-language CVs, missing information, wrong-role CVs, prompt injection and counterfactual sensitive-attribute changes. Valid citation text alone does not demonstrate that it supports a score.
- Agree acceptance criteria before opening the holdout. Treat provisional thresholds as proposals, not universal proof that autonomous decisions are safe.
- Verify institutional provider/data approval, retention and deletion, authenticated access, incident response and rollback on the integrated release.
- Preserve final human decisions and reasons. Recheck disagreements and overrides; independent evaluation must not expose AI suggestions beforehand.

These expectations are consistent with [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/), particularly documented test sets/metrics, validity in deployment context and human oversight. For OpenRouter, review its [data collection](https://openrouter.ai/docs/guides/privacy/data-collection) and [zero data retention](https://openrouter.ai/docs/guides/features/zdr) controls for the actual upstream routing policy; an API key alone does not establish institutional data approval.

## Recommended sequence

1. Fix F1–F4 and add regressions for all reproduced failures.
2. Align JD grounding, shortlist policy, HR overrides and source versions (F5–F6).
3. Integrate provider/RAG/agent changes, then test one immutable release candidate (F7).
4. Complete the business edge cases, responsive browser journey and operational drills.
5. Run independent role-specific evaluation and obtain the responsible institution's approval for assisted use.

A portfolio demonstration can describe the project as an implemented, evaluated prototype while accurately reporting these limits. Public live deployment or autonomous CV rejection/selection is not justified by 18 selected software tests or a successful frontend build.
