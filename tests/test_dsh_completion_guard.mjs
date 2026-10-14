import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { apply, createReceiptGuard, verifyReceipt, digest } from '../src/adapters/dsh_completion_guard.ts';

const policy = {tool:'mcp__demo__publish',statuses:['preview','needs_review'],max_continuations:2,artifact_root:tmpdir()};
test('only the named successful hashed receipt completes; pending/error/plain text never do',()=>{
  const guard=createReceiptGuard(policy,()=>true);
  const result=body=>({content:[{type:'text',text:JSON.stringify(body)}]});
  guard.observe({name:'mcp__demo__read'},result({status:'preview'}));
  guard.observe({name:policy.tool},{...result({status:'preview'}),isError:true});
  guard.observe({name:policy.tool},result({status:'pending_claim_decisions',pending_claim_ids:['claim:A']}));
  assert.equal(guard.stop().continuation,1);assert.deepEqual(guard.state().pending_claim_ids,['claim:A']);
  guard.observe({name:policy.tool},result({status:'preview'}));
  assert.equal(guard.stop(),null);
});
test('bounded exhaustion cannot report completion or reset on tool progress',()=>{
  const guard=createReceiptGuard(policy,()=>false);
  assert.equal(guard.stop().continuation,1);assert.equal(guard.stop().continuation,2);
  assert.throws(()=>guard.stop(),/TASK_MISSING_DELIVERY_RECEIPT/);
  assert.equal(guard.state().delivered,false);
});
test('artifact digest, location and symlink guards are actual file checks',()=>{
  const root=mkdtempSync(join(tmpdir(),'sss-receipt-')),artifact=join(root,'result.json');
  const payload={schema_version:1,message:'科研证据',nested:{b:2,a:1}};
  writeFileSync(artifact,JSON.stringify(payload));const receipt={artifact,artifact_sha256:digest(payload)};
  try {
    assert.equal(verifyReceipt(receipt,root),true);
    assert.equal(verifyReceipt({...receipt,artifact_sha256:'0'.repeat(64)},root),false);
    assert.equal(verifyReceipt(receipt,join(root,'other')),false);
    const link=join(root,'link.json');symlinkSync(artifact,link);
    assert.equal(verifyReceipt({...receipt,artifact:link},root),false);
    writeFileSync(artifact,'{"changed":true}');assert.equal(verifyReceipt(receipt,root),false);
  }finally{rmSync(root,{recursive:true});}
});
test('agent state and plugin steering are isolated, cancellation makes no follow-up',()=>{
  let created;apply({on(event,fn){assert.equal(event,'agent/created');created=fn;}},policy);
  const agent=id=>{const handlers={},messages=[];const a={session:{id},ctx:{on(e,f){handlers[e]=f;}},steer(m){messages.push(m);}};created({agent:a});return{a,handlers,messages};};
  const x=agent('one'),y=agent('two');
  x.handlers['agent/turn-stopping']({signal:{aborted:true}});assert.equal(x.messages.length,0);
  x.handlers['agent/turn-stopping']({signal:{aborted:false}});
  assert.equal(x.messages[0].source.kind,'task-completion-guard');assert.equal(x.messages[0].source.session_id,'one');
  assert.equal(x.messages[0].source.model_requests_skipped_verified,0);assert.equal(y.messages.length,0);
  y.handlers['agent/turn-stopping']({signal:{aborted:false}});assert.equal(y.messages[0].source.continuation,1);
});
