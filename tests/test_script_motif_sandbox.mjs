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
