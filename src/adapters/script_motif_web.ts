/** Wrap only the native provider continuation, after all existing admission guards. */
import {appendFileSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import * as native from './dsh_web_tasks.ts';
import {createScriptInterceptor,loadScriptLibrary,registerScriptCache} from './script_motif_runtime.ts';
import {createNegativeRuntime,loadNegativeLibrary} from './script_negative_runtime.ts';
export const name=native.name;
export const inject=native.inject;
export function apply(ctx:any){
 const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
 const current=new Map<string,any>();
 function interceptor(session:string){
  if(!process.env.SSS_SCRIPT_MOTIF_CONFIG)return null;
  const active=readdirSync(join(policy.output,'tasks')).map(id=>{
   try{const output=join(policy.output,'tasks',id),state=JSON.parse(readFileSync(join(output,'task-state.json'),'utf8'));return {output,state};}catch{return null;}
  }).filter(t=>t?.state.session_id===session&&t.state.status==='running'&&t.state.user_id===policy.user_id);
  if(active.length!==1)return null;
  const {output,state}=active[0]!;
  if(state.scene!=='paper-proofreading'||state.mode!=='baseline'||state.rsi!==false)return null;
  if(current.get(session)?.id===state.task_id)return current.get(session).runtime;
  const audit=(row:any)=>appendFileSync(join(output,'script-motif-audit.jsonl'),JSON.stringify({...row,task_id:state.task_id,at:new Date().toISOString()})+'\n',{mode:0o600});
  let runtime:any;
  try{
   const settings=JSON.parse(readFileSync(process.env.SSS_SCRIPT_MOTIF_CONFIG!,'utf8'));
   if(settings.learningStore){
    const pointer=JSON.parse(readFileSync(join(settings.learningStore,'latest.json'),'utf8'));
    if(pointer.user!==policy.user_id||!/^round-[a-f0-9]+\/library\.json$/.test(pointer.file))throw Error('foreign_script_library');
    settings.library=join(settings.learningStore,pointer.file);
   }
   const library=settings.library?loadScriptLibrary(settings.library):null;
   const task=JSON.parse(readFileSync(join(output,'task.json'),'utf8')),effective=JSON.parse(readFileSync(join(output,'effective-config.json'),'utf8'));
   if(effective.session_id!==session||effective.user_id!==policy.user_id)throw Error('script_owner_changed');
   const negative=settings.negativeLibrary?createNegativeRuntime({library:loadNegativeLibrary(settings.negativeLibrary),workspace:effective.workspace,mode:settings.negativeMode,audit}):null;
   if(!library&&!negative)throw Error('motif_library_required');
   writeFileSync(join(output,'script-motif-config.json'),JSON.stringify({...settings,library_digest:library?.digest}),{mode:0o600});
   runtime=library?createScriptInterceptor({...settings,library,workspace:effective.workspace,session,
    goal:task.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n'),audit}):{dispose(){},observe(){},frontierPrompt(){return '';},intercept(_id:any,_request:any,next:any){return next();}};
   runtime.negative=negative;
   if(library&&settings.catalog)runtime.catalog=registerScriptCache({...settings,library,workspace:effective.workspace,session,audit,frontier:runtime.frontier});
  }catch(error:any){audit({kind:'script_fallback',reason:error.message});runtime=null;}
  current.set(session,{id:state.task_id,runtime});return runtime;
 }
 ctx.on('agent/created',({agent}:any)=>{
  agent.ctx.systemPrompt.variable('script_cache_catalog',()=>{const r=interceptor(agent.session.id);return (r?.catalog??'')+(r?.frontierPrompt()??'')+(r?.negative?.prompt()??'');});
  agent.ctx.systemPrompt.section({name:'script-cache-catalog',order:10220,text:'{{script_cache_catalog}}'});
  agent.ctx.tools.guard((execution:any)=>interceptor(agent.session.id)?.negative?.guard(execution));
  agent.ctx.on('tools/result',(execution:any,result:any)=>{const r=current.get(agent.session.id)?.runtime;r?.observe(agent.session.id,execution,result);r?.negative?.observe(execution,result);});
 },{global:true});
 const scheduled=new Set();
 ctx.on('agent/status',({agent,status}:any)=>{
  if(status==='idle')current.get(agent.session.id)?.runtime?.dispose();
  if(status!=='idle'||!process.env.SSS_SCRIPT_MOTIF_LEARNING_STORE)return;
  setTimeout(()=>{
   for(const id of readdirSync(join(policy.output,'tasks')))try{
    const output=join(policy.output,'tasks',id),state=JSON.parse(readFileSync(join(output,'task-state.json'),'utf8'));
    if(state.session_id!==agent.session.id||state.user_id!==policy.user_id||state.status!=='completed'||state.mode!=='baseline'||scheduled.has(id))continue;
    scheduled.add(id);
    const worker=fileURLToPath(new URL('../../scripts/advance-script-motifs.py',import.meta.url));
    const child=spawn(policy.learning_python,[worker,'--task',output,'--store',process.env.SSS_SCRIPT_MOTIF_LEARNING_STORE!,'--user',policy.user_id],
     {env:{PATH:process.env.PATH,SSS_PYTHON:policy.learning_python,SSS_LOCAL_SCRIPT_EXPERIMENT:process.env.SSS_LOCAL_SCRIPT_EXPERIMENT,PYTHONUTF8:'1'},stdio:'ignore'});
    child.on('error',()=>{});
   }catch{}
  },50);
 },{global:true});
 const wrapped=new Proxy(ctx,{get(target,key){
  if(key==='on')return (event:any,handler:any,...rest:any[])=>target.on(event,event==='llm/stream'
   ?(request:any,next:any)=>handler(request,()=>{const runtime=interceptor(request.sessionId);return (async function*(){
     runtime?.negative?.beforeRequest(request);
     const stream=runtime?await runtime.intercept(request.sessionId,request,next):next();for await(const chunk of stream)yield chunk;
    })();})
   :handler,...rest);
  const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
 }});
 return native.apply(wrapped);
}
