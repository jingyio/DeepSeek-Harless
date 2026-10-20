/** Protocol/state diagnostics; real task cost is measured separately. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync,symlinkSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createReuseMediation,patchValue,project,reuseSyntaxCorrection,reuseChangeSummary} from '../src/adapters/reuse_mediation.ts';
const schema={type:'object',properties:{title:{type:'string'},sections:{type:'array',items:{type:'object'}}},required:['title','sections'],additionalProperties:false};
const tool={name:'mcp__test__export',parameters:schema};
const nextTool={name:'mcp__test__read',parameters:{type:'object',properties:{handle:{type:'string'}},required:['handle'],additionalProperties:false}};
const result=value=>({content:[{type:'text',text:JSON.stringify(value)}]});
test('delivery change summary uses actual JSON differences, escaping pointers and bounding output',()=>{
 const before={title:'same',sections:[{paragraphs:['keep','revise']}]},after={sections:[{paragraphs:['keep','corrected']}],title:'same'};
 assert.deepEqual(reuseChangeSummary(before,after).changed_pointers,['/sections/0/paragraphs/1']);
 assert.equal(reuseChangeSummary(before,before).changed_fields,0);
 assert.deepEqual(reuseChangeSummary({'a/b':{'~':1}},{'a/b':{'~':2}}).changed_pointers,['/a~1b/~0']);
 const summary=reuseChangeSummary(Array(100).fill('before'),Array(100).fill('after'));assert.equal(summary.changed_fields,100);assert.equal(summary.changed_pointers.length,64);assert.equal(summary.truncated,true);
});
test('syntax diagnostic preserves semantic patches but never executes the rejected shell command',async t=>{
 const f=fixture(t),plan={calls:[{tool:tool.name,arguments:{title:'text with } and [ and quote "',sections:[]},patches:[{op:'replace',path:'/title',value:'semantic choice'}]}]};
 const canonical='geneloop-reuse '+JSON.stringify(plan);
 for(const command of [canonical+' 2>&1',"cd /work && geneloop-reuse '"+JSON.stringify(plan)+"' | tail -40"]){
  assert.equal(reuseSyntaxCorrection(command),canonical);
  assert.throws(()=>f.r.prepare(command),e=>e.message.includes('retry_command')&&e.message.includes('整体未执行'));
  assert.equal(await dispatch(f),null);assert.ok(!f.audit.some(a=>a.kind==='reuse_plan_selected'));
 }
 const payload=f.r.prepare(canonical);f.r.observe({name:'bash',arguments:{command:canonical}},result(payload.control_receipt));
 assert.equal((await dispatch(f)).arguments.title,'semantic choice');
});
test('syntax hints cannot infer a plan from scripts, shell substitution, truncated JSON or foreign cwd',()=>{
 for(const command of ['cat > plan.json <<EOF\n{}\nEOF\ngeneloop-reuse --plan /work/plan.json','geneloop-reuse "$(cat plan.json)"','geneloop-reuse {"calls":[','cd /tmp && geneloop-reuse {"calls":[{}]}',"geneloop-reuse '{\"calls\":[{}]} broken"])
  assert.equal(reuseSyntaxCorrection(command),null);
});
test('corrected framing does not bypass artifact validation',t=>{
 const f=fixture(t),command='geneloop-reuse '+JSON.stringify({calls:[{tool:tool.name,base:{artifact:'stale'}}]})+' 2>&1';
 assert.throws(()=>f.r.prepare(command),/retry_command/);
 assert.throws(()=>f.r.prepare(reuseSyntaxCorrection(command)),/stale_reuse_artifact/);
});
function fixture(t){
 const workspace=realpathSync(mkdtempSync(join(tmpdir(),'reuse-')));for(const d of ['inputs','code','outputs'])mkdirSync(join(workspace,d));
 t.after(()=>rmSync(workspace,{recursive:true,force:true}));writeFileSync(join(workspace,'inputs/paper.tex'),'current');
 writeFileSync(join(workspace,'approved-inputs.json'),JSON.stringify({files:{'paper.tex':createHash('sha256').update('current').digest('hex')}}));
 const tools=[tool,nextTool],audit=[];
 const r=createReuseMediation({workspace,tools,library:{contracts:tools.map(t=>({tool:t.name,parameters:Object.keys(t.parameters.properties),schema_sha256:digest(t.parameters)}))},audit:v=>audit.push(v)});
 return {r,workspace,audit,tools};
}
function values(f){return JSON.parse(f.r.prompt().split('\n').at(-1)).current_values;}
function accept(f,calls){const command='geneloop-reuse '+JSON.stringify({calls});const payload=f.r.prepare(command);f.r.observe({name:'bash',arguments:{command}},result(payload.control_receipt));}
async function dispatch(f){const stream=f.r.ready();if(!stream)return null;for await(const chunk of stream)if(chunk.block?.type==='tool-call')return {name:chunk.block.name,callId:chunk.block.id,arguments:JSON.parse(chunk.block.arguments)};}
test('artifact forwarding then one paragraph patch preserves the other 29 paragraphs',async t=>{
 const f=fixture(t),sections=[{heading:'results',paragraphs:Array.from({length:30},(_,i)=>'paragraph '+i)}];
 writeFileSync(join(f.workspace,'code/sections.json'),JSON.stringify(sections));
 const id=values(f).find(v=>v.origin.kind==='file').id;
 accept(f,[{tool:tool.name,arguments:{title:'report'},bindings:[{at:'/sections',from:{artifact:id}}]}]);
 const first=await dispatch(f);f.r.guard(first);assert.deepEqual(first.arguments.sections,sections);
 f.r.observe(first,result({exported:true}));
 const base=values(f).find(v=>v.origin.kind==='arguments').id;
 accept(f,[{tool:tool.name,base:{artifact:base},patches:[{op:'replace',path:'/sections/0/paragraphs/12',value:'corrected'}]}]);
 const second=await dispatch(f);f.r.guard(second);
 assert.equal(second.arguments.sections[0].paragraphs.filter((p,i)=>p===sections[0].paragraphs[i]).length,29);
 assert.equal(sections[0].paragraphs[12],'paragraph 12');
});
test('a field restoration copies current values without regenerating arrays and guards both source and base',async t=>{
 const f=fixture(t),approved={title:'approved',sections:[{paragraphs:['one','two','three']}]},candidate={title:'semantic revision',sections:[{paragraphs:['combined']}]};
 writeFileSync(join(f.workspace,'code/approved.json'),JSON.stringify(approved));writeFileSync(join(f.workspace,'code/candidate.json'),JSON.stringify(candidate));
 const rows=values(f),from=rows.find(r=>r.origin.path==='/work/approved.json').id,base=rows.find(r=>r.origin.path==='/work/candidate.json').id;
 const patch={op:'replace',path:'/sections/0/paragraphs',from:{artifact:from,pointer:'/sections/0/paragraphs'}};
 accept(f,[{tool:tool.name,base:{artifact:base},patches:[patch]}]);const call=await dispatch(f);f.r.guard(call);
 assert.deepEqual(call.arguments.sections,approved.sections);assert.equal(call.arguments.title,candidate.title);
 writeFileSync(join(f.workspace,'code/approved.json'),JSON.stringify({...approved,title:'new source'}));assert.throws(()=>f.r.guard(call),/guard_failed/);
 const g=fixture(t);writeFileSync(join(g.workspace,'code/a.json'),JSON.stringify(approved));const id=values(g)[0].id;
 assert.throws(()=>accept(g,[{tool:tool.name,base:{artifact:id},patches:[{...patch,from:{artifact:id},value:'conflict'}]}]),/requires_current_artifact/);
 assert.throws(()=>accept(g,[{tool:tool.name,base:{artifact:id},patches:[{...patch,from:{step:0}}]}]));
});
test('one semantic plan binds the successful previous result and continues without model decisions',async t=>{
 const f=fixture(t);accept(f,[{tool:tool.name,arguments:{title:'x',sections:[]}},{tool:nextTool.name,bindings:[{at:'/handle',from:{step:0,pointer:'/handle'}}]}]);
 const a=await dispatch(f);f.r.observe(a,result({exported:true,handle:'fresh-handle'}));
 const b=await dispatch(f);assert.deepEqual(b.arguments,{handle:'fresh-handle'});f.r.guard(b);f.r.observe(b,result({data:['current']}));
 assert.equal(await dispatch(f),null);assert.ok(f.audit.some(a=>a.kind==='reuse_plan_completed'&&a.steps===2));
});
test('inspection reads exact current values, bounds large content and never authorizes execution',async t=>{
 const f=fixture(t),path=join(f.workspace,'code/current.json');writeFileSync(path,JSON.stringify({title:'current approved text',sections:[],large:'x'.repeat(17000)}));
 const id=values(f).find(v=>v.origin.path==='/work/current.json').id;
 const inspect=pointer=>f.r.prepare('geneloop-reuse '+JSON.stringify({inspect:{artifact:id,pointer}})).control_receipt;
 const one=inspect('/title');assert.equal(one.kind,'reuse_inspection');assert.equal(one.complete,true);assert.equal(one.value,'current approved text');assert.equal(one.value_sha256,digest(one.value));
 const large=inspect('/large');assert.equal(large.complete,false);assert.equal(large.value,undefined);assert.equal(await dispatch(f),null);
 assert.throws(()=>f.r.prepare('geneloop-reuse '+JSON.stringify({inspect:{step:0}})));
 assert.throws(()=>inspect('/__proto__/polluted'));
 writeFileSync(path,'{}');assert.throws(()=>inspect('/title'),/stale/);
 assert.ok(!f.audit.some(r=>r.kind==='reuse_plan_selected'));
});
test('typed export failure stops successors but allows a new semantic correction',async t=>{
 const f=fixture(t);accept(f,[{tool:tool.name,arguments:{title:'x',sections:[]}},{tool:nextTool.name,arguments:{handle:'wrong'}}]);
 f.r.observe(await dispatch(f),result({exported:false,failed_checks:['page_constraint_satisfied']}));
 assert.equal(await dispatch(f),null);assert.ok(!f.audit.some(a=>a.kind==='reuse_plan_completed'));
 assert.ok(f.r.prompt().includes('当前有一个明确的参数修订机会'));
 const base=values(f).find(v=>v.origin.kind==='arguments').id;
 accept(f,[{tool:tool.name,base:{artifact:base},patches:[{op:'replace',path:'/title',value:'fixed'}]}]);assert.equal((await dispatch(f)).arguments.title,'fixed');
});
test('diagnostic calls do not evict the previous large report arguments',t=>{
 const f=fixture(t);
 f.r.observe({name:tool.name,callId:'full',arguments:{title:'report',sections:[{text:'long report'}]}},result({exported:false}));
 const old=values(f).find(v=>v.origin.kind==='arguments').id;
 f.r.observe({name:tool.name,callId:'diagnostic',arguments:{title:'diagnostic',sections:[]}},result({exported:true}));
 assert.ok(values(f).some(v=>v.id===old));
});
test('live evidence is appended once without changing the stable system prefix',t=>{
 const f=fixture(t),before=f.r.staticPrompt();
 f.r.observe({name:tool.name,callId:'report',arguments:{title:'report',sections:[]}},result({exported:false,failed_checks:['layout']}));
 const notice=f.r.takeNotice();assert.ok(notice.includes('参数修订机会'));assert.ok(notice.includes('geneloop-reuse'));
 assert.equal(f.r.takeNotice(),'');assert.equal(f.r.staticPrompt(),before);
});
test('changed file after selection and after proposal is rejected',async t=>{
 const f=fixture(t),path=join(f.workspace,'code/data.json');writeFileSync(path,'[]');const id=values(f)[0].id;
 accept(f,[{tool:tool.name,arguments:{title:'x'},bindings:[{at:'/sections',from:{artifact:id}}]}]);
 const call=await dispatch(f);writeFileSync(path,'[{}]');assert.throws(()=>f.r.guard(call),/guard_failed/);
 const g=fixture(t);writeFileSync(join(g.workspace,'code/data.json'),'[]');const other=values(g)[0].id;
 accept(g,[{tool:tool.name,arguments:{title:'x'},bindings:[{at:'/sections',from:{artifact:other}}]}]);writeFileSync(join(g.workspace,'code/data.json'),'[{}]');assert.equal(await dispatch(g),null);
});
test('cross-task artifact, changed original, bad schema, changed offered tools fail closed',async t=>{
 const f=fixture(t),g=fixture(t);writeFileSync(join(f.workspace,'code/data.json'),'[]');const id=values(f)[0].id;
 assert.throws(()=>accept(g,[{tool:tool.name,arguments:{title:'x'},bindings:[{at:'/sections',from:{artifact:id}}]}]),/stale/);
 assert.throws(()=>accept(f,[{tool:tool.name,arguments:{title:4,sections:[]}}]),/schema/);
 accept(f,[{tool:tool.name,arguments:{title:'x',sections:[]}}]);f.r.update({tools:[]});assert.equal(await dispatch(f),null);
 writeFileSync(join(g.workspace,'inputs/paper.tex'),'changed');assert.throws(()=>accept(g,[{tool:tool.name,arguments:{title:'x',sections:[]}}]),/source_changed/);
});
test('no control receipt forgery, no forward references or shell-tail evaluation',async t=>{
 const f=fixture(t);assert.throws(()=>accept(f,[{tool:nextTool.name,bindings:[{at:'/handle',from:{step:0,pointer:'/handle'}}]}]),/forward/);
 const command='geneloop-reuse '+JSON.stringify({calls:[{tool:tool.name,arguments:{title:'x',sections:[]}}]});
 assert.throws(()=>f.r.prepare(command+'; echo 1'));
 const p=f.r.prepare(command);f.r.observe({name:'bash',arguments:{command}},result({...p.control_receipt,nonce:'fake'}));assert.equal(await dispatch(f),null);
});
test('JSON patches enforce tests, exact indices, safe pointers and absence of mutation',()=>{
 const value={a:[1,2],b:{'a/b':3}};assert.equal(project(value,'/b/a~1b'),3);
 assert.throws(()=>patchValue(value,[{op:'test',path:'/a/0',value:2}]),/test_failed/);
 for(const path of ['/a/-1','/a/01','/a/99','/__proto__/x','/b/~3'])assert.throws(()=>patchValue(value,[{op:'replace',path,value:4}]));
 assert.deepEqual(patchValue(value,[{op:'add',path:'/a/-',value:3},{op:'remove',path:'/b/a~1b'}]),{a:[1,2,3],b:{}});assert.deepEqual(value,{a:[1,2],b:{'a/b':3}});
});
test('artifact scanning skips symlinks and dispatch rejects changed user goals',async t=>{
 const f=fixture(t);symlinkSync(join(f.workspace,'inputs/paper.tex'),join(f.workspace,'code/linked.json'));assert.deepEqual(values(f),[]);
 f.r.update({tools:f.tools,messages:[{role:'user',source:{kind:'user'},content:'export'}]});
 accept(f,[{tool:tool.name,arguments:{title:'x',sections:[]}}]);
 f.r.update({tools:f.tools,messages:[{role:'user',source:{kind:'user'},content:'stop exporting'}]});assert.equal(await dispatch(f),null);
});
test('real recovery shell framing accepts static plans, rejects shell expansion, and checks plan versions',async t=>{
 const f=fixture(t),plan={calls:[{tool:tool.name,arguments:{title:'current',sections:[]}}]};
 for(const command of ['cd /work && geneloop-reuse "$(cat /work/plan.json)"','cd /tmp && geneloop-reuse '+JSON.stringify(plan),'geneloop-reuse --plan /work/../plan.json'])assert.throws(()=>f.r.prepare(command));
 writeFileSync(join(f.workspace,'code/plan.json'),JSON.stringify(plan));
 const command='cd /work && geneloop-reuse --plan /work/plan.json',payload=f.r.prepare(command);
 f.r.observe({name:'bash',arguments:{command}},result(payload.control_receipt));
 const call=await dispatch(f);f.r.guard(call);writeFileSync(join(f.workspace,'code/plan.json'),JSON.stringify({...plan,changed:true}));
 assert.throws(()=>f.r.guard(call),/guard_failed/);
});
test('static JSON with current-directory prefix is interpreted without executing shell',async t=>{
 const f=fixture(t),command='cd /work && geneloop-reuse '+JSON.stringify({calls:[{tool:tool.name,arguments:{title:'current',sections:[]}}]});
 const payload=f.r.prepare(command);f.r.observe({name:'bash',arguments:{command}},result(payload.control_receipt));
 assert.equal((await dispatch(f)).arguments.title,'current');
});
test('native shell stderr does not hide a valid one-use receipt, but failed or duplicate receipts reject',async t=>{
 for(const variant of ['stderr','failed','duplicate']){
  const f=fixture(t),command='geneloop-reuse '+JSON.stringify({calls:[{tool:tool.name,arguments:{title:'x',sections:[]}}]});
  const payload=f.r.prepare(command),line=JSON.stringify(payload.control_receipt);
  const output={content:[{type:'text',text:line+'\n'+(variant==='duplicate'?line:'[stderr]\n(node) module warning\n')}],isError:variant==='failed'};
  f.r.observe({name:'bash',arguments:{command}},output);
  assert.equal(!!await dispatch(f),variant==='stderr');
 }
});
test('script successors require verified cache facts, including complete batch count',async t=>{
 for(const verified of [true,false]){
  const f=fixture(t),script={id:'script_test',inputs:[{}]};
  const r=createReuseMediation({workspace:f.workspace,tools:[{name:'bash',parameters:{}},nextTool],scriptLibrary:{programs:[script]},library:{contracts:[{tool:nextTool.name,schema_sha256:digest(nextTool.parameters)}]},audit:v=>f.audit.push(v)});
  f.r=r;accept(f,[{script:script.id,paths:['/work/current.json']},{tool:nextTool.name,bindings:[{at:'/handle',from:{step:0,pointer:'/results/0/output/handle'}}]}]);
  const a=await dispatch(f);r.observe(a,{content:[{type:'text',text:'receipt\n[stderr]\nwarning'}]},verified?[{program:script,bound:[],output:'{"handle":"fresh"}'}]:[]);
  const b=await dispatch(f);assert.equal(!!b,verified);if(b)assert.equal(b.arguments.handle,'fresh');
 }
});
test('notices offer schema-compatible nested arguments and do not promote unchanged failures or metadata',t=>{
 const f=fixture(t),path=join(f.workspace,'code/current.json');
 writeFileSync(path,JSON.stringify({metadata:{foo:'irrelevant'},arguments:{title:'current',sections:[]}}));
 const notice=f.r.takeNotice();assert.ok(notice.includes('ready_calls'));assert.ok(notice.includes('/arguments'));assert.ok(!notice.includes('irrelevant'));
 f.r.observe({name:tool.name,callId:'failed',arguments:{title:'current',sections:[]}},result({exported:false}));
 writeFileSync(join(f.workspace,'code/copy.json'),JSON.stringify({title:'current',sections:[]}));
 const after=f.r.takeNotice();assert.ok(after.includes('修订'));assert.ok(!after.includes('ready_calls'));
 writeFileSync(join(f.workspace,'code/metadata.json'),JSON.stringify({tool_error:'pending'}));assert.equal(f.r.takeNotice(),'');
});
test('one selected learned diagnostic runs multiple native probes and returns bounded evidence',async t=>{
 const f=fixture(t),contract={id:'probe_test',tool:tool.name,schema_sha256:digest(schema),failure:{exported:false,failed_checks:['layout']},success_fields:['exported'],axes:[{path:['sections']}],max_probes:12};
 f.r=createReuseMediation({workspace:f.workspace,tools:f.tools,library:{contracts:[{tool:tool.name,schema_sha256:digest(schema)}],probe_contracts:[contract]},probeTools:[tool.name],audit:v=>f.audit.push(v)});
 const original={title:'whole',sections:[{text:'safe1'},{text:'bad'},{text:'safe2'},{text:'safe3'}]},failure=contract.failure;
 f.r.observe({name:tool.name,callId:'original',arguments:original},result(failure));
 const id=values(f).find(v=>v.origin.kind==='arguments').id;
 assert.ok(f.r.takeNotice().includes('diagnose'));
 const command='geneloop-reuse '+JSON.stringify({diagnose:{contract:contract.id,base:{artifact:id}}});
 const receipt=f.r.prepare(command);f.r.observe({name:'bash',arguments:{command}},result(receipt.control_receipt));
 let calls=0,notice='';
 for(let call;call=await dispatch(f);){f.r.guard(call);calls++;f.r.observe(call,result(call.arguments.sections.some(s=>s.text==='bad')?failure:{exported:true}));notice+=f.r.takeNotice();}
 assert.equal(calls,3);assert.ok(notice.includes('bad'));assert.ok(notice.includes('不能作为完整报告交付'));assert.equal(original.sections.length,4);
 assert.equal(f.audit.filter(x=>x.kind==='reuse_probe_completed').length,1);
 assert.throws(()=>f.r.prepare(command),/current_failure/);
});
test('diagnosis without effect allowlist or with foreign failure is unavailable',t=>{
 const f=fixture(t);f.r.observe({name:tool.name,callId:'bad',arguments:{title:'x',sections:[{},{}]}},result({exported:false,failed_checks:['layout']}));
 const id=values(f).find(v=>v.origin.kind==='arguments').id;
 assert.throws(()=>f.r.prepare('geneloop-reuse '+JSON.stringify({diagnose:{contract:'unseen',base:{artifact:id}}})),/current_failure/);
});

function liveEvidence(f,args){return {version:1,kind:'review_execution_evidence',arguments_sha256:digest(args),source_versions:JSON.parse(readFileSafe(join(f.workspace,'approved-inputs.json'))).files,config_sha256:'a'.repeat(64),grant_sha256:digest(null),task_id:null};}
function readFileSafe(path){return readFileSync(path,'utf8');}
function sourceArgs(f){return {title:'complete report',sections:[{heading:'results',paragraphs:Array.from({length:30},(_,i)=>'statement '+i)}],source_versions:JSON.parse(readFileSafe(join(f.workspace,'approved-inputs.json'))).files};}
function evidenceRuntime(f,options={}){
 const parameters={...schema,properties:{...schema.properties,source_versions:{type:'object'}}},exportTool={name:tool.name,parameters};
 const probe={id:'probe_fields',tool:tool.name,schema_sha256:digest(parameters),failure:{exported:false,failed_checks:['all_text_preserved']},success_fields:['exported'],axes:[{path:['sections','*','paragraphs']}],max_probes:12};
 f.r=createReuseMediation({workspace:f.workspace,tools:[exportTool],library:{contracts:[{tool:tool.name,schema_sha256:digest(parameters)}],probe_contracts:[probe]},probeTools:[tool.name],audit:v=>f.audit.push(v),...options});return probe;
}
test('verified current field evidence suppresses unrelated diagnosis and patch preserves all other fields',async t=>{
 const f=fixture(t),probe=evidenceRuntime(f),args=sourceArgs(f),path='/sections/0/paragraphs/12';
 const failure={exported:false,failed_checks:['all_text_preserved'],execution_evidence:liveEvidence(f,args),argument_issues:[{pointer:path,check:'all_text_preserved',value_sha256:createHash('sha256').update(args.sections[0].paragraphs[12]).digest('hex')}]};
 f.r.observe({name:tool.name,callId:'current-failure',arguments:args},result(failure));
 const notice=f.r.takeNotice();assert.ok(notice.includes('statement 12'));assert.ok(notice.includes('无需重复分段定位'));assert.ok(!notice.includes('"diagnose"'));
 const id=values(f).find(v=>v.origin.kind==='arguments').id;
 assert.throws(()=>f.r.prepare('geneloop-reuse '+JSON.stringify({diagnose:{contract:probe.id,base:{artifact:id}}})),/current_failure/);
 accept(f,[{tool:tool.name,base:{artifact:id},patches:[{op:'replace',path,value:'necessary semantic correction'}]}]);
 const call=await dispatch(f);assert.deepEqual(call.arguments.source_versions,args.source_versions);
 assert.equal(call.arguments.sections[0].paragraphs.filter((p,i)=>p===args.sections[0].paragraphs[i]).length,29);
 assert.ok(f.audit.some(a=>a.kind==='reuse_patch_bound'&&a.patch_paths.includes(path)));
});
test('stale argument, source, grant or field evidence cannot suppress diagnosis as a verified location',t=>{
 for(const changed of ['argument','source','grant','field']){
  const f=fixture(t);evidenceRuntime(f);const args=sourceArgs(f),e=liveEvidence(f,args);
  const issue={pointer:'/sections/0/paragraphs/0',check:'all_text_preserved',value_sha256:createHash('sha256').update('statement 0').digest('hex')};
  if(changed==='argument')e.arguments_sha256='0'.repeat(64);
  if(changed==='source')e.source_versions={};if(changed==='grant')e.grant_sha256='0'.repeat(64);if(changed==='field')issue.value_sha256='0'.repeat(64);
  f.r.observe({name:tool.name,callId:changed,arguments:args},result({exported:false,failed_checks:['all_text_preserved'],execution_evidence:e,argument_issues:[issue]}));
  assert.ok(!f.r.takeNotice().includes('当前已校验的定位证据'));
 }
});
test('only actual source-bound delivery files permit a completion handoff; tampering invalidates it',t=>{
 const f=fixture(t);evidenceRuntime(f);const args=sourceArgs(f),dir=join(f.workspace,'outputs/documents/current');mkdirSync(dir,{recursive:true});
 const name='outputs/documents/current/review.pdf',data=Buffer.from('diagnostic file bytes');writeFileSync(join(f.workspace,name),data);
 const files=[{name,sha256:createHash('sha256').update(data).digest('hex'),bytes:data.length}];
 const receipt={layout_passed:true,source_versions:args.source_versions,files};const raw=JSON.stringify(receipt),receipt_name='outputs/documents/current/delivery.json';writeFileSync(join(f.workspace,receipt_name),raw);
 const response={exported:true,artifacts:files,execution_evidence:{...liveEvidence(f,args),delivery_passed:true,receipt_name,receipt_sha256:createHash('sha256').update(raw).digest('hex')}};
 f.r.observe({name:tool.name,callId:'success',arguments:args},result(response));
 assert.ok(f.r.takeNotice().includes('现在交回你生成最终回答'));assert.equal(f.audit.filter(a=>a.kind==='reuse_delivery_verified').length,1);
 writeFileSync(join(f.workspace,name),'changed');f.r.observe({name:tool.name,callId:'stale',arguments:args},result(response));
 assert.ok(!f.r.takeNotice().includes('交付成功'));assert.equal(f.audit.filter(a=>a.kind==='reuse_delivery_verified').length,1);
});

test('explicit protected recovery target is offered before action with bounded shape and no full text',t=>{
 const f=fixture(t),args={title:'report',sections:[{heading:'h',paragraphs:['private contents','another paragraph']}]};
 writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify({version:1,kind:'current_review_recovery_scope',policy:'preserve_structure_allow_semantic_leaf_revisions',arguments:args}));
 const prefix=f.r.staticPrompt(),notice=f.r.takeNotice();
 assert.ok(notice.includes('受保护的当前恢复目标'));assert.ok(notice.includes('/sections/0/paragraphs'));assert.ok(!notice.includes('private contents'));assert.equal(f.r.staticPrompt(),prefix);
});

function currentObligation(f){
 evidenceRuntime(f);const args=sourceArgs(f),task_id='current-task';
 const goal={kind:'current_review_recovery_scope',version:1,task_id,source_versions:args.source_versions,arguments:args,policy:'preserve_structure_allow_semantic_leaf_revisions',origin:'explicit_current_recovery_requirement_not_inferred_from_history',execution_obligation:{kind:'resume_current_operation',tool:tool.name,arguments_sha256:digest(args),max_attempts:1}};
 const grant={schema_version:1,task_id,allow_output:true};
 writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify(goal));writeFileSync(join(f.workspace,'paper-output-grant.json'),JSON.stringify(grant));
 f.r.update({tools:[{name:tool.name,parameters:{...schema,properties:{...schema.properties,source_versions:{type:'object'}}}}],messages:[{role:'user',source:{kind:'user'},content:'resume the current report'}]});
 return {goal,grant,args};
}
test('explicit current obligation executes once without model selection and returns failures to semantic repair',async t=>{
 const f=fixture(t),{args}=currentObligation(f),call=await dispatch(f);assert.deepEqual(call.arguments,args);f.r.guard(call);
 f.r.observe(call,result({exported:false,failed_checks:['layout']}));
 assert.equal(await dispatch(f),null);assert.equal(await dispatch(f),null);
 assert.ok(f.r.takeNotice().includes('参数修订机会'));
 assert.equal(f.audit.filter(a=>a.kind==='reuse_current_obligation_started').length,1);
 assert.ok(!f.audit.some(a=>a.kind==='reuse_plan_selected'));
});
test('a matched negative constraint offers an executable current-field restoration, without auto selecting it',async t=>{
 const f=fixture(t),{args,goal,grant}=currentObligation(f);delete goal.execution_obligation;
 writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify(goal));
 const bad=structuredClone(args),pointer='/sections/0/paragraphs';bad.sections[0].paragraphs.pop();
 const scopeHash=createHash('sha256').update(readFileSync(join(f.workspace,'review-recovery-scope.json'))).digest('hex');
 const failure={exported:false,failed_checks:['shape'],execution_evidence:{...liveEvidence(f,bad),task_id:grant.task_id,grant_sha256:digest(grant),recovery_scope_sha256:scopeHash},argument_issues:[{pointer,check:'shape',hash_kind:'json',value_sha256:digest(bad.sections[0].paragraphs)}]};
 f.r.observe({name:tool.name,callId:'real-failure',arguments:bad},result(failure));
 f.r.setNegativeConstraint({motif_id:'negative_test',failure_code:'shape',failure_arguments_sha256:digest(bad),scope_sha256:scopeHash,issues:[{pointer}]});
 const text=f.r.takeNotice(),line=text.split('\n').find(x=>x.startsWith('{"negative_restoration_candidate"'));
 assert.ok(line);assert.equal(await dispatch(f),null);const command=JSON.parse(line).negative_restoration_candidate.command;
 const receipt=f.r.prepare(command);f.r.observe({name:'bash',arguments:{command}},result(receipt.control_receipt));const call=await dispatch(f);f.r.guard(call);assert.deepEqual(call.arguments,args);
});
function typedChoiceFixture(t){
 const f=fixture(t),{args,goal,grant}=currentObligation(f);delete goal.execution_obligation;
 writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify(goal));evidenceRuntime(f,{repairChoices:true});
 const bad=structuredClone(args),pointer='/sections/0/paragraphs';bad.sections[0].paragraphs.pop();bad.title='keep current semantic edit';
 const scopeHash=createHash('sha256').update(readFileSync(join(f.workspace,'review-recovery-scope.json'))).digest('hex');
 const failure={exported:false,failed_checks:['shape'],execution_evidence:{...liveEvidence(f,bad),task_id:grant.task_id,grant_sha256:digest(grant),recovery_scope_sha256:scopeHash},argument_issues:[{pointer,check:'shape',hash_kind:'json',value_sha256:digest(bad.sections[0].paragraphs)}]};
 f.r.observe({name:tool.name,callId:'current',arguments:bad},result(failure));
 const constraint={motif_id:'certified',failure_code:'shape',failure_arguments_sha256:digest(bad),scope_sha256:scopeHash,issues:[{pointer}]};f.r.setNegativeConstraint(constraint);
 const id=f.audit.find(x=>x.kind==='reuse_repair_choice_offered').request_id;
 return {...f,args,bad,id,constraint,command:status=>'geneloop-reuse '+JSON.stringify({repair_choice:{request_id:id,status}})};
}
test('typed repair choice shows complete current evidence and requires verified selection before field restoration',async t=>{
 const f=typedChoiceFixture(t),notice=f.r.takeNotice();assert.ok(notice.includes('statement 29'));assert.ok(notice.includes('unknown'));assert.equal(await dispatch(f),null);
 assert.throws(()=>f.r.prepare('geneloop-reuse '+JSON.stringify({calls:[]})),/typed_resolution/);
 const command=f.command('restore');assert.equal(f.r.guard({name:'bash',arguments:{command}}),undefined);
 const p=f.r.prepare(command);assert.equal(await dispatch(f),null);f.r.observe({name:'bash',arguments:{command}},result(p.control_receipt));
 const call=await dispatch(f);f.r.guard(call);assert.deepEqual(call.arguments.sections,f.args.sections);assert.equal(call.arguments.title,f.bad.title);
 assert.ok(f.audit.some(x=>x.kind==='reuse_repair_choice_verified'&&x.status==='restore'));
 writeFileSync(join(f.workspace,'paper-output-grant.json'),'{}');assert.throws(()=>f.r.guard(call));
});
test('unknown and nonconforming choices release once; stale or forged choices cannot dispatch',async t=>{
 for(const status of ['unknown','ambiguous','unneeded']){
  const f=typedChoiceFixture(t),command=f.command(status),p=f.r.prepare(command);f.r.observe({name:'bash',arguments:{command}},result(p.control_receipt));assert.equal(await dispatch(f),null);
  f.r.setNegativeConstraint(f.constraint);assert.equal(f.audit.filter(x=>x.kind==='reuse_repair_choice_offered').length,1);
 }
 const f=typedChoiceFixture(t);assert.match(f.r.guard({name:'bash',arguments:{command:'python3 read.py'}}),/交回普通流程/);assert.equal(f.r.guard({name:'bash',arguments:{command:'python3 read.py'}}),undefined);
 const g=typedChoiceFixture(t),command=g.command('restore'),p=g.r.prepare(command);g.r.observe({name:'bash',arguments:{command}},result({...p.control_receipt,nonce:'forged'}));assert.equal(await dispatch(g),null);
 const h=typedChoiceFixture(t);writeFileSync(join(h.workspace,'review-recovery-scope.json'),'{}');assert.throws(()=>h.r.prepare(h.command('restore')));assert.equal(await dispatch(h),null);
});
test('delivery handoff reports changes against the actual task start, separating earlier goal differences',t=>{
 const f=fixture(t),{goal,grant,args}=currentObligation(f);
 const initial=structuredClone(args);initial.title='already revised before this task';initial.sections[0].paragraphs.pop();
 goal.resume_arguments=initial;goal.execution_obligation.arguments_pointer='/resume_arguments';goal.execution_obligation.arguments_sha256=digest(initial);
 writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify(goal));
 const after={...args,title:initial.title},dir='outputs/documents/current';mkdirSync(join(f.workspace,dir),{recursive:true});
 const name=dir+'/review.pdf',data=Buffer.from('protocol diagnostic');writeFileSync(join(f.workspace,name),data);
 const files=[{name,bytes:data.length,sha256:createHash('sha256').update(data).digest('hex')}],receipt_name=dir+'/delivery.json',raw=JSON.stringify({layout_passed:true,task_id:grant.task_id,source_versions:args.source_versions,files});writeFileSync(join(f.workspace,receipt_name),raw);
 const e={...liveEvidence(f,after),task_id:grant.task_id,grant_sha256:digest(grant),recovery_scope_sha256:createHash('sha256').update(readFileSync(join(f.workspace,'review-recovery-scope.json'))).digest('hex'),delivery_passed:true,receipt_name,receipt_sha256:createHash('sha256').update(raw).digest('hex')};
 f.r.observe({name:tool.name,callId:'success',arguments:after},result({exported:true,artifacts:files,execution_evidence:e}));
 const record=f.audit.find(x=>x.kind==='reuse_delivery_verified');assert.deepEqual(record.changes.changed_pointers,['/title']);assert.deepEqual(record.current_run_changes.changed_pointers,['/sections/0/paragraphs']);assert.equal(record.current_run_changes.basis_sha256,digest(initial));
 const notice=f.r.takeNotice();assert.ok(notice.includes('current_run_changes'));assert.ok(!notice.includes('"changes":'));assert.ok(notice.includes('历史内容'));
});
test('a real failed candidate can resume separately from the approved complete goal, with exact pointer and source binding',async t=>{
 const f=fixture(t),{goal,args}=currentObligation(f);
 goal.resume_arguments=structuredClone(args);goal.resume_arguments.sections[0].paragraphs.pop();
 goal.execution_obligation.arguments_pointer='/resume_arguments';goal.execution_obligation.arguments_sha256=digest(goal.resume_arguments);
 writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify(goal));
 const call=await dispatch(f);f.r.guard(call);assert.equal(call.arguments.sections[0].paragraphs.length,29);
 assert.equal(goal.arguments.sections[0].paragraphs.length,30);
 for(const change of ['pointer','source']){
  const g=fixture(t),{goal:target}=currentObligation(g);target.resume_arguments=structuredClone(target.arguments);target.execution_obligation.arguments_pointer=change==='pointer'?'/arbitrary':'/resume_arguments';
  if(change==='source')target.resume_arguments.source_versions={};target.execution_obligation.arguments_sha256=digest(target.resume_arguments);
  writeFileSync(join(g.workspace,'review-recovery-scope.json'),JSON.stringify(target));assert.equal(await dispatch(g),null);
 }
});
test('missing obligation, foreign task, revoked grant, changed sources or hashes cannot trigger automatic execution',async t=>{
 for(const changed of ['missing','task','grant','source','hash','schema','attempts','origin']){
  const f=fixture(t),{goal,grant}=currentObligation(f);
  if(changed==='missing')delete goal.execution_obligation;
  if(changed==='task')grant.task_id='other';if(changed==='grant')grant.allow_output=false;
  if(changed==='source')goal.source_versions={};if(changed==='hash')goal.execution_obligation.arguments_sha256='0'.repeat(64);
  if(changed==='schema')goal.arguments.title=8;if(changed==='attempts')goal.execution_obligation.max_attempts=2;if(changed==='origin')goal.origin='historical_similar_task';
  writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify(goal));writeFileSync(join(f.workspace,'paper-output-grant.json'),JSON.stringify(grant));
  assert.equal(await dispatch(f),null,changed);
 }
});
test('obligation rechecks grant and scope at dispatch and never resumes after user goal changes',async t=>{
 for(const changed of ['grant','goal','user']){
  const f=fixture(t),{goal,grant}=currentObligation(f),call=await dispatch(f);
  if(changed==='grant'){grant.allow_output=false;writeFileSync(join(f.workspace,'paper-output-grant.json'),JSON.stringify(grant));}
  if(changed==='goal'){goal.arguments.title='changed';writeFileSync(join(f.workspace,'review-recovery-scope.json'),JSON.stringify(goal));}
  if(changed==='user')f.r.update({tools:f.tools,messages:[{role:'user',source:{kind:'user'},content:'stop'}]});
  assert.throws(()=>f.r.guard(call),/guard_failed/);
 }
});
