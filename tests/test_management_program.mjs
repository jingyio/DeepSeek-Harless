import test from 'node:test';import assert from 'node:assert/strict';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {validateManagementProgram,copyProgramActions,createManagementProgramRuntime} from '../src/adapters/management_program.ts';
const prefix='mcp__file_management__',obs=v=>({value:{structuredContent:v}});
function fixture(mode='all',context=false){
 const files={'source/a.txt':digest('same'),'source/nested/z.md':digest('same'),'source/empty.txt':digest(''),'source/empty.md':digest(''),'outside.txt':digest('sentinel')};
 if(context)files['rules/notice.txt']=digest('Actual unchanged notice');
 const spec={objective:'Back up the selected originals and recover actual backups',rules:{read_only:false},external_roots:{},initial_tree:{workspace:{files,directories:['source','source/nested',...(context?['rules']:[])]}}};
 const scope={input_sha256:digest(spec),execution_version:'e'.repeat(64)},names=['read_task','list_files','hash_files','pin_file','read_file','preview_actions','execute_plan'];
 const tools=names.map(n=>({name:prefix+n,parameters:{type:'object',properties:{}}}));
 const catalog=Object.fromEntries(tools.map(t=>[t.name,{schema:t.parameters,schema_sha256:digest(t.parameters)}]));
 const recipe={objective:spec.objective,guard:{objective_sha256:digest(spec.objective),context_text_sha256:context?digest('Actual unchanged notice'):null,destination_prefixes:['backup/','recovery/']},context_paths:context?['rules/notice.txt']:[],source_prefixes:['source/'],
  steps:mode==='min'||mode==='max'?[{op:'hash_representatives',order:mode},{op:'copy_map',source:'hash_representatives',strip_prefix:'',destination_slot:0}]:[{op:'copy_map',source:mode==='nonempty'?'nonempty_txt_sources':'task_sources',strip_prefix:'source/',destination_slot:0},{op:'copy_map',source:'prior_targets',strip_prefix:'backup/',destination_slot:1}]};
 const artifact={kind:'learned_management_copy_program',status:'trace_validated_effectful',recipe,tool_contracts:catalog,source_task_fingerprints:['train-a','train-b'],validation_task_fingerprint:'independent-native',certification_contract:'sss-management-program-certification-v1'};artifact.certified_digest=digest(artifact);
 const policy={schema_version:1,format:'sss-management-program-v1',artifact,execution_version_sha256:scope.execution_version};policy.policy_digest=digest(policy);
 const entry={entry_id:policy.policy_digest,kind:'management_program',policy,activated_generation:1};let state=structuredClone(spec.initial_tree),plans=new Map(),calls=[],audit=[];
 const inventory=()=>Object.entries(state.workspace.files).map(([path,sha256])=>({path,sha256,root_id:'workspace',bytes:sha256===digest('')?0:10,file_id:'file:local:'+digest({path:'workspace/'+path,sha:sha256}).slice(0,24)}));
 const actual=(name,args)=>{
  const rows=inventory(),out={_sss_scope:scope};calls.push({name,args});
  if(name==='list_files')return {...out,files:rows,snapshot_sha256:digest(state)};
  if(name==='hash_files'){const groups=new Map();for(const id of args.file_ids){const r=rows.find(r=>r.file_id===id);if(!groups.has(r.sha256))groups.set(r.sha256,[]);groups.get(r.sha256).push({file_id:r.file_id,path:'workspace/'+r.path});}return {groups:[...groups].map(([sha256,files])=>({sha256,files}))};}
  if(name==='pin_file'){const r=rows.find(r=>r.file_id===args.file_id);return {...out,file_id:r.file_id,source_id:'actual-rule-handle',source_version:digest({path:'workspace/'+r.path,sha:r.sha256,parser:'fm-parser-v1'})};}
  if(name==='read_file')return {...out,file_id:rows.find(r=>r.path==='rules/notice.txt').file_id,source_id:args.source_id,path:'workspace/rules/notice.txt',sha256:files['rules/notice.txt'],source_version:digest({path:'workspace/rules/notice.txt',sha:files['rules/notice.txt'],parser:'fm-parser-v1'}),text:'Actual unchanged notice',status:'readable',truncated:false};
  if(name==='preview_actions'){const plan_id='plan-'+plans.size,actions=args.actions.map(a=>{const r=rows.find(r=>r.file_id===a.file_ids[0]);return {...a,source:r.path,source_root:'workspace',destination_root:'workspace',source_sha256:r.sha256};});plans.set(plan_id,actions);return {...out,plan_id,actions,status:'validated_management_plan',risks:[]};}
  if(name==='execute_plan'){const actions=plans.get(args.plan_id);for(const a of actions){state.workspace.files[a.destination]=state.workspace.files[a.source];const parts=a.destination.split('/');for(let i=1;i<parts.length;i++){const dir=parts.slice(0,i).join('/');if(!state.workspace.directories.includes(dir))state.workspace.directories.push(dir);}}state.workspace.directories.sort();return {...out,_sss_authorized:true,status:'executed_verified',plan_id:args.plan_id,operation_count:actions.length,snapshot_sha256:digest(state)};}
  throw Error('unexpected tool '+name);
 };
 const c=createManagementProgramRuntime([entry],{scope,catalog},spec,r=>audit.push(r));
 const start=()=>c.observe({name:prefix+'read_task',callId:'actual-model-root',arguments:{}},obs({_sss_scope:scope,learning_scope:scope,objective:spec.objective}));
 let serial=0;
 const next=()=>c.propose(tools,()=>String(++serial))[0];
 const finish=()=>{for(let i=0;i<30&&!c.done&&!c.halted;i++){const call=next();assert.ok(call);c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs(actual(call.proposal.tool.slice(prefix.length),call.proposal.arguments)));}};
 return {spec,scope,tools,policy,entry,inventory,actual,c,start,next,finish,calls,audit,get state(){return state;}};
}

for(const mode of ['all','nonempty','min','max'])test('current MCP copy interpreter completes '+mode+' using verified actual identities',()=>{
 const f=fixture(mode,true);validateManagementProgram(f.policy);assert.equal(f.start(),true);f.finish();assert.equal(f.c.done,true);assert.equal(f.c.halted,false);
 const complete=f.audit.filter(r=>r.kind==='management_program_complete');assert.equal(complete.length,1);assert.equal(complete[0].copy_stages,['min','max'].includes(mode)?1:2);
 assert.equal(f.calls.filter(r=>r.name==='submit_report').length,0);
 if(mode==='nonempty'){assert.equal(f.state.workspace.files['backup/empty.txt'],undefined);assert.ok(f.state.workspace.files['backup/empty.md']);}
 const reads=f.audit.filter(r=>r.kind==='operation_model_request_bypassed_verified'),probes=f.audit.filter(r=>r.kind==='management_program_probe_verified');assert.equal(reads.length+probes.length,f.calls.length);assert.equal(probes.length,3);
});

test('actual native inventory prefetch is adopted and never counted as a skipped request',()=>{
 const f=fixture();f.start();f.c.observe({name:prefix+'list_files',callId:'native-prefetch',arguments:{}},obs(f.actual('list_files',{})));f.finish();assert.equal(f.c.done,true);
 assert.equal(f.audit.filter(r=>r.kind==='management_program_native_step_adopted').length,1);assert.ok(!f.audit.some(r=>r.kind==='operation_model_request_bypassed_verified'&&r.call_id==='native-prefetch'));
});

test('a changed rule keeps verified read-only retrieval evidence without claiming script reuse',()=>{
 const f=fixture('all',true);f.start();
 while(!f.c.halted){const call=f.next();assert.ok(call);const out=f.actual(call.proposal.tool.slice(prefix.length),call.proposal.arguments);
  if(call.proposal.tool.endsWith('__read_file'))out.text='New ordinary goal rule';
  f.c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs(out));}
 assert.equal(f.audit.filter(r=>r.kind==='management_program_probe_verified').length,3);
 assert.equal(f.audit.filter(r=>r.kind==='operation_model_request_bypassed_verified').length,0);
 assert.equal(f.audit.some(r=>r.kind==='management_program_complete'||r.kind==='experience_selected'),false);
 assert.equal(f.calls.some(r=>r.name==='preview_actions'||r.name==='execute_plan'),false);
});

test('an explicit current input roster never widens to other files in the same source directory',()=>{
 const f=fixture();f.spec.approved_inputs=[{path:'source/a.txt'}];f.scope.input_sha256=digest(f.spec);f.start();f.finish();
 assert.equal(f.c.done,true);assert.ok(f.state.workspace.files['backup/a.txt']);assert.equal(f.state.workspace.files['backup/nested/z.md'],undefined);
 assert.deepEqual(f.calls.filter(c=>c.name==='preview_actions').map(c=>c.args.actions.length),[1,1]);
});

for(const damage of ['inventory','schema','authority','scope','rule'])test('current program fails closed after '+damage+' changes',()=>{
 const f=fixture('all',true);f.start();
 for(let i=0;i<20&&!f.c.halted;i++){
  if(damage==='schema'){f.tools[1].parameters={};assert.equal(f.next(),undefined);break;}
  const call=f.next();assert.ok(call);let out=f.actual(call.proposal.tool.slice(prefix.length),call.proposal.arguments);
  if(damage==='inventory'&&call.proposal.tool.endsWith('__list_files'))out.files[0].sha256='wrong';
  if(damage==='scope')out._sss_scope={};
  if(damage==='rule'&&call.proposal.tool.endsWith('__read_file'))out.text='New conflicting notice';
  if(damage==='authority'&&call.proposal.tool.endsWith('__execute_plan'))out._sss_authorized=false;
  f.c.observe({name:call.proposal.tool,callId:call.callId,arguments:call.proposal.arguments},obs(out));
 }
 assert.equal(f.c.halted,true);assert.equal(f.c.done,false);assert.equal(f.audit.some(r=>r.kind==='management_program_complete'),false);assert.equal(f.next(),undefined);
});

test('read-only and outside-root tasks never arm a learned copy program',()=>{
 for(const change of [s=>s.rules.read_only=true,s=>s.external_roots={'external-root':{}}]){
  const f=fixture();change(f.spec);f.scope.input_sha256=digest(f.spec);assert.equal(f.start(),false);assert.equal(f.next(),undefined);
 }
});

test('an original task with existing effects resumes through ordinary Harness without restarting the copy program',()=>{
 const f=fixture();
 assert.equal(f.c.observe({name:prefix+'read_task',callId:'resumed-native-root',arguments:{}},obs({_sss_scope:f.scope,learning_scope:f.scope,objective:f.spec.objective,recovery_state:[{plan_id:'original-plan',status:'executed_verified'}]})),false);
 assert.equal(f.next(),undefined);assert.equal(f.c.halted,false);assert.equal(f.audit.length,0);
});

test('arbitrary extra instructions and existing destination fail closed',()=>{
 const f=fixture();f.policy.artifact.recipe.steps[0].op='exec';assert.throws(()=>validateManagementProgram(f.policy));
 const g=fixture();const rows=g.inventory();rows.push({...rows[0],path:'backup/a.txt'});assert.throws(()=>copyProgramActions(g.policy.artifact.recipe,rows,null,[],0),/destination conflict/);
});

test('the learned empty txt filter preserves case-insensitive extension semantics',()=>{
 const f=fixture('nonempty');const rows=f.inventory();rows.push({...rows.find(r=>r.path==='source/empty.txt'),file_id:'upper-case-empty',path:'source/EMPTY.TXT'});
 assert.equal(copyProgramActions(f.policy.artifact.recipe,rows,null,[],0).some(a=>a.destination==='backup/EMPTY.TXT'),false);
});
