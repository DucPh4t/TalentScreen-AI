# Serialized packing and RAG V2 verification — 2026-10-09

Scope: improve the existing evidence/request packing and retrieval workflow. No UI, provider/model, production DB, migration, dependency, real CV or paid-call change. V2 is an explicit opt-in; defaults and older retrieval snapshots remain compatible.

## Implementation and tests

- Complete compact JSON/UTF-8 budget covers rubric, evidence maps/IDs, tool schemas, message/protocol and repair history. Whole spans are evicted consistently across request, registry and criterion scope; quote text is immutable.
- Unique evidence-character cap also applies after tool expansion. New evidence takes priority; assistant tool-call prose and invalid repair answers are discarded without breaking protocol IDs/arguments.
- Claim/span indexing, exact section-local dedup, short approved bilingual queries and larger search pool use a separate V2 embedding configuration. V1 index/hash behavior remains compatible; canonical spans and frozen datasets are unchanged.
- Snapshot pins record retrieval/model configuration and packing version. Unsupported explicit packing versions fail before indexing/egress. SQL tests verify index coexistence/reuse and exact sanitized-version/config scoping.
- Test-first failures for absent V2/policy/CLI functionality and missing byte-aware fitting were observed before implementation. Extended tests exercise actual graph oversized multilingual evidence, two-tool expansion, malformed-output repair and real adapter byte serialization through HTTPX MockTransport.
- Final isolated backend suite: **446 passed, 1 opt-in E5 skip, 0 failures/errors** (447 collected), exit 0. Offline flags prevent model downloads; migrations ran only on disposable PostgreSQL.
- Log SHA-256: `46ff9c77d2da35264c38f97e3a5d714641c0629bf3af71378e3c1f2000d37bea`.
- JUnit SHA-256: `48f5d5f0d7004347ab98281249e855459b1bb9755631a055dbafa092c5cb8692`.
- Frontend unchanged; no new frontend build or visual-verification claim.

## Independent code review

The read-only reviewer found one P1 (evicted quote survived assistant tool prose), one P2 (partial optional diagnostics caused graph KeyError), and a packing-version provenance gap. Each was reproduced with a failing regression before its fix. The same reviewer rechecked the fixes and found **no remaining Critical/Important issues** in the diff. The executor verified test and benchmark results; the reviewer did not independently rerun heavy tests.

## Frozen comparison

Source algorithm commit `cc15360c69576a1e3099d199646cbfc871b0eea6`, clean at both starts. Development results informed configuration; no ranking changes followed code freeze/public evaluation. Both final experiments used the identical verified UTF-8 bound, prompt/schema, E5 revision, inputs and seed.

Actual E5 on MPS + pgvector + LangGraph completed **480/480 accepted service runs**, comparing V1/V2 over all 60 frozen stress cases and four profiles. LLM was mock; zero tools/repairs were used by that model. All 480 measured requests fit <=65,536 serialized bytes and <=24,000 unique evidence characters. Both journals reconcile with no integrity errors, zero estimated spend, held funds or unresolved admissions.

Hybrid sufficient-group coverage improved **45/222 → 210/222** overall; public slice **24/87 → 86/87**. Remaining misses and visible synthetic references limit the claim to retrieval availability. Model accuracy, human agreement, live tool recovery and real hiring readiness remain unmeasured.

See [results and exact provenance](../evaluation/rag-packing-results-2026-10-09.md) and [configuration/rollback](../evaluation/rag-pipeline-versions.md). All baseline, intermediate, failed-test and final ignored journals/logs are preserved in the primary checkout before removing this owned worktree. Frozen V1/V2 inputs and reference labels were never rewritten to improve metrics.
