import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import ts from 'typescript';
let view={};
try {
  const source=await readFile(new URL('../src/lib/reranking-summary.ts',import.meta.url),'utf8');
  const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
  view=await import(`data:text/javascript;base64,${Buffer.from(js).toString('base64')}`);
} catch(e) {if(e.code!=='ENOENT')throw e;}
test('only an applied incomplete evidence selection requests HR review',()=>{
  for(const s of [undefined,null,{mode:'off',applied:false,needs_evidence_review:true},{mode:'shadow',applied:false,needs_evidence_review:true},{mode:'rerank',applied:true,needs_evidence_review:false}]){
    assert.equal(view.evidenceReviewMessage?.(s),null);
  }
  assert.equal(view.evidenceReviewMessage?.({mode:'rerank',applied:true,needs_evidence_review:true}),
    'Một số bằng chứng chưa được đưa vào đánh giá. Hãy đối chiếu CV hoặc yêu cầu AI tìm thêm trước khi quyết định.');
});
