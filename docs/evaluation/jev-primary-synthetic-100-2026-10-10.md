# Jev-primary evaluation: 100 synthetic multi-role cases

**Run date:** 10 October 2026  
**Purpose:** exercise the live hybrid retrieval, evidence-agent, and Jev-primary scoring path; compare outputs with deterministic synthetic design expectations. This is an exploratory software/pipeline evaluation, not a hiring-quality benchmark.

## Executive result

| Measure | Result | Denominator / interpretation |
|---|---:|---|
| Planned cases | 100 | 5 role families × 20 cases |
| Assessment status | 88 accepted, 6 failed, 6 skipped | No case missing from the 100 planned cases |
| Successful Jev primary-score calls | 87 | One accepted case had no evidence and correctly made no Jev call; 12 failed/skipped cases did not reach Jev scoring |
| Jev score MAE | **0.0963** | 342 numeric criterion-score pairs, against synthetic expected scores on a 0–4 scale |
| Assessment-status agreement | 91.48% | 528 criteria in accepted cases; compares pipeline status labels with synthetic references, not Jev numeric score quality |
| Retrieval span Recall@5 | 44.54% | Mean over 476 criterion-level retrieval observations with reference evidence |
| Retrieval span Recall@10 | **99.58%** | Same 476 criterion-level observations |
| Sufficient-evidence-group coverage | 100.00% initial and final | 476 positive criterion-level observations; at least one reference evidence group was present in the evidence set |
| Annotated citation precision | 84.74% | 603 returned citations checked against reference evidence spans |
| Correct abstention | 89.81% | 141 / 157 references whose expected score was null |
| False-zero rate | 0.00% | 0 / 157 null-score references |
| Unsupported-score rate | 9.55% | 15 / 157 null-score references received a numeric score |
| Conflict agreement | 100.00% | 74 synthetic conflicting-evidence references; agreement requires the conflict status and a null score |
| Citation scope violations | 0 recorded | 603 returned citations; benchmark scope diagnostic |

MAE, retrieval, citation, abstention, and status figures are descriptive of this frozen synthetic set only. They do not estimate accuracy on real applicants.

## Per-role results

Every role contains 20 planned cases and six rubric criteria per case. MAE is pooled over numeric reference pairs from accepted cases only.

| Role family | Accepted / planned | Failed | Skipped | Numeric pairs | Jev MAE |
|---|---:|---:|---:|---:|---:|
| Senior AI Engineer | 20 / 20 | 0 | 0 | 74 | 0.1350 |
| Software Development Manager | 20 / 20 | 0 | 0 | 85 | 0.0088 |
| Java Backend Developer | 15 / 20 | 3 | 2 | 57 | 0.1904 |
| Mobile/Web QA | 18 / 20 | 1 | 1 | 72 | 0.0925 |
| Agentic Engineer | 15 / 20 | 2 | 3 | 54 | 0.0870 |

The Java Backend and Agentic Engineer groups had the lowest assessment acceptance. Do not hide these failures when citing the overall score metrics.

## Language slices

The dataset contains 35 Vietnamese, 35 English, and 30 mixed-language cases. Slices are descriptive and are not statistically powered comparisons.

| Language | Accepted / planned | Failed | Skipped | Numeric pairs | Jev MAE | Recall@10 / ranked criteria |
|---|---:|---:|---:|---:|---:|---:|
| English | 35 / 35 | 0 | 0 | 137 | 0.1123 | 100.00% / 181 |
| Mixed | 26 / 30 | 2 | 2 | 99 | 0.1219 | 100.00% / 139 |
| Vietnamese | 27 / 35 | 4 | 4 | 106 | 0.0518 | 98.72% / 156 |

## Pipeline configuration and outcomes

- **Profile:** `hybrid_agent`; dense multilingual E5 plus PostgreSQL lexical retrieval, with the bounded evidence agent/tools enabled.
- **Primary scorer:** TypeSafe Jev `jev-1.13.0`; `ASSESSMENT_SCORER_MODE=jev`.
- **Evidence agent / explanation provider:** DeepSeek `deepseek-flash`; DeepSeek produced evidence/status observations and optional explanations, not the numeric primary score.
- **Jev reranking:** disabled (`JEV_MODE=off`, `JEV_RERANK_MODE=off`); no Jev rerank invocations.
- **Retrieval and packing:** retrieval V1; `intfloat/multilingual-e5-base` revision `d128750597153bb5987e10b1c3493a34e5a4502a`; serialized-evidence-v1; real embeddings on Apple MPS.
- **Run shape:** 17 isolated batches, 100 distinct case IDs, one repetition, concurrency 1, temperature 0. Manifests report no missing, duplicate, or unexpected case IDs.
- **Invocations:** 309 total; 87 Jev and 222 DeepSeek. All recorded provider invocation statuses succeeded, but provider-call success did not guarantee an accepted assessment.
- **Failure/skip diagnostics across 12 cases:** 7 `AGENT_MODEL_ROUND_LIMIT`, 2 `AGENT_TOOL_SCOPE_REJECTED`, 3 `ASSESSMENT_OUTPUT_INVALID`.
- **Peak-rate cost estimate:** **$0.48056297** total — Jev $0.01378003 and DeepSeek $0.46678294. Provider invoice data was unavailable; this is not an invoiced amount.

## Dataset and provenance

Dataset: [`synthetic_100_multi_role_v2`](../../fixtures/ai_benchmark/synthetic_100_multi_role_v2/). The generator is [`build_multi_role_synthetic_100.py`](../../scripts/build_multi_role_synthetic_100.py).

- 100 synthetic CV-like cases; 5 role families; 6 criteria per role.
- Expected labels are authored design expectations mapped deterministically from synthetic templates to draft anchors; one documented cross-criterion reference correction is included. There was no HR/IT review, independent annotation, adjudication, or human gold.
- The nominal split is 80 development and 20 public-test cases. The public-test split is **not protected**; this run evaluated all 100 cases and is not a holdout result.
- Five identity counterfactual pairs are included; this run does not establish fairness or absence of demographic bias.
- Dataset revision: `multi-role-synthetic-100-v2`; seed `20261010`.
- Dataset SHA-256: `0d41d41c11f55dee900b546936799262df67c45b9893f38ca63c1b8367475470`.
- Source revision: `53019bfacac03e0af88b3f31024dc6f3b6c36304`; manifests record `git_dirty=true`.
- Effective prompt SHA-256: `07c20d0408ad66b6d0633288f118942e95d765ac41b999017f5fc0ef77a82313`.
- Report source: per-batch `metrics.json`, `manifest.json`, and invocation journals under the gitignored `reports/` directory. This tracked document aggregates those 17 batch reports; raw per-case provider outputs are not committed.

## Metric definitions

- **Jev MAE:** mean absolute difference between the Jev fractional 0–4 score and the synthetic expected score, only where both are numeric. The overall denominator is 342 pairs.
- **Status agreement:** exact match between the produced criterion status and the synthetic reference status for accepted assessments. The status is part of the evidence/assessment output; this is not a Jev numeric-score metric.
- **Span Recall@K:** per criterion, recall of reference evidence spans in the ranked retrieval result at K; reported as the mean over the 476 criterion-level observations with at least one sufficient-evidence group.
- **Sufficient-evidence-group coverage:** fraction of those 476 retrieval observations where the initial/final evidence set contains every span in at least one reference group. It does not measure false-positive ranking quality.
- **Annotated citation precision:** citations in returned observations that match a reference-relevant span, divided by 603 annotated citations.
- **Correct abstention / false zero / unsupported score:** calculated over 157 synthetic references with no expected numeric score. Correct abstention also requires the expected status; a numeric zero is counted as false zero; any numeric score is unsupported.
- **Conflict agreement:** among 74 synthetic conflict references, the output must preserve `conflicting_evidence` and leave the numeric score null.

The aggregate metrics are pooled using their explicit denominators, except Recall@K and evidence-group coverage, which are the benchmark evaluator's mean over criterion-level observations. Metric implementation: [`benchmark/metrics.py`](../../services/backend/app/services/evaluation/benchmark/metrics.py).

## Limitations and appropriate use

This run has no independent HR/IT labels, protected holdout, real applicant CVs, comparative baseline, repeated trials, confidence intervals, or validated hiring outcomes. Its cases and labels share the same synthetic design process, and the prompt/source worktree was dirty. It can show that the live Jev-primary pipeline executes and reveal software failure modes on these fixtures; it cannot establish hiring accuracy, candidate-job matching quality, fairness, production readiness, or that Jev is better than another scorer. Do not call this a gold benchmark or use it to make hiring decisions.

Re-run the software tests and obtain a clean-source, independently labeled HR/IT evaluation before making model-quality or deployment claims.