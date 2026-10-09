# Jev-primary synthetic seed dataset v1

This is a **provisional synthetic contract/evaluation seed**, not a validated hiring benchmark. Every job description and CV snippet is invented for this fixture. `expected.jsonl` was drafted by an AI assistant and requires independent HR and IT review before its labels may be called expert-approved.

## Files and model boundary

- `role_specs.json`: five fictional IT job descriptions, dynamic criteria, and a shared draft 0–4 evidence anchor scale.
- `cases.jsonl`: ten fictional, already-sanitized CV inputs. This is the only case data intended for a model request, together with the matching role spec.
- `expected.jsonl`: provisional expected criterion status, anchor score, allowed evidence spans, and evidence-grounded rationale. **Never include this file in model context.**
- `manifest.json`: dataset scope, label provenance, adjudication state, and file hashes.

The ten cases cover Node/NestJS Backend, AI/ML, .NET Full-stack, Android, and Java/Spring Backend, with Vietnamese, English, and mixed-language text. Cases intentionally include clear evidence, sparse/tool-list-only evidence, a guided contribution, and contradictory claims. Missing and conflicting evidence use `null`; neither is a zero.

Scores are per-criterion documentary evidence anchors, not verified skill, hiring recommendations, probabilities, or a universal candidate ranking. Exact Jev probability distributions are deliberately not part of the gold labels. Compare model outputs to the reviewed anchor/status/citation labels and report probabilities separately.

## Required review before benchmark use

Have HR and IT reviewers independently check the same frozen inputs and expected labels without seeing model outputs or each other's ratings. Record their source-span citations and reason for every score; use `null` for insufficient or conflicting evidence. Preserve their original labels and adjudication separately. Any changes require a new dataset revision and regenerated hashes. Since this fixture is committed/public and authored with assistance from this model, it is **not a blind holdout** and cannot pass a real-hiring readiness gate.

No real CV, personal data, API key, external model call, or hiring decision is included in this seed.
