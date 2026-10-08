# HR screening and interview workflow B

Approved in chat on 2026-10-08: implement option B from the workflow audit.

## Scope
- Screening decision means invite / request information / stop; it is not an offer.
- HR can override AI with one reason and supersede a decision with optimistic concurrency.
- One acknowledgement replaces three repeated attestations; criterion review remains explicit, private, saved by source version, and invalidated on source changes.
- Waiting for candidate information remains actionable; outdated decisions never conceal a changed CV/JD/rubric.
- Interview has preparation / scorecard / summary views in one tab, responsive to mobile.
- Preparation stores round, label, focus criteria, assigned interviewers, schedule/channel/link; questions can be edited through existing versioned revisions.
- Interview plans may be prepared before inviting. An invitation cannot be approved without current advance decision and real scheduling data, with no placeholders.
- Scorecards remain separate from AI scores; absent observations remain null. Submission requires assigned focus criteria, or an explicit explanation for unobserved focus criteria. Corrections preserve history and do not pretend a new interview occurred.
- Interviewers submit independently; an owner who interviews sees others' ratings only after submitting their own.
- Round conclusions require all assigned interviewers' current submitted cards and reference their versions. Outcomes: next round / additional evidence / not continue / propose hire. Propose hire is advisory and creates no offer.
- AI question generation remains grounded in approved CV and dynamic rubric. Reuse existing providers and spans, no new LLM or email-sending integration.
- Audit, source freshness, privacy, role authorization and cost bounds remain server enforced.

## Non-goals
Calendar sync, automatic email delivery, automatic hiring decisions, offers and a full ATS.
