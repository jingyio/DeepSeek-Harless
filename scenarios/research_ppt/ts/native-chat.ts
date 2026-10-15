/** 官方 Session 主聊天的薄桥接；语义工作仍由既有 Harness SDK 执行。 */
import { createHash, randomUUID } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join, extname } from 'node:path';
import { createUserMessage } from '@deepseek-ai/dsh-llm';

type Turn = { id:string; session_id:string; request_id:string; fingerprint:string; kind:string;
  message:string; status:string; task_id?:string; parent_version?:string; parent_deck_sha?:string; preview?:any; failure?:string; response?:string };
type Service = {command:(raw:any)=>Promise<any>;view:(id:string)=>Promise<any>;
  importFile:(name:string,stream:AsyncIterable<Uint8Array>,bytes:number)=>Promise<any>;busy?:()=>boolean};
const sha=(value:any)=>createHash('sha256').update(JSON.stringify(value??null)).digest('hex');
const publicFailure=(message?:string)=>!message?undefined:/预算|额度/.test(message)?'服务额度暂不可用，请联系管理员。':/页码|页数/.test(message)?'请明确需要修改的页码或生成页数。':/版本|旧版/.test(message)?'稿件版本已变化，请刷新后重新发送。':'本次操作未完成，已有稿件已保留。请稍后重试。';
function visibleReply(text:string){return text.split('\n').filter(line=>!/(?:mcp__|\$\s*\d|(?:token|预算|费用|账单|模型请求)|(?:inspect_deck|validate_deck|deliver_deck|revise_deck|host_delivery|baseline|普通DSH))/i.test(line)).join('\n').trim();}
/** 主聊天只投影用户交付信息；原始对照、预算、工具与失败日志保留服务端。 */
export function publicPptTurn(value:any){
  const task=value.task,feedback=task?.feedback?.find((r:any)=>r.request_id===value.id),result=feedback?.results?.optimized;
  const current=task?.current_decks?.optimized;
  const artifacts=(task?.artifacts??[]).filter((a:any)=>a.group==='optimized'&&a.version===current?.version)
    .map(({id,kind,name,download_url}:any)=>({id,kind,name,download_url}));
  const ready=value.status==='completed';
  const stage=ready?'complete':value.status==='queued'?'queued':value.kind==='feedback'?'revising':task?.progress??'reading';
  const descriptions:Record<string,string>={reading:'正在读取资料，确认论文内容与来源。',planning:'正在梳理方法和实验结果，安排汇报内容。',checking:'正在检查页面排版、引用和文件预览。',revising:'正在结合这条反馈检查当前稿件。',queued:'已收到你的反馈，正在等待当前处理完成。',complete:value.kind==='feedback'?'已完成本条反馈。':'PPT 已生成并通过文件与渲染检查。'};
  return {id:value.id,kind:value.kind,status:value.status,failure:publicFailure(value.failure),
    progress:{stage,summary:descriptions[stage]??descriptions.reading},
    reply:visibleReply(result?.reply??value.response??''),
    delivery:artifacts.length?{slides:task.slides,version:current.version,artifacts}:null};
}
export function nativePptOptions(message:string,names:string[]) {
  const countsText=message.replace(/第\s*[\d\s、,，和及到至–~\-]+\s*页/g,'');
  const matches=[...countsText.matchAll(/(?:约|共|制作|生成|做成)?\s*(\d+)\s*页(?:左右)?/g)];
  const counts=[...new Set(matches.map(m=>Number(m[1])))];
  if(counts.length>1||counts.some(n=>n<1||n>30))throw Error('请明确1–30页中的一个页数');
  return {instruction:message||'根据上传资料制作准确、自然的中文科研汇报，保留原图与来源，说明方法、实验条件和局限。',
    slides:counts[0]??15,template:'lab',operation:names.length===1&&extname(names[0]).toLowerCase()==='.pptx'?'restyle':'generate'};
}
export function installNativePptChat(ctx:any,config:{output:string},service:Service,owns:(id:string)=>boolean,requireIdle:()=>void=()=>{}) {
  const path=join(config.output,'ppt-native-chat.json');
  const state:{sessions:Record<string,string>;turns:Turn[]}=existsSync(path)?JSON.parse(readFileSync(path,'utf8')):{sessions:{},turns:[]};
  const persist=()=>{writeFileSync(path+'.tmp',JSON.stringify(state,null,2),{mode:0o600});renameSync(path+'.tmp',path);};
  const timers=new Map<string,ReturnType<typeof setTimeout>>();
  let serial=Promise.resolve();
  const admit=<T>(fn:()=>Promise<T>)=>{const p=serial.then(fn);serial=p.then(()=>undefined,()=>undefined);return p;};
  function get(sessionId:string,id?:string) {
    if(!owns(sessionId))throw Error('会话不属于当前用户');
    const row=id?state.turns.find(t=>t.id===id&&t.session_id===sessionId):[...state.turns].reverse().find(t=>t.session_id===sessionId);
    if(!row)throw Error('PPT聊天记录不存在');return row;
  }
  const agentFor=(id:string)=>{const agent=ctx.agents.get(id);if(!agent)throw Error('请先打开此会话以恢复Agent');return agent;};
  function done(t:Turn,text:string) {
    const session=agentFor(t.session_id).session;
    if(!session.snapshotEvents().some((e:any)=>e.type==='command/done'&&e.data.commandId===t.id))
      session.append('command/done',{commandId:t.id,kind:t.status==='failed'?'error':'success',text});
  }
  async function refresh(t:Turn) {
    let task:any;
    if(t.task_id)task=await service.view(t.task_id);
    if(t.status==='queued'&&!service.busy?.()) {
      await admit(async()=>{if(t.status!=='queued'||service.busy?.())return;
        try{task=await service.view(t.task_id!);if(t.kind==='feedback'&&task?.current_decks?.optimized?.sha256!==t.parent_deck_sha)throw Error('稿件版本已变化，请重新发送');
          t.parent_version=task.current_version;await confirmTurn(t);
        }catch(e){t.status='failed';t.failure=String((e as Error).message);persist();}
      });task=await service.view(t.task_id!);
    }
    if(t.status==='running'&&task) {
      const feedback=t.kind==='feedback'?task.feedback.find((r:any)=>r.request_id===t.id):null;
      const r=feedback?.results?.optimized;
      const delivered=task.results?.optimized?.mechanical_delivery_verified&&task.results?.optimized?.strategy_adherence!==false;
      const status=t.kind==='feedback'?(r&&['answered','delivered'].includes(r.status)?'completed':r?.status==='failed'?'failed':feedback?.status??'running'):
        delivered?'completed':task.status;
      if(status!=='running'){
        t.status=status;t.failure=status==='completed'?undefined:feedback?.failure??task.failure??undefined;persist();
        done(t,visibleReply(r?.reply??'')||(t.status==='completed'?'已完成，请查看本条消息的成品。':publicFailure(t.failure)??'PPT操作已结束。'));
      }
    }
    return {...t,fingerprint:undefined,task};
  }
  function watch(t:Turn) {
    if(timers.has(t.id))return;
    const poll=async()=>{timers.delete(t.id);try{await refresh(t);}catch{}if(['running','queued'].includes(t.status))timers.set(t.id,setTimeout(poll,1500));};
    timers.set(t.id,setTimeout(poll,500));
  }
  async function publishUser(agent:any,request:any) {
    const ids:string[]=[],content:any[]=[];
    for(const part of request.content) {
      if(part.type==='text')content.push(part);
      else if(part.type==='file') {const ref=ctx.fileUploads.resolve(agent,part.receiptId);if(!ref)throw Error('上传回执不属于当前会话');ids.push(part.receiptId);content.push({type:'file',attachment:ref});}
      else throw Error('本入口接收PDF/PPTX和文字；图片插入暂未接入');
    }
    const message=createUserMessage({content:await ctx.attachments.admitPromptContent(content),source:{kind:'user',rpcId:request.requestId}} as any);
    const binding=ctx.fileUploads.bindPrompt(agent,ids,request.requestId);
    try{agent.session.append('user/message',message,{surfaceOp:'append'});binding.commit();}finally{binding[Symbol.dispose]();}
  }
  async function confirmTurn(t:Turn) {
    requireIdle();
    if(service.busy?.()){t.status='queued';persist();watch(t);return{...t};}
    if(t.kind==='generate')await service.command({action:'submit',task_id:t.task_id,confirmation_digest:t.preview.confirmation_digest});
    else await service.command({action:'message',task_id:t.task_id,message:t.message,request_id:t.id,expected_version:t.parent_version});
    t.status='running';persist();watch(t);return refresh(t);
  }
  const api={
    hasSession:(id:string)=>Boolean(state.sessions[id]),
    busy:()=>Boolean(service.busy?.())||state.turns.some(t=>['running','queued'].includes(t.status)),
    async view(sessionId:string,id?:string){const t=get(sessionId,id);if(!ctx.agents.get(sessionId))await ctx.sessionController.create({sessionId});const value=await refresh(t);if(!['preparing','preview','running','queued'].includes(t.status))done(t,t.response??publicFailure(t.failure)??'已完成，请查看本条消息的成品。');return value;},
    async start(agent:any,request:any) {return admit(async()=>{
      const sessionId=agent.session.id;if(!owns(sessionId))throw Error('会话不属于当前用户');
      if(typeof request.requestId!=='string'||!request.requestId||request.requestId.length>128||!Array.isArray(request.content))throw Error('无效请求');
      const fingerprint=sha(request.content),duplicate=state.turns.find(t=>t.session_id===sessionId&&t.request_id===request.requestId);
      if(duplicate){if(duplicate.fingerprint!==fingerprint)throw Error('同一请求ID不可更改输入');return{accepted:true};}
      const acceptedUser=agent.session.snapshotEvents().find((e:any)=>e.type==='user/message'&&e.data.source?.rpcId===request.requestId);
      if(acceptedUser){if(sha(acceptedUser.data.content)!==fingerprint)throw Error('同一请求ID不可更改输入');return{accepted:true};}
      const latest=[...state.turns].reverse().find(t=>t.session_id===sessionId);
      const message=request.content.filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n').trim();
      if(latest?.status==='preview'&&request.content.every((p:any)=>p.type==='text')&&/^(?:确认|确认生成|确认执行|开始生成|开始执行)[。！!\s]*$/.test(message)) {
        await publishUser(agent,request);await confirmTurn(latest);return{accepted:true};
      }
      if(latest&&['running','preview','queued'].includes(latest.status))throw Error('请先等待或停止当前PPT操作');
      if(message.length>10000||request.content.some((p:any)=>!['text','file'].includes(p.type)))throw Error('请发送不超过10000字的文字和PDF/PPTX');
      const fileParts=request.content.filter((p:any)=>p.type==='file');
      if(fileParts.length>8)throw Error('最多上传8份资料');
      const taskId=state.sessions[sessionId];
      if(taskId&&fileParts.length)throw Error('本会话已绑定稿件；使用新会话制作另一份PPT，当前稿件不会被替换');
      if(taskId&&!message)throw Error('请输入反馈或问题');
      const t:Turn={id:randomUUID(),session_id:sessionId,request_id:request.requestId,fingerprint,kind:taskId?'feedback':'generate',message,status:'preparing'};
      const imported=[];
      for(const part of fileParts){const ref=ctx.fileUploads.resolve(agent,part.receiptId);if(!ref)throw Error('上传回执不属于当前会话');imported.push(await service.importFile(ref.name,ctx.attachments.readFileStream(ref),ref.bytes));}
      await publishUser(agent,request);state.turns.push(t);persist();
      agent.session.append('command/run',{commandId:t.id,name:'ppt-agent',args:message,source:{kind:'user'}});
      try {
        if(taskId){const task=await service.view(taskId);t.task_id=taskId;t.parent_version=task.current_version;
          if(!task.current_decks.optimized?.sha256)throw Error('稿件尚未交付，暂时无法继续改页');
          t.parent_deck_sha=task.current_decks.optimized.sha256;
          t.preview={budget_usd_total:0.5,message,impact:'对当前两份稿件执行反馈，明确页码才可改页；保留旧稿与非目标页。'};
        } else if(imported.length){
          const options=nativePptOptions(message,imported.map(r=>r.name));
          const preview=await service.command({action:'preview',receipt_ids:imported.map(r=>r.id),...options});
          t.task_id=preview.task_id;t.preview=preview;state.sessions[sessionId]=preview.task_id;
        }else{t.status='completed';t.response='请上传PDF/PPTX并说明要求。我会制作一份可编辑PPT；未规定页数时默认约15页。';persist();done(t,t.response);return{accepted:true};}
        t.status='preview';persist();await confirmTurn(t);
      } catch(e){t.status='failed';t.failure=String((e as Error).message);persist();done(t,publicFailure(t.failure)!);}
      return{accepted:true};
    });},
    async confirm(sessionId:string,id:string,digest:string){return admit(async()=>{
      const t=get(sessionId,id);if(!ctx.agents.get(sessionId))await ctx.sessionController.create({sessionId});if(digest!==sha(t.preview))throw Error('预览变化，请刷新');
      if(t.status!=='preview')return refresh(t);
      return confirmTurn(t);
    });},
    async cancel(sessionId:string,id:string){return admit(async()=>{
      const t=get(sessionId,id);if(!['preview','running','queued'].includes(t.status))return refresh(t);
      if(t.status==='running'||t.kind==='generate')await service.command({action:'cancel',task_id:t.task_id});
      if(t.kind==='generate'&&['preview','queued'].includes(t.status))delete state.sessions[sessionId];
      t.status='cancelled';persist();done(t,'已停止，已有稿件已保留。');return refresh(t);
    });},
  };
  for(const t of state.turns)if(t.status==='preparing'){t.status='failed';t.failure='准备过程被中断，请重新发送；没有自动重复调用模型';}persist();
  for(const t of state.turns)if(['running','queued'].includes(t.status))watch(t);
  ctx.effect(()=>()=>{for(const timer of timers.values())clearTimeout(timer);},'research-ppt-native-cleanup');
  ctx.effect(()=>ctx.connection.fetch.register({path:'/api/harless/ppt/chat',methods:['GET','POST'],requestBody:'buffered',fetch:async(request:Request)=>{
    try{let value:any;
      if(request.method==='GET'){const url=new URL(request.url);value=await api.view(url.searchParams.get('session_id')??'',url.searchParams.get('turn_id')??undefined);}
      else {const raw=await request.json() as any;if(Object.keys(raw).some(k=>!['action','session_id','turn_id','preview_digest'].includes(k)))throw Error('无效聊天操作');
        value=raw.action==='confirm'?await api.confirm(raw.session_id,raw.turn_id,raw.preview_digest):raw.action==='cancel'?await api.cancel(raw.session_id,raw.turn_id):(()=>{throw Error('无效操作');})();}
      return Response.json(publicPptTurn(value),{headers:{'Cache-Control':'no-store'}});
    }catch(e){return Response.json({error:publicFailure(String((e as Error).message))},{status:400});}
  }}),'research-ppt-native-api');
  return api;
}
