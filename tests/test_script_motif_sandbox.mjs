/** Real OS sandbox diagnostics. No model/provider and no manuscript data. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {sandboxRun} from '../scripts/certify-script-motifs.mjs';
import {createScriptInterceptor,consumeScriptGrant} from '../src/adapters/script_motif_runtime.ts';
const enabled=process.platform==='darwin'||process.platform==='linux'&&existsSync('/usr/bin/bwrap');
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
 for(const code of ["open('/work/inputs/data.txt','w').write('changed')",`print(open(${JSON.stringify(join(parent,'outside.txt'))}).read())`,"import socket;socket.create_connection(('127.0.0.1',80),timeout=1)"]){
  assert.throws(()=>sandboxRun(root,"python3 - <<'PY'\n"+code+'\nPY'),/sandbox_replay_failed/);
 }
 assert.equal(readFileSync(join(root,'inputs','data.txt'),'utf8'),'fresh data');
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
