/** Wrap only the native provider continuation, after all existing admission guards. */
import {appendFileSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import * as native from './dsh_web_tasks.ts';
import {createScriptInterceptor,loadScriptLibrary,registerScriptCache,registerReuseMediation} from './script_motif_runtime.ts';
import {createNegativeRuntime,loadNegativeLibrary} from './script_negative_runtime.ts';
import {createReuseMediation,loadReuseLibrary} from './reuse_mediation.ts';
import {createReuseTrace} from './reuse_trace.ts';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
export const name=native.name;
export const inject=native.inject;
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
   const settings=JSON.parse(readFileSync(process.env.SSS_SCRIPT_MOTIF_CONFIG!,'utf8'));
   if(settings.learningStore){
    const pointer=JSON.parse(readFileSync(join(settings.learningStore,'latest.json'),'utf8'));
    if(pointer.user!==policy.user_id||!/^round-[a-f0-9]+\/library\.json$/.test(pointer.file))throw Error('foreign_script_library');
    settings.library=join(settings.learningStore,pointer.file);
    if(pointer.reuse_file){
     if(!/^round-[a-f0-9]+\/reuse-library\.json$/.test(pointer.reuse_file))throw Error('foreign_reuse_library');
     settings.reuseLibrary=join(settings.learningStore,pointer.reuse_file);
    }
   }
   const library=settings.library?loadScriptLibrary(settings.library):null;
   const task=JSON.parse(readFileSync(join(output,'task.json'),'utf8')),effective=JSON.parse(readFileSync(join(output,'effective-config.json'),'utf8'));
   if(effective.session_id!==session||effective.user_id!==policy.user_id)throw Error('script_owner_changed');
   const negative=settings.negativeLibrary?createNegativeRuntime({library:loadNegativeLibrary(settings.negativeLibrary),workspace:effective.workspace,mode:settings.negativeMode,audit}):null;
   const reuse=settings.reuseLibrary?createReuseMediation({library:loadReuseLibrary(settings.reuseLibrary),scriptLibrary:library,workspace:effective.workspace,tools:effective.tools,mode:settings.mode,probeTools:settings.probeTools??[],audit}):null;
   if(!library&&!negative&&!reuse)throw Error('motif_library_required');
   writeFileSync(join(output,'script-motif-config.json'),JSON.stringify({...settings,library_digest:library?.digest}),{mode:0o600});
   runtime=library?createScriptInterceptor({...settings,library,workspace:effective.workspace,session,
    goal:task.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n'),audit}):{dispose(){},observe(){},frontierPrompt(){return '';},intercept(_id:any,_request:any,next:any){return next();}};
   runtime.negative=negative;
   runtime.reuse=reuse;registerReuseMediation(session,reuse);
   if(library&&settings.catalog)runtime.catalog=registerScriptCache({...settings,library,workspace:effective.workspace,session,audit,frontier:runtime.frontier});
  }catch(error:any){audit({kind:'script_fallback',reason:error.message});runtime=null;}
  current.set(session,{id:state.task_id,runtime});return runtime;
 }
 ctx.on('agent/created',({agent}:any)=>{
  agent.ctx.systemPrompt.variable('script_cache_catalog',()=>{const r=interceptor(agent.session.id);return (r?.catalog??'')+(r?.reuse?.staticPrompt()??'');});
  agent.ctx.systemPrompt.section({name:'script-cache-catalog',order:10220,text:'{{script_cache_catalog}}'});
  agent.ctx.tools.guard((execution:any)=>{trace(agent.session.id)?.before(execution);const r=interceptor(agent.session.id);r?.reuse?.guard(execution);return r?.negative?.guard(execution);});
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
