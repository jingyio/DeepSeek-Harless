/** Wrap only the native provider continuation, after all existing admission guards. */
import {appendFileSync,readFileSync,readdirSync,writeFileSync,existsSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import * as native from './dsh_web_tasks.ts';
import {createScriptInterceptor,loadScriptLibrary,registerScriptCache,registerReuseMediation} from './script_motif_runtime.ts';
import {createNegativeRuntime,loadNegativeLibrary} from './script_negative_runtime.ts';
import {createReuseMediation,loadReuseLibrary} from './reuse_mediation.ts';
import {createReuseTrace} from './reuse_trace.ts';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
import {resolveScriptLearningSettings} from './script_learning_store.ts';
export const name=native.name;
export const inject=native.inject;
/** An absent/empty/disabled positive matcher must not disable Negative advice. */
export function optionalScriptRuntime(settings:any,library:any,options:any,audit:(row:any)=>void){
 const fallback=()=>({positiveUnavailable:true,dispose(){},observe(){},frontierPrompt(){return '';},intercept(_id:any,_request:any,next:any){return next();}});
 if(!library?.programs?.length)return fallback();
 try{return createScriptInterceptor({...settings,library,...options,audit});}
 catch(error:any){audit({kind:'script_component_fallback',component:'positive_matcher',reason:error.message});return fallback();}
}
export function apply(ctx:any){
 const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
 const current=new Map<string,any>();
 const traces=new Map<string,any>();
 function trace(session:string){
  if(process.env.SSS_REUSE_TRACE!=='1')return null;
  for(const id of readdirSync(join(policy.output,'tasks')))try{
   const output=join(policy.output,'tasks',id),state=JSON.parse(readFileSync(join(output,'task-state.json'),'utf8'));
   if(state.session_id!==session||state.status!=='running'||state.user_id!==policy.user_id)continue;
   if(!traces.has(id)){const cfg=JSON.parse(readFileSync(join(output,'effective-config.json'),'utf8'));traces.set(id,createReuseTrace(cfg.workspace,output));}
   return traces.get(id);
  }catch{}
  return null;
 }
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
   const {settings,snapshot}=resolveScriptLearningSettings(JSON.parse(readFileSync(process.env.SSS_SCRIPT_MOTIF_CONFIG!,'utf8')),policy.user_id);
   if(snapshot)writeFileSync(join(output,'script-learning-snapshot.json'),JSON.stringify({...snapshot,status:snapshot.status==='loaded'?'resolved':snapshot.status},null,2)+'\n',{mode:0o600});
   if(snapshot?.status==='cold_start'&&!settings.library&&!settings.reuseLibrary&&!settings.negativeLibrary){
    audit({kind:'script_learning_cold_start'});current.set(session,{id:state.task_id,runtime:null});return null;
   }
   const library=settings.library?loadScriptLibrary(settings.library):null;
   const task=JSON.parse(readFileSync(join(output,'task.json'),'utf8')),effective=JSON.parse(readFileSync(join(output,'effective-config.json'),'utf8'));
   if(effective.session_id!==session||effective.user_id!==policy.user_id)throw Error('script_owner_changed');
   const negative=settings.negativeLibrary?createNegativeRuntime({library:loadNegativeLibrary(settings.negativeLibrary),workspace:effective.workspace,mode:settings.negativeMode,audit}):null;
   const reuse=settings.reuseLibrary?createReuseMediation({library:loadReuseLibrary(settings.reuseLibrary),scriptLibrary:library,workspace:effective.workspace,tools:effective.tools,mode:settings.mode,probeTools:settings.probeTools??[],repairChoices:settings.repairChoices===true,captureCurrentReport:settings.captureCurrentReport===true,audit}):null;
   if(!library&&!negative&&!reuse)throw Error('motif_library_required');
   writeFileSync(join(output,'script-motif-config.json'),JSON.stringify({...settings,library_digest:library?.digest}),{mode:0o600});
   runtime=optionalScriptRuntime(settings,library,{workspace:effective.workspace,session,
    goal:task.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n')},audit);
   runtime.negative=negative;
   runtime.reuse=reuse;registerReuseMediation(session,reuse);
   if(library&&settings.catalog&&!runtime.positiveUnavailable)runtime.catalog=registerScriptCache({...settings,library,workspace:effective.workspace,session,audit,frontier:runtime.frontier});
   if(snapshot?.status==='loaded'){
    writeFileSync(join(output,'script-learning-snapshot.json'),JSON.stringify(snapshot,null,2)+'\n',{mode:0o600});
    audit({kind:'script_learning_library_loaded',library_digest:library?.digest,reuse_digest:snapshot.reuse?.digest??null,negative_digest:snapshot.negative?.digest??null,triggered_by_task:snapshot.triggered_by_task,pointer_sha256:snapshot.pointer_sha256});
   }
  }catch(error:any){audit({kind:'script_fallback',reason:error.message});runtime=null;}
  current.set(session,{id:state.task_id,runtime});return runtime;
 }
 ctx.on('agent/created',({agent}:any)=>{
  agent.ctx.systemPrompt.variable('script_cache_catalog',()=>{const r=interceptor(agent.session.id);return (r?.catalog??'')+(r?.reuse?.staticPrompt()??'');});
  agent.ctx.systemPrompt.section({name:'script-cache-catalog',order:10220,text:'{{script_cache_catalog}}'});
  agent.ctx.tools.guard((execution:any)=>{trace(agent.session.id)?.before(execution);const r=interceptor(agent.session.id);return r?.reuse?.guard(execution)??r?.negative?.guard(execution);});
  agent.ctx.on('tools/result',(execution:any,result:any)=>{
   trace(agent.session.id)?.after(execution,result);const r=current.get(agent.session.id)?.runtime;
   const facts=r?.observe(agent.session.id,execution,result);r?.reuse?.observe(execution,result,facts??[]);r?.negative?.observe(execution,result);
   r?.reuse?.setNegativeConstraint(r?.negative?.currentConstraint?.());
   const negativeNotice=r?.negative?.takeNotice?.();
   if(negativeNotice)agent.inject(createUserMessage({source:{kind:'plugin',plugin:'script-motif-negative',form:'notice',summary:'当前失败条件与修订约束'},content:[{type:'text',text:negativeNotice}]}));
   const notice=(r?.frontierNotice?.()??'')+(r?.reuse?.takeNotice()??'');
   if(notice)agent.inject(createUserMessage({source:{kind:'plugin',plugin:'script-motif-reuse',form:'notice',summary:'当前可复用数据与待修订参数'},content:[{type:'text',text:notice}]}));
  });
 },{global:true});
 const scheduled=new Set();
 ctx.on('agent/status',({agent,status}:any)=>{
  if(status==='idle'){current.get(agent.session.id)?.runtime?.dispose();registerReuseMediation(agent.session.id,null);}
  if(status!=='idle'||!process.env.SSS_SCRIPT_MOTIF_LEARNING_STORE)return;
  setTimeout(()=>{
   for(const id of readdirSync(join(policy.output,'tasks')))try{
    const output=join(policy.output,'tasks',id),state=JSON.parse(readFileSync(join(output,'task-state.json'),'utf8'));
    const negativeEnabled=existsSync(join(process.env.SSS_SCRIPT_MOTIF_LEARNING_STORE!,'negative-learning.json'));
    if(state.session_id!==agent.session.id||state.user_id!==policy.user_id||!(state.status==='completed'||negativeEnabled&&['failed','cancelled'].includes(state.status))||state.mode!=='baseline'||scheduled.has(id))continue;
    scheduled.add(id);
    const worker=fileURLToPath(new URL('../../scripts/advance-script-motifs.py',import.meta.url));
    mkdirSync(process.env.SSS_SCRIPT_MOTIF_LEARNING_STORE!,{recursive:true,mode:0o700});
    const child=spawn(policy.learning_python,[worker,'--task',output,'--store',process.env.SSS_SCRIPT_MOTIF_LEARNING_STORE!,'--user',policy.user_id],
     {env:{PATH:process.env.PATH,SSS_PYTHON:policy.learning_python,SSS_LOCAL_SCRIPT_EXPERIMENT:process.env.SSS_LOCAL_SCRIPT_EXPERIMENT,PYTHONUTF8:'1',
       ...((negativeEnabled||existsSync(join(process.env.SSS_SCRIPT_MOTIF_LEARNING_STORE!,'description-learning.json')))&&process.env.DEEPSEEK_API_KEY?{DEEPSEEK_API_KEY:process.env.DEEPSEEK_API_KEY}:{})},stdio:'ignore'});
    const failed=(reason:string)=>{if(!existsSync(join(output,'script-learning-status.json')))writeFileSync(join(output,'script-learning-status.json'),JSON.stringify({status:'failed',reason}),{mode:0o600});};
    child.on('error',()=>failed('learning_worker_spawn_failed'));
    child.on('exit',(code,signal)=>{if(code!==0||signal)failed('learning_worker_exited_without_result');});
   }catch{}
  },50);
 },{global:true});
 const wrapped=new Proxy(ctx,{get(target,key){
  if(key==='on')return (event:any,handler:any,...rest:any[])=>target.on(event,event==='llm/stream'
   ?(request:any,next:any)=>handler(request,()=>{const runtime=interceptor(request.sessionId);return (async function*(){
     runtime?.negative?.update(request);
     runtime?.reuse?.update(request);
     const reused=runtime?.reuse?.ready();
     const checkedNext=()=>{runtime?.negative?.beforeRequest(request);return next();};
     const stream=reused??(runtime?await runtime.intercept(request.sessionId,request,checkedNext):checkedNext());for await(const chunk of stream)yield chunk;
    })();})
   :handler,...rest);
  const value=Reflect.get(target,key,target);return typeof value==='function'?value.bind(target):value;
 }});
 return native.apply(wrapped);
}
