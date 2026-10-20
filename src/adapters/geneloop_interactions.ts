/** Human answers for native DSH questions, addressed through the public conversation.
 * The native tool owns its durable result. This bridge holds only a live promise;
 * neither a browser refresh nor another account can silently answer a question.
 */
import {randomUUID} from 'node:crypto';

type Owner={session:string;task:string;lane:'baseline'|'motif'};
export function createInteractionBridge(resolve:(agent:any)=>Owner|undefined){
 const pending=new Map<string,{owner:Owner;agent:any;request:any;settle:(answer:any)=>void;reject:(error:any)=>void;cleanup:()=>void}>();
 const failure=(text:string,status=409)=>Object.assign(Error(text),{status});
 const same=(a:Owner,b:Owner)=>a.session===b.session&&a.task===b.task&&a.lane===b.lane;
 function questions(request:any){
  if(!Array.isArray(request.questions)||!request.questions.length)throw failure('问题为空');
  const ids=new Set();
  for(const q of request.questions){
   if(typeof q.id!=='string'||!q.id||ids.has(q.id)||typeof q.question!=='string'||!q.question)throw failure('问题格式无效');
   ids.add(q.id);const labels=(q.options??[]).map((o:any)=>o.label);
   if(labels.some((x:any)=>typeof x!=='string'||!x)||new Set(labels).size!==labels.length)throw failure('问题选项无效');
  }
  return structuredClone(request.questions);
 }
 return {
  ask(request:any,next:()=>Promise<any>){
   const owner=resolve(request.agent);if(!owner)return next();
   const rows=questions(request),id=randomUUID();
   request.signal?.throwIfAborted();
   return new Promise((settle,reject)=>{
    const cleanup=()=>{pending.delete(id);request.signal?.removeEventListener('abort',cancel);};
    const cancel=()=>{cleanup();reject(Object.assign(Error('提问已取消'),{name:'AbortError'}));};
    pending.set(id,{owner,agent:request.agent,request:{questions:rows},settle,reject,cleanup});
    request.signal?.addEventListener('abort',cancel,{once:true});
    if(request.signal?.aborted)cancel();
   });
  },
  list(session:string){
   return [...pending].filter(([,p])=>p.owner.session===session).map(([id,p])=>({id,session_id:session,lane:p.owner.lane,task_id:p.owner.task,...p.request}));
  },
  answer(session:string,id:string,answers:any){
   const row=pending.get(id);if(!row||row.owner.session!==session)throw failure('提问已结束或不属于当前对话',404);
   // Exact task liveness is rechecked through the retained calling agent.
   const owner=resolve(row.agent);if(!owner||!same(owner,row.owner))throw failure('提问任务已结束');
   if(!Array.isArray(answers)||answers.length!==row.request.questions.length)throw failure('请回答全部问题',400);
   const ids=new Set(),normalized=[];
   for(const q of row.request.questions){
    const a=answers.find((x:any)=>x?.id===q.id);
    if(!a||ids.has(a.id)||!Array.isArray(a.selected)||new Set(a.selected).size!==a.selected.length||
       a.selected.some((s:any)=>typeof s!=='string'||!(q.options??[]).some((o:any)=>o.label===s))||
       (!q.multiSelect&&a.selected.length>1)||(a.custom!==undefined&&typeof a.custom!=='string')||
       (!a.selected.length&&!a.custom?.trim()))throw failure('答案格式无效',400);
    ids.add(a.id);normalized.push({id:a.id,selected:[...a.selected],...(a.custom===undefined?{}:{custom:a.custom})});
   }
   row.cleanup();row.settle({answers:normalized});
   return {answered:true};
  },
  dispose(){for(const p of [...pending.values()]){p.cleanup();p.reject(Object.assign(Error('提问服务已关闭'),{name:'AbortError'}));}},
 };
}

export function installInteractionBridge(ctx:any,options:{resolve:(agent:any)=>Owner|undefined;owns:(id:string)=>Promise<void>}){
 const bridge=createInteractionBridge(options.resolve);
 ctx.on('user-questions/request',(request:any,next:any)=>bridge.ask(request,next),{global:true,prepend:true});
 ctx.effect(()=>()=>bridge.dispose(),'geneloop-questions-lifetime');
 ctx.effect(()=>ctx.connection.fetch.register({path:'/api/harless/questions',methods:['GET','POST'],requestBody:'buffered',async fetch(request:Request){
  const rejected=ctx.connection.requestRejection(request);if(rejected)return new Response('Unauthorized',{status:rejected});
  try{
   const body=request.method==='POST'?await request.json():null;
   const session=body?.session_id??new URL(request.url).searchParams.get('session_id');
   if(typeof session!=='string')throw Object.assign(Error('缺少对话'),{status:400});
   await options.owns(session);
   return Response.json(request.method==='GET'?{questions:bridge.list(session)}:bridge.answer(session,body.id,body.answers),{headers:{'Cache-Control':'no-store'}});
  }catch(error:any){return Response.json({error:{message:error.status?error.message:'无法处理提问'}},{status:error.status??500,headers:{'Cache-Control':'no-store'}});}
 }}),'geneloop-questions-route');
 return bridge;
}
