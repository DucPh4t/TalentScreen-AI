# TalentScreen AI — HR/IT role-play on the draft Backend Python vacancy

Date: 2026-09-27 (Asia/Ho_Chi_Minh). The project user explicitly delegated both the HR and IT review roles to one AI assistant for this MVP review. Reviewer: one AI assistant, sequentially applying an HR process lens and an IT competency lens. This is a **delegated design decision**, not two statistically independent people, not a school authorization, not an HR blind label, and not a G2/G5/G7 signature. The actual JD, rubric and recruitment decision remain under the named university owners.

## Delegated decision

| Role applied by the assistant | Decision | Reason |
|---|---|---|
| HR process reviewer | **Approve the draft JD for sandbox and synthetic workflow rehearsal only. Withhold approval for an actual requisition.** | The job context and forbidden-attribute exclusions are usable, but the employing unit, real duties and terms are still unknown. The threshold and clarification workload have not been calibrated on applicants for this vacancy. |
| IT competency reviewer | **Approve the six-criterion rubric as a technical baseline for sandbox tests only. Withhold activation for real hiring.** | Structure, JD citations and anchors are coherent; actual task weighting, SQL anchor edge cases and the 70-point rule require review against the real position. |

Combined state: `approved_for_synthetic_rehearsal_only`. Do not set a production rubric version to `approved`, enter a person's name in `approved_by`, create two reviewer identities, or record a G2/G5/G7 PASS from this delegation. These would imply evidence or identities this review does not have. The assistant's role-play judgments may be used to find product defects and prepare questions for the real owners.

## Material reviewed

- Draft JD: `fixtures/seeds/jd-backend-python.vi.md`.
- Draft rubric: `fixtures/seeds/rubric-backend-python.v1.json`.
- Frozen synthetic rehearsal corpus: `fixtures/holdout_rehearsal/manifest.json`, 30 distinct one-line CV scenarios, 10 each in Vietnamese, English and mixed language.
- Per-case annotations: `private_storage/eval/simulated_hr_it_roleplay_2026-09-27.json` (local, ignored by Git, mode 0600). This file includes source hashes, all six outcomes/scores, source text quotes and a provenance flag. It deliberately does **not** use `hr_blind` as its origin.

## Simulated HR process review

**Sandbox verdict: acceptable as a review exercise. Real-vacancy approval: withheld.**

The JD names a concrete junior–middle Backend Python role and admits coursework, personal projects and community work on the same evidence basis as paid work. It explicitly excludes age, gender, hometown, school prestige, CV language and career gaps. Missing evidence leads to a clarification path rather than rejection. The reviewer can see the source JD requirement and CV evidence before deciding.

HR would still need to fill the actual employing unit, reporting owner, systems and duties, working conditions, contract terms, compensation, application period and applicant contact. HR must confirm that the six criteria describe this vacancy rather than a generic software role. The score is **documented evidence in a CV**, not an absolute measure of ability. A concise CV should be invited to clarify missing dimensions; neither `needs_clarification` nor `review_required` means "reject".

The seed recommendation policy is not ready for an operational advance decision. It requires evidence for all six criteria and a comparable score of at least 70 with three core floors. A candidate documented at level 2 across all six criteria receives only 50/100, although level 2 describes completing ordinary work. HR should first decide what the score should mean for a junior–middle interview invitation and estimate the time needed to review incomplete CVs. Do not tune the threshold on the frozen rehearsal corpus and then report performance on that same corpus.

## Simulated IT competency review

**Rubric structure: technically coherent for rehearsal; calibration and actual-job relevance still open.**

The six criterion IDs and weights (20/25/20/15/10/10) match the JD excerpts and sum to 100. Anchors 0–4 distinguish a narrow task from a complete function and from a trade-off with verification. The contract correctly separates an explicit score 0 from `insufficient_evidence` and `conflicting_evidence`. Python frameworks are interchangeable evidence; tool names alone do not earn points. No external portfolio URL should be fetched to fill a gap.

Items for a real IT lead to settle before approving:

1. Is API design correctly weighted above Python and SQL for the actual systems? Confirm with the vacancy owner and typical tasks, not with the candidate pool.
2. Are anchor 2 expectations attainable from a normal CV without forcing applicants to disclose internal implementation details? The answer may be a structured clarification question rather than a lower score.
3. For SQL anchors, state whether a transaction or index without an explicit query and post-change verification qualifies for level 2 or 3. In the rehearsal, `rehearsal_12` was held to level 1 because it says an execution plan was checked before adding an index but gives no measured result after the change.
4. Preserve the distinction between implementing an endpoint and modifying its authorization. A security change can be evidenced without inferring full API design ownership.
5. Add an interview check for source claims and boundaries: the CV is not proof that code worked, and AI must not turn a candidate's prompt-injection text into an instruction.

## Rehearsal annotations and policy behavior

This single assistant scored 30 synthetic cases against the seed anchors; it did not observe DeepSeek predictions or human decisions. The 180 criterion judgments comprise 48 `assessed`, 130 `insufficient_evidence` and 2 `conflicting_evidence`. Assessed anchors comprise two 0s, twenty-four 1s, seventeen 2s, four 3s and one 4. Weighted mean evidence coverage is 32% for Vietnamese, 24% for English and 33% for mixed-language cases. No case has full coverage, so all 30 receive the seed-policy `needs_clarification` recommendation. These are **designed stress cases**, not a representative applicant sample; the figures must not be presented as accuracy, fairness or expected production rates.

Edge-case decisions to carry into calibration:

| Case | Simulated reading |
|---|---|
| `rehearsal_04`, `19`, `24` | Lists of technologies and vague team participation provide no attributable task; all six criteria remain unknown. |
| `rehearsal_09` | Explicitly says no Python application work and no practical SQL use; two scores of 0 are supported, while unrelated omissions remain unknown. |
| `rehearsal_10` | The FastAPI endpoint is narrow evidence; the embedded demand to assign all 4s is ignored as untrusted CV content. |
| `rehearsal_18` | Claims of owning a Python payment endpoint and doing only CSS in the same project conflict; Python and API scores remain null pending clarification. |
| `rehearsal_28` | Earlier frontend-only work and later Python endpoint work are a chronology, not a contradiction. |
| `rehearsal_29` | The Vietnamese and English sentences describe one FastAPI task; do not double-count it. |
| `rehearsal_30` | The portfolio link is not fetched; a skills list does not establish the missing work. |

The private annotations use each one-line synthetic CV as the source quote. This is sufficient to trace this rehearsal but coarser than the span-level citations required from real uploaded CVs. Some anchors remain judgment calls; a separate human rater must be able to disagree without seeing this file.

## Gate disposition and next evidence

- **G2 remains pending.** Only the actual HR owner and IT lead can approve a JD/rubric version and hiring policy for a real requisition. This role-play can be attached as pre-read, never recorded as their approval.
- **G5 remains pending.** These are one assistant's synthetic judgments, not two independent human labels or real-vacancy shadow results. The assistant has now seen this rehearsal holdout; do not treat it as a blind evaluation of this assistant or a model prompted with these annotations. A future operational holdout must be separately frozen.
- **G7 remains pending.** A simulated HR walkthrough does not establish that the actual HR team can use the application.

Next live calibration should have two people independently mark evidence status, quote and anchor before opening any AI result; retain both original ratings and a separately adjudicated version. Run the real shadow on authorized applications for the actual approved vacancy, then inspect disagreements by criterion and CV language before any gate sign-off.
