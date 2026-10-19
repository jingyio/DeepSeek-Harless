/** Exact-scope negative guard diagnostics, including native ToolRuntime. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync,symlinkSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {Context} from '@deepseek-ai/cordis';
import {ToolRuntime} from '@deepseek-ai/dsh-tools';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
import {createNegativeRuntime} from '../src/adapters/script_negative_runtime.ts';
const hash=v=>createHash('sha256').update(v).digest('hex');
function fixture(t,mode='enforce'){
 const workspace=realpathSync(mkdtempSync(join(tmpdir(),'negative-motif-')));
 t.after(()=>rmSync(workspace,{recursive:true,force:true}));
 mkdirSync(join(workspace,'inputs'));mkdirSync(join(workspace,'outputs'));
 writeFileSync(join(workspace,'inputs','source.txt'),'current');
 writeFileSync(join(workspace,'approved-inputs.json'),JSON.stringify({files:{'source.txt':hash('current')}}));
 const state=join(workspace,'outputs','draft.json');writeFileSync(state,'{"invalid":true}');
 const version=hash('{"invalid":true}'),tools=[{name:'mcp__docs__finalize',parameters:{type:'object'}}],events=[];
 const rule={id:'negative-diagnostic',tool:'mcp__docs__finalize',failure_code:'invalid_shape',tools_sha256:digest(tools),
  retry_policy:'warn_then_exact_version_block',failure_flags:[['done']],version_slots:[{argument_path:['version'],result_path:['current_version']}]};
 const runtime=createNegativeRuntime({library:{rules:[rule]},workspace,mode,audit:r=>events.push(r)});
 const call={name:rule.tool,arguments:{version}};
 const request=(system='')=>({system,tools,messages:[]});runtime.beforeRequest(request());
 const fail=()=>runtime.observe(call,{isError:false,content:[{type:'text',text:JSON.stringify({done:false,validation_error:'invalid_shape',current_version:version})}]});
 const warn=()=>{const p=runtime.prompt();runtime.beforeRequest(request(p));return p;};
 return {runtime,call,fail,warn,request,state,workspace,events,version};
}
test('history alone and a prompt accessor do not authorize early stopping',t=>{
 const f=fixture(t);assert.equal(f.runtime.guard(f.call),undefined);
 f.fail();assert.match(f.runtime.prompt(),/invalid_shape/);assert.equal(f.runtime.guard(f.call),undefined);
 f.warn();assert.match(f.runtime.guard(f.call),/早停/);
 assert.equal(f.events.filter(e=>e.kind==='negative_prompt_delivered').length,1);
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
test('native tool guard stops the retry body and leaves different tools usable',async t=>{
 const f=fixture(t);const ctx=new Context();ctx.systemPrompt={tools(){}};const tools=new ToolRuntime(ctx);let calls=0;
 const disposers=[tools.guard(f.runtime.guard),ctx.on('tools/result',f.runtime.observe)];
 t.after(()=>disposers.reverse().forEach(d=>d()));
 for(const name of [f.call.name,'mcp__docs__repair'])disposers.push(tools.register({name,description:'diagnostic',parameters:{type:'object'},
  output:{schema:{type:'object'},render:(_a,v)=>[{type:'text',text:JSON.stringify(v)}]},async execute(){calls++;return {done:false,validation_error:'invalid_shape',current_version:f.version};}}));
 const run=(name,id)=>tools.execute({name,arguments:f.call.arguments,callId:id,signal:new AbortController().signal});
 assert.equal((await run(f.call.name,'first')).isError,false);f.warn();
 assert.equal((await run(f.call.name,'repeat')).isError,true);assert.equal(calls,1);
 assert.equal((await run(f.call.name,'repeat-again')).isError,true);assert.equal(calls,1);
 assert.equal((await run('mcp__docs__repair','alternative')).isError,false);assert.equal(calls,2);
});
