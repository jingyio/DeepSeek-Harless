/** Actual sandbox and decoder diagnostics, not real model cost measurements. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {deflateSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,rmSync,realpathSync,existsSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {decodeScriptReceipt,scriptCommand,createScriptInterceptor,consumeScriptGrant} from '../src/adapters/script_motif_runtime.ts';
import {sandboxRun} from '../scripts/certify-script-motifs.mjs';
const sha=b=>createHash('sha256').update(b).digest('hex');
const pack=value=>{const bytes=Buffer.from(JSON.stringify(value));return {kind:'script_motif_envelope',encoding:'zlib_base64_v1',payload:deflateSync(bytes).toString('base64'),sha256:sha(bytes)};};
test('bounded lossless receipt transport rejects corruption, nested receipts and expansion bombs',()=>{
 const receipt={kind:'script_motif_receipt',nonce:'current',output:'你好😀',observations:[],artifacts_text:'{}'};
 assert.deepEqual(decodeScriptReceipt(pack(receipt)),receipt);assert.equal(decodeScriptReceipt(receipt),receipt);
 for(const mutate of [v=>v.sha256='0'.repeat(64),v=>v.payload+='!',v=>v.encoding='other',v=>v.extra=true]){
  const e=pack(receipt);mutate(e);assert.throws(()=>decodeScriptReceipt(e));
 }
 assert.throws(()=>decodeScriptReceipt(pack(pack(receipt))),/nested_or_foreign/);
 assert.throws(()=>decodeScriptReceipt(pack({kind:'script_motif_receipt',output:'x'.repeat(300000)})));
 assert.throws(()=>decodeScriptReceipt({...pack(receipt),payload:'A'.repeat(48004)}));
});
const enabled=process.platform==='darwin'||process.platform==='linux'&&existsSync('/usr/bin/bwrap');
if(process.platform==='darwin')process.env.SSS_LOCAL_SCRIPT_EXPERIMENT='1';
function workspace(t){
 const root=realpathSync(mkdtempSync(join(tmpdir(),'receipt-envelope-')));for(const d of ['code','inputs','outputs/code','command-tmp'])mkdirSync(join(root,d),{recursive:true});
 writeFileSync(join(root,'inputs/data.txt'),'a\nb\n');t.after(()=>rmSync(root,{recursive:true,force:true}));return root;
}
const p={id:'diagnostic',inputs:[{suffix:'.txt',format:'text'}],template:"rows=open('__MOTIF_INPUT_0__').read().splitlines()\nprint('count',len(rows))\nprint('文字😀',rows)",description:'read current lines',
 certification:{receipt_protocol:'bounded_zlib_v1'}};
test('actual sandbox compressed and original receipts preserve every evidence byte',{skip:!enabled},t=>{
 const root=workspace(t),version=sha(readFileSync(join(root,'inputs/data.txt'))),args=[p,['/work/inputs/data.txt'],[version],'current'];
 const original=JSON.parse(sandboxRun(root,scriptCommand(...args))),compressed=JSON.parse(sandboxRun(root,scriptCommand(...args,{compactReceipt:true})));
 assert.deepEqual(decodeScriptReceipt(compressed),original);assert.equal(compressed.kind,'script_motif_envelope');
 const network={...p,inputs:[],network_policy:'fixed_metadata_get_v1',template:"import urllib.request\nprint(urllib.request.urlopen('https://example.invalid/').read())"};
 const demand=JSON.parse(sandboxRun(root,scriptCommand(network,[],[],'n',{compactReceipt:true})));
 assert.equal(demand.kind,'script_http_demand');
});
test('Runtime still requires authentic grant, current nonce/version and final receipt before recording',{skip:!enabled},async t=>{
 const root=workspace(t),audit=[],runtime=createScriptInterceptor({library:{programs:[p]},workspace:root,session:'envelope',goal:'current lines',mode:'execute',compactContext:true,similarity:async()=>[.99],audit:r=>audit.push(r)});t.after(()=>runtime.dispose());
 let call;for await(const event of await runtime.intercept('envelope',{tools:[{name:'bash'}]},()=>{}))if(event.block?.type==='tool-call')call=event.block;
 const execution={name:'bash',callId:call.id,arguments:JSON.parse(call.arguments)},body=consumeScriptGrant('envelope',execution.arguments.command),raw=sandboxRun(root,body),result={content:[{type:'text',text:raw}]};
 assert.equal(JSON.parse(raw).kind,'script_motif_envelope');
 const projection=runtime.projectResult(execution,result);assert.ok(projection);assert.ok(!audit.some(r=>r.kind==='script_model_request_skipped_verified'));
 runtime.observe('envelope',execution,{...result,content:projection});
 assert.ok(audit.some(r=>r.kind==='script_model_request_skipped_verified'));assert.ok(audit.find(r=>r.kind==='script_evidence_raw').decoded_receipt);
});

test('JSON escaping can exceed native Bash clipping even when stdout remains below its bound',{skip:!enabled},t=>{
 const root=workspace(t),version=sha(readFileSync(join(root,'inputs/data.txt')));
 const large={...p,template:"n=len(open('__MOTIF_INPUT_0__').read())\nprint(chr(1)*(n*2500))"},args=[large,['/work/inputs/data.txt'],[version],'escaped'];
 const plain=sandboxRun(root,scriptCommand(...args)),packed=sandboxRun(root,scriptCommand(...args,{compactReceipt:true}));
 assert.ok(Buffer.byteLength(JSON.parse(plain).output)<16000);assert.ok(Buffer.byteLength(plain)>50000);
 assert.ok(Buffer.byteLength(packed)<48000);assert.deepEqual(decodeScriptReceipt(JSON.parse(packed)),JSON.parse(plain));
});

test('highly compressible stdout is decoded for the model even when its projection is larger',{skip:!enabled},async t=>{
 const root=workspace(t),q={...p,template:"n=len(open('__MOTIF_INPUT_0__').read())\nprint('x'*(n*2500))"},audit=[];
 const rt=createScriptInterceptor({library:{programs:[q]},workspace:root,session:'expanding-projection',goal:'read',mode:'execute',compactContext:true,similarity:async()=>[.99],audit:r=>audit.push(r)});t.after(()=>rt.dispose());
 let call;for await(const e of await rt.intercept('expanding-projection',{tools:[{name:'bash'}]},()=>{}))if(e.block?.type==='tool-call')call=e.block;
 const ex={name:'bash',callId:call.id,arguments:JSON.parse(call.arguments)},raw=sandboxRun(root,consumeScriptGrant('expanding-projection',ex.arguments.command));
 const projected=rt.projectResult(ex,{content:[{type:'text',text:raw}]});assert.ok(Buffer.byteLength(projected[0].text)>Buffer.byteLength(raw));
 assert.equal(JSON.parse(projected[0].text).stdout,'x'.repeat(10000)+'\n');rt.observe('expanding-projection',ex,{content:projected});assert.ok(audit.some(r=>r.kind==='script_model_request_skipped_verified'));
});
for(const compactContext of [false,true])test('legacy/no-projection path preserves readable plaintext: '+compactContext,{skip:!enabled},async t=>{
 const root=workspace(t),legacy={...p,certification:compactContext?{}:p.certification};
 const rt=createScriptInterceptor({library:{programs:[legacy]},workspace:root,session:'plain-'+compactContext,goal:'read',mode:'execute',compactContext,similarity:async()=>[.99],audit:()=>{}});t.after(()=>rt.dispose());
 let call;for await(const e of await rt.intercept('plain-'+compactContext,{tools:[{name:'bash'}]},()=>{}))if(e.block?.type==='tool-call')call=e.block;
 const ex={name:'bash',callId:call.id,arguments:JSON.parse(call.arguments)},raw=sandboxRun(root,consumeScriptGrant('plain-'+compactContext,ex.arguments.command));assert.equal(JSON.parse(raw).kind,'script_motif_receipt');
});
