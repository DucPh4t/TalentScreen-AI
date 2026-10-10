import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

// Compile the real TS helper without adding a second test framework or TS loader.
const source = await readFile(new URL('../src/lib/application-list.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { filterApplicationList, applicationNextTask, shortlistEvidenceFallback } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`);
const applications = [
  { id: 'a', public_label: 'CAND-01', status: 'active', current_assessment_run_id: 'old-run' },
  { id: 'b', public_label: 'CAND-02', status: 'active' },
  { id: 'c', public_label: 'CAND-03', status: 'active' },
];
const queue = [
  { application_id: 'a', workflow_stage: 'ready_for_ai', sanitized_status: 'approved', risk_flags: [] },
  { application_id: 'b', workflow_stage: 'needs_review', sanitized_status: 'draft', risk_flags: ['contact_data'] },
  { application_id: 'c', workflow_stage: 'awaiting_decision', sanitized_status: 'approved', risk_flags: [] },
];

test('filters by trimmed case-insensitive candidate code without changing FIFO order', () => {
  const result = filterApplicationList(applications, queue, { search: '  cand-0  ' });
  assert.deepEqual(result.map(row => row.id), ['a', 'b', 'c']);
  assert.notStrictEqual(result, applications);
});
test('combines task and CV-review filters; a no-match query returns an empty result', () => {
  assert.deepEqual(filterApplicationList(applications, queue, { pendingOnly: true }).map(row => row.id), ['b']);
  assert.deepEqual(filterApplicationList(applications, queue, { stage: 'awaiting_decision', search: '02' }), []);
});
test('queue outage preserves candidate access instead of hiding rows behind stale filters', () => {
  assert.deepEqual(filterApplicationList(applications, [], { stage: 'needs_review', pendingOnly: true, queueUnavailable: true }).map(row => row.id), ['a', 'b', 'c']);
});
test('an old assessment pointer never changes a ready-for-AI task into a current result', () => {
  const task = applicationNextTask(applications[0], queue[0]);
  assert.equal(task.label, 'Chuẩn bị phân tích');
  assert.equal(task.hint, 'Đối chiếu CV với rubric hiện hành.');
});
test('independent reviewer sees no model stage or recommendation', () => {
  assert.deepEqual(applicationNextTask(applications[2], queue[2], true), {
    label: 'Chấm độc lập', hint: 'Rà soát bằng chứng trước khi xem gợi ý AI.', tone: 'neutral',
  });
});
test('missing queue and deleted applications do not invent a successful assessment', () => {
  assert.equal(applicationNextTask(applications[0], undefined).label, 'Chưa tải được trạng thái');
  assert.equal(applicationNextTask({ ...applications[0], status: 'tombstoned' }, queue[0]).label, 'Hồ sơ không còn hoạt động');
});

// No missing-criteria array is not proof of complete evidence when no current run exists.
test('unassessed or missing-coverage shortlist never presents evidence as complete', () => {
  assert.equal(shortlistEvidenceFallback?.({ tier: 'not_assessed', coverage: null }), 'Chưa có đánh giá hiện hành');
  assert.equal(shortlistEvidenceFallback?.({ tier: 'recommend', coverage: null }), 'Chưa có đánh giá hiện hành');
});
test('partial coverage stays explicit even when the missing-criteria array is empty', () => {
  assert.equal(shortlistEvidenceFallback?.({ tier: 'below_threshold', coverage: .5 }), 'Bằng chứng còn thiếu');
  assert.equal(shortlistEvidenceFallback?.({ tier: 'recommend', coverage: 1 }), 'Không có mục cần làm rõ được ghi nhận');
});
