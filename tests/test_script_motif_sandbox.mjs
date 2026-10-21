/** Real OS sandbox diagnostics. No model/provider and no manuscript data. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,existsSync,lstatSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {sandboxRun} from '../scripts/certify-script-motifs.mjs';
import {createScriptInterceptor,consumeScriptGrant} from '../src/adapters/script_motif_runtime.ts';
const enabled=process.platform==='darwin'||process.platform==='linux'&&existsSync('/usr/bin/bwrap');
const linuxEnabled=process.platform==='linux'&&existsSync('/usr/bin/bwrap');
if(process.platform==='darwin')process.env.SSS_LOCAL_SCRIPT_EXPERIMENT='1';
function fixture(t){
 const parent=realpathSync(mkdtempSync(join(tmpdir(),'script-sandbox-'))),root=join(parent,'work');
 for(const p of ['inputs','code','outputs/code','command-tmp'])mkdirSync(join(root,p),{recursive:true});
 writeFileSync(join(root,'inputs','data.txt'),'fresh data');writeFileSync(join(parent,'outside.txt'),'OUTSIDE_SENTINEL');
 t.after(()=>rmSync(parent,{recursive:true,force:true}));return {root,parent};
}
test('sandbox permits current input reads, denies user-file writes, unrelated reads and network',{skip:!enabled},t=>{
 const {root,parent}=fixture(t);
 assert.equal(sandboxRun(root,'python3 -c "print(open(\'/work/inputs/data.txt\').read())"'),'fresh data\n');
 for(const code of ["open('/work/inputs/data.txt','w').write('changed')","open('/work/not-allowed.txt','w').write('changed')",`print(open(${JSON.stringify(join(parent,'outside.txt'))}).read())`,"import socket;socket.create_connection(('127.0.0.1',80),timeout=1)"]){
  assert.throws(()=>sandboxRun(root,"python3 - <<'PY'\n"+code+'\nPY'),/sandbox_replay_failed/);
 }
 assert.equal(readFileSync(join(root,'inputs','data.txt'),'utf8'),'fresh data');
});
test('first read-only invocation prepares fixed child mount points without a prior writable command',{skip:!linuxEnabled},t=>{
 const {root}=fixture(t);
 for(const name of ['inputs','outputs'])assert.equal(existsSync(join(root,'code',name)),false);
 assert.equal(sandboxRun(root,'python3 -c "print(open(\'/work/inputs/data.txt\').read())"'),'fresh data\n');
 for(const name of ['inputs','outputs'])assert.ok(lstatSync(join(root,'code',name)).isDirectory());
});
test('sandbox refuses redirected scratch and child mount points before launching a command',{skip:!linuxEnabled},t=>{
 const {root,parent}=fixture(t),scratch=join(root,'code');
 for(const name of ['inputs','outputs'])for(const kind of ['symlink','file']){
  const point=join(scratch,name);
  if(kind==='symlink')symlinkSync(parent,point);else writeFileSync(point,'not a mount directory');
  assert.throws(()=>sandboxRun(root,'true'),/fixed directory/);
  rmSync(point);
 }
 rmSync(scratch,{recursive:true});symlinkSync(parent,scratch);
 assert.throws(()=>sandboxRun(root,'true'),/fixed directory/);
 assert.equal(existsSync(join(parent,'inputs')),false,'rejected aliases must not create mount points outside scratch');
});
test('actual sandbox receipt verifies a skipped provider decision; source stays out of tool arguments',{skip:!enabled},async t=>{
 const {root}=fixture(t),rows=[];
 const program={id:'script_diagnostic',template:"print(open('__MOTIF_INPUT_0__').read())",inputs:[{suffix:'.txt',format:'text'}],description:'read current input'};
 const runtime=createScriptInterceptor({library:{programs:[program]},workspace:root,session:'s',goal:'read input',mode:'execute',similarity:async()=>[.95],audit:r=>rows.push(r)});
 let call;for await(const chunk of await runtime.intercept('s',{tools:[{name:'bash'}]},()=>{throw Error('provider must not run');}))if(chunk.block?.type==='tool-call')call=chunk.block;
 const args=JSON.parse(call.arguments);assert.ok(!args.command.includes('print('));
 const body=consumeScriptGrant('s',args.command);assert.equal(typeof body,'string');
 const stdout=sandboxRun(root,body);runtime.observe('s',{callId:call.id,name:'bash',arguments:args},{isError:false,content:[{type:'text',text:stdout}]});
 assert.equal(rows.at(-1).kind,'script_model_request_skipped_verified');
 assert.equal(await runtime.intercept('s',{tools:[{name:'bash'}]},()=>42),42);
});
test('post-execute compact content preserves full stdout and raw proof without mutating frozen values',{skip:!enabled},async t=>{
 const {root}=fixture(t),audit=[];
 const program={id:'script_evidence',template:"print(open('__MOTIF_INPUT_0__').read())",inputs:[{suffix:'.txt',format:'text'}],description:'read input'};
 const runtime=createScriptInterceptor({library:{programs:[program]},workspace:root,session:'compact',goal:'read',mode:'execute',compactContext:true,similarity:async()=>[.95],audit:r=>audit.push(r)});
 t.after(()=>runtime.dispose());let call;
 for await(const chunk of await runtime.intercept('compact',{tools:[{name:'bash'}]},()=>{}))if(chunk.block?.type==='tool-call')call=chunk.block;
 const arguments_=JSON.parse(call.arguments),text=sandboxRun(root,consumeScriptGrant('compact',arguments_.command));
 const execution=Object.freeze({callId:call.id,name:'bash',arguments:Object.freeze(arguments_)});
 const content=Object.freeze([Object.freeze({type:'text',text})]),value=Object.freeze({stdout:text});
 const result=Object.freeze({isError:false,content,value});
 const projected=runtime.projectResult(execution,result),view=JSON.parse(projected[0].text);
 assert.equal(view.stdout,JSON.parse(text).output);assert.equal(view.program,program.id);assert.equal(view.inputs[0].path,'/work/inputs/data.txt');
 assert.equal(result.content,content);assert.equal(result.value,value);assert.equal(result.content[0].text,text);
 const raw=audit.find(a=>a.kind==='script_evidence_raw');assert.deepEqual(raw.content,content);
 assert.equal(runtime.projectResult({...execution,callId:'forged'},result),undefined);
 assert.equal(runtime.projectResult(execution,{...result,content:[{type:'text',text:JSON.stringify({...JSON.parse(text),output:'tampered'})}]}),undefined);
 writeFileSync(join(root,'inputs/data.txt'),'new version');assert.equal(runtime.projectResult(execution,result),undefined);
 writeFileSync(join(root,'inputs/data.txt'),'fresh data');
 runtime.observe('compact',execution,{...result,content:projected});
 assert.ok(audit.some(a=>a.kind==='script_model_request_skipped_verified'));
 assert.equal(await runtime.intercept('compact',Object.freeze({tools:[{name:'bash'}],messages:Object.freeze([])}),()=>42),42);
});
test('later post-policy changes cannot turn projected evidence into a verified result',{skip:!enabled},async t=>{
 const {root}=fixture(t),audit=[],program={id:'script',template:"print(open('__MOTIF_INPUT_0__').read())",inputs:[{suffix:'.txt',format:'text'}]};
 const runtime=createScriptInterceptor({library:{programs:[program]},workspace:root,session:'changed',goal:'read',mode:'execute',compactContext:true,similarity:async()=>[.95],audit:r=>audit.push(r)});
 t.after(()=>runtime.dispose());let call;
 for await(const c of await runtime.intercept('changed',{tools:[{name:'bash'}]},()=>{}))if(c.block?.type==='tool-call')call=c.block;
 const execution={callId:call.id,name:'bash',arguments:JSON.parse(call.arguments)},result={content:[{type:'text',text:sandboxRun(root,consumeScriptGrant('changed',execution.arguments.command))}]};
 const projected=runtime.projectResult(execution,result);assert.ok(projected);
 runtime.observe('changed',execution,{content:[{type:'text',text:projected[0].text+'changed'}]});
 assert.ok(audit.some(a=>a.kind==='script_result_unverified'));assert.equal(await runtime.intercept('changed',{tools:[{name:'bash'}]},()=>42),42);
});
test('certified JSON fields are checked on fresh outputs and verified values reach artifact mediation',{skip:!enabled},async t=>{
 const {root}=fixture(t);writeFileSync(join(root,'inputs/data.txt'),'7');
 for(const type of ['number','string']){
  const audit=[],session='fields-'+type,program={id:'fields',template:"import json\nprint(json.dumps({'count':int(open('__MOTIF_INPUT_0__').read())}))",inputs:[{suffix:'.txt',format:'text'}],certification:{output_schema:{type:'object',required:['count'],properties:{count:{type}}}}};
  const runtime=createScriptInterceptor({library:{programs:[program]},workspace:root,session,goal:'count',mode:'execute',compactContext:true,similarity:async()=>[.95],audit:r=>audit.push(r)});t.after(()=>runtime.dispose());
  let call;for await(const c of await runtime.intercept(session,{tools:[{name:'bash'}]},()=>{}))if(c.block?.type==='tool-call')call=c.block;
  const execution={callId:call.id,name:'bash',arguments:JSON.parse(call.arguments)},result={content:[{type:'text',text:sandboxRun(root,consumeScriptGrant(session,execution.arguments.command))}]};
  const facts=runtime.observe(session,execution,result);
  assert.equal(facts.length,type==='number'?1:0);
  if(type==='number')assert.deepEqual(JSON.parse(facts[0].output),{count:7});
  else assert.ok(audit.some(a=>a.kind==='script_result_schema_mismatch'));
 }
});

import {registerScriptCache,prepareCacheInvocation,scriptCommand} from '../src/adapters/script_motif_runtime.ts';
import {runCertifiedScript} from '../scripts/run-certified-script.mjs';
import {createHash} from 'node:crypto';
test('model-selected cache rebinds fresh input and unlocks only its learned successor',{skip:!enabled},async t=>{
 const {root}=fixture(t),rows=[],session='demand-bound';
 const first={id:'read',template:"print(open('__MOTIF_INPUT_0__').read())",inputs:[{suffix:'.txt',format:'text'}],intent:'read current data',description:'read current data'};
 const second={...first,id:'length',template:"print(len(open('__MOTIF_INPUT_0__').read()))",source_goal:'check document',predecessor:{tool:'bash',program_id:'read',intent:'read current data'}};
 const library={programs:[first,second]};
 const runtime=createScriptInterceptor({library,workspace:root,session,goal:'check document',mode:'execute',demandBound:true,audit:r=>rows.push(r),similarity:async(_q,d)=>d.map(()=>.99)});
 t.after(()=>runtime.dispose());registerScriptCache({library,workspace:root,session,audit:r=>rows.push(r)});
 runtime.observe(session,{name:'bash',callId:'unrelated',arguments:{description:'read current data'}},{isError:false});
 assert.equal(await runtime.intercept(session,{tools:[{name:'bash'}]},()=> 'provider'),'provider');
 assert.throws(()=>prepareCacheInvocation(session,'geneloop-cache '+JSON.stringify({calls:[{id:'read',paths:['/work/../../outside.txt']}]})),/fixed/);
 const command='geneloop-cache '+JSON.stringify({calls:[{id:'read',paths:['/work/inputs/data.txt']}]});
 const batch=prepareCacheInvocation(session,command);
 const receipt=runCertifiedScript(batch.jobs[0]);assert.equal(receipt.output,'fresh data\n');
 writeFileSync(join(root,'code/unrelated.txt'),'another same-format document');
 runtime.observe(session,{name:'bash',callId:'selected',arguments:{command}},{content:[{type:'text',text:JSON.stringify({kind:'script_cache_batch_receipt',receipts:[receipt]})}]});
 let call;for await(const chunk of await runtime.intercept(session,{tools:[{name:'bash'}]},()=>{throw Error('provider bypass expected');}))if(chunk.block?.type==='tool-call')call=chunk.block;
 const args=JSON.parse(call.arguments),body=consumeScriptGrant(session,args.command);
 runtime.observe(session,{name:'bash',callId:call.id,arguments:args},{content:[{type:'text',text:sandboxRun(root,body)}]});
 assert.ok(rows.some(r=>r.kind==='script_cache_verified'));
 assert.ok(rows.some(r=>r.kind==='script_model_request_skipped_verified'));
});
test('network script is suspended in sandbox and consumes only hashed fresh snapshots',{skip:!enabled},t=>{
 const {root}=fixture(t),url='https://export.arxiv.org/api/query?id_list=1606.08415',program={id:'http-diagnostic',inputs:[],network_policy:'fixed_metadata_get_v1',template:`import urllib.request\nprint(urllib.request.urlopen('${url}').read().decode())`};
 const demand=JSON.parse(sandboxRun(root,scriptCommand(program,[],[],'n')));
 assert.equal(demand.kind,'script_http_demand');assert.equal(demand.url,url);
 const bytes='current metadata';writeFileSync(join(root,'code/response'),bytes);
 const http={[url]:{file:'/work/response',sha256:createHash('sha256').update(bytes).digest('hex')}};
 assert.equal(JSON.parse(sandboxRun(root,scriptCommand(program,[],[],'n',{http}))).output,bytes+'\n');
 writeFileSync(join(root,'code/response'),'changed');
 assert.throws(()=>sandboxRun(root,scriptCommand(program,[],[],'n',{http})),/sandbox_replay_failed/);
});

import ScriptMotifShell from '../src/adapters/script_motif_shell.ts';
import {commandLayout} from '../src/adapters/geneloop_shell.ts';
import {spawnSync} from 'node:child_process';
test('native shell resolution dispatches the cache driver without exposing source',{skip:!enabled},t=>{
 const {root}=fixture(t),session='sss-1234567890abcdef1234567890abcdef',layout=commandLayout(root,session);
 writeFileSync(join(layout.inputs,'current.txt'),'fresh bridge input');
 const program={id:'bridge',template:"print(open('__MOTIF_INPUT_0__').read())",inputs:[{suffix:'.txt',format:'text'}]};
 registerScriptCache({session,workspace:layout.work,library:{programs:[program]},audit:()=>{}});
 const policy=join(root,'policy.json');writeFileSync(policy,JSON.stringify({output:root,command_resources:{network:'none'}}));
 const prior=process.env.SSS_WEB_POLICY;process.env.SSS_WEB_POLICY=policy;t.after(()=>{if(prior===undefined)delete process.env.SSS_WEB_POLICY;else process.env.SSS_WEB_POLICY=prior;});
 const shell=Object.create(ScriptMotifShell.prototype);
 Object.defineProperty(shell,'ctx',{value:{get:()=>({currentInitiator:()=>({session:{id:session,header:{cwd:layout.scratch}}})})}});
 Object.defineProperty(shell,'config',{value:{timeoutMs:10000,maxTimeoutMs:20000,maxOutputBytes:64000}});
 const command='cd /work && geneloop-cache '+JSON.stringify({calls:[{id:'bridge',paths:['/work/inputs/current.txt']}]});
 assert.throws(()=>shell.resolve({command:command+' 2>&1 | head -60'}),/不要附加 head/);
 assert.throws(()=>shell.resolve({command:command.replace('cd /work','cd /work/../../etc')}),/workspace/);
 const spec=shell.resolve({command});assert.ok(!command.includes(program.template));
 const run=spawnSync(spec.geneloopArgv[0],spec.geneloopArgv.slice(1),{encoding:'utf8',timeout:15000});
 assert.equal(run.status,0,run.stderr);assert.equal(JSON.parse(run.stdout).receipts[0].output,'fresh bridge input\n');
});

import {observeScriptCache} from '../src/adapters/script_motif_runtime.ts';
test('partial or malformed batch never publishes a verified continuation anchor',{skip:!enabled},t=>{
 const {root}=fixture(t),session='atomic-cache',audit=[];
 const program={id:'atomic',inputs:[{suffix:'.txt',format:'text'}],template:"print(open('__MOTIF_INPUT_0__').read())"};
 registerScriptCache({session,workspace:root,library:{programs:[program]},audit:r=>audit.push(r)});
 const command='geneloop-cache '+JSON.stringify({calls:[{id:'atomic',paths:['/work/inputs/data.txt']},{id:'atomic',paths:['/work/inputs/data.txt']}]});
 const jobs=prepareCacheInvocation(session,command).jobs,first=runCertifiedScript(jobs[0]);
 const facts=observeScriptCache(session,{name:'bash',arguments:{command}},{content:[{type:'text',text:JSON.stringify({kind:'script_cache_batch_receipt',receipts:[first,{...first,nonce:jobs[1].nonce,output_sha256:'changed'}]})}]});
 assert.deepEqual(facts,[]);assert.ok(!audit.some(r=>r.kind==='script_cache_verified'));assert.equal(audit.at(-1).kind,'script_cache_result_unverified');
});

test('typed current choice drives two real sandbox nodes with no intervening provider call',{skip:!enabled},async t=>{
 const {root}=fixture(t),session='frontier-sandbox',rows=[];
 const first={id:'frontier-read',inputs:[{suffix:'.txt',format:'text'}],template:"print(open('__MOTIF_INPUT_0__').read())",interface:{stdout_labels:['text']}};
 const second={...first,id:'frontier-count',template:"print(len(open('__MOTIF_INPUT_0__').read()))",predecessor:{program_id:first.id}};
 const library={programs:[first,second],digest:'diagnostic'};
 const runtime=createScriptInterceptor({library,workspace:root,session,goal:'check this document',mode:'execute',executionFrontier:true,
   similarity:async()=>{throw Error('not an embedding decision');},audit:r=>rows.push(r)});
 registerScriptCache({library,workspace:root,session,audit:r=>rows.push(r),frontier:runtime.frontier});t.after(()=>runtime.dispose());
 const gap=JSON.parse(runtime.frontierPrompt().split('\n').at(-1));
 const command='geneloop-resolve '+JSON.stringify({request_id:gap.request_id,status:'selected',candidate_id:gap.candidates[0].id});
 const receipt=prepareCacheInvocation(session,command).control_receipt;
 runtime.observe(session,{name:'bash',arguments:{command}},{content:[{type:'text',text:JSON.stringify(receipt)}]});
 for(let step=0;step<2;step++){
  let call;for await(const chunk of await runtime.intercept(session,{tools:[{name:'bash'}]},()=>{throw Error('provider must not run between nodes');}))if(chunk.block?.type==='tool-call')call=chunk.block;
  const args=JSON.parse(call.arguments),body=consumeScriptGrant(session,args.command);
  runtime.observe(session,{callId:call.id,name:'bash',arguments:args},{content:[{type:'text',text:sandboxRun(root,body)}]});
 }
 assert.equal(rows.filter(r=>r.kind==='script_model_request_skipped_verified').length,2);
 assert.equal(rows.filter(r=>r.kind==='script_frontier_completed').length,1);
 assert.equal(await runtime.intercept(session,{tools:[{name:'bash'}]},()=> 'semantic conclusion still needed'),'semantic conclusion still needed');
});

import {bindScript,scriptVirtualHost} from '../src/adapters/script_motif_runtime.ts';
test('current output scratch inputs bind through canonical virtual paths, preserving version guards',{skip:!enabled},t=>{
 const {root}=fixture(t);mkdirSync(join(root,'outputs/code/unz'));writeFileSync(join(root,'outputs/code/unz/source.bib'),'current bibliography');
 const program={id:'output-scope',inputs:[{suffix:'.bib',format:'text'}],template:"print(open('__MOTIF_INPUT_0__').read())"};
 const bound=bindScript(program,root);assert.equal(bound[0].path,'/work/outputs/unz/source.bib');
 assert.equal(scriptVirtualHost(root,bound[0].path),join(root,'outputs/code/unz/source.bib'));
 const session='outputs-binding';registerScriptCache({session,workspace:root,library:{programs:[program]},audit:()=>{}});
 const command='cd /work/outputs/unz && geneloop-cache '+JSON.stringify({calls:[{id:program.id,paths:[bound[0].path]}]});
 const job=prepareCacheInvocation(session,command).jobs[0];assert.equal(runCertifiedScript(job).output,'current bibliography\n');
 writeFileSync(join(root,'outputs/code/unz/source.bib'),'changed');assert.throws(()=>runCertifiedScript(job),/sandbox_failed/);
 writeFileSync(join(root,'code/another.bib'),'different');assert.throws(()=>bindScript(program,root),/ambiguous/);
});

test('a changed current user envelope cancels a selected frontier before executing',{skip:!enabled},async t=>{
 const {root}=fixture(t),session='goal-change',rows=[];
 const a={id:'a',inputs:[{suffix:'.txt',format:'text'}],template:"print(open('__MOTIF_INPUT_0__').read())"};
 const library={programs:[a,{...a,id:'b',predecessor:{program_id:'a'}}]};
 const runtime=createScriptInterceptor({library,workspace:root,session,goal:'check document',mode:'execute',executionFrontier:true,similarity:async()=>[1],audit:r=>rows.push(r)});
 registerScriptCache({library,workspace:root,session,audit:()=>{},frontier:runtime.frontier});t.after(()=>runtime.dispose());
 const options={tools:[{name:'bash'}],messages:[{id:'u',role:'user',source:{kind:'user'},content:[{type:'text',text:'check document'}]}]};
 assert.equal(await runtime.intercept(session,options,()=> 'model'),'model');
 const gap=JSON.parse(runtime.frontierPrompt().split('\n').at(-1));
 const command='geneloop-resolve '+JSON.stringify({request_id:gap.request_id,status:'selected',candidate_id:gap.candidates[0].id});
 const receipt=prepareCacheInvocation(session,command).control_receipt;
 runtime.observe(session,{name:'bash',arguments:{command}},{content:[{type:'text',text:JSON.stringify(receipt)}]});
 const changed={...options,messages:[...options.messages,{id:'new',role:'user',source:{kind:'user'},content:[{type:'text',text:'translate only; no checks'}]}]};
 assert.equal(await runtime.intercept(session,changed,()=> 'new semantic decision'),'new semantic decision');
 assert.ok(rows.some(r=>r.reason==='user_goal_changed'));assert.ok(!rows.some(r=>r.kind==='script_bypass_attempt'));
});
