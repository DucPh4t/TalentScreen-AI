export type ScreeningOutcome = 'advance' | 'request_information' | 'not_advance';
export type ClarificationResolution = 'candidate_confirmed_no_experience' | 'no_response_after_contact' | 'independent_evidence_based_reason';
export const outcomeLabels: Record<string, string> = {
  advance: 'Mời phỏng vấn', request_information: 'Chờ bổ sung thông tin', not_advance: 'Không tiếp tục', propose_hire: 'Đề xuất tuyển',
};
export function screeningPayload(result: {kind:'assessment_run'|'hr_revision';id:string}, reviewed: string[], outcome: ScreeningOutcome, reason: string, previous: string | null, rubricId: string, clarificationResolution?: ClarificationResolution | null) {
  return { effective_result: result, reviewed_criterion_ids: reviewed, acknowledged:true, outcome, reason:reason.trim(),
    clarification_resolution: clarificationResolution || null,
    expected_previous_decision_id:previous, expected_rubric_version_id:rubricId };
}
export function workflowTab(stage: string): 'sanitization'|'assessment'|'revision'|'interview' {
  if (['awaiting_upload','reading','needs_review'].includes(stage)) return 'sanitization';
  if (['waiting_information','not_advanced'].includes(stage)) return 'revision';
  if (['awaiting_interview','interview_completed','interview_review'].includes(stage)) return 'interview';
  return 'assessment';
}
export function interviewConsensus(criteria: Array<{id:string;label?:string}>, cards: Array<{status:string;is_stale:boolean;criteria:Array<{criterion_id:string;outcome:string;score:number|null}>}>) {
  const current = cards.filter(card=>card.status === 'finalized' && !card.is_stale);
  return criteria.map(criterion=> {
    const entries = current.flatMap(card=>card.criteria.filter(entry=>entry.criterion_id === criterion.id));
    const scores = entries.filter(entry=>entry.outcome === 'assessed' && entry.score !== null).map(entry=>entry.score as number);
    return {criterion_id:criterion.id,label:criterion.label || criterion.id,scores,
      unobserved:entries.filter(entry=>entry.outcome === 'not_observed').length,
      conflicting:entries.filter(entry=>entry.outcome === 'conflicting_evidence').length,
      disagreement:scores.length > 1 && Math.max(...scores)-Math.min(...scores) >= 2};
  });
}

// Keep text and its optimistic token together until saved or explicitly reloaded.
export function preserveEditBase<T>(original:T, incoming:T, dirty:boolean):T {
  return dirty ? original : incoming;
}
export async function refreshInterviewCards<T>(client:{getInterviewScorecards:(applicationId:string)=>Promise<T[]>}, applicationId:string):Promise<T[]> {
  return client.getInterviewScorecards(applicationId);
}
