import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyResponse } from '../scripts/evaluate-citation-shadow.mjs';

test('whole request opportunity needs exactly the same arguments and no semantic text',()=>{
  const plan=[{tool:'read_citations',arguments:{citation_id:'source-owned'}}];
  const call={type:'tool-call',name:'read_citations',arguments:JSON.stringify({citation_id:'source-owned'})};
  assert.equal(classifyResponse([call],plan),'closed_tool_continuation');
  assert.equal(classifyResponse([call,{type:'text',text:'Need to decide which publication version applies'}],plan),'text_or_semantic_review');
  assert.equal(classifyResponse([{...call,arguments:JSON.stringify({citation_id:'source-other'})}],plan),'mixed_or_different_tools');
  assert.equal(classifyResponse([call,{type:'tool-call',name:'bash',arguments:'{}'}],plan),'mixed_or_different_tools');
  assert.equal(classifyResponse([call],[]),'no_candidate');
});

test('parallel request comparison permits permutation but preserves multiplicity',()=>{
  const plan=[{tool:'read',arguments:{id:'a'}},{tool:'read',arguments:{id:'b'}}];
  const calls=plan.slice().reverse().map(p=>({type:'tool-call',name:p.tool,arguments:p.arguments}));
  assert.equal(classifyResponse(calls,plan),'closed_tool_continuation');
  assert.equal(classifyResponse([calls[0],calls[0]],plan),'mixed_or_different_tools');
});
