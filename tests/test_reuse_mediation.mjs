/** Protocol/state diagnostics; real task cost is measured separately. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,realpathSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createReuseMediation,patchValue,project} from '../src/adapters/reuse_mediation.ts';
const schema={type:'object',properties:{title:{type:'string'},sections:{type:'array',items:{type:'object'}}},required:['title','sections'],additionalProperties:false};
const tool={name:'mcp__test__export',parameters:schema};
const nextTool={name:'mcp__test__read',parameters:{type:'object',properties:{handle:{type:'string'}},required:['handle'],additionalProperties:false}};
const result=value=>({content:[{type:'text',text:JSON.stringify(value)}]});
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
test('one semantic plan binds the successful previous result and continues without model decisions',async t=>{
 const f=fixture(t);accept(f,[{tool:tool.name,arguments:{title:'x',sections:[]}},{tool:nextTool.name,bindings:[{at:'/handle',from:{step:0,pointer:'/handle'}}]}]);
 const a=await dispatch(f);f.r.observe(a,result({exported:true,handle:'fresh-handle'}));
 const b=await dispatch(f);assert.deepEqual(b.arguments,{handle:'fresh-handle'});f.r.guard(b);f.r.observe(b,result({data:['current']}));
 assert.equal(await dispatch(f),null);assert.ok(f.audit.some(a=>a.kind==='reuse_plan_completed'&&a.steps===2));
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
