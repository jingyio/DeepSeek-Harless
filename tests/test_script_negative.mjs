/** Exact-scope negative guard diagnostics, including native ToolRuntime. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,symlinkSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {Context} from '@deepseek-ai/cordis';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createNegativeRuntime} from '../src/adapters/script_negative_runtime.ts';
import {evaluateFieldGuard,validateFieldGuard} from '../src/adapters/negative_field_runtime.ts';
const hash=v=>createHash('sha256').update(v).digest('hex');
function fixture(t,mode='enforce',fieldGuard=null,document=null,toolScoped=false){
 const workspace=realpathSync(mkdtempSync(join(tmpdir(),'negative-motif-')));
 t.after(()=>rmSync(workspace,{recursive:true,force:true}));
 mkdirSync(join(workspace,'inputs'));mkdirSync(join(workspace,'outputs'));
 writeFileSync(join(workspace,'inputs','source.txt'),'current');
 writeFileSync(join(workspace,'approved-inputs.json'),JSON.stringify({files:{'source.txt':hash('current')}}));
 const initial=fieldGuard?JSON.stringify(document??{owner:'current',report:{records:[{tag:'a'},{tag:'a'}],notes:['first','second'],title:'sample'}}):'{"invalid":true}';
 const state=join(workspace,'outputs','draft.json');writeFileSync(state,initial);
 const version=hash(initial),tools=[{name:'mcp__docs__finalize',parameters:{type:'object'}}],events=[];
 const rule={id:'negative-diagnostic',tool:'mcp__docs__finalize',failure_code:'invalid_shape',tools_sha256:digest(tools),
  retry_policy:'warn_then_exact_version_block',failure_flags:[['done']],version_slots:[{argument_path:['version'],result_path:['current_version']}]};
 if(fieldGuard){rule.retry_policy='warn_then_field_guard';rule.field_guard=fieldGuard;}
 if(toolScoped){rule.retry_policy='prompt_only';rule.tool_schema_sha256=digest(tools[0].parameters);rule.schema_scope='exact_tool_schema_prompt_only';}
 const runtime=createNegativeRuntime({library:{rules:[rule]},workspace,mode,audit:r=>events.push(r)});
 const call={name:rule.tool,arguments:{version}};
 const request=(system='')=>({system,tools,messages:[]});runtime.beforeRequest(request());
 const fail=()=>runtime.observe(call,{isError:false,content:[{type:'text',text:JSON.stringify({done:false,validation_error:'invalid_shape',current_version:version})}]});
 const warn=()=>{const p=runtime.prompt();runtime.beforeRequest(request(p));return p;};
 return {runtime,call,fail,warn,request,state,workspace,events,version,tools};
}
test('tool-scoped prompt advice tolerates added unrelated tools without granting retry blocking',t=>{
 const f=fixture(t,'enforce',null,null,true),request={...f.request(),tools:[...f.tools,{name:'read_image',parameters:{type:'object'}}]};
 f.runtime.beforeRequest(request);f.fail();const text=f.runtime.takeNotice();assert.match(text,/invalid_shape/);
 f.runtime.beforeRequest({...request,system:text});assert.equal(f.events.filter(e=>e.kind==='negative_prompt_delivered').length,1);
 assert.equal(f.runtime.guard(f.call),undefined);
});
test('changed target schema invalidates tool-scoped advice and legacy rules still require the entire catalog',t=>{
 const f=fixture(t,'prompt',null,null,true);f.fail();assert.match(f.runtime.prompt(),/invalid_shape/);
 f.runtime.beforeRequest({...f.request(),tools:[{...f.tools[0],parameters:{type:'object',required:['new']}}]});
 assert.equal(f.runtime.prompt(),'');f.fail();assert.equal(f.runtime.prompt(),'');
 const legacy=fixture(t,'prompt');legacy.runtime.beforeRequest({...legacy.request(),tools:[...legacy.tools,{name:'new_tool',parameters:{}}]});
 legacy.fail();assert.equal(legacy.runtime.prompt(),'');
});
test('history alone and a prompt accessor do not authorize early stopping',t=>{
 const f=fixture(t);assert.equal(f.runtime.guard(f.call),undefined);
 f.fail();assert.match(f.runtime.prompt(),/invalid_shape/);assert.equal(f.runtime.guard(f.call),undefined);
 f.warn();assert.match(f.runtime.guard(f.call),/早停/);
 assert.equal(f.events.filter(e=>e.kind==='negative_prompt_delivered').length,1);
});
test('Python-compiled dependency survives irrelevant edits and releases only when repaired or uncertain',t=>{
 const run=spawnSync(process.env.SSS_PYTHON??'python3',['-c',"import sys,json;sys.path.insert(0,'tests');from test_negative_fields import compiled_sample;print(json.dumps(compiled_sample()))"],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);const guard=validateFieldGuard(JSON.parse(run.stdout));
 const f=fixture(t,'enforce',guard);f.fail();assert.match(f.warn(),/records/);
 const document={owner:'current',report:{records:[{tag:'a'},{tag:'a'}],notes:['changed'],title:'new title'}};
 const write=()=>{const raw=JSON.stringify(document);writeFileSync(f.state,raw);return {...f.call,arguments:{version:hash(raw)}};};
 assert.match(f.runtime.guard(write()),/早停/); // Full file SHA changed; cause did not.
 document.report.records[0].tag='b';document.report.records[1].tag='b';
 assert.match(f.runtime.guard(write()),/早停/); // Related fields changed, but still violate the predicate.
 document.report.records[1].tag='c';assert.equal(f.runtime.guard(write()),undefined);
 assert.equal(f.runtime.prompt(),'');
 assert.equal(evaluateFieldGuard(guard,{report:{records:[{tag:4},{tag:4}]}}),null);
});
test('field guard never crosses the wrapper owner context or masks a changed semantic argument',t=>{
 const run=spawnSync(process.env.SSS_PYTHON??'python3',['-c',"import sys,json;sys.path.insert(0,'tests');from test_negative_fields import compiled_sample;print(json.dumps(compiled_sample()))"],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);const guard=JSON.parse(run.stdout),f=fixture(t,'enforce',guard);f.fail();f.warn();
 assert.equal(f.runtime.guard({...f.call,arguments:{...f.call.arguments,scope:'different'}}),undefined);
 const changed=JSON.stringify({owner:'other-task',report:{records:[{tag:'a'},{tag:'a'}]}});writeFileSync(f.state,changed);
 assert.equal(f.runtime.guard({...f.call,arguments:{version:hash(changed)}}),undefined);
});
test('multiple Python-learned error families agree with TS and gate changed-version retries',t=>{
 const result=spawnSync(process.env.SSS_PYTHON??'python3',['-c',"import sys,json;sys.path.insert(0,'tests');from test_negative_fields import compiled_cases;print(json.dumps(compiled_cases()))"],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);const cases=JSON.parse(result.stdout);assert.equal(cases.length,7);
 for(const c of cases){
  const guard=validateFieldGuard(c.guard);
  assert.equal(evaluateFieldGuard(guard,c.failed),true);assert.equal(evaluateFieldGuard(guard,c.valid),false);
  const f=fixture(t,'enforce',guard,{owner:'current',...c.failed});f.fail();f.warn();
  const changed=JSON.stringify({owner:'current',report:{...c.failed.report,irrelevant_note:'edited'}});writeFileSync(f.state,changed);
  assert.match(f.runtime.guard({...f.call,arguments:{version:hash(changed)}}),/早停/);
  const repaired=JSON.stringify({owner:'current',...c.valid});writeFileSync(f.state,repaired);
  assert.equal(f.runtime.guard({...f.call,arguments:{version:hash(repaired)}}),undefined);
  const absent={owner:'current',report:{}};assert.equal(evaluateFieldGuard(guard,absent),null);
 }
});
test('v2 requires two-way cause evidence and rejects free variables and oversized IR',()=>{
 const result=spawnSync(process.env.SSS_PYTHON??'python3',['-c',"import sys,json;sys.path.insert(0,'tests');from test_negative_fields import compiled_sample;print(json.dumps(compiled_sample()))"],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);const guard=JSON.parse(result.stdout);
 const missing=structuredClone(guard);delete missing.certification.cause_interventions.reintroduction;
 assert.throws(()=>validateFieldGuard(missing),/cause/);
 assert.throws(()=>validateFieldGuard(guard,'another_error'),/inconsistent_cause_error/);
 assert.throws(()=>validateFieldGuard({...guard,predicate:{op:'var',name:'v1'}}),/unsupported_field/);
 assert.throws(()=>validateFieldGuard({...guard,predicate:{op:'array',values:Array.from({length:300},()=>({op:'const',value:true}))}}),/invalid_field_guard/);
 assert.equal(evaluateFieldGuard(guard,{report:{records:Array(10001).fill({tag:'a'})}}),null);
});
test('prompt mode never denies an execution',t=>{
 const f=fixture(t,'prompt');f.fail();f.warn();assert.equal(f.runtime.guard(f.call),undefined);
});
for(const mutation of ['parameters','state','source','schema','human','symlink'])test(mutation+' change releases the exact retry guard',t=>{
 const f=fixture(t);f.fail();f.warn();let call=f.call;
 if(mutation==='parameters')call={...call,arguments:{...call.arguments,repair:true}};
 if(mutation==='state')writeFileSync(f.state,'{"fixed":true}');
 if(mutation==='source')writeFileSync(join(f.workspace,'inputs','source.txt'),'new source');
 if(mutation==='schema')f.runtime.beforeRequest({...f.request(f.runtime.prompt()),tools:[]});
 if(mutation==='human')f.runtime.beforeRequest({...f.request(f.runtime.prompt()),messages:[{role:'user',source:{kind:'user'},id:'new',content:[{type:'text',text:'new goal'}]}]});
 if(mutation==='symlink'){rmSync(f.state);writeFileSync(join(f.workspace,'outside.json'),'{"invalid":true}');symlinkSync(join(f.workspace,'outside.json'),f.state);}
 assert.equal(f.runtime.guard(call),undefined);
});
test('missing and ambiguous authoritative version anchors remain prompt-only',t=>{
 const f=fixture(t);writeFileSync(join(f.workspace,'outputs','duplicate.json'),'{"invalid":true}');
 f.fail();f.warn();assert.equal(f.runtime.guard(f.call),undefined);
});
test('opaque and transient errors do not become deterministic negative patterns',t=>{
 const f=fixture(t);f.runtime.observe(f.call,{isError:true,content:[{type:'text',text:'HTTP 502'}]});
 assert.equal(f.runtime.prompt(),'');assert.equal(f.runtime.guard(f.call),undefined);
});
test('native MCP canonical wrappers use the shared observation decoder',t=>{
 const f=fixture(t);const packet={content:[{type:'text',text:JSON.stringify({done:false,validation_error:'invalid_shape',current_version:f.version})}],isError:false};
 f.runtime.observe(f.call,{isError:false,value:packet,content:packet.content});
 assert.match(f.warn(),/invalid_shape/);assert.match(f.runtime.guard(f.call),/早停/);
});
test('new opaque error or a different failure invalidates the previous negative evidence',t=>{
 for(const result of [{isError:true,content:[]},{isError:false,value:{validation_error:'different_problem'}},
  {isError:false,value:{done:true,validation_error:'invalid_shape'}}]){
  const f=fixture(t);f.fail();f.warn();f.runtime.observe(f.call,result);
  assert.equal(f.runtime.guard(f.call),undefined);assert.equal(f.runtime.prompt(),'');
 }
});
for(const field of [false,true])test('native tool guard stops '+(field?'field-dependent changed-version':'exact')+' retry body and leaves different tools usable',async t=>{
 let guard=null;
 if(field){const result=spawnSync(process.env.SSS_PYTHON??'python3',['-c',"import sys,json;sys.path.insert(0,'tests');from test_negative_fields import compiled_sample;print(json.dumps(compiled_sample()))"],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);guard=JSON.parse(result.stdout);}
 const f=fixture(t,'enforce',guard);const ctx=new Context();ctx.systemPrompt={tools(){}};const tools=new ToolRuntime(ctx);let calls=0;
 const disposers=[tools.guard(f.runtime.guard),ctx.on('tools/result',f.runtime.observe)];
 t.after(()=>disposers.reverse().forEach(d=>d()));
 for(const name of [f.call.name,'mcp__docs__repair'])disposers.push(tools.register({name,description:'diagnostic',parameters:{type:'object'},
  output:{schema:{type:'object'},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},async execute(){calls++;return {done:false,validation_error:'invalid_shape',current_version:f.version};}}));
 let args=f.call.arguments;
 const run=(name,id)=>tools.execute({name,arguments:args,callId:id,signal:new AbortController().signal});
 assert.equal((await run(f.call.name,'first')).isError,false);f.warn();
 if(field){const changed=JSON.stringify({owner:'current',report:{records:[{tag:'a'},{tag:'a'}],notes:['new'],title:'changed'}});writeFileSync(f.state,changed);args={version:hash(changed)};}
 assert.equal((await run(f.call.name,'repeat')).isError,true);assert.equal(calls,1);
 assert.equal((await run(f.call.name,'repeat-again')).isError,true);assert.equal(calls,1);
 assert.equal((await run('mcp__docs__repair','alternative')).isError,false);assert.equal(calls,2);
});
test('Python tuple type is preserved and cannot activate a false list gate',()=>{
 const result=spawnSync(process.env.SSS_PYTHON??'python3',['-c',"import sys,json;sys.path.insert(0,'tests');from test_negative_fields import compiled_container_case;print(json.dumps(compiled_container_case()))"],{encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);const c=JSON.parse(result.stdout),guard=validateFieldGuard(c.guard);
 assert.equal(evaluateFieldGuard(guard,c.failed),true);assert.equal(evaluateFieldGuard(guard,c.valid),false);
});
