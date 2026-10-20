/** File-only extension; existing Paper/PPT/Data hosts and certificates stay intact.
 * Uses the installed Harness SDK runner, not another semantic decision loop.
 */
import {spawn} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {existsSync,readFileSync,writeFileSync,mkdirSync,renameSync,readdirSync,lstatSync} from 'node:fs';
import {join,dirname,basename,resolve,relative,isAbsolute,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
import {createUserMessage,createAssistantMessage} from '@deepseek-ai/dsh-llm';
import {digest} from '../motif_core/online_skill_runtime.mjs';
import {managementFileContent} from './file_task_scope.ts';
import {fileEventProjection} from './file_event_projection.ts';
import {interruptedTurnClosers} from '@deepseek-ai/dsh-session';
import {publicConversationContext} from './dsh_web_tasks.ts';

const root=fileURLToPath(new URL('../../',import.meta.url));
const hash=(data:Uint8Array|string)=>createHash('sha256').update(data).digest('hex');
const save=(file:string,value:any)=>{mkdirSync(dirname(file),{recursive:true,mode:0o700});writeFileSync(file+'.tmp',JSON.stringify(value),{mode:0o600});renameSync(file+'.tmp',file);};
export const fileShortcut=(text:string)=>/^\s*\/(?:file|files|management)(?=\s|$|[^\x00-\x7f])/i.exec(text);
const terminal=new Set(['completed','failed','interrupted','cancelled']);

export function fileArtifactBytes(file:string,base:string,sha256:string){
 const path=resolve(file),scope=resolve(base),local=relative(scope,path);
 if(!local||isAbsolute(local)||local==='..'||local.startsWith('..'+sep))throw Error('artifact_scope_changed');
 for(let cursor=path;;cursor=dirname(cursor)){
  if(lstatSync(cursor).isSymbolicLink())throw Error('artifact_scope_changed');
  if(dirname(cursor)===cursor)break;
 }
 const data=readFileSync(path);if(hash(data)!==sha256)throw Error('artifact_bytes_changed');return data;
}

export function installFileScene(ctx:any,launch:typeof spawn=spawn){
 const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
 const deployed=policy.scenes?.find((row:any)=>row.id==='files');
 if(!deployed||deployed.unavailable_reason||!deployed.allowed_tools?.length)return;
 const owner=policy.budget_task_prefix?'member-'+policy.budget_task_prefix:policy.user_id??'local-operator';
 // Members' output is the host-persisted per-account bind mount. Owners keep
 // the established home so existing tasks and recovery records stay readable.
 const home=policy.budget_task_prefix?resolve(policy.output,'file-management/accounts',hash(owner)):
  resolve(root,'.local/web/file-management/accounts',hash(owner));
 mkdirSync(join(home,'tasks'),{recursive:true,mode:0o700});
 const controller=ctx.sessionController;
 const original={prompt:controller.prompt.bind(controller),cancel:controller.cancel.bind(controller),selectModel:controller.selectModel.bind(controller)};
 const agents=new Map<string,any>(),children=new Map<string,any>(),aborters=new Map<string,AbortController>();
 const admissions=new Map<string,{request_digest:string,promise:Promise<any>,cancelled:boolean}>();
 const selected=new Set<string>(),models=new Map<string,any>();
 const stateFile=join(home,'selection.json');
 if(existsSync(stateFile)){const saved=JSON.parse(readFileSync(stateFile,'utf8'));for(const id of saved.sessions??[])selected.add(id);for(const [id,m] of Object.entries(saved.models??{}))models.set(id,m);}
 const persist=()=>save(stateFile,{sessions:[...selected],models:Object.fromEntries(models)});
 const tasks=new Map<string,any>();
 for(const id of readdirSync(join(home,'tasks'))){
  if(!/^[a-f0-9]{32}$/.test(id))continue;
  const f=join(home,'tasks',id,'state.json');if(!existsSync(f))continue;
  const task=JSON.parse(readFileSync(f,'utf8'));tasks.set(id,task);
  if(!terminal.has(task.status)){task.status='interrupted';save(f,task);}
 }
 const store=(task:any)=>save(join(home,'tasks',task.id,'state.json'),task);
 const owned=async(id:string)=>{if(typeof id!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(id))throw Error('invalid_session');return controller.inspect(id);};
 const settings=(session:string)=>({selected:selected.has(session),automatic:true,mode:'execute',rsi:true,scene:{id:'files',label:'文件管理',shortcut:'file',available:true,execute_available:true,runtime_kind:'management_graph_v3'}});
 const publicTask=(task:any)=>({id:'file-'+task.id,session_id:task.session,turn:task.turn,presentation:'single',status:task.status,
  lanes:{baseline:{status:task.status,artifacts:(task.artifacts??[]).map(({path,...row}:any)=>row)}},
  rsi:{automatic:true,upstream_requests:task.metrics?.upstream_requests??null,cost_usd:task.metrics?.budget_accounted_usd??null,
   acceptance_passed:task.metrics?.acceptance_passed??false,learning:task.metrics?.continuous_rsi?.worker?'scheduled':'recorded'}});
 function end(task:any,text?:string){
  const agent=agents.get(task.session);if(!agent)return;
  // Use Harness's own interruption closure for any partially displayed call.
  // It marks unknown outcomes instead of inventing a tool result or retry.
  for(const closer of interruptedTurnClosers(agent.session.snapshotEvents()))if(closer.type!=='turn/end')
   agent.session.append(closer.type,closer.data,{...(closer.surfaceOp?{surfaceOp:closer.surfaceOp}:{}),...(closer.sourceEventSeqs?{sourceEventSeqs:closer.sourceEventSeqs}:{})});
  if(text){
   const step=1+Math.max(0,...agent.session.snapshotEvents().filter((e:any)=>e.type==='step/start'&&e.data.turn===task.turn).map((e:any)=>e.data.step));
   agent.session.append('step/start',{turn:task.turn,step});
   agent.session.append('assistant/message',{turn:task.turn,step,stream:[],message:createAssistantMessage({content:[{type:'text',text}],source:{provider:'deepseek-official',model:task.model}})},{surfaceOp:'append'});
   agent.session.append('step/end',{turn:task.turn,step});
  }
  const events=agent.session.snapshotEvents();
  if(!events.some((e:any)=>e.type==='turn/end'&&e.data.turn===task.turn))agent.session.append('turn/end',{turn:task.turn,reason:{kind:'completed'}});
 }
 async function approve(task:any,agent:any,signal:AbortSignal){
  const directory=join(home,'tasks',task.id,'approvals');if(!existsSync(directory))return;
  for(const file of readdirSync(directory).filter(f=>f.endsWith('.request.json'))){
   const id=file.slice(0,-13),answer=join(directory,id+'.decision.json');if(existsSync(answer))continue;
   const request=JSON.parse(readFileSync(join(directory,file),'utf8'));
   const approval=agent.ctx.get('approval');if(!approval)throw Error('native approval service unavailable');
   const outcome=await approval.request({agent,toolName:'file_management',callId:request.call_id,reason:(request.direction==='restore'?'请确认恢复本次文件操作：':'请确认本次文件操作：')+JSON.stringify({direction:request.direction,actions:request.actions,risks:request.risks}),signal});
   const events=agent.session.snapshotEvents(),asked=[...events].reverse().find((e:any)=>e.type==='approval/asked'&&e.data.callId===request.call_id),decided=events.find((e:any)=>e.type==='approval/decided'&&e.data.id===asked?.data.id);
   save(answer,{request_digest:digest(request),outcome,session_id:task.session,native_asked:asked,native_decided:decided});
  }
 }
 async function start(task:any,resume=false){
  if(children.has(task.session))throw Error('file_task_already_running');
  const directory=join(home,'tasks',task.id),agent=agents.get(task.session);
  if(!agent)throw Error('native_session_unavailable');
  if(resume){task.previous_turns=[...(task.previous_turns??[]),task.turn];task.turn=1+Math.max(0,...agent.session.snapshotEvents().filter((e:any)=>e.type==='turn/start').map((e:any)=>e.data.turn));agent.session.append('turn/start',{turn:task.turn});agent.session.append('user/message',createUserMessage({content:[{type:'text',text:'恢复原文件管理任务，沿用原文件、权限和剩余预算。'}],source:{kind:'user',rpcId:'file-resume-'+randomUUID()}}),{surfaceOp:'append'});}
  const abort=new AbortController();aborters.set(task.session,abort);
  task.status='running';store(task);
  const child=launch(policy.python??process.env.SSS_PYTHON??'python3',[join(root,'scenarios/file-management/file_scene_worker.py')],{
   cwd:root,env:{...process.env,HARLESS_MANAGEMENT_PRIVATE_ROOT:home,...(policy.provider_mode==='mock'?{SSS_MOCK_ENDPOINT:policy.endpoint}:{})},stdio:['pipe','pipe','pipe']});
  children.set(task.session,child);
  let buffer='',result:any=null,approvalBusy=false,bridgeFailed=false;
  const project=fileEventProjection(agent.session,task.turn);
  const publish=(row:any)=>{
   if(row.kind==='bound'){task.origin=row.origin;task.out=row.out;task.job_file=row.job_file;store(task);}
   if(row.kind==='event'&&!bridgeFailed){
    project(row.event);
   }
   if(row.kind==='error'){task.failure={type:row.type,message:row.message};store(task);}
   if(row.kind==='result')result=row;
  };
  child.stdout.setEncoding('utf8');child.stdout.on('data',(data:string)=>{buffer+=data;let line;while((line=buffer.indexOf('\n'))>=0){const raw=buffer.slice(0,line);buffer=buffer.slice(line+1);try{publish(JSON.parse(raw));}catch(error){if(!bridgeFailed){bridgeFailed=true;task.failure={type:'native_projection',message:String(error)};store(task);writeFileSync(join(directory,'bridge-error.txt'),String(error),{mode:0o600});child.kill();}}}});
  child.stderr.on('data',(data:Buffer)=>{writeFileSync(join(directory,'stderr.log'),data,{flag:'a',mode:0o600});});
  const timer=setInterval(()=>{if(approvalBusy)return;approvalBusy=true;approve(task,agent,abort.signal).catch(error=>{task.failure={type:'approval',message:String(error)};child.kill();}).finally(()=>approvalBusy=false);},200);
  const settle=(code:any)=>{clearInterval(timer);children.delete(task.session);aborters.delete(task.session);
   if(result){task.status=result.status;task.metrics=result.metrics;task.artifacts=result.artifacts;store(task);end(task,task.status==='completed'?undefined:'文件管理任务未通过验收；失败、费用及恢复记录已保存。');}
   else{task.status='interrupted';task.failure??={type:'process_exit',code};store(task);end(task,'文件管理任务已中断，原任务、操作记录和预算已保留，可恢复后继续。');}
  };
  child.on('error',error=>{task.failure={type:'spawn',message:String(error)};});child.once('close',settle);
  child.stdin.end(JSON.stringify({request_file:join(directory,'request.json'),...(resume?{resume_origin:task.origin}:{})})+'\n');
 }
 ctx.on('agent/created',({agent}:any)=>{agents.set(agent.session.id,agent);queueMicrotask(()=>{for(const task of tasks.values())if(task.session===agent.session.id&&terminal.has(task.status)&&!agent.session.snapshotEvents().some((e:any)=>e.type==='turn/end'&&e.data.turn===task.turn))end(task,task.status==='completed'?undefined:'原文件管理任务已中断，文件效果、原预算和恢复记录已保留。');});});
 controller.selectModel=async(request:any,signal:any)=>{const result=await original.selectModel(request,signal);models.set(request.sessionId,{provider:request.provider,model:request.model,reasoning_effort:request.reasoningEffort??'off'});persist();return result;};
 controller.prompt=async(request:any,signal:any)=>{
  const pending=admissions.get(request.sessionId);
  if(pending){await owned(request.sessionId);if(pending.request_digest===digest(request))return pending.promise;throw Error('请等待当前文件管理任务完成或取消。');}
  const first=request.content?.find((p:any)=>p.type==='text'),match=first&&fileShortcut(first.text);
  if(children.has(request.sessionId)){const prior=[...tasks.values()].find(t=>t.session===request.sessionId&&t.request_id===request.requestId);if(prior&&prior.request_digest===digest(request)){await owned(request.sessionId);return {sessionId:request.sessionId,requestId:request.requestId};}throw Error('请等待当前文件管理任务完成或取消。');}
  if(!match){if(selected.delete(request.sessionId))persist();return original.prompt(request,signal);}
  if(typeof request.requestId!=='string'||!request.requestId||request.mode!=='queue'||!Array.isArray(request.content))throw Error('invalid_file_prompt');
  const checkAdmission=()=>{if(signal?.aborted||admissions.get(request.sessionId)?.cancelled)throw Error('file_admission_cancelled');};
  const admit=async()=>{
  const snapshot=await owned(request.sessionId);
  checkAdmission();
  const prior=[...tasks.values()].find(t=>t.session===request.sessionId&&t.request_id===request.requestId);
  if(prior){if(prior.request_digest!==digest(request))throw Error('file_request_changed');return {sessionId:request.sessionId,requestId:request.requestId};}
  if([...tasks.values()].some(t=>t.session===request.sessionId&&t.status==='interrupted'))throw Error('请先恢复原文件管理任务。');
  const latest=snapshot.events.filter((e:any)=>e.type==='turn/start').at(-1);
  if(latest&&!snapshot.events.some((e:any)=>e.type==='turn/end'&&e.data.turn===latest.data.turn))throw Error('请等待当前任务完成。');
  const fallback=policy.models?.find((m:any)=>m.available&&m.provider==='deepseek-official')??{provider:'deepseek-official',model:'deepseek-flash'};
  const model=models.get(request.sessionId)??fallback;
  if(model.provider!=='deepseek-official'||model.reasoning_effort&&model.reasoning_effort!=='off')throw Error('当前文件管理入口使用 DeepSeek / Off；请选择此模式后发送。');
  await original.selectModel({sessionId:request.sessionId,provider:model.provider,model:model.model,reasoningEffort:'off'},signal);
  checkAdmission();
  const agent=agents.get(request.sessionId);if(!agent)throw Error('native_session_unavailable');
  const id=randomUUID().replaceAll('-',''),directory=join(home,'tasks',id);mkdirSync(join(directory,'inputs'),{recursive:true,mode:0o700});
  const sources:any[]=[],content:any[]=[],receipts:string[]=[];
  const sourceContent=await managementFileContent(ctx,agent,{runtime_kind:'management_graph_v3'} as any,request.content);
  for(const part of sourceContent){
   if(part.type==='image'){content.push(part);continue;}
   if(part.type==='text'){content.push(part);continue;}
   if(part.type!=='file')throw Error('不支持的文件任务输入类型。');
   const ref=ctx.fileUploads.resolve(agent,part.receiptId);if(!ref||sources.length>=40||ref.bytes>20*1024*1024)throw Error('file_receipt_not_owned_or_limit');
   const name=basename(ref.name);if(name!==ref.name||name.startsWith('.')||/[\x00-\x1f\\/]/.test(name)||name.length>160||sources.some(s=>s.name===name))throw Error('invalid_or_duplicate_filename');
   const chunks:Buffer[]=[];let bytes=0;for await(const chunk of ctx.attachments.readFileStream(ref)){bytes+=chunk.length;if(bytes>20*1024*1024)throw Error('file_size_limit');chunks.push(Buffer.from(chunk));}
   if(bytes!==ref.bytes)throw Error('file_bytes_changed');const data=Buffer.concat(chunks),path=join(directory,'inputs',name);writeFileSync(path,data,{mode:0o600});sources.push({name,path,sha256:hash(data)});
   content.push({type:'file',attachment:ref});receipts.push(part.receiptId);
  }
  const text=request.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n');
  const objective=match?text.slice(match[0].length).trim():text;
  const group=ctx.workspaceRegistry?.list().find((w:any)=>w.sessionIds.includes(request.sessionId));
  const workspaceId=group?.id??request.sessionId;
  // The worker mutates its registered copy directly. A stable per-session
  // scope preserves multi-turn files without sharing effects between chats.
  // Existing task requests (including recovery) retain their original scope.
  const copyScope='session-'+digest({workspace_id:workspaceId,session_id:request.sessionId});
  const task={id,workspace_id:workspaceId,session:request.sessionId,request_id:request.requestId,request_digest:digest(request),turn:1+Math.max(0,...snapshot.events.filter((e:any)=>e.type==='turn/start').map((e:any)=>e.data.turn)),status:'admitted',next_step:0,model:model.model};
  const priorContext=await publicConversationContext(ctx,request.sessionId)??snapshot.events.filter((e:any)=>['user/message','assistant/message'].includes(e.type)).slice(-6).map((e:any)=>({role:e.type.startsWith('user')?'user':'assistant',text:(e.data.content??e.data.message?.content??[]).filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n')}));
  checkAdmission();
  const input={task_id:id,directory,objective,prior_context:priorContext,workspace_id:copyScope,owner,sources,model:model.model,provider_mode:policy.provider_mode,budget_usd:policy.budget_usd??null};
  const admitted=await ctx.attachments.admitPromptContent(content);checkAdmission();
  const binding=ctx.fileUploads.bindPrompt(agent,receipts,request.requestId);
  try{save(join(directory,'request.json'),input);tasks.set(id,task);store(task);agent.session.append('turn/start',{turn:task.turn});agent.session.append('user/message',createUserMessage({content:admitted,source:{kind:'user',rpcId:request.requestId}}),{surfaceOp:'append'});binding.commit();}finally{binding[Symbol.dispose]();}
  selected.delete(request.sessionId);persist();checkAdmission();await start(task);return {sessionId:request.sessionId,requestId:request.requestId};
  };
  // Reserve synchronously before any ownership/model/upload await. Retries
  // await the same admission; distinct sessions have no shared execution gate.
  const admission={request_digest:digest(request),promise:Promise.resolve().then(admit),cancelled:false};
  admissions.set(request.sessionId,admission);
  try{return await admission.promise;}finally{if(admissions.get(request.sessionId)===admission)admissions.delete(request.sessionId);}
 };
 controller.cancel=async(request:any)=>{await owned(request.sessionId);const pending=admissions.get(request.sessionId);if(pending)pending.cancelled=true;if(children.has(request.sessionId)){aborters.get(request.sessionId)?.abort();children.get(request.sessionId).kill();return {sessionId:request.sessionId};}if(pending)return {sessionId:request.sessionId};return original.cancel(request);};
 ctx.effect(()=>ctx.connection.fetch.register({path:'/api/harless/file-scene',methods:['GET','POST'],requestBody:'buffered',async fetch(request:Request){
  const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
  try{
   const url=new URL(request.url),body=request.method==='POST'?await request.json():null,session=body?.session_id??url.searchParams.get('session_id');await owned(session);
   if(body?.action==='select'){if(body.selected)selected.add(session);else selected.delete(session);persist();return Response.json(settings(session));}
   const id=(body?.id??url.searchParams.get('id')??'').replace(/^file-/,'');
   const task=id?tasks.get(id):[...tasks.values()].find(t=>t.session===session&&(t.turn===Number(url.searchParams.get('turn'))||(t.previous_turns??[]).includes(Number(url.searchParams.get('turn')))));
   if(body?.action==='resume'){if(!task||task.session!==session||task.status!=='interrupted'||!task.origin)throw Error('original_file_task_not_recoverable');await original.selectModel({sessionId:session,provider:'deepseek-official',model:task.model,reasoningEffort:'off'});await start(task,true);return Response.json(publicTask(task));}
   if(!id&&!url.searchParams.has('turn'))return Response.json(settings(session));
   if(!task||task.session!==session)return new Response('Not found',{status:404});
   const requestedTurn=Number(url.searchParams.get('turn'));
   if(requestedTurn&&(task.previous_turns??[]).includes(requestedTurn))return Response.json({...publicTask(task),turn:requestedTurn,status:'interrupted',resumed:true,lanes:{baseline:{status:'interrupted',artifacts:[]}}});
   if(!terminal.has(task.status))return Response.json({pending:true},{status:202});
   const file=url.searchParams.get('file');
   if(file){const row=task.artifacts?.find((r:any)=>r.id===file);if(!row||task.status!=='completed'||url.searchParams.get('lane')!=='baseline')return new Response('Not found',{status:404});
    const data=fileArtifactBytes(row.path,join(home,'tasks',task.id,'exports'),row.sha256);
    return new Response(data,{headers:{'Content-Type':'application/octet-stream','Content-Disposition':"attachment; filename*=UTF-8''"+encodeURIComponent(basename(row.name)),'Cache-Control':'no-store'}});
   }
   return Response.json(publicTask(task),{headers:{'Cache-Control':'no-store'}});
  }catch{return Response.json({error:{code:'file_scene_unavailable',message:'文件管理请求未通过校验，原记录已保留。'}},{status:409});}
 }}),'file-scene-route');
 ctx.effect(()=>()=>{for(const [id,child] of children){aborters.get(id)?.abort();child.kill();}controller.prompt=original.prompt;controller.cancel=original.cancel;controller.selectModel=original.selectModel;},'file-scene-lifetime');
}
