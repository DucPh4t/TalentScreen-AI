# HR and Interview Workflow B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Ship the approved screening-to-interview workflow with fewer actions and server-enforced review controls.

**Architecture:** Reuse decisions, attestations, question revisions and scorecards. Add a private review-progress record and a versioned interview-round plan with append-only conclusions; scorecard corrections retain previous observations. Extract focused UI components from the application page.

**Tech Stack:** FastAPI, SQLAlchemy, PostgreSQL, Alembic, Next.js 15, React 19, TypeScript, pytest and node:test.

**Spec:** docs/superpowers/specs/2026-10-08-hr-interview-workflow-b.md

## Global Constraints
- Work only under /Users/nguyenducphat/TalentScreen AI; preserve local secrets and real candidate records.
- Use an isolated disposable PostgreSQL database for all pytest runs.
- Dynamic criteria, 0–4 observations, missing evidence != zero, HR-only conclusions.
- No external email delivery or automated hiring decisions.
- Source snapshots, optimistic versions and audit events are mandatory for writes.

## Review Focus
- Two tabs editing the same plan/card must conflict rather than overwrite.
- Changed CV/JD/rubric must invalidate review progress, questions and conclusions.
- Waiting for supplementary information must not disappear from the queue.
- A participating owner must not see other interview scores before submitting.
- Unobserved focus criteria and empty/placeholder schedules cannot look complete.

### Task 1: Persist review and repair screening lifecycle
**Files:** services/backend/app/db/models/hr_workflow.py; schemas/hr_workflow.py; services/hr_workflow.py; api/v1/decision.py; services/decision.py; api/v1/workflow.py; alembic/versions/0c84e9d57a62_hr_interview_workflow.py; tests/test_hr_interview_workflow.py.
**Interfaces:** GET/PUT /applications/{id}/review-progress (source_hash, reviewed_criterion_ids, expected_version); POST /applications/{id}/screening-decision (effective_result, reviewed_criterion_ids, acknowledged, outcome, reason, expected_previous_decision_id, expected_rubric_version_id). Atomic attestation + decision; reason used as override when needed.
- [x] Write tests for request-information vs advance states, superseding/override, stale progress and conflicts.
- [x] Run isolated tests and observe intended failures.
- [x] Implement current-source validation, persistence, atomic decision and explicit queue stages.
- [x] Verify tests, record evidence in ledger.

### Task 2: Interview round preparation, corrections and conclusions
**Files:** hr_workflow models/schemas/service; api/v1/interview.py; services/interview.py; services/interview_scorecard.py; schemas/interview.py; models/interview.py; tests/test_hr_interview_workflow.py.
**Interfaces:** GET/PUT /applications/{id}/interview-rounds/{round_no}; POST .../conclusions; POST /interview-scorecards/{id}/amend; existing PUT scorecard gets submit flag. Plan contains source_hash, row_version, focus_criterion_ids, interviewer_ids, starts_at, duration_minutes, channel, meeting_location. Conclusions contain outcome, reason and immutable card versions.
- [x] Write tests for plan authorization/conflicts/staleness, focus submission, blind owner, amendments and conclusion source versions.
- [x] Run isolated tests and observe intended failures.
- [x] Implement bounded round plan and append-only conclusions; preserve submitted scorecard history and existing legacy scorecards.
- [x] Validate question freshness against rubric/JD/effective-result and enforce usable scheduling before invitation approval.
- [x] Verify focused tests and migration upgrade/downgrade, record ledger.

### Task 3: Simplify responsive HR and interview UI
**Files:** apps/web/src/components/ScreeningDecision.tsx; InterviewWorkspace.tsx; apps/web/src/lib/hr-workflow.ts; api.ts; workflow.ts; application-list.ts; applications/[id]/page.tsx; app/globals.css; tests/hr-workflow.test.mjs.
**Interfaces:** Components consume current application/rubric/effective result, current user/role and refresh callback; POST exact server contracts from tasks 1 and 2.
- [x] Write node tests for decision payload, source-sensitive routing, focus and consensus helpers; observe failures.
- [x] Implement one acknowledgement, supersede/history, outcome-specific response template, three interview views, revision editing, persisted focus, corrections and human conclusions.
- [x] Keep score/answer paired, missing observations explicit; preserve edits during refresh; save-and-submit atomically; no unsafe bulk hiring actions.
- [x] Verify node tests and production build; inspect desktop/mobile browser flows using synthetic records only.

### Task 4: Regression and review
- [x] Run PRIVATE_STORAGE_ROOT=/tmp/talentscreen-workflow-b make test with complete output saved privately.
- [x] Review the whole change with a fresh reviewer, fix important findings with RED/GREEN regression tests.
- [x] Update workflow documentation and evidence ledger with exact results and material limitations.
- [x] Commit verified implementation; push only if authorized by current session.
