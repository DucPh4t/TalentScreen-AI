# JD rubric drafting repair — 2026-10-08

## Problem and confirmed causes

The JD-to-rubric action returned `RUBRIC_DRAFT_UNAVAILABLE` even when the
provider accepted the request. The error hid several distinct failure modes.
Live diagnostics used the already reviewed JD and the configured provider;
only response metadata was inspected or logged.

- With thinking unspecified, one response exhausted 6,000 completion tokens
  entirely on reasoning, returned no JSON content, and ended with `length`.
- After disabling thinking, another response produced weights totaling 110
  and changed the wording of ten JD quotations. Canonical validation correctly
  rejected it.
- Adding the schema initially encouraged verbose optional evidence arrays:
  another response reached 6,000 tokens with 107 optional evidence-field
  occurrences and was truncated.
- The first compact response completed, but its zero-point anchors described
  absence of claims. That required a further prompt and validation correction.

## Implemented contract: `jd-competencies-v6`

1. Explicitly disable thinking for this JSON drafting call. Retain the
   6,000-token allowance, 45-second timeout, budget ledger and single-call flow.
2. Send the internal proposal JSON Schema. Anchor proposals contain only a
   strict integer score and a concise description, bounded to 400 characters.
   Canonical output still provides the existing optional arrays as empty lists.
3. Assign stable passage IDs to exact non-empty JD lines. The model selects
   source IDs; the server resolves original quotations. Unknown IDs and
   model-supplied quotations are rejected. Markdown and internal whitespace
   remain intact.
4. Interpret proposed weights as relative priorities. Normalize using constrained
   largest remainder, with a minimum of one percent and stable ties. The final
   canonical weights must total 100. This is a draft allocation for HR review,
   not evidence that the weights or thresholds have been calibrated.
5. Enforce strict policy integers and core minima from 0 to 4 before canonical
   validation. Booleans, numeric strings and integral floats cannot silently
   become policy scores. The public API DTO remains unchanged.
6. Reject zero anchors that use the observed Vietnamese/English absence phrases.
   Prompt level zero as direct evidence of an incorrect action or deficient
   result; missing CV evidence remains `score=null` in candidate assessment.
7. Classify provider authentication, quota, timeout, truncation, rate limit and
   schema failures separately. Client errors and job logs contain fixed safe
   messages, never raw model JSON or credentials. Invalid drafts are not saved.

The existing JD egress review, canonical anti-discrimination checks, source
validation, Owner approval and post-call JD-version guard remain in force.

## Verification

- Full backend regression: **297 passed**, using the disposable PostgreSQL/
  pgvector database created by `scripts/test_backend_isolated.sh`. All existing
  Alembic migrations were applied to the empty test database.
- Frontend regression: **16 passed** with `npm test` in `apps/web`.
- New failure cases were reproduced before fixes: default reasoning contract,
  invalid sources, weight allocation, policy coercion, optional anchor arrays
  and absence-based zero anchors. Provider failure tests verify no draft is saved.
- Final live browser action: `POST .../rubrics/draft-from-jd` returned **201**
  with `DeepSeekHTTPXProvider`, model `deepseek-flash`, prompt v6.
- Recorded generation: **9.48 seconds**, **3,304 input / 2,666 output tokens**;
  ledger cost **USD 0.0041904** according to the configured rate card.
- Persisted draft version 2: **9 criteria**, **100% total weight**, **22 exact
  source citations**, all anchors 0–4, and no detected absence phrase at level 0.
- The browser displays the draft, its citations and review acknowledgement;
  approval stays disabled until that acknowledgement is checked.
- Code review found and closed one policy-coercion issue; final review reported
  no blocking findings.

No candidate data was sent as part of this repair. No schema migration is
required. Existing approved rubrics are preserved; HR must review and approve
new draft version 2 before it becomes the active rubric.

## Limits

This live check establishes that the reported JD can now generate and persist
an explainable draft. It does not establish reliability across every JD or
validate hiring accuracy. Exact source membership does not prove semantic
relevance, and phrase checks are not a complete semantic fairness validator.
HR still reviews competency choices, anchors, weights and core floors. Provider
errors can recur; the system reports the classified cause and fails closed.
Uncertain billed outcomes remain reserved in the ledger rather than being
incorrectly treated as free requests.
