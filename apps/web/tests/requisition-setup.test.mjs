import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

const source = await readFile(new URL('../src/lib/requisition-setup.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
const { getRequisitionSetup } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`);
const requisition = { current_jd_version_id: 'jd-1', current_rubric_version_id: 'rubric-1' };
const approved = { id: 'rubric-1', status: 'approved', jd_version_id: 'jd-1' };

// A missing prerequisite must not send the HR user to an action the API rejects.
test('missing JD routes to setup and prevents opening intake', () => {
  const state = getRequisitionSetup({ ...requisition, current_jd_version_id: null }, [approved]);
  assert.equal(state?.ready, false);
  assert.equal(state?.action, 'setup');
  assert.equal(state?.blocker, 'missing_jd');
});
test('no rubric routes to criteria setup instead of an upload instruction', () => {
  const state = getRequisitionSetup({ ...requisition, current_rubric_version_id: null }, []);
  assert.equal(state?.ready, false);
  assert.equal(state?.action, 'setup');
  assert.equal(state?.blocker, 'missing_rubric');
});
test('a draft rubric still requires explicit approval', () => {
  const state = getRequisitionSetup({ ...requisition, current_rubric_version_id: null }, [{ ...approved, status: 'draft' }]);
  assert.equal(state?.ready, false);
  assert.equal(state?.blocker, 'unapproved_rubric');
});
test('an unapproved current rubric cannot enable the open button', () => {
  assert.equal(getRequisitionSetup(requisition, [{ ...approved, status: 'draft' }])?.ready, false);
});
test('rubric for an older JD cannot enable intake for the current JD', () => {
  const state = getRequisitionSetup(requisition, [{ ...approved, jd_version_id: 'jd-0' }]);
  assert.equal(state?.ready, false);
  assert.equal(state?.blocker, 'outdated_rubric');
});
test('a lookup outage requires reload even if stale approved metadata remains', () => {
  const state = getRequisitionSetup(requisition, [approved], true);
  assert.equal(state?.ready, false);
  assert.equal(state?.action, 'reload');
});
test('a missing current rubric record fails closed instead of trusting its ID', () => {
  assert.equal(getRequisitionSetup(requisition, [])?.ready, false);
});
test('current approved rubric enables intake even when a newer draft is being edited', () => {
  const state = getRequisitionSetup(requisition, [{ ...approved, id: 'new-draft', status: 'draft' }, approved]);
  assert.equal(state?.ready, true);
  assert.equal(state?.action, 'open');
  assert.equal(state?.blocker, null);
});
