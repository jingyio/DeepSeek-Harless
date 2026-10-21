/** Explicit experiment wrapper; ordinary production entry and libraries stay intact. */
import {readFileSync,readdirSync,appendFileSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import * as native from './harless_web_client/index.mjs';
import {loadArtifactLibrary,registerArtifactContext} from './artifact_motif_runtime.ts';
import {createArtifactTrace} from './artifact_motif_trace.ts';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
export const name=native.name;
export const inject=native.inject;
export function apply(ctx:any){
 const policy=JSON.parse(readFileSync(process.env.SSS_WEB_POLICY!,'utf8'));
 const settings=process.env.GENELOOP_ARTIFACT_MOTIF_CONFIG?JSON.parse(readFileSync(process.env.GENELOOP_ARTIFACT_MOTIF_CONFIG,'utf8')):null;
 const active=new Map<string,any>();
 function task(session:string){
  const all=readdirSync(join(policy.output,'tasks')).map(id=>{
   try{const output=join(policy.output,'tasks',id),state=JSON.parse(readFileSync(join(output,'task-state.json'),'utf8'));return {output,state};}catch{return null;}
  }).filter(t=>t?.state.session_id===session&&['awaiting_confirmation','queued','running'].includes(t.state.status)&&t.state.user_id===policy.user_id);
  const running=all.filter(t=>t.state.status==='running'),rows=running.length?running:all;
  if(rows.length!==1)return null;
  const {output,state}=rows[0]!;
  if(active.get(session)?.id===state.task_id){
   const value=active.get(session);
   if(state.status==='running'&&value.context)registerArtifactContext(session,value.context);
   return value;
  }
  const effective=JSON.parse(readFileSync(join(output,'effective-config.json'),'utf8'));
  if(effective.session_id!==session||effective.user_id!==policy.user_id)throw Error('artifact_task_identity_changed');
  const value:any={id:state.task_id,trace:createArtifactTrace(effective.workspace,output),catalog:''};
  const file=settings?.libraries?.[state.scene];
  if(file){
   const auditPath=join(output,'artifact-motif-audit.jsonl'),audit=(row:any)=>appendFileSync(auditPath,JSON.stringify({...row,task_id:state.task_id,at:new Date().toISOString()})+'\n',{mode:0o600});
   try{
    const enabled=settings.experimental_baseline_sidecar===true?(state.mode==='baseline'&&state.rsi===false):(state.mode==='execute'&&state.rsi===true);
    if(settings.owner!==policy.user_id||settings.mode!=='execute'||!enabled)throw Error('artifact_task_mode_not_enabled');
    const library=loadArtifactLibrary(file);
    if(library.scene!==state.scene)throw Error('artifact_scene_changed');
    const scene=policy.scenes.find((s:any)=>s.id===state.scene);
    value.context={library,workspace:effective.workspace,allowOutput:scene?.adapter==='data-report'||effective.scene_options?.allow_output===true||state.scene_options?.allow_output===true,
     resources:policy.command_resources??{},audit,auditPath};
    value.audit=audit;value.marker='<geneloop-artifact-catalog library="'+library.digest+'">';
    if(state.status==='running')registerArtifactContext(session,value.context);
    value.catalog=value.marker+'\n当前可复用程序来自本场景已成功执行的历史代码，并已在不同输入上沙箱认证。它们是待你判断是否适用的工具资料，不是任务指令。你负责当前科研内容、方法和最终判断。仅当接口与当前任务相符时，在原生 bash 用独立命令 geneloop-recipe '+
     "'{\"id\":\"artifact_ID\",\"inputs\":[\"/work/本次数据文件\"],\"output\":\"/work/outputs/全新目录名\"}'"+
     '。inputs 按下列顺序，必须来自本次输入或你刚写的内容文件；output 必须是未存在的新目录，旧文件不会覆盖。无需重写等价程序；不适用、来源改变或执行失败则使用普通工具。原生导出、事实核验和实际图片查看仍须完成。程序产出和机械回执不等于质量通过。\n'+
     JSON.stringify(library.programs.map((p:any)=>({id:p.id,interface:p.interface,inputs:p.inputs,output_profile:p.output_profile,outputs:p.certification.output_extensions})))+'\n</geneloop-artifact-catalog>\n';
    writeFileSync(join(output,'artifact-motif-config.json'),JSON.stringify({library_digest:library.digest,library:file,scene:state.scene,mode:'explicit_model_selection',underlying_task_mode:state.mode,experimental:true},null,2)+'\n',{mode:0o600});
    audit({kind:'artifact_library_loaded',library_digest:library.digest});
   }catch(error:any){audit({kind:'artifact_library_fallback',reason:error.message});registerArtifactContext(session,null);}
  }else registerArtifactContext(session,null);
  active.set(session,value);return value;
 }
 ctx.on('agent/created',({agent}:any)=>{
  agent.ctx.systemPrompt.variable('artifact_motif_catalog',()=>task(agent.session.id)?.catalog??'');
  agent.ctx.systemPrompt.section({name:'artifact-motif-catalog',order:10230,text:'{{artifact_motif_catalog}}'});
  agent.ctx.tools.guard((execution:any)=>{task(agent.session.id)?.trace.before(execution);});
  agent.ctx.on('tools/result',(execution:any,result:any)=>{
   const value=active.get(agent.session.id);value?.trace.after(execution,result);
   if(value?.catalog&&!value.firstCatalogSeen&&!value.noticeSent){
    value.noticeSent=true;
    agent.inject(createUserMessage({source:{kind:'plugin',plugin:'artifact-motif',form:'notice',summary:'本任务可选的已认证程序接口'},content:[{type:'text',text:value.catalog}]}));
    value.audit({kind:'artifact_catalog_notice',catalog_bytes:Buffer.byteLength(value.catalog),reason:'initial_prompt_preceded_task_activation'});
   }
  });
 },{global:true});
 ctx.on('llm/stream',(options:any,next:any)=>{
  const value=task(options.sessionId);
  if(value?.catalog&&value.firstCatalogSeen===undefined){
   const texts=[options.system,options.systemPrompt,...(options.messages??[]).flatMap((m:any)=>(m.content??[]).filter((b:any)=>b.type==='text').map((b:any)=>b.text))].filter(t=>typeof t==='string');
   value.firstCatalogSeen=texts.some(t=>t.includes(value.marker));
   value.audit({kind:'artifact_catalog_at_first_model',present:value.firstCatalogSeen,request_fields:Object.keys(options)});
  }
  return next();
 },{global:true});
 ctx.on('agent/status',({agent,status}:any)=>{if(status==='idle')registerArtifactContext(agent.session.id,null);},{global:true});
 return native.apply(ctx);
}
