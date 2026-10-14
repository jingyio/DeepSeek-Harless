import test from 'node:test';
import assert from 'node:assert/strict';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createAcceptanceGuard, validatePolicy } from '../src/adapters/dsh_acceptance_guard.ts';
import { createCollectionGate } from '../src/adapters/dsh_entry_motif.ts';
const root=join(tmpdir(),'sss-acceptance-test');
const policy={kind:'file_management',max_repairs:2,project_root:root,python:'python3',task_file:join(root,'.local/task.json'),delivery_root:join(root,'.local/delivery'),archive_root:join(root,'.local/acceptance')};
const signal=new AbortController().signal;
test('failed acceptance steers ordinary repair and only a subsequent valid check completes',async()=>{
 const observed=[];const guard=createAcceptanceGuard(policy,async(round,receipt,events)=>{observed.push({round,receipt,events});return {passed:round===1,errors:round===0?['wrong final directory']:[],repairable:true};});
 guard.observe({name:'mcp__file_management__submit_report'},{content:[{type:'text',text:'{"artifact":"actual-report"}'}]});
 const repair=await guard.stop([{type:'tool/result'}],signal);assert.equal(repair.repair,1);assert.match(repair.instruction,/普通DeepSeek Harness/);
 assert.equal(await guard.stop([],signal),null);assert.deepEqual(guard.state(),{repairs:1,checks:2,accepted:true});assert.equal(observed[0].receipt.artifact,'actual-report');
});
test('tool progress and another failed report cannot reset the two-repair ceiling',async()=>{
 const guard=createAcceptanceGuard(policy,async()=>({passed:false,errors:['failure'],repairable:true}));
 assert.equal((await guard.stop([],signal)).repair,1);guard.observe({name:'read'},{content:[]});
 assert.equal((await guard.stop([],signal)).repair,2);
 await assert.rejects(guard.stop([],signal),/bounded repair exhausted/);assert.equal(guard.state().repairs,2);
});
test('irreversible history and verifier errors stop without speculative model repair',async()=>{
 for(const result of [{passed:false,errors:['extra historical reads'],repairable:false},{fatal:true,passed:false,errors:['changed permissions']}]){
  const guard=createAcceptanceGuard(policy,async()=>result);await assert.rejects(guard.stop([],signal),/TASK_ACCEPTANCE/);assert.equal(guard.state().repairs,0);
 }
});
test('cancelled turns cannot start a verifier or another repair',async()=>{
 const controller=new AbortController();controller.abort();let calls=0;
 const guard=createAcceptanceGuard(policy,async()=>{calls++;return {passed:false,errors:[]};});
 assert.equal(await guard.stop([],controller.signal),null);assert.equal(calls,0);
});
test('repair cannot increase retries, substitute a verifier, or escape private scope',()=>{
 assert.throws(()=>validatePolicy({...policy,max_repairs:3}),/Invalid/);
 assert.throws(()=>validatePolicy({...policy,script:'/tmp/arbitrary.py'}),/Invalid/);
 assert.throws(()=>validatePolicy({...policy,task_file:'/tmp/other-task'}),/private/);
});
test('an acceptance repair disables active collection automation before another bypass',()=>{
 let failed='',normal=0;const controller={fail:reason=>{failed=reason;},propose:()=>{throw Error('must not bypass');}};
 const gate=createCollectionGate({}, {session_id:'session'},()=>{},()=>controller);
 assert.equal(gate.intercept({messages:[{source:{kind:'task-acceptance-repair'}}]},()=>++normal,true),1);
 assert.equal(failed,'acceptance_repair_requires_ordinary_harness');assert.equal(normal,1);
});
