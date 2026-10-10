import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';
let workflow = {};
try {
  const source = await readFile(new URL('../src/lib/hr-workflow.ts', import.meta.url), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
  workflow = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`);
} catch (e) { if(e.code !== 'ENOENT') throw e; }

test('screening payload binds decision replacement and rubric to the selected evidence result', () => {
  assert.deepEqual(workflow.screeningPayload?.({ kind:'hr_revision',id:'hr-2' }, ['react','testing'], 'advance', '  Đã đối chiếu đầy đủ bằng chứng về năng lực.  ', 'decision-1', 'rubric-2'), {
    effective_result:{kind:'hr_revision',id:'hr-2'}, reviewed_criterion_ids:['react','testing'], acknowledged:true,
    outcome:'advance',reason:'Đã đối chiếu đầy đủ bằng chứng về năng lực.',clarification_resolution:null,expected_previous_decision_id:'decision-1',expected_rubric_version_id:'rubric-2'
  });
  assert.equal(workflow.screeningPayload?.({ kind:'assessment_run',id:'run-1' }, ['python_backend'], 'not_advance', 'Đã xác minh với ứng viên và lưu kết luận rõ ràng.', 'decision-2', 'rubric-3', 'candidate_confirmed_no_experience')?.clarification_resolution, 'candidate_confirmed_no_experience');
});
test('waiting information and rejection route to HR follow-up instead of interview', () => {
  assert.equal(workflow.workflowTab?.('waiting_information'), 'revision');
  assert.equal(workflow.workflowTab?.('not_advanced'), 'revision');
  assert.equal(workflow.workflowTab?.('awaiting_interview'), 'interview');
  assert.equal(workflow.workflowTab?.('needs_review'), 'sanitization');
});
test('summary ignores stale cards and never turns unobserved evidence into a zero score', () => {
  const rows = workflow.interviewConsensus?.([{id:'design',label:'Thiết kế'}], [
    {is_stale:false,status:'finalized',criteria:[{criterion_id:'design',outcome:'assessed',score:3}]},
    {is_stale:false,status:'finalized',criteria:[{criterion_id:'design',outcome:'not_observed',score:null}]},
    {is_stale:true,status:'finalized',criteria:[{criterion_id:'design',outcome:'assessed',score:0}]}
  ]);
  assert.deepEqual(rows, [{criterion_id:'design',label:'Thiết kế',scores:[3],unobserved:1,conflicting:0,disagreement:false}]);
});
test('large interviewer disagreement is visible without inventing a hiring recommendation', () => {
  const rows = workflow.interviewConsensus?.([{id:'react',label:'React'}], [0,3].map(score=>({is_stale:false,status:'finalized',criteria:[{criterion_id:'react',outcome:'assessed',score}]})));
  assert.equal(rows?.[0]?.disagreement, true);
  assert.deepEqual(rows?.[0]?.scores, [0,3]);
});

test('dirty scorecard and plan edits retain the original optimistic version during refresh', () => {
  const original = {id:'card-1',row_version:1,source_hash:'source-1'};
  const newer = {id:'card-1',row_version:2,source_hash:'source-1'};
  assert.deepEqual(workflow.preserveEditBase?.(original,newer,true),original);
  assert.deepEqual(workflow.preserveEditBase?.(original,newer,false),newer);
});
test('saving own card reloads the newly unblinded panel cards from the server', async () => {
  const expected = [{id:'own',status:'finalized'},{id:'peer',status:'finalized'}];
  const calls = [];
  const client = {getInterviewScorecards:async applicationId=>{calls.push(applicationId);return expected;}};
  const result = await workflow.refreshInterviewCards?.(client,'application-1');
  assert.deepEqual(result,expected);
  assert.deepEqual(calls,['application-1']);
});
