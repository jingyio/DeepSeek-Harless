import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync, realpathSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, basename, sep } from 'node:path';
const options={skip:!process.features?.typescript};
test('Scene task mount alias is allowed only for the same directory identity',options,async()=>{
 const {memberTaskRoots}=await import('../src/adapters/harless_member_file_scope.ts');
 const directory=mkdtempSync(join(tmpdir(),'harless-member-files-alias-'));
 try{
  const own=join(directory,'own'),foreign=join(directory,'foreign');mkdirSync(own);mkdirSync(foreign);
  assert.deepEqual(memberTaskRoots(own,join(directory,'absent')),[join(own,'sessions'),join(own,'managed-workspaces')]);
  assert.deepEqual(memberTaskRoots(own,own),[join(own,'sessions'),join(own,'managed-workspaces'),join(own,'sessions'),join(own,'managed-workspaces')]);
  assert.throws(()=>memberTaskRoots(own,foreign),/只允许/);
 }finally{assert.ok(resolve(directory).startsWith(resolve(tmpdir())+sep));rmSync(directory,{recursive:true,force:true});}
});
async function fixture(){
 const {guardMemberFileRpc}=await import('../src/adapters/harless_member_file_scope.ts');
 const directory=mkdtempSync(join(tmpdir(),'harless-member-files-')),work=join(directory,'workspace'),sessions=join(directory,'sessions'),config=join(directory,'config');
 for(const p of [work,sessions,config])mkdirSync(p);writeFileSync(join(work,'own.txt'),'owned');writeFileSync(join(config,'policy.json'),'internal');
 const calls=[],gateway={async invoke(req){calls.push(req);return {absolutePath:req.namespace==='workspaceFiles'?req.args.path:undefined};},async stream(){return(async function*(){yield {kind:'ready'};yield {kind:'change',change:{absolutePath:join(work,'own.txt')}};yield {kind:'change',change:{absolutePath:join(config,'policy.json')}};})();}};
 const guard=guardMemberFileRpc(gateway,async id=>id==='own'?{workspaceRoot:work}:undefined,[work,sessions]);
 const rpc=(method,path,extra={})=>guard.invoke({namespace:'workspaceFiles',method,args:{workspaceFileScopeId:'own',path,...extra}});
 return {directory,work,sessions,config,gateway:guard,rpc,calls,close(){const target=resolve(directory);assert.ok(target.startsWith(resolve(tmpdir())+sep)&&basename(target).startsWith('harless-member-files-'));rmSync(target,{recursive:true,force:true});}};
}
test('Member file RPCs reject scope and path escapes before invoking the underlying service',options,async()=>{
 const f=await fixture();try{
  for(const method of ['list','stat','read','readAll','readBytes']){
   await f.rpc(method,'own.txt');const count=f.calls.length;
   for(const path of ['../config/policy.json',f.config,'/proc/self/environ','/etc/passwd'])await assert.rejects(f.rpc(method,path),/只允许/);
   assert.equal(f.calls.length,count);
  }
  await assert.rejects(f.rpc('read','own.txt',{workspaceFileScopeId:'foreign'}),/只允许/);
  await f.rpc('stat','missing.txt');
 }finally{f.close();}
});
test('Related assets, workspace creation, directory browsing and stream scopes share containment',options,async()=>{
 const f=await fixture();try{
  await f.rpc('readRelated','own.txt',{relativePath:'own.txt'});
  await assert.rejects(f.rpc('readRelated','own.txt',{relativePath:'../config/policy.json'}),/只允许/);
  await assert.rejects(f.gateway.invoke({namespace:'workspace',method:'create',args:{request:{path:f.config}}}),/只允许/);
  await assert.rejects(f.gateway.invoke({namespace:'directoryPicker',method:'list',args:{path:f.config}}),/只允许/);
  await f.gateway.invoke({namespace:'directoryPicker',method:'list',args:{}});assert.equal(f.calls.at(-1).args.path,realpathSync(f.work));
  assert.equal(f.gateway.scope({workspaceRoot:f.work}).workspaceRoot,realpathSync(f.work));
  assert.throws(()=>f.gateway.scope({workspaceRoot:f.config}),/只允许/);
 }finally{f.close();}
});
test('Symlinked ancestors cannot expose configuration through member file RPCs',options,async t=>{
 const f=await fixture();try{
  const link=join(f.work,'outside');try{symlinkSync(f.config,link,process.platform==='win32'?'junction':'dir');}catch(e){if(['EPERM','EACCES'].includes(e.code)){t.skip('symlink creation not permitted');return;}throw e;}
  await assert.rejects(f.rpc('read',join(link,'policy.json')),/只允许/);await assert.rejects(f.rpc('stat',join(link,'missing.json')),/只允许/);assert.equal(f.calls.length,0);
 }finally{f.close();}
});

test('Member plugin registers guarded RPC routes and the shared stream scope lookup',options,async()=>{
 const {apply}=await import('../src/adapters/dsh_member_workspace.ts');
 const routes=new Map(),calls=[],work=resolve('/user/workspace');let configured;
 const original={resolve:async id=>id==='own'?{workspaceRoot:work}:id==='internal'?{workspaceRoot:resolve('/user/config')}:undefined};
 const ctx={workspaceRegistry:{async create(path,title){calls.push({bootstrap:path,title});}},
  connection:{fetch:{register(route){routes.set(route.path,route);}}},
  typert:{lookups:{get(){return configured?{resolve:configured}:original;},configure(key,resolver){assert.equal(key,'workspaceFileScope');configured=resolver;}}},
  typertGateway:{async invoke(request){calls.push(request);return {absolutePath:request.args.path,text:'own bytes'};}}};
 await apply(ctx);assert.equal(routes.size,6);assert.equal(calls[0].bootstrap,'/user/workspace');
 for(const endpoint of ['workspace/create','directoryPicker/list','directoryPicker/createDirectory'])assert.equal(routes.has('/api/'+endpoint),false);
 await assert.rejects(configured('internal'),/只允许/);await assert.rejects(configured('foreign'),/只允许/);
 const endpoint='workspaceFiles/read',route=routes.get('/api/'+endpoint);
 const send=async(path,method=endpoint)=>route.fetch(new Request('http://localhost/api/'+endpoint,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({type:'client-request',rpcId:'audit',method,payload:{args:{workspaceFileScopeId:'own',path,range:{}}}})}));
 assert.equal((await (await send('own.txt')).json()).result.value.text,'own bytes');const n=calls.length;
 const denied=await (await send('../config/policy.json')).json();assert.equal(denied.result.error.code,'gateway/forbidden');assert.equal(calls.length,n);
 assert.equal((await (await send('own.txt','workspaceFiles/readAll')).json()).result.ok,false);assert.equal(calls.length,n);
 assert.equal((await route.fetch(new Request('http://localhost/api/'+endpoint,{method:'POST',headers:{'content-type':'application/json'},body:'{}'}))).status,400);
});
