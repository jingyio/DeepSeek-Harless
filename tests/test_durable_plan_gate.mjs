import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';import {join,dirname} from 'node:path';import {createHash} from 'node:crypto';
import {FileJob,digest} from '../src/adapters/file_workflow_job.ts';
import {createJobPlanGuard} from '../src/adapters/dsh_job_plan_gate.ts';
import {createCollectionGate} from '../src/adapters/dsh_entry_motif.ts';
import {markAgentLoopRequest} from '@deepseek-ai/dsh-llm';
const runtimeNames=['src/adapters/dsh_entry_motif.ts','src/adapters/dsh_job_plan_gate.ts','src/motif_core/authorized_plan_policy.ts','src/motif_core/online_skill_runtime.mjs'];
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
function fixture(){
 const root=mkdtempSync(join(tmpdir(),'sss-durable-plan-'));
 const save=(n,v)=>{const p=join(root,n);mkdirSync(dirname(p),{recursive:true});writeFileSync(p,JSON.stringify(v));return p;};
 const input={task_id:'t',write_grant:{max_actions:2,allowed_ops:['move'],source_paths:['a.txt'],destination_prefixes:['out/'],allow_restore:true},initial_snapshot:{'a.txt':'a'.repeat(64)}};
 const file=save('.local/task.json',input),path=join(root,'.local/job.json'),delivery=join(root,'.local/delivery'),job=new FileJob(root,path);
 job.apply('init',{task_file:file,delivery_root:delivery,execution_version_sha256:'b'.repeat(64),limits:{budget_usd:1,max_requests:3,max_steps:3,max_output:1000,max_repairs:2}});
 const policy=save('.local/library/libraries/recovery15/plan-policy.json',{});
 const deps={'service.py':sha(save('service.py','frozen service'))},runtime=Object.fromEntries(runtimeNames.map(n=>[n,sha(save(n,'frozen runtime'))]));
 const lock=save('.local/library/library-lock.json',{groups:{recovery15:{execution_version_sha256:'b'.repeat(64),plan_component_version_sha256:'c'.repeat(64),dependencies:deps}},artifacts:[{kind:'plan',group:'recovery15',path:'recovery15/plan-policy.json',sha256:sha(policy)}]});
 const binding=save('.local/binding.json',{format:'sss-durable-plan-binding-v1',schema_version:1,job_file:path,task_sha256:sha(file),delivery_root:delivery,service_execution_version_sha256:'b'.repeat(64),limits_sha256:digest(job.load().limits),library_lock_file:lock,library_lock_sha256:sha(lock),policy_sha256:sha(policy),runtime_source:runtime});
 const task={task_id:'t',input_version:digest(input),grant:input.write_grant,grant_sha256:digest(input.write_grant),snapshot_sha256:digest(input.initial_snapshot),execution_version_sha256:'c'.repeat(64)};
 const rows=[],guard=()=>createJobPlanGuard(root,binding,policy,task,r=>rows.push(r));return {root,save,file,path,job,delivery,policy,lock,binding,task,rows,guard};
}
test('explicit activation preserves every original limit/counter and survives cold reconstruction',()=>{
 const f=fixture(),before=f.job.load();assert.equal(f.guard().activate(),true);assert.equal(f.guard().allow(),true);
 const now=f.job.load();for(const k of ['limits','requests','steps','spent_units','repairs','checks','pending','task_sha256','execution_version_sha256'])assert.deepEqual(now[k],before[k]);
 assert.equal(now.motif_disabled,false);assert.equal(f.guard().activate(),true);
});
for(const reason of ['revoke','cancel','pause','repair','budget','requests','pending','task','source','lock','binding','component','service'])test('automatic effects stop on '+reason,()=>{
 const f=fixture(),g=f.guard();assert.equal(g.activate(),true);
 if(['revoke','cancel','pause','repair'].includes(reason))f.job.apply(reason);
 else if(['budget','requests','pending'].includes(reason)){
   const s=f.job.load();if(reason==='budget')s.spent_units=1000000000;else if(reason==='requests')s.requests=3;else s.pending={1:{amount:1}};f.job.commit(s,'fixture_limit',{});
 }else if(reason==='task')writeFileSync(f.file,'{}');
 else if(reason==='source')writeFileSync(join(f.root,'service.py'),'changed');
 else if(reason==='lock')writeFileSync(f.lock,'{}');
 else if(reason==='binding')writeFileSync(f.binding,'{}');
 else if(reason==='component')f.task.execution_version_sha256='d'.repeat(64);
 else {const s=f.job.load();s.execution_version_sha256='d'.repeat(64);f.job.commit(s,'fixture_version',{});}
 assert.equal(g.allow(),false);assert.ok(f.rows.some(r=>r.kind==='durable_plan_deferred'));
 if(reason==='binding')assert.throws(()=>f.guard(),/invalid durable plan binding/);
 else if(reason!=='task')assert.equal(f.guard().activate(),false);
});
test('semantic failure disables Motif durably without charging an acceptance repair or resetting costs',()=>{
 const f=fixture(),g=f.guard();g.activate();g.disable('actual_tool_failed');const s=f.job.load();assert.equal(s.motif_disabled,true);assert.equal(s.repairs,0);assert.equal(f.guard().activate(),false);
});
for(const reason of ['schema','prompt','repair'])test('session gate rejection remains disabled on cold reconstruction: '+reason,()=>{
 const f=fixture(),guard=f.guard();guard.activate();const prompt='original task';
 const task={session_id:'s',prompt_sha256:createHash('sha256').update(prompt).digest('hex')};
 const controller={done:false,halted:false,pending:0,armed:true,fail(){this.halted=true;},observe(){},propose(){this.halted=true;return [];}};
 const gate=createCollectionGate({},task,()=>{},()=>controller,guard);
 const messages=[{id:'user-1',role:'user',source:{kind:'user'},content:[{type:'text',text:reason==='prompt'?'changed question':prompt}]}];
 if(reason==='repair')messages.push({role:'user',source:{kind:'task-acceptance-repair'},content:[]});
 const options=markAgentLoopRequest({sessionId:'s',messages,tools:[]});let forwarded=0;
 gate.intercept(options,()=>{forwarded++;return 'ordinary harness';},true);
 assert.equal(forwarded,1);assert.equal(f.job.load().motif_disabled,true);assert.equal(f.guard().activate(),false);
});
