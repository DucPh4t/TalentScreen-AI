# Synthetic long-context benchmark v2

This is an adversarial **retrieval stress collection**, not a sample of real applicant CVs. It retains the v1 JSON wire schema; `dataset_revision: v2` and disjoint `v2-` case/cluster IDs identify this collection. V1 is unchanged.

- 60 synthetic cases: Backend Node.js, AI/ML and Android, 20 per role.
- Each role has 7 Vietnamese, 7 English and 6 mixed-language cases; 36 development / 24 public-test cases in total.
- Scores, statuses, sufficient evidence groups and role rubrics are inherited from the frozen v1 design expectations. The builder relocates exact quotations to the canonical production spans; it does not invent new HR labels.
- Every CV contains 30 deliberately repetitive, keyword-rich archived team planning notes. These explicitly disclaim personal implementation, testing or measured outcomes. They are distractors, not evidence of technical competence. This repetition limits ecological validity.
- Technical contributions appear before or after the archive. Conflicting claims and their corrections are separated by the archive; buried evidence exceeds the 24,000-character full-text limit. Identity counterfactual pairs preserve identical sanitized technical text.
- Anchor levels 0–4, null, insufficient and conflicting evidence remain distinct. Absence of evidence does not mean zero competence.

`manifest.json` binds cases, roles and evaluator-only references by SHA-256, includes the authoring script hash and the source v1 manifest hash. It is frozen before any retrieval measurement. The benchmark runner/model/tools receive input cases and roles, **never reference labels**. Public-test cases are not a protected holdout; labels are synthetic design expectations, not independent HR/IT judgments.

## Reproduce / validate

The builder refuses an existing output directory. Do not overwrite this frozen collection or tune it after observing rankings. A future collection needs a new revision and recorded hash.

```bash
.venv/bin/python scripts/build_ai_benchmark_v2.py --output /tmp/talent-benchmark-v2-reproduction
.venv/bin/python scripts/run_ai_benchmark.py validate --dataset fixtures/ai_benchmark/v2
```

The first diagnostic selection was declared before measurement: `v2-node-10,v2-node-13,v2-ai-10,v2-ai-13,v2-android-10,v2-android-13`, all four profiles, seed 20261008. It tests conflict separation and buried evidence only; it does not estimate performance over all 60 cases. Real cached E5 + mock LLM measures retrieval and pipeline contracts; model scoring accuracy and agent recovery effectiveness remain unmeasured.
