// Free admission/lifecycle diagnostics; worker output below is explicitly fake.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {EventEmitter} from 'node:events';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
const enabled={skip:!process.features?.typescript};

async function fixture(){
 const {installFileScene,fileShortcut}=await import('../src/adapters/harless_file_scene.ts');
 const directory=mkdtempSync(join(tmpdir(),'file-plugin-')),id='file-test-'+randomUUID(),events=[];
 const policy=join(directory,'policy.json'),saved=process.env.SSS_WEB_POLICY;
 writeFileSync(policy,JSON.stringify({output:directory,user_id:id,provider_mode:'mock',budget_usd:.25,
  python:'diagnostic-only',scenes:[{id:'files',allowed_tools:['mcp__file_management__list_files']}]}));
 process.env.SSS_WEB_POLICY=policy;
 const routes=new Map(),hooks=new Map(),disposers=[],calls=[],workers=[];
 const agent={session:{id:'owned',snapshotEvents:()=>events,append(type,data,metadata){const event={seq:events.length,time:Date.now(),type,data,...metadata};events.push(event);return event;}},ctx:{get(){return null;}}};
 const ctx={sessionController:{
  async inspect(session){if(session!=='owned')throw Error('not owned');return {meta:{},events};},
  async prompt(request){calls.push(request);return {delegated:true};},async cancel(){return {cancelled:true};},async selectModel(){return {};},
 },attachments:{async admitPromptContent(content){return content;}},fileUploads:{resolve(){throw Error('foreign receipt');},bindPrompt(){return {commit(){},[Symbol.dispose](){}};}},
 workspaceRegistry:{list:()=>[{id:'workspace-a',sessionIds:['owned']}]},on(name,handler){hooks.set(name,handler);},
 connection:{requestRejection:()=>null,fetch:{register(route){routes.set(route.path,route);return ()=>{};}}},effect(install){const dispose=install();if(typeof dispose==='function')disposers.push(dispose);}};
 function launch(_python,args,options){
  const child=new EventEmitter();child.stdout=new EventEmitter();child.stdout.setEncoding=()=>{};child.stderr=new EventEmitter();
  child.stdin={end(raw){child.input=JSON.parse(raw);}};child.kill=()=>{child.emit('close',143);};
  child.options=options;child.args=args;workers.push(child);return child;
 }
 installFileScene(ctx,launch);hooks.get('agent/created')({agent});
 const route=routes.get('/api/harless/file-scene');
 const api=(query='',body)=>route.fetch(new Request('http://127.0.0.1/api/harless/file-scene?session_id=owned'+query,{method:body?'POST':'GET',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})}));
 return {ctx,events,calls,workers,api,fileShortcut,async close(){for(const dispose of disposers.reverse())dispose();if(saved===undefined)delete process.env.SSS_WEB_POLICY;else process.env.SSS_WEB_POLICY=saved;rmSync(directory,{recursive:true,force:true});
  // The tests have no uploads, recovery data or real requests.
  const root=fileURLToPath(new URL('../',import.meta.url));const {createHash}=await import('node:crypto');rmSync(join(root,'.local/web/file-management/accounts',createHash('sha256').update(id).digest('hex')),{recursive:true,force:true});}};
}

test('file extension delegates Paper/PPT/Data/chat without launching or changing their requests',enabled,async()=>{
 const f=await fixture();try{
  for(const text of ['/paper 检查','/ppt 制作','/data 分析','ordinary chat']){
   const request={sessionId:'owned',requestId:randomUUID(),mode:'queue',content:[{type:'text',text}]};
   assert.deepEqual(await f.ctx.sessionController.prompt(request),{delegated:true});assert.equal(f.calls.at(-1),request);
  }
  assert.equal(f.workers.length,0);
  assert.ok(f.fileShortcut('/file整理资料'));assert.equal(f.fileShortcut('/file.txt'),null);
 }finally{await f.close();}
});

test('file admission is owned, automatic, idempotent and retains native lifecycle',enabled,async()=>{
 const f=await fixture();try{
  const settings=await (await f.api()).json();assert.equal(settings.automatic,true);assert.equal(settings.scene.shortcut,'file');
  const request={sessionId:'owned',requestId:'one',mode:'queue',content:[{type:'text',text:'/file 盘点任务副本'}]};
  await assert.rejects(f.ctx.sessionController.prompt({...request,sessionId:'foreign'}));assert.equal(f.workers.length,0);
  await f.ctx.sessionController.prompt(request,new AbortController().signal);assert.equal(f.workers.length,1);
  assert.match(f.workers[0].args[0],/file_scene_worker\.py$/);
  assert.equal(JSON.parse(readFileSync(f.workers[0].input.request_file)).objective,'盘点任务副本');
  assert.equal(f.events[0].type,'turn/start');assert.equal(f.events[1].type,'user/message');
  // Pending request retries are acknowledgements, never second executions.
  await assert.rejects(f.ctx.sessionController.prompt({...request,requestId:'different'}));
  f.workers[0].stdout.emit('data',JSON.stringify({kind:'result',status:'completed',metrics:{acceptance_passed:true,upstream_requests:0,budget_accounted_usd:0},artifacts:[]})+'\n');
  f.workers[0].emit('close',0);
  await f.ctx.sessionController.prompt(request,new AbortController().signal);assert.equal(f.workers.length,1);
  assert.equal(f.events.at(-1).type,'turn/end');
  const result=await (await f.api('&turn=1')).json();assert.equal(result.status,'completed');assert.equal(result.rsi.cost_usd,0);
  await assert.rejects(f.ctx.sessionController.prompt({...request,content:[{type:'text',text:'/file changed'}]}));
 }finally{await f.close();}
});

test('foreign upload receipts fail before worker dispatch or native turn publication',enabled,async()=>{
 const f=await fixture();try{
  await assert.rejects(f.ctx.sessionController.prompt({sessionId:'owned',requestId:'upload',mode:'queue',content:[{type:'text',text:'/file 整理'},{type:'file',receiptId:'other-owner'}]},new AbortController().signal));
  assert.equal(f.workers.length,0);assert.equal(f.events.length,0);
 }finally{await f.close();}
});
