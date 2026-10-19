// Free bridge diagnostics. Decisions here are synthetic, not model/UI evidence.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync,readdirSync,rmSync,symlinkSync,realpathSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
const enabled={skip:!process.features?.typescript};
async function fixture(){
 const {apply}=await import('../src/adapters/file_approval_bridge.ts');
 const {digest}=await import('../src/motif_core/online_skill_runtime.mjs');
 const home=realpathSync(mkdtempSync(join(tmpdir(),'file-approval-'))),delivery=join(home,'delivery'),requests=join(home,'requests');
 mkdirSync(delivery);const task=join(home,'task.json');writeFileSync(task,'{}');
 const prior={};for(const [key,value] of Object.entries({HARLESS_FILE_APPROVAL_HOME:requests,FM_OUTPUT:delivery,FM_TASK_FILE:task})){prior[key]=process.env[key];process.env[key]=value;}
 let handler;apply({on(_name,fn){fn({agent:{ctx:{on(_event,fn){handler=fn;}}}});}});
 const state={plans:{p:{plan_id:'p',plan_sha256:'v1',before:{version:1},actions:[{op:'overwrite',source:'a',destination:'b'}],risks:['overwrite']}},expected_tree:{version:1},journals:{}};
 const store=()=>writeFileSync(join(delivery,'management-state.json'),JSON.stringify(state));store();
 let prompts=0,effects=0;
 async function execute(outcome='allowed-once',name='mcp__file_management__execute_plan'){
  const call=handler({name,arguments:{plan_id:'p'},signal:new AbortController().signal,callId:'synthetic-call'},()=>++effects);
  call.catch(()=>{});
  // A persisted approval or denial returns without publishing a request.
  await new Promise(resolve=>setTimeout(resolve,5));
  for(const file of readdirSync(requests).filter(f=>f.endsWith('.request.json'))){
   const target=join(requests,file.replace('.request.json','.decision.json'));if(readdirSync(requests).includes(file.replace('.request.json','.decision.json')))continue;
   const request=JSON.parse(readFileSync(join(requests,file)));prompts++;
   writeFileSync(target,JSON.stringify({request_digest:digest(request),outcome,native_asked:{data:{id:'synthetic-'+prompts}},native_decided:{data:{id:'synthetic-'+prompts,outcome}}}));
  }
  return call;
 }
 return {state,store,execute,get prompts(){return prompts;},get effects(){return effects;},home,delivery,close(){for(const [key,value] of Object.entries(prior)){if(value===undefined)delete process.env[key];else process.env[key]=value;}rmSync(home,{recursive:true,force:true});}};
}
test('high-risk permission is exact, persisted and distinct for restore',enabled,async()=>{
 const f=await fixture();try{
  await f.execute();await f.execute();assert.equal(f.prompts,1);assert.equal(f.effects,2);
  f.state.plans.p.plan_sha256='v2';f.state.plans.p.before.version=2;f.store();await f.execute();assert.equal(f.prompts,2);
  await f.execute('allowed-once','mcp__file_management__restore_plan');assert.equal(f.prompts,3);
 }finally{f.close();}
});
test('a denied plan is retained and cannot repeatedly ask or execute',enabled,async()=>{
 const f=await fixture();try{
  await assert.rejects(f.execute('denied'));await assert.rejects(f.execute('allowed-once'));
  assert.equal(f.prompts,1);assert.equal(f.effects,0);
 }finally{f.close();}
});
test('ordinary workspace operations require no extra approval',enabled,async()=>{
 const f=await fixture();try{f.state.plans.p.risks=[];f.store();await f.execute();assert.equal(f.prompts,0);assert.equal(f.effects,1);}finally{f.close();}
});
test('file download rejects escaped, modified and symlink artifacts',enabled,async()=>{
 const {fileArtifactBytes}=await import('../src/adapters/harless_file_scene.ts');
 const home=realpathSync(mkdtempSync(join(tmpdir(),'file-artifact-'))),base=join(home,'exports');mkdirSync(base);
 try{
  const data=Buffer.from('synthetic artifact'),sha=createHash('sha256').update(data).digest('hex'),file=join(base,'result.txt');writeFileSync(file,data);
  assert.deepEqual(fileArtifactBytes(file,base,sha),data);
  assert.throws(()=>fileArtifactBytes(join(home,'result.txt'),base,sha),/scope/);
  assert.throws(()=>fileArtifactBytes(file,base,'bad'),/bytes/);
  symlinkSync(file,join(base,'link.txt'));assert.throws(()=>fileArtifactBytes(join(base,'link.txt'),base,sha),/scope/);
 }finally{rmSync(home,{recursive:true,force:true});}
});
