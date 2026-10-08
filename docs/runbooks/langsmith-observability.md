# Developer observability with LangSmith

LangGraph executes the bounded assessment workflow. LangSmith is optional developer
telemetry; HR sees CV evidence, assessment status and review actions in the app.
The local minimized audit trace remains in PostgreSQL, but no technical trace panel
or LangSmith credentials are exposed to the frontend.

## Enable locally

1. Create a LangSmith account and API key in the [LangSmith settings](https://smith.langchain.com/settings).
2. Update the untracked root `.env` (never paste the key into a chat or commit it):

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<your-own-key>
LANGSMITH_PROJECT=talentscreen-dev
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Use `https://eu.api.smith.langchain.com` if the workspace is in the EU region.
The project name identifies the developer trace collection. Keep access restricted
to developers allowed to inspect operational metadata. Tracing defaults to **off**;
enabling without a nonempty key is a configuration error.

3. Restart both backend and worker. In separate terminals, from the repository root:

```bash
make dev-backend BACKEND_PORT=8011
make dev-worker
```

Stop the existing instances first; do not start competing workers for this test.
If the local backend uses another port, retain its existing port and frontend rewrite.

4. Run the connectivity probe:

```bash
.venv/bin/python scripts/probe_langsmith.py
```

This creates **one synthetic telemetry span**, flushes it and reads it back. It
makes no CV/model/DB request. Read-back retries only missing/pending runs, up to
eight reads, to tolerate asynchronous ingestion. Access/network failures are not
retried. `verified: true` and exit code 0 confirm read-back;
`not_enabled` exits 2; export/read-back failures exit 1. A successful local mock
transport test is not cloud verification.

5. Run a new, approved assessment through the app. Open the project in LangSmith
and search by `assessment_run_id` or `job_id`. Historical runs are not backfilled.

## What a developer can inspect

A full hybrid assessment produces this nested span tree (only executed branches
appear; loops create another span rather than overwriting the previous attempt):

```text
assessment
├── initial_rag
│   └── hybrid_retrieve_for_criterion (once per criterion)
└── assessment_agent
    ├── authorize
    ├── model
    │   └── bounded_llm_call
    ├── tools                     (optional; may repeat)
    │   ├── retrieve_more_evidence
    │   │   └── hybrid_retrieve_for_criterion
    │   └── get_source_spans
    ├── model                     (after tools)
    │   └── bounded_llm_call
    ├── validate
    ├── repair                    (only on invalid JSON/evidence)
    ├── model
    │   └── bounded_llm_call
    └── validate
```

The actual LangGraph has **five nodes**: `authorize`, `model`, `tools`, `validate`,
`repair`. Initial RAG retrieval and deterministic scoring are outside the graph.
Baseline assessments do not pretend to execute hybrid RAG. A blocked snapshot
stops before any model call. Validation rejection is marked as a rejected span,
including when the subsequent repair succeeds. A normal Python return carrying a
failed assessment is still marked failed at the root.

JD-to-rubric drafting has its own `jd_to_rubric` root and bounded LLM child. Tool
argument validation and HTTP/budget admission remain unchanged by observability.

Available metadata: opaque run/job/JD IDs, prompt versions, retrieval strategy,
provider/model, actual counters, result counts, usage token counts when reported,
ledger-calculated cost and fixed error codes. Span start/end times provide latency.
Unknown token counts stay unknown; LangSmith's displayed estimated provider prices
are not the billing ledger. This integration is a manual RunTree span hierarchy,
not LangGraph checkpointing or an HR-facing graph visualization.

## Privacy and failure boundaries

- Inputs and outputs are empty. No raw/redacted CV, JD text, prompt, completion,
  query hint, tool arguments, candidate name/contact, quotes or span content is sent.
- Metadata is an allowlist of counts, known enums and opaque correlation IDs.
  Free-form exception messages, stack traces and validation details are excluded.
- Automatic LangGraph tracing is disabled inside the observed workflow because
  its state contains candidate-derived messages. Merely hiding final outputs would
  not be sufficient. The SDK client additionally hides inputs/outputs and omits
  runtime details.
- Spans describe the operations that actually execute. They do not infer skill,
  determine hiring decisions or prove model fairness/accuracy.
- Telemetry is best effort. Export outages do not change scores, transactions,
  external-call limits or business errors; cancellations still propagate.
- Cloud metadata is a separate copy. Apply the workspace's retention and access
  policy; deleting a candidate from the app does not automatically delete external
  LangSmith records. Correlation IDs are operational data, not anonymous data.
- No content-based LangSmith evaluator is enabled. For quality evaluation, compare
  evidence/labels in the existing local benchmark, or separately approve a synthetic
  content dataset. Metadata-only traces primarily measure reliability and performance.

## Verification

```bash
PRIVATE_STORAGE_ROOT=/tmp/talentscreen-tests \
  bash scripts/test_backend_isolated.sh services/backend/tests --tb=short
```

The isolated test script disables cloud telemetry. Tests explicitly replace only
the export transport and exercise real RunTree serialization and actual graph
execution, including repair, privacy, cancellation, concurrency and export outage.

References: [manual instrumentation](https://docs.langchain.com/langsmith/annotate-code),
[hide inputs/outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs),
[LLM usage metadata](https://docs.langchain.com/langsmith/log-llm-trace).
