# LangSmith observability verification — 2026-10-08

## Delivered scope

Developer-only optional LangSmith RunTree telemetry replaces the technical trace
panel in the HR application workspace. The existing PostgreSQL audit trace remains.
HR evidence, status, error recovery and decision actions are preserved.

Actual LangGraph node invocations are observed: authorize, model, tools, validate
and repair. Retrieval, bounded provider calls and JD-to-rubric drafting have nested
spans. No graph state, CV/JD text, prompts, responses, tool arguments or source
quotes are exported. Metadata uses an allowlist; inputs and outputs are empty.
Automatic graph state tracing and ambient write replicas are suppressed.

## Verification evidence

| Check | Result |
| --- | --- |
| Focused observability and actual assessment graph tests | 27 passed |
| Full backend suite on throwaway PostgreSQL + pgvector | 312 passed, 0 failed; exit 0 |
| Frontend workflow tests | 16 passed, 0 failed; exit 0 |
| Next.js production build with type checking | Passed; exit 0 |
| Browser: technical trace panel | 0 matching elements |
| Browser: criterion evidence heading | 1 matching element |
| Initial local LangSmith connectivity probe | not_enabled, verified=false; exit 2 |
| Whitespace validation | git diff --check passed |

Regression coverage uses the real SDK RunTree serializer with only export
transport replaced, and real LangGraph execution with a scripted model provider.
It checks repair paths, rejected validation spans, usage counts, metadata privacy,
concurrent parent isolation, cancellation, export outages and failed business
returns. Production assessment output stays unchanged during a telemetry outage.

Red/green checks exposed and fixed prompt-version filtering, ambient replica
configuration, configuration errors containing secret inputs, and non-string
exception codes replacing the original business error. The final full suite ran
after these fixes. Test databases are isolated from application CV records.

## Review and remaining boundary

Source and diff were reviewed locally. An independent reviewer was attempted but
could not run because its usage quota was exhausted; this report does not claim
an independent review was completed.

At the initial implementation checkpoint, no key was provided and tracing was
disabled. The subsequent local setup below verifies cloud delivery. Historical
assessments are not backfilled.

Cloud traces contain operational correlation IDs and have separate access and
retention controls; deleting an application does not delete LangSmith records.
This change does not alter scoring, approval gates or hiring decisions. See the
[setup and verification runbook](../runbooks/langsmith-observability.md).


## Cloud setup follow-up

The owner subsequently supplied a key for the private project `ScreenCV Talent`.
Only the ignored local `.env` was updated; no credential is included in Git.
Backend and worker were restarted after confirming the queue was idle.

The first immediate read returned 404. Reading the same synthetic run after
ingestion completed succeeded, with empty inputs and outputs. The probe now retries
only missing/pending runs, up to eight reads with one second between attempts.
Other errors propagate to the existing safe failure result without retries.

Four probe tests were added. The read-back tests were observed failing before the
fix, then all 16 focused probe/observability tests passed. A fresh cloud probe
returned `status=verified`, `verified=true`, exit 0. Both frontend (2004) and
backend (8011) responded with HTTP 200 after restart. No candidate CV, model prompt,
model response or hiring decision was used in this cloud connectivity check.

This confirms synthetic span export/read-back, not a production assessment's
accuracy or a visual inspection of the LangSmith dashboard. New approved app
assessments will use the configured tracing project.
