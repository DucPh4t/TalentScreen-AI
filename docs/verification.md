# Verification evidence

This page separates reproducible software checks from model-quality claims. It records local verification for the RAG/agent implementation and HR redesign on **2026-10-07**. The README edit does not change application behavior.

## Reproducible checks

```bash
make test

.venv/bin/python scripts/run_rag_benchmark.py \
  --dataset fixtures/rag_benchmark/synthetic.jsonl \
  --output /tmp/talentscreen-rag-benchmark.json
```

`make test` starts a disposable PostgreSQL/pgvector container, migrates an empty schema, runs the backend suite, and builds the frontend. It does not run against the application's configured database. Model/embedding behavior is mocked or deterministic in the suite; no live-provider key is needed.

| Check | Local result | Scope |
| --- | --- | --- |
| Backend regression suite | 242 tests passed | Workflow and software contracts. |
| Alembic from empty database | Passed through `43de8b507ac2` | Forward migration chain to current schema. |
| Next.js production build | Passed | Compilation and TypeScript checks. |
| Synthetic benchmark CLI | Passed; four development fixture rows | Schema, manifest and aggregate reporting; no model inference. |
| Browser workflow | Passed on isolated synthetic services | Auth, navigation, queue, JD/rubric, candidate review, retention, legacy redirect. |
| Responsive checks | 320 / 390 / 820 / 1440 px | Checked layouts had no page-level overflow; comparison tables intentionally scroll internally. |
| Keyboard dialog checks | Passed | Focus containment, Escape dismissal, focus restoration. |

The synthetic report identifies `data_scope: synthetic_only` and `readiness: NOT_AUTHORIZED_FOR_LIVE_DECISIONS`. Its values exercise evaluator behavior; they are not measured provider quality.

One existing Starlette deprecation warning was emitted for the legacy HTTP 413 constant in an intake test; it did not fail the suite.

## Tests by contract

| Contract | Test entry points |
| --- | --- |
| E5 prefixes/vector shape, chunks, configuration and retrieval scope | [test_hybrid_retrieval.py](../services/backend/tests/test_hybrid_retrieval.py) |
| Tool limits, isolation, injection-shaped requests, stale snapshots, late results after deletion | [test_assessment_agent.py](../services/backend/tests/test_assessment_agent.py) |
| Dynamic rubrics, schema alignment, missing evidence, core-floor scoring | [test_dynamic_rubric_regression.py](../services/backend/tests/test_dynamic_rubric_regression.py) |
| Prompt versions, grounding and assessment validation | [test_assessment_prompt.py](../services/backend/tests/test_assessment_prompt.py), [test_assessment.py](../services/backend/tests/test_assessment.py) |
| Provider failures, spend reservation/settlement, requisition cap | [test_llm_adapter.py](../services/backend/tests/test_llm_adapter.py), [test_admin_observability.py](../services/backend/tests/test_admin_observability.py) |
| Jev contracts and migration | [test_jev_provider.py](../services/backend/tests/test_jev_provider.py), [test_jev_shadow_migration.py](../services/backend/tests/test_jev_shadow_migration.py) |
| Auth/CSRF, cross-scope access, decisions, deletion | [test_auth.py](../services/backend/tests/test_auth.py), [test_sec_regression.py](../services/backend/tests/test_sec_regression.py), [test_decisions.py](../services/backend/tests/test_decisions.py), [test_deletion.py](../services/backend/tests/test_deletion.py) |
| Benchmark schema/privacy, criterion metrics, manifests, aggregate reporting | [test_rag_benchmark_cli.py](../services/backend/tests/test_rag_benchmark_cli.py), [test_evaluation_metrics.py](../services/backend/tests/test_evaluation_metrics.py) |

This is a map of tests, not a code-coverage percentage or security certification.

## UI and integration evidence

The [redesign review](reviews/2026-10-07-hr-workspace-redesign.md) records two isolated synthetic deployment smoke runs covering auth/CSRF, JD/rubric approval, upload/worker processing, redacted-text approval, hybrid mock assessment, validation, comparison, role isolation, metrics, and logout.

Browser checks used a disposable synthetic database and mock primary provider; Jev was off. No real CVs or hiring decisions were used. [Desktop](reviews/hr-redesign-desktop-2026-10-07.jpg) and [mobile](reviews/hr-redesign-mobile-2026-10-07.jpg) screenshots are committed with the review.

## Model-quality evidence still required

| Dimension | Required evidence |
| --- | --- |
| Retrieval relevance | Per-role criterion/evidence labels, Recall@5/10, sufficient-evidence retrieval. |
| Scoring | Blind independent HR/IT labels, human-human baseline, MAE/agreement/coverage and error review on protected holdout. |
| Fairness | Counterfactual and representative subgroup analysis under approved data governance. |
| Live providers | Configured primary/optional shadow workflows, failure behavior, usage/invoice reconciliation. |
| Operations | Representative load/SLOs, alerts, incident/rollback drills, deletion plus restore-and-repurge verification. |

The [protocol](evaluation/rag-agent-benchmark-protocol.md) and [G1–G7 gates](runbooks/rag-agent-readiness.md) define this work. Mock/synthetic passes do not establish these outcomes.

## README presentation references

Public primary repositories reviewed on 2026-10-07:

- [LangGraph](https://github.com/langchain-ai/langgraph): short purpose statement, direct getting-started path, deeper documentation links.
- [RAGFlow](https://github.com/infiniflow/ragflow): separate features, architecture, and local setup, with navigation for longer content.
- [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template): concrete stack/features, UI examples, separate development/deployment documentation.

Only presentation structure informed this documentation update; their code, results, or maturity are not attributed to TalentScreen AI.
