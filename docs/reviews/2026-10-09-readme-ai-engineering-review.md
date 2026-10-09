# README review: AI Engineering portfolio

Reviewed on **9 October 2026** against the local code and recorded evaluation artifacts. Reference repositories were inspected on the same date. This compares documentation patterns and project scope, not measured quality across products.

## Assessment

The existing README already had a useful foundation: a concrete HR problem, stack badges, product workflow, architecture, code links, a reproducible synthetic benchmark, and explicit limitations. Its main weaknesses were a hidden product screenshot, an unexplained “hybrid” label, and inconsistent Jev positioning: the engineering table mentioned evidence reranking while the setup described only the older secondary scoring shadow.

The revision makes the product visible immediately, explains each retrieval/model role, gives Jev its own section and badge, and distinguishes execution success from retrieval coverage and hiring accuracy. It keeps detailed financial/rollback policy in the runbook. The README remains a portfolio entry point; specialist reports carry experiment provenance.

## Related repositories

| Reference | Documentation pattern observed | Application to TalentScreen |
|---|---|---|
| [RAGFlow](https://github.com/infiniflow/ragflow) | Product definition, navigation, features, architecture, local deployment, and documentation links | Lead with the HR use case and a screenshot; provide an architecture overview before deeper retrieval details. RAGFlow has a broader document/agent platform scope, so feature breadth is not a suitable parity target. |
| [Onyx](https://github.com/onyx-dot-app/onyx) | Explains its context layer, how it works, security/data processing, and deployment modes | Explain what is indexed and who can access it. TalentScreen searches one approved CV snapshot against an approved rubric, rather than a connected organizational knowledge corpus. |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Concise positioning, installation, reasons to use the framework, and links to observability/documentation | Make the actual graph and tool boundaries easy to inspect. TalentScreen uses five graph nodes and two scoped tools; it does not automatically inherit LangGraph checkpoint persistence or every framework capability. |
| [RAG From Scratch](https://github.com/langchain-ai/rag-from-scratch) | Notebook-based progression through indexing, retrieval, and generation | Give a clear pipeline explanation. TalentScreen's additional reviewable work includes application state, approvals, worker execution, scoring validation, cost accounting, migrations, and regression tests. This is a scope distinction, not a quality ranking. |

These repositories are references, not upstream implementations or endorsements. TalentScreen depends on LangGraph; its retrieval and Jev workflow should be reviewed through the linked local source files and experiment reports.

## Technical claims checked

- **Hybrid retrieval:** E5/pgvector cosine ranking plus PostgreSQL `simple` full-text tokenization and `ts_rank_cd`, fused with RRF (`k=60`). Do not advertise BM25, a cross-encoder, or learned rank fusion.
- **Jev role:** optional classification of approved criterion–passage relevance. It is not a hiring agent or an applicant score. The legacy secondary scoring shadow is separate and mutually exclusive.
- **Agent role:** read-only evidence tools, bounded calls, exact citation validation, and one repair allowance. Durable job/run state is stored in PostgreSQL; the transient graph has no checkpointer.
- **Evaluation:** 480/480 E5 + mock runs measure recorded synthetic execution and evidence coverage. They do not establish live scoring accuracy or HR agreement.
- **Jev evidence:** real provider calls occurred, but negative evidence losses, a confounded off/enabled comparison, and an unresolved invocation prevent activation. The post-fix implementation has not had a paid rerun.
- **Verification counts:** 506 backend passes/one opt-in skip, 23 frontend passes, and an eight-route production build are dated recorded results, not a fresh suite run for this documentation edit.

Sources: [retrieval](../../services/backend/app/services/retrieval.py), [graph](../../services/backend/app/services/agent/assessment_graph.py), [Jev contracts](../../services/backend/app/services/reranking/contracts.py), [controlled retrieval results](../evaluation/rag-packing-results-2026-10-09.md), [Jev results](../evaluation/jev-reranking-results-2026-10-09.md), and [verification](2026-10-09-jev-reranking-verification.md).

## Remaining presentation and evidence gaps

A short narrated demo would make the JD → rubric → CV → evidence → human decision workflow faster to understand. No demo link has been invented. The repository also lacks a root license; the author should choose one before advertising redistribution rights. No license badge was added.

The next substantive AI Engineering evidence is a controlled post-fix live comparison, measured model-requested tool recovery, and independently reviewed HR/IT holdout labels. A polished README cannot substitute for these measurements. Jev remains off by default and real hiring readiness remains unproven.
