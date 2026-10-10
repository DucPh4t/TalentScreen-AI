# Annotator guide: independent CV evidence labels

## Before annotation

- Use only the locally approved source package assigned to you.
- Read the frozen JD, competency criterion, scoring anchors, and canonical sanitized CV text.
- Do not open AI rankings, scores, explanations, prompts, or previous reviewers' labels.
- Confirm the JD/criterion text was authored independently of the CV. Flag any query that appears copied from a CV; do not label it until corrected.
- Use the supplied opaque candidate/JD keys. Do not add names, email, phone, address, age, gender, photo, school name, or other identity details to notes.
- Each unit is labeled independently by one HR reviewer and one IT reviewer. Record only the assigned opaque reviewer key and role.

## Retrieval relevance

Judge every candidate in the assigned query pool:

- `0`: no CV evidence relevant to this JD competency.
- `1`: weak or incidental evidence; the skill is mentioned without enough context to show application.
- `2`: relevant evidence with partial scope, recency, ownership, or outcome.
- `3`: direct evidence that closely matches the competency and requested scope.

For grades 1–3, select the shortest exact source span that supports the grade. Grade 0 must have no evidence span. Judge task evidence, not identity, prestige, inferred age, or assumptions about ability.

## Rubric assessment

Choose exactly one:

- `supported`: the CV directly supports the criterion at the selected score anchor.
- `partial`: the CV supports some, but not all, of the criterion/scope.
- `not_evidenced`: the CV has no assessable statement for this criterion. Set score to `null` and provide no evidence. Do not interpret this as lack of ability.
- `contradicted`: explicit CV evidence conflicts with the claim being evaluated. Cite the conflicting text and use the approved scoring anchor; do not invent a penalty.
- `conflicting_evidence`: cite at least two exact spans that materially disagree about the same scoped claim, set score to `null`, and explain the disagreement for adjudication. Do not use this for missing evidence or collapse it into `contradicted`.

Select a 0–4 score only when evidence is present and an anchor applies. Quote the exact text and record zero-based start/end character offsets in the canonical text. Check that `end - start` equals quote length. Preserve negation, dates, units, and ownership context; do not paraphrase evidence into a quote.

## Disagreement and adjudication

Submit individual labels before discussion. Do not overwrite them after seeing another label. A separate adjudicator records their opaque key, final label, and a concise reason whenever status, score, or exact evidence differs. Preserve uncertainty and missing evidence explicitly. Never ask an LLM to create, reconcile, or fill in gold labels.

## Escalate

Stop and contact the data owner if a record appears to contain unredacted identity data, if a source's permission is unclear, if text extraction has shifted offsets, or if the rubric/query is ambiguous. Do not copy questionable content into chat, tickets, or logs.
