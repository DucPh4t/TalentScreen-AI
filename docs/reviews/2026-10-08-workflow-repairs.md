# Workflow repairs and JD-driven rubrics

Date: 2026-10-08. Scope: five requested workflow repairs and user-entered JDs in the main checkout (`d47db0c` plus local changes).

## Delivered behavior

| Area | Behavior and boundary |
| --- | --- |
| Duplicate hints | Current-file hashes and organization-scoped HMAC fingerprints of normalized local contact data identify possible duplicates across distinct Candidate rows. Results respect memberships and contain counts/reasons, never raw contacts or hashes. Shared contacts can be false positives; no automatic merging or score changes. Legacy files have exact-file matching; contact matching starts on ingestion. |
| HR review SLA | Only fresh successful assessments awaiting an HR decision can breach the 72-hour timer. Timing starts at assessment completion. Completed, parsing, privacy-review and ready-for-AI stages do not receive this warning. |
| Correspondence | Three deterministic templates, explicitly described as templates. GET is read-only; POST generates; saving and approving create immutable numbered revisions. No LLM agent or email transport. |
| Content and approval | Generated clarification points use approved criterion labels rather than copying model `missing_information`. Boundary filters reject internal fields and score patterns. Owner review/acknowledgement is required for approval, with actor/time/source snapshot. Optimistic version checks reject concurrent stale edits. Copy rechecks the approved revision; changed decisions, JD/rubric, source or assessment invalidate drafts. Filters are defense in depth, not proof that every possible paraphrase is safe; human content review remains necessary. |
| Reassessment | Approving a new rubric queues all eligible current approved CVs, including already-assessed applications. Snapshot deduplication avoids a second automatic run for an identical queued/running/succeeded snapshot. Historical runs are preserved. Closed, unapproved, and otherwise ineligible records remain gated. |
| User JD | Vacancy creation requires user-entered JD text. No Backend seed button. Configured provider generation uses a versioned prompt, structured schema and invocation budget ledger; JD egress review is a separate action. Proposed criteria quote actual requirements and remain drafts until HR approval. Mock mode extracts clauses locally and makes no external call. |
| Approved scoring policy | Shortlist core floors are taken from the approved rubric policy; large weights do not implicitly become mandatory core criteria. Missing evidence remains unknown. |
| Concurrent source changes | Application locks precede Document/SanitizedVersion locks, avoiding the deadlock between reassessment FK inserts and source revocation/editing. |
| Deletion | Candidate/application purge removes every correspondence revision and records the purged count. |

Dynamic JD generation was exercised with React/TypeScript and product-design/Figma requirements. Supporting arbitrary role input does not establish evaluation quality for every profession; HR must review the proposed rubric.

## Verification actually executed

- Full backend suite: **275 passed, 0 failed, 0 skipped**, on disposable PostgreSQL/pgvector; 55.516 seconds in the final JUnit result.
- Focused repair suite: **27 passed**, including actual concurrent PostgreSQL sessions. Before the lock-order fix, the concurrency regression reproduced `DeadlockDetectedError`.
- Migration: clean upgrade and upgrade/downgrade roundtrip with existing email revisions. Legacy unverified approvals are invalidated while bodies remain preserved.
- Frontend: `npm run build` completed production compilation and TypeScript checks for all eight routes.
- `git diff --check`: clean.
- Model-provider branch: exercised through the real rubric validation/job/invocation-ledger path using an injected mock adapter. **No live model request or real CV scoring was performed in this repair run.**
- One existing Starlette HTTP 413 naming deprecation warning remains; no failing test.

Reproduce from repository root:

```bash
PRIVATE_STORAGE_ROOT=/tmp/talentscreen-workflow-repairs \
DEV_EVAL_BUDGET_USD=10 PILOT_MONTHLY_BUDGET_USD=10 \
bash scripts/test_backend_isolated.sh services/backend/tests --tb=short

cd apps/web
npm run build
```

JUnit evidence for this local run: `/tmp/talentscreen-repairs-full-final.xml` and `/tmp/talentscreen-repairs-focused-final.xml`. These temporary files are not repository artifacts.

## Local runtime update

The actual local database was backed up inside private storage with mode 0600 before upgrading from `c2f1a90d34b7` to `b8c2d41a9e06`. Counts before/after remained 629 applications, 518 documents and 436 sanitized versions. This check does not claim a restore rehearsal.

Frontend stays on `http://localhost:2004`. Backend uses `http://127.0.0.1:8011` because port 8000 belongs to another project. Only gitignored local environment files were updated. Backend health returns 200 and the frontend authentication proxy returns the expected 401 without a session. The browser smoke test reaches the login page; an authenticated full browser journey was not run in this repair pass.

## Scope limits

These repairs do not close every finding in the earlier [readiness review](2026-10-08-hitl-enhancements-readiness.md), particularly Executive Summary unknown-evidence handling and consistent source/blind-review guards across derived views. The separate OpenRouter/Jev-removal worktree has not been merged or claimed as tested here. No autonomous hiring decision or production-readiness claim is made.
