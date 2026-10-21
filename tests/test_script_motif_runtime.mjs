/** Structural/semantic seam diagnostics, vectors are deliberately injected. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,symlinkSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {bindScript,createScriptInterceptor,consumeScriptGrant,scriptCommand,registerScriptCache,witnessedOutputSchema} from '../src/adapters/script_motif_runtime.ts';
test('JSON field contracts require two real-shaped outputs and never publish changing data keys as fields',()=>{
 const schema=witnessedOutputSchema(['{"value":{"count":2,"issues":[]}}','{"value":{"count":3,"issues":["x"]}}']);
 assert.equal(schema.properties.value.properties.count.type,'number');assert.equal(schema.properties.value.properties.issues.type,'array');
 assert.equal(witnessedOutputSchema(['{"value":1}']),undefined);
 assert.equal(witnessedOutputSchema(['{"value":1}','not JSON']),undefined);
 const dynamic=witnessedOutputSchema(['{"value":{"source_specific_key":1}}','{"value":{"new_task_key":2}}']);
 assert.deepEqual(dynamic.properties.value,{type:'object'});
 assert.equal(witnessedOutputSchema(['{"value":1}','{"value":"one"}']),undefined);
});
function fixture(t){const workspace=realpathSync(mkdtempSync(join(tmpdir(),'script-motif-')));for(const d of ['inputs','code'])mkdirSync(join(workspace,d));t.after(()=>rmSync(workspace,{recursive:true,force:true}));const path=join(workspace,'inputs','new.bib');writeFileSync(path,'@article{new}\n');return {workspace,path,program:{id:'script_test',template:"print(open('__MOTIF_INPUT_0__').read())",description:'统计 BibTeX 条目',inputs:[{suffix:'.bib',format:'text'}]}};}
test('binding is by current contract, refuses ambiguity and symlinks',t=>{const {workspace,path,program}=fixture(t);assert.equal(bindScript(program,workspace)[0].path,'/work/inputs/new.bib');writeFileSync(join(workspace,'inputs','second.bib'),'x');assert.throws(()=>bindScript(program,workspace),/ambiguous/);rmSync(path);symlinkSync(join(workspace,'inputs','second.bib'),path);assert.equal(bindScript(program,workspace).length,1);});
test('an approved input can bind before the first command creates scratch',t=>{
 const {workspace,program}=fixture(t);rmSync(join(workspace,'code'),{recursive:true});
 assert.equal(bindScript(program,workspace)[0].path,'/work/inputs/new.bib');
});
test('low semantic score and Shadow both call the provider',async t=>{const {workspace,program}=fixture(t);for(const [mode,score] of [['execute',.3],['shadow',.95]]){let calls=0;const audit=[];const r=createScriptInterceptor({library:{programs:[program]},workspace,session:'s',goal:'检查参考文献',mode,audit:r=>audit.push(r),similarity:async()=>[score]});await r.intercept('s',{tools:[{name:'bash'}]},()=>{calls++;return 'normal';});assert.equal(calls,1);assert.equal(audit.some(r=>r.kind==='script_candidates_ranked'),true);assert.equal(audit.some(r=>r.kind==='script_bypass_attempt'),false);}});
test('execute uses a one-use session/input-bound grant; stale input refuses dispatch',async t=>{const {workspace,path,program}=fixture(t);const r=createScriptInterceptor({library:{programs:[program]},workspace,session:'s',goal:'检查参考文献',mode:'execute',audit:()=>{},similarity:async()=>[.95]});let normal=0;const stream=await r.intercept('s',{tools:[{name:'bash'}]},()=>{normal++;});let call;for await(const chunk of stream)if(chunk.block?.type==='tool-call')call=chunk.block;assert.equal(normal,0);const command=JSON.parse(call.arguments).command;writeFileSync(path,'changed');assert.throws(()=>consumeScriptGrant('s',command),/changed/);assert.equal(consumeScriptGrant('s',command),false);});
test('unverified result halts future bypasses',async t=>{const {workspace,program}=fixture(t);const rows=[];const r=createScriptInterceptor({library:{programs:[program]},workspace,session:'s',goal:'检查参考文献',mode:'execute',audit:r=>rows.push(r),similarity:async()=>[.95]});let call;for await(const chunk of await r.intercept('s',{tools:[{name:'bash'}]},()=>{}))if(chunk.block?.type==='tool-call')call=chunk.block;r.observe('s',{name:'bash',callId:call.id,arguments:JSON.parse(call.arguments)},{isError:false,content:[{type:'text',text:'not a receipt'}]});assert.equal(rows.at(-1).kind,'script_result_unverified');assert.equal(await r.intercept('s',{tools:[{name:'bash'}]},()=>42),42);});
test('script bindings cannot break out of generated source quoting',()=>{const command=scriptCommand({id:'x',template:"print(open('__MOTIF_INPUT_0__').read())",inputs:[{}]},['/work/inputs/a\";bad.bib'],['a'],'test');assert.ok(command.includes('a\\";bad.bib'));assert.throws(()=>scriptCommand({inputs:[{}]},['/tmp/a'],['a'],'n'),/binding/);});

test('contextual matching requires a successful compatible predecessor before embedding', async t => {
  const {workspace,program}=fixture(t);
  program.source_goal='检查书目'; program.predecessor={tool:'bash',intent:'列出输入'};
  let embeddings=0;
  const runtime=createScriptInterceptor({library:{programs:[program]},workspace,session:'s',goal:'检查书目',mode:'execute',audit:()=>{},similarity:async()=>{embeddings++;return [.99];}});
  for(const event of [null,{name:'web_search',callId:'search',arguments:{}},{name:'bash',callId:'failed-bash',arguments:{}}]){
    if(event)runtime.observe('s',event,{isError:event.name==='bash'});
    assert.equal(await runtime.intercept('s',{tools:[{name:'bash'}]},()=> 'provider'),'provider');
  }
  assert.equal(embeddings,0);
});

test('negative task intent vetoes a structurally compatible high-scoring script', async t => {
  const {workspace,program}=fixture(t),audit=[];
  program.source_goal='检查参考文献'; program.predecessor={tool:'bash',intent:'列出输入'};
  const runtime=createScriptInterceptor({library:{programs:[program]},workspace,session:'s',goal:'仅翻译摘要',mode:'execute',negativeGoals:['只翻译'],audit:row=>audit.push(row),similarity:async (_query,descriptions)=>descriptions.length===1?[.99]:[.7,.95]});
  runtime.observe('s',{name:'bash',callId:'list-inputs',arguments:{description:'列出输入'}},{isError:false});
  assert.equal(await runtime.intercept('s',{tools:[{name:'bash'}]},()=> 'provider'),'provider');
  assert.ok(audit.some(row=>row.kind==='script_goal_rejected'));
  assert.ok(!audit.some(row=>row.kind==='script_bypass_attempt'));
});

test('near-tied candidate scripts defer instead of selecting by insertion order', async t => {
  const {workspace,program}=fixture(t);
  const programs=[program,{...program,id:'second',description:'另一个可能相关的脚本'}];
  const runtime=createScriptInterceptor({library:{programs},workspace,session:'s',goal:'检查文档',mode:'execute',audit:()=>{},similarity:async()=>[.94,.93]});
  assert.equal(await runtime.intercept('s',{tools:[{name:'bash'}]},()=> 'provider'),'provider');
});

test('frontier admission exposes one initial selection without duplicating the script catalogue',t=>{
 const {workspace,program}=fixture(t),audit=[];
 program.description='count current records';program.interface={stdout_labels:['count'],imports:['re']};
 const library={programs:[program],digest:'current'};
 const runtime=createScriptInterceptor({library,workspace,session:'initial-frontier',goal:'count records',mode:'execute',executionFrontier:true,audit:r=>audit.push(r),similarity:async()=>[1]});
 t.after(()=>runtime.dispose());
 const catalogue=registerScriptCache({library,workspace,session:'initial-frontier',audit:r=>audit.push(r),frontier:runtime.frontier});
 assert.ok(catalogue.includes('candidate_ids'));
 assert.ok(catalogue.includes(program.description));
 assert.ok(!catalogue.includes(program.template));
 assert.ok(!catalogue.includes('stdout_labels'));
 assert.equal(runtime.frontier.takeNotice(),'');
 assert.equal(audit.filter(r=>r.kind==='script_frontier_notice'&&r.delivery==='initial_stable_prefix').length,1);
});
test('frontier catalogue keeps explicit cache access for operators it cannot auto-bind',t=>{
 const {workspace,path,program}=fixture(t),network={...program,id:'network',argv_contract:{max_items:2},inputs:[]};
 writeFileSync(join(workspace,'inputs','another.bib'),'@article{other}\n');
 const library={programs:[program,network],digest:'current'};
 const runtime=createScriptInterceptor({library,workspace,session:'cache-fallback',goal:'check selected document',mode:'execute',executionFrontier:true,audit:()=>{},similarity:async()=>[1]});
 t.after(()=>runtime.dispose());
 const catalogue=registerScriptCache({library,workspace,session:'cache-fallback',audit:()=>{},frontier:runtime.frontier});
 assert.ok(catalogue.includes('argv_contract'));
 assert.ok(catalogue.includes('network'));
 assert.ok(catalogue.includes(program.id));
 assert.equal(runtime.frontier.ready(),null);
});
