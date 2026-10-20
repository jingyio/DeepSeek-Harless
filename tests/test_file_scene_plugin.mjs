// Free admission/lifecycle diagnostics; worker output below is explicitly fake.
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,relative} from 'node:path';
import {EventEmitter} from 'node:events';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
const enabled={skip:!process.features?.typescript};

async function fixture(budget=.25,sessions=['owned'],member=false){
 const {installFileScene,fileShortcut}=await import('../src/adapters/harless_file_scene.ts');
 const directory=mkdtempSync(join(tmpdir(),'file-plugin-')),id='file-test-'+randomUUID(),events=[];
 const policy=join(directory,'policy.json'),saved=process.env.SSS_WEB_POLICY;
 writeFileSync(policy,JSON.stringify({output:directory,user_id:id,...(member?{budget_task_prefix:id}:{}),provider_mode:'mock',budget_usd:budget,
  python:'diagnostic-only',scenes:[{id:'files',allowed_tools:['mcp__file_management__list_files']}]}));
 process.env.SSS_WEB_POLICY=policy;
 const routes=new Map(),hooks=new Map(),disposers=[],calls=[],workers=[],uploads=new Map();
 const upload=(session,name,text)=>{const receiptId=randomUUID();uploads.set(receiptId,{session,name,bytes:Buffer.byteLength(text),diagnosticText:text});return {type:'file',receiptId};};
 const histories=new Map(sessions.map(session=>[session,session==='owned'?events:[]]));
 const agents=sessions.map(id=>({session:{id,snapshotEvents:()=>histories.get(id),append(type,data,metadata){const rows=histories.get(id),event={seq:rows.length,time:Date.now(),type,data,...metadata};rows.push(event);return event;}},ctx:{get(){return null;}}}));
 const ctx={sessionController:{
  async inspect(session){if(!histories.has(session))throw Error('not owned');return {meta:{},events:histories.get(session)};},
  async prompt(request){calls.push(request);return {delegated:true};},async cancel(){return {cancelled:true};},async selectModel(){return {};},
 },attachments:{async admitPromptContent(content){return content;},async *readFileStream(ref){yield Buffer.from(ref.diagnosticText);}},fileUploads:{resolve(agent,id){const ref=uploads.get(id);if(ref?.session!==agent.session.id)throw Error('foreign receipt');return ref;},bindPrompt(){return {commit(){},[Symbol.dispose](){}};}},
 workspaceRegistry:{list:()=>[{id:'workspace-a',sessionIds:sessions}]},on(name,handler){hooks.set(name,handler);},
 connection:{requestRejection:()=>null,fetch:{register(route){routes.set(route.path,route);return ()=>{};}}},effect(install){const dispose=install();if(typeof dispose==='function')disposers.push(dispose);}};
 function launch(_python,args,options){
  const child=new EventEmitter();child.stdout=new EventEmitter();child.stdout.setEncoding=()=>{};child.stderr=new EventEmitter();
  child.stdin={end(raw){child.input=JSON.parse(raw);ctx.onWorkerInput?.(child);}};child.kill=()=>{child.killed=true;child.emit('close',143);};
  child.options=options;child.args=args;workers.push(child);return child;
 }
 installFileScene(ctx,launch);for(const agent of agents)hooks.get('agent/created')({agent});
 const route=routes.get('/api/harless/file-scene');
 const api=(query='',body)=>route.fetch(new Request('http://127.0.0.1/api/harless/file-scene?session_id=owned'+query,{method:body?'POST':'GET',...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})}));
 return {ctx,events,histories,calls,workers,api,fileShortcut,upload,directory,async close(){for(const dispose of disposers.reverse())dispose();if(saved===undefined)delete process.env.SSS_WEB_POLICY;else process.env.SSS_WEB_POLICY=saved;rmSync(directory,{recursive:true,force:true});
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

test('file worker receives the uncapped policy instead of a hidden five dollar allowance',enabled,async()=>{
 const f=await fixture(null);try{
  await f.ctx.sessionController.prompt({sessionId:'owned',requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'/file 盘点文件'}]});
  const request=JSON.parse(readFileSync(f.workers[0].input.request_file));
  assert.equal(request.budget_usd,null);
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

test('different chats in one workspace run together with isolated copies, history and cancellation',enabled,async()=>{
 const f=await fixture(null,['owned','sibling','third']);try{
  const prompt=(sessionId,text)=>f.ctx.sessionController.prompt({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'/file '+text}]});
  await Promise.all([prompt('owned','only alpha'),prompt('sibling','only beta'),prompt('third','only gamma')]);
  assert.equal(f.workers.length,3);
  const inputs=f.workers.map(w=>JSON.parse(readFileSync(w.input.request_file)));
  assert.equal(new Set(inputs.map(r=>r.workspace_id)).size,3);
  assert.equal(new Set(inputs.map(r=>r.directory)).size,3);
  assert.ok(inputs.every(r=>r.budget_usd===null));
  assert.deepEqual(inputs.map(r=>r.prior_context),[[],[],[]]);
  assert.deepEqual(inputs.map(r=>r.objective),['only alpha','only beta','only gamma']);
  await f.ctx.sessionController.cancel({sessionId:'owned'});
  assert.equal(f.workers[0].killed,true);
  assert.equal(f.workers[1].killed,undefined);assert.equal(f.workers[2].killed,undefined);
  for(const worker of f.workers.slice(1)){
   worker.stdout.emit('data',JSON.stringify({kind:'result',status:'completed',metrics:{acceptance_passed:true,upstream_requests:0},artifacts:[]})+'\n');
   worker.emit('close',0);
  }
  assert.equal(f.histories.get('sibling').at(-1).type,'turn/end');
  assert.equal(f.histories.get('third').at(-1).type,'turn/end');
  await prompt('sibling','beta follow-up');
  const followup=JSON.parse(readFileSync(f.workers[3].input.request_file));
  assert.equal(followup.workspace_id,inputs[1].workspace_id);
  assert.deepEqual(followup.prior_context.map(r=>r.text),['/file only beta']);
  assert.equal(f.histories.get('sibling').filter(e=>e.type==='turn/start').at(-1).data.turn,2);
 }finally{await f.close();}
});

test('completed File requests return to Chat while explicit File follow-ups keep their private copy',enabled,async()=>{
 const f=await fixture();try{
  const request=(text)=>({sessionId:'owned',requestId:randomUUID(),mode:'queue',content:[{type:'text',text}]});
  await f.ctx.sessionController.prompt(request('/file inspect'));
  const initial=JSON.parse(readFileSync(f.workers[0].input.request_file));
  f.workers[0].stdout.emit('data',JSON.stringify({kind:'result',status:'completed',metrics:{acceptance_passed:true},artifacts:[]})+'\n');f.workers[0].emit('close',0);
  assert.equal((await (await f.api()).json()).selected,false);
  const greeting=request('你好');assert.deepEqual(await f.ctx.sessionController.prompt(greeting),{delegated:true});assert.equal(f.calls.at(-1),greeting);
  assert.equal(f.workers.length,1);
  await f.ctx.sessionController.prompt(request('/file continue organizing'));
  assert.equal(JSON.parse(readFileSync(f.workers[1].input.request_file)).workspace_id,initial.workspace_id);
 }finally{await f.close();}
});

test('one chat is reserved throughout async admission and identical retries dispatch only once',enabled,async()=>{
 const f=await fixture();try{
  const request={sessionId:'owned',requestId:'simultaneous',mode:'queue',content:[{type:'text',text:'/file inspect'}]};
  const first=f.ctx.sessionController.prompt(request);
  const duplicate=f.ctx.sessionController.prompt({...request});
  await assert.rejects(f.ctx.sessionController.prompt({...request,requestId:'other'}),/当前文件管理任务/);
  assert.deepEqual(await first,await duplicate);
  assert.equal(f.workers.length,1);assert.equal(f.events.filter(e=>e.type==='turn/start').length,1);
  await assert.rejects(f.ctx.sessionController.prompt({...request,requestId:'other'}),/当前文件管理任务/);
 }finally{await f.close();}
});

test('cancelling pending admission never starts its worker or blocks another chat',enabled,async()=>{
 const f=await fixture(null,['owned','sibling']);try{
  let release,ready;
  const held=new Promise(resolve=>{release=resolve;}),entered=new Promise(resolve=>{ready=resolve;});
  f.ctx.attachments.admitPromptContent=async content=>{if(content[0].text.includes('slow')){ready();await held;}return content;};
  const request={sessionId:'owned',requestId:'slow',mode:'queue',content:[{type:'text',text:'/file slow preparation'}]};
  const pending=f.ctx.sessionController.prompt(request);await entered;
  await f.ctx.sessionController.prompt({...request,sessionId:'sibling',requestId:'fast',content:[{type:'text',text:'/file fast preparation'}]});
  assert.equal(f.workers.length,1);
  await assert.rejects(f.ctx.sessionController.cancel({sessionId:'foreign'}),/not owned/);
  await f.ctx.sessionController.cancel({sessionId:'owned'});release();
  await assert.rejects(pending,/file_admission_cancelled/);
  assert.equal(f.workers.length,1);assert.equal(f.events.length,0);assert.equal(f.workers[0].killed,undefined);
  await f.ctx.sessionController.prompt({...request,requestId:'new',content:[{type:'text',text:'/file fresh preparation'}]});
  assert.equal(f.workers.length,2);
 }finally{await f.close();}
});

test('parallel chats may upload the same filename without sharing approved bytes',enabled,async()=>{
 const f=await fixture(null,['owned','sibling']);try{
  const one=f.upload('owned','notes.txt','alpha private'),two=f.upload('sibling','notes.txt','beta private');
  const request=(sessionId,file)=>({sessionId,requestId:randomUUID(),mode:'queue',content:[{type:'text',text:'/file inspect this upload'},file]});
  await Promise.all([f.ctx.sessionController.prompt(request('owned',one)),f.ctx.sessionController.prompt(request('sibling',two))]);
  assert.equal(f.workers.length,2);
  const inputs=f.workers.map(w=>JSON.parse(readFileSync(w.input.request_file)));
  assert.notEqual(inputs[0].workspace_id,inputs[1].workspace_id);
  assert.notEqual(inputs[0].sources[0].path,inputs[1].sources[0].path);
  assert.deepEqual(inputs.map(r=>readFileSync(r.sources[0].path,'utf8')),['alpha private','beta private']);
  assert.notEqual(inputs[0].sources[0].sha256,inputs[1].sources[0].sha256);
 }finally{await f.close();}
});

test('cancellation between worker startup and admission acknowledgement kills the owning worker',enabled,async()=>{
 const f=await fixture();try{
  let cancellation;
  f.ctx.onWorkerInput=()=>{cancellation=f.ctx.sessionController.cancel({sessionId:'owned'});};
  await f.ctx.sessionController.prompt({sessionId:'owned',requestId:'startup-cancel',mode:'queue',content:[{type:'text',text:'/file inspect'}]});
  await cancellation;
  assert.equal(f.workers.length,1);assert.equal(f.workers[0].killed,true);
  assert.equal(f.events.at(-1).type,'turn/end');
  assert.equal((await (await f.api('&turn=1')).json()).status,'interrupted');
 }finally{await f.close();}
});

test('member task and worker state use the persisted member output bind',enabled,async()=>{
 const f=await fixture(null,['owned'],true);try{
  await f.ctx.sessionController.prompt({sessionId:'owned',requestId:'member',mode:'queue',content:[{type:'text',text:'/file inspect'}]});
  const home=f.workers[0].options.env.HARLESS_MANAGEMENT_PRIVATE_ROOT;
  assert.match(relative(f.directory,home).replaceAll('\\','/'),/^file-management\/accounts\/[a-f0-9]{64}$/);
  assert.ok(f.workers[0].input.request_file.startsWith(home));
 }finally{await f.close();}
});
