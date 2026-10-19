import test from 'node:test';import assert from 'node:assert/strict';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {validateScript,createScriptController} from '../src/adapters/dsh_learned_script.ts';
const prefix='mcp__file_management__',hex='a'.repeat(64),names=['read_task','list_files','pin_file','read_file','hash_files','preview_actions','execute_plan','submit_report'];
function fixture(){
 const spec={objective:'copy sources',report_contract:{kind:'task_result'},initial_snapshot:{'.experiment-copy':hex,'source/a.txt':hex},workflow_contract:{workflow_id:'FM17',source_paths:['source/a.txt'],destination_prefixes:['backup-set/','recovery-drill/'],required_reads:[],context_paths:[]},allowed_operations:['copy']};
 const s={format:'sss-learned-copy-script-v1',schema_version:1,execution_version_sha256:hex,objective_sha256:digest(spec.objective),workflow_id:'FM17',destination_prefixes:spec.workflow_contract.destination_prefixes,context_text_sha256:null,
 steps:[{op:'copy_map',source:'task_sources',strip_prefix:'source/',destination_prefix:'backup-set/'},{op:'copy_map',source:'prior_targets',strip_prefix:'backup-set/',destination_prefix:'recovery-drill/'}],training:[1,2].map(i=>({role:'explore',events_sha256:hex,task_fingerprint:digest(i)})),tool_schema_sha256:Object.fromEntries(names.map(n=>[prefix+n,digest({})]))};
 s.script_digest=digest(s);return {s,spec,tools:names.map(n=>({name:prefix+n,parameters:{}}))};
}
test('bounded script refuses arbitrary instructions, traversal and validation evidence as training',()=>{
 const {s}=fixture();validateScript(s);
 for(const change of [v=>v.steps.push({op:'exec',code:'shell'}),v=>v.steps[0].destination_prefix='../bad/',v=>v.training[0].role='holdout']){
  const v=structuredClone(s);delete v.script_digest;change(v);v.script_digest=digest(v);assert.throws(()=>validateScript(v));
 }
});
test('actual objective, permission and schema changes defer before copy effects',()=>{
 const {s,spec,tools}=fixture(),audit=[];const c=createScriptController(s,{spec,input_sha256:digest(spec),prompt_sha256:hex},r=>audit.push(r));
 const p=c.propose(tools).call;c.observe({callId:p.callId,name:p.proposal.tool,arguments:p.proposal.arguments},{value:{structuredContent:{...spec,input_sha256:digest(spec),copy_only:true,workflow_execution_version_sha256:hex,objective:'new rule'}}});
 assert.equal(c.halted,true);assert.equal(c.propose(tools),null);assert.equal(audit.at(-1).kind,'learned_script_deferred');
 const changed=createScriptController(s,{spec,input_sha256:digest(spec),prompt_sha256:hex},()=>{});assert.equal(changed.propose(tools.slice(1)),null);assert.equal(changed.halted,true);
});
test('failed actual tool halts permanently and never emits a second automatic call',()=>{
 const {s,spec,tools}=fixture();const c=createScriptController(s,{spec,input_sha256:digest(spec),prompt_sha256:hex},()=>{}),p=c.propose(tools).call;
 c.observe({callId:p.callId,name:p.proposal.tool,arguments:{}},{isError:true});assert.equal(c.halted,true);assert.equal(c.propose(tools),null);
});
