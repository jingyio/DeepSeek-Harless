/** Single-owner authenticated Web adapter, reusing the frozen paired runner. */
import { createHash, randomUUID } from 'node:crypto';
import { createReadStream, existsSync, mkdirSync, readFileSync, renameSync, statSync, unlinkSync, writeFileSync } from 'node:fs';
import { basename, extname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
const root = resolve(fileURLToPath(new URL('../../../', import.meta.url)));
const hash = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
const MAX_FILE = 100 * 1024 * 1024, MAX_TOTAL = 256 * 1024 * 1024;
type Receipt = { id: string; name: string; path: string; sha256: string; bytes: number };
type Task = { id: string; status: string; digest: string; trial: string; trial_sha256: string; created_at: string;
  budget_usd: number; instruction: string; slides: number; template: string; operation: string;
  files: Receipt[]; failure?: string; finished_at?: string; version?: string; feedback?: FeedbackTurn[]; budget_hold_usd?: number; settled?: boolean; };
type FeedbackTurn = {id:string;request_id:string;message:string;status:string;created_at:string;parent_version:string;groups?:string[];
  budget_usd:number;budget_hold_usd:number;settled?:boolean;results?:any;failure?:string;finished_at?:string};
export function normalizePptRequest(raw: any, receipts: Map<string, Receipt>) {
  const keys = ['action','receipt_ids','instruction','slides','template','operation','budget_usd'];
  if (!raw || typeof raw !== 'object' || Array.isArray(raw) || Object.keys(raw).some(k => !keys.includes(k))) throw Error('不支持的PPT参数');
  if (!Array.isArray(raw.receipt_ids) || raw.receipt_ids.length < 1 || raw.receipt_ids.length > 8 || new Set(raw.receipt_ids).size !== raw.receipt_ids.length) throw Error('需1–8份独立上传文件');
  const files = raw.receipt_ids.map((id: string) => { const row = receipts.get(id); if (!row) throw Error('上传回执不存在'); return row; });
  if (files.reduce((n: number, f: Receipt) => n + f.bytes, 0) > MAX_TOTAL) throw Error('总大小超过256 MiB');
  const instruction = raw.instruction ?? '根据论文制作准确、自然的中文科研汇报，说明方法、实验条件和局限，使用原文图件并标注来源。';
  const slides = raw.slides ?? 15, template = raw.template ?? 'lab', operation = raw.operation ?? 'generate', budget = raw.budget_usd ?? 3;
  if (typeof instruction !== 'string' || !instruction.trim() || instruction.length > 10000 || !Number.isInteger(slides) || slides < 1 || slides > 30 || !['lab','academic'].includes(template) || !['generate','restyle'].includes(operation) || typeof budget !== 'number' || !Number.isFinite(budget) || budget <= 0 || budget > 3) throw Error('无效说明、页数、模板、操作或预算');
  if (operation === 'restyle' && (files.length !== 1 || extname(files[0].name).toLowerCase() !== '.pptx')) throw Error('重排需要一份PPTX');
  return { instruction, slides, template, operation, budget_usd: budget, files };
}
async function fileHash(path: string) { const h = createHash('sha256'); for await (const chunk of createReadStream(path)) h.update(chunk); return h.digest('hex'); }
const privateFile = (path: string) => { const p = resolve(path); if (!p.startsWith(join(root,'.local') + sep)) throw Error('文件越出私有目录'); return p; };
const save = (path: string, value: any) => { writeFileSync(path+'.tmp',JSON.stringify(value,null,2),{mode:0o600}); renameSync(path+'.tmp',path); };
export function installPptWeb(ctx: any, config: { output: string; provider_mode: string; ppt_run_budget_usd?: number; ppt_state_directory?:string }) {
  const directory = config.ppt_state_directory?privateFile(config.ppt_state_directory):join(config.output,'ppt'); mkdirSync(directory,{recursive:true,mode:0o700});
  const statePath = join(directory,'state.json');
  const stored = existsSync(statePath) ? JSON.parse(readFileSync(statePath,'utf8')) : {receipts:[],tasks:[],reserved_usd:0};
  const receipts = new Map<string,Receipt>(stored.receipts.map((r:Receipt)=>[r.id,r]));
  const tasks = new Map<string,Task>(stored.tasks.map((t:Task)=>[t.id,t]));
  let reserved=Number(stored.reserved_usd), active:string|null=null;
  const cap=config.ppt_run_budget_usd??3;
  if (!Number.isFinite(cap)||cap<0||cap>100) throw Error('无效PPT启动预算');
  const persist=()=>save(statePath,{receipts:[...receipts.values()],tasks:[...tasks.values()],reserved_usd:reserved});
  for(const t of tasks.values())if(t.status==='running'){t.status='interrupted';t.failure='服务重启，保留账本，不自动重复付费';}persist();
  for(const t of tasks.values())for(const turn of t.feedback??[])if(turn.status==='running'){turn.status='interrupted';turn.failure='服务重启，原稿保留；不会自动重复付费';}persist();
  let admission=Promise.resolve();
  const serial=<T>(fn:()=>Promise<T>):Promise<T>=>{const p=admission.then(fn);admission=p.then(()=>undefined,()=>undefined);return p;};
  const running=new Map<string,ReturnType<typeof spawn>>();
  function stop(child:ReturnType<typeof spawn>|undefined){if(!child?.pid)return;try{if(process.platform==='win32')child.kill();else process.kill(-child.pid,'SIGTERM');}catch{}}
  function python(args:string[],input?:any,log?:string){
    const child=spawn(process.env.SSS_PYTHON||'python',args,{cwd:root,env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'},detached:process.platform!=='win32',stdio:['pipe','pipe','pipe']});let output='';
    const stream=(chunk:Buffer)=>{if(log)writeFileSync(log,chunk,{flag:'a',mode:0o600});else{output+=chunk.toString();if(output.length>1024*1024)stop(child);}};
    child.stdout.on('data',stream);child.stderr.on('data',log?stream:()=>{});child.stdin.end(input===undefined?undefined:JSON.stringify(input));
    const done=new Promise<{code:number;output:string}>((ok,fail)=>{child.on('error',fail);child.on('close',code=>ok({code:code??-1,output}));});return{child,done};
  }
  function get(id:unknown){if(typeof id!=='string'||!tasks.has(id))throw Error('任务不存在');return tasks.get(id)!;}
  function settle(record: {budget_usd:number;budget_hold_usd?:number;settled?:boolean}, results:any){
    if(record.settled)return;
    const accounts=((record as FeedbackTurn).groups??['baseline','optimized']).map(g=>results[g]?.accounting);
    if(accounts.some(a=>!a?.usage_complete||a.unsettled_request_count!==0||typeof a.observed_proxy_usd!=='number'||!Number.isFinite(a.observed_proxy_usd)||a.observed_proxy_usd<0))return;
    const actual=accounts.reduce((n,a)=>n+a.observed_proxy_usd,0),held=record.budget_hold_usd??record.budget_usd;
    if(actual>held+1e-6)return;
    reserved=Math.max(0,reserved-held+actual);record.budget_hold_usd=actual;record.settled=true;persist();
  }
  async function files(task:Task){
    const area=resolve(task.trial,'..'),reportPath=join(area,'comparison.json');
    const report=existsSync(reportPath)?JSON.parse(readFileSync(reportPath,'utf8')):{results:{}};
    // 逐组独立验收后即可交付；内部对照不阻挡已完成的用户成品。
    for(const group of ['optimized','baseline']){const path=join(area,group+'-result.json');if(!report.results[group]&&existsSync(path))try{report.results[group]=JSON.parse(readFileSync(path,'utf8'));}catch{}}
    for(const turn of task.feedback??[])if(turn.status==='running')for(const group of turn.groups??['optimized','baseline']){
      const path=join(area,turn.id,group,'result.json');if(existsSync(path))try{turn.results??={};turn.results[group]=JSON.parse(readFileSync(path,'utf8'));}catch{}
    }
    const results:any={},artifacts:any[]=[];
    const current:any={};
    for(const group of ['baseline','optimized']){const r=report.results[group];if(!r)continue;results[group]={status:r.status,mechanical_delivery_verified:r.mechanical_delivery_verified,strategy_adherence:r.strategy_adherence,elapsed_seconds:r.elapsed_seconds,accounting:r.accounting,quality:'待用户评审'};
      const append=(deliveries:any[],version:number)=>{for(const delivery of deliveries??[]){if(delivery.deck_id)current[group]={deck_id:delivery.deck_id,sha256:delivery.files.find((f:any)=>f.kind==='pptx')?.sha256,version};for(const row of delivery.files??[]){const path=privateFile(row.path),id=hash(group+':'+path+':'+row.sha256);artifacts.push({id,group,kind:row.kind,name:basename(path),sha256:row.sha256,path,version});}}};
      if(r.mechanical_delivery_verified)append(r.deliveries,0);
      let revision=0;
      for(const turn of task.feedback??[])if(turn.status!=='cancelled'&&turn.status!=='interrupted'&&turn.results?.[group]?.status==='delivered')append(turn.results[group].deliveries,++revision);
    }
    if(['completed','failed'].includes(task.status))settle(task,report.results);
    for(const turn of task.feedback??[])if(turn.status!=='running'&&turn.results)settle(turn,turn.results);
    const version=hash(JSON.stringify(current));if(task.version!==version){task.version=version;persist();}
    return{results,artifacts,current};
  }
  async function view(t:Task){const data=await files(t);const all=['baseline','optimized'].map(g=>[data.results[g]?.accounting,...(t.feedback??[]).map(turn=>turn.results?.[g]?.accounting)]).flat();
    const known=all.length>0&&all.every(a=>a?.usage_complete&&a.unsettled_request_count===0);
    let progress='reading';
    try{const trial=JSON.parse(readFileSync(t.trial,'utf8')),eventsPath=join(resolve(trial.groups.optimized.job,'..'),'feedback.jsonl');
      const kinds=existsSync(eventsPath)?readFileSync(eventsPath,'utf8').split('\n').slice(-200).flatMap(line=>{try{return[JSON.parse(line).kind];}catch{return[];}}):[];
      if(kinds.includes('source_pinned'))progress='planning';if(kinds.includes('render_passed'))progress='checking';
    }catch{}
    return{task_id:t.id,status:t.status,execution_busy:Boolean(active),progress,confirmation_digest:t.digest,current_version:t.version,current_decks:data.current,feedback_budget_usd:0.5,
    feedback:(t.feedback??[]).map(turn=>({...turn,results:turn.results?Object.fromEntries(Object.entries(turn.results).map(([g,r]:any)=>[g,{status:r.status,reply:r.reply,accounting:r.accounting,target_pages:r.target_pages,failure:r.failure}])):undefined})),
    cumulative:{proxy_model_usd:known?all.reduce((n,a)=>n+a.observed_proxy_usd,0):null,requests:known?all.reduce((n,a)=>n+a.upstream_requests,0):null,scope:'生成和全部反馈，包括失败；代理估费，不是账单实付'},
    created_at:t.created_at,finished_at:t.finished_at,failure:t.failure??null,instruction:t.instruction,slides:t.slides,template:t.template,operation:t.operation,budget_usd_total:t.budget_usd,budget_usd_per_group:t.budget_usd/2,model:'deepseek-flash',reasoning_effort:'off',max_steps_per_group:60,max_output_tokens:8000,rsi_candidate_generation:false,compression:false,files:t.files.map(({id,name,bytes,sha256})=>({id,name,bytes,sha256})),results:data.results,artifacts:data.artifacts.map(({path,...a})=>({...a,download_url:'/api/harless/ppt/download?task_id='+t.id+'&artifact_id='+a.id})),impact:'串行生成普通DSH与优化Agent两套新文件，不覆盖输入；两路支出合计另报。',budget_scope:{reserved_usd:reserved,launch_cap_usd:cap,note:'持久累计PPT额度；付费前预留上限，只有完整结算后释放未使用额度。失败/未知费用保守留账，重启不归零。'}};}
  const send=(res:any,status:number,value:any)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
  async function body(req:any,limit:number){const chunks:Buffer[]=[];let n=0;for await(const chunk of req){n+=chunk.length;if(n>limit)throw Error('请求过大');chunks.push(chunk);}return Buffer.concat(chunks);}
  const handler=(kind:string)=>async(req:any,res:any)=>{
    const rejected=ctx.connection.requestRejection(req);if(rejected){res.writeHead(rejected);res.end('请先登录Harness');return;}
    try{
      if(req.method==='POST'&&req.headers.origin&&new URL(req.headers.origin).host!==req.headers.host){send(res,403,{error:'拒绝跨站写请求'});return;}
      const url=new URL(req.url,'http://localhost');
      if(kind==='page'){if(req.method!=='GET')throw Error('需GET');res.writeHead(200,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end(readFileSync(fileURLToPath(new URL('../web-panel.html',import.meta.url))));return;}
      if(kind==='upload'){
        if(receipts.size>=32||[...receipts.values()].reduce((n,r)=>n+r.bytes,0)>=512*1024*1024)throw Error('本次启动上传留存额度已满，请由管理员归档');
        if(req.method!=='POST')throw Error('上传需POST');const name=url.searchParams.get('name')??'';
        if(!name||name.length>255||/[\x00-\x1f\\/]/.test(name)||!['.pdf','.pptx'].includes(extname(name).toLowerCase()))throw Error('只接收PDF/PPTX文件名');
        if(Number(req.headers['content-length']??0)>MAX_FILE)throw Error('单文件超过100 MiB');
        const id=randomUUID(),path=join(directory,id+extname(name).toLowerCase());let n=0;const h=createHash('sha256');writeFileSync(path,'',{mode:0o600});
        try{for await(const chunk of req){n+=chunk.length;if(n>MAX_FILE)throw Error('单文件超过100 MiB');h.update(chunk);writeFileSync(path,chunk,{flag:'a'});}if(!n)throw Error('文件为空');}catch(e){unlinkSync(path);throw e;}
        const receipt={id,name,path,bytes:n,sha256:h.digest('hex')};receipts.set(id,receipt);persist();send(res,201,{id,name,bytes:n,sha256:receipt.sha256});return;
      }
      if(kind==='download'){
        if(req.method!=='GET')throw Error('下载需GET');const t=get(url.searchParams.get('task_id')),a=(await files(t)).artifacts.find(a=>a.id===url.searchParams.get('artifact_id'));
        if(!a||await fileHash(a.path)!==a.sha256)throw Error('成品不存在或版本变化');const mime:any={pptx:'application/vnd.openxmlformats-officedocument.presentationml.presentation',pdf:'application/pdf',png:'image/png',preview:'image/png'};
        res.writeHead(200,{'Content-Type':mime[a.kind]??'application/octet-stream','Content-Length':statSync(a.path).size,'Content-Disposition':(url.searchParams.get('inline')==='1'&&['pdf','png','preview'].includes(a.kind)?'inline':'attachment')+'; filename="'+a.group+'-'+a.kind+extname(a.name)+'"','Cache-Control':'no-store'});createReadStream(a.path).pipe(res);return;
      }
      if(req.method==='GET'){const id=url.searchParams.get('task_id');send(res,200,id?await view(get(id)):{tasks:await Promise.all([...tasks.values()].map(view)),default_slides:15,max_file_bytes:MAX_FILE,paid_calls_enabled:config.provider_mode==='real'});return;}
      if(req.method!=='POST')throw Error('需GET/POST');const raw=JSON.parse((await body(req,32768)).toString('utf8'));
      const value=await command(raw);send(res,200,value);
    }catch(e){if(!res.headersSent)send(res,400,{error:String((e as Error).message)});}
  };
  // 主聊天与备用页共用准入、预算、版本和运行器，不能另建付费循环。
  const command=(raw:any)=>serial(async()=>{
        if(raw.action==='message'){
          if(Object.keys(raw).some(k=>!['action','task_id','message','request_id','expected_version'].includes(k))||typeof raw.message!=='string'||!raw.message.trim()||raw.message.length>10000||typeof raw.request_id!=='string'||!/^[a-zA-Z0-9_-]{8,80}$/.test(raw.request_id))throw Error('反馈需要有效消息、请求ID和当前版本');
          const t=get(raw.task_id);const duplicate=t.feedback?.find(turn=>turn.request_id===raw.request_id);
          if(duplicate){if(duplicate.message!==raw.message||duplicate.parent_version!==raw.expected_version)throw Error('请求ID已用于不同反馈');return view(t);}
          const data=await files(t);if(raw.expected_version!==t.version)throw Error('你正在查看旧版，请刷新后再反馈');
          if(!['completed','failed'].includes(t.status)||!data.current?.optimized?.sha256)throw Error('需要有效已交付稿件才能继续反馈');
          if(active)throw Error('已有PPT任务运行，请稍候');if(config.provider_mode!=='real')throw Error('未启用真实模型');
          const groups=['optimized','baseline'].filter(g=>data.current[g]?.sha256);
          const budget=0.25*groups.length;if(reserved+budget>cap+1e-9)throw Error('累计预算不足，请管理员调整额度；不会重置历史费用');
          const turn:FeedbackTurn={id:randomUUID(),request_id:raw.request_id,message:raw.message,status:'running',created_at:new Date().toISOString(),parent_version:t.version!,groups,budget_usd:budget,budget_hold_usd:budget};
          const area=join(directory,turn.id);mkdirSync(area,{mode:0o700});const trial=JSON.parse(readFileSync(t.trial,'utf8'));
          const history_by_group=Object.fromEntries(['baseline','optimized'].map(g=>[g,(t.feedback??[]).slice(-4).flatMap(old=>[{role:'user',content:old.message},{role:'assistant',content:old.results?.[g]?.reply??old.failure??''}])]));
          const request=join(area,'request.json');save(request,{message:raw.message,expected_version:t.version,history_by_group,budget_usd:budget,groups:Object.fromEntries(groups.map(g=>[g,{...data.current[g],job:trial.groups[g].job}]))});
          t.feedback??=[];t.feedback.push(turn);reserved+=budget;active=t.id;persist();
          const run=spawn('node',[join(root,'scenarios/research_ppt/dist/feedback-runner.js'),request],{cwd:root,env:{...process.env},detached:process.platform!=='win32',stdio:['ignore','pipe','pipe']});running.set(t.id,run);
          const log=join(area,'runner.log');run.stdout.on('data',b=>writeFileSync(log,b,{flag:'a',mode:0o600}));run.stderr.on('data',b=>writeFileSync(log,b,{flag:'a',mode:0o600}));
          const timer=setTimeout(()=>stop(run),1800000);
          const done=new Promise<number>((ok,fail)=>{run.on('error',fail);run.on('close',code=>ok(code??-1));});
          done.then(code=>{const resultPath=join(area,'result.json');if(existsSync(resultPath)){turn.results=JSON.parse(readFileSync(resultPath,'utf8')).results;settle(turn,turn.results);}if(turn.status==='running'){turn.status=code===0&&turn.results&&Object.values(turn.results).every((r:any)=>r.status!=='failed')?'completed':'failed';if(turn.status==='failed')turn.failure='本条反馈未全部完成，原稿与全部费用保留';}turn.finished_at=new Date().toISOString();persist();})
            .catch(()=>{turn.status='failed';turn.failure='反馈运行或结果核验失败，原稿保留';persist();}).finally(()=>{clearTimeout(timer);running.delete(t.id);active=null;});
          return view(t);
        }
        if(raw.action==='preview'){
          const options=normalizePptRequest(raw,receipts);for(const f of options.files)if(await fileHash(f.path)!==f.sha256)throw Error('输入版本变化');
          const prep=python(['-m','scenarios.research_ppt.web_bridge'],{...options,files:undefined,inputs:options.files.map((f:Receipt)=>f.path)});const timer=setTimeout(()=>stop(prep.child),120000);let result;try{result=await prep.done;}finally{clearTimeout(timer);}
          if(result.code!==0)throw Error('预览失败，请检查依赖或文件解析；未调用模型');const trial=privateFile(JSON.parse(result.output.trim()).trial),trial_sha256=await fileHash(trial);
          const t:Task={id:randomUUID(),status:'awaiting_confirmation',created_at:new Date().toISOString(),...options,trial,trial_sha256,digest:hash(trial_sha256+JSON.stringify(options))};tasks.set(t.id,t);persist();return view(t);
        }
        if(!raw||Object.keys(raw).some(k=>!['action','task_id','confirmation_digest'].includes(k)))throw Error('无效执行参数');const t=get(raw.task_id);
        if(raw.action==='cancel'){const turn=[...(t.feedback??[])].reverse().find(r=>r.status==='running');if(turn){stop(running.get(t.id));turn.status='cancelled';turn.failure='用户取消，原稿保留';persist();}if(t.status==='running')stop(running.get(t.id));if(['running','awaiting_confirmation'].includes(t.status)){t.status='cancelled';persist();}return view(t);}
        if(raw.action!=='submit')throw Error('只支持preview/submit/cancel');if(t.status!=='awaiting_confirmation')throw Error('已提交或结束，不能重复调用');
        if(raw.confirmation_digest!==t.digest||await fileHash(t.trial)!==t.trial_sha256)throw Error('确认不匹配');for(const f of t.files)if(await fileHash(f.path)!==f.sha256)throw Error('输入版本变化');
        if(config.provider_mode!=='real')throw Error('未启用真实模型');if(active)throw Error('已有PPT任务运行');if(reserved+t.budget_usd>cap+1e-9)throw Error('PPT启动预算不足，不能用新任务重置');
        reserved+=t.budget_usd;t.status='running';active=t.id;persist();const run=python(['-m','scenarios.research_ppt.trial','--trial',t.trial,'--call-model'],undefined,join(directory,t.id+'.log'));running.set(t.id,run.child);const timer=setTimeout(()=>stop(run.child),3600000);
        run.done.then(async({code})=>{const data=await files(t);if(t.status==='running'){t.status=code===0&&['baseline','optimized'].every(g=>data.results[g]?.mechanical_delivery_verified&&data.results[g]?.strategy_adherence!==false)?'completed':'failed';if(t.status==='failed')t.failure='规划或交付未全部通过，保留已验收成品和失败账本';}t.finished_at=new Date().toISOString();persist();}).catch(()=>{t.status='failed';t.failure='运行器或结果读取失败';persist();}).finally(()=>{clearTimeout(timer);running.delete(t.id);active=null;});return view(t);
      });
  for(const[path,kind]of[['/ppt','page'],['/api/harless/ppt','task'],['/api/harless/ppt/upload','upload'],['/api/harless/ppt/download','download']])ctx.effect(()=>ctx.webServer.register({kind:'exact',path,handler:handler(kind)}),'research-ppt-'+kind);
  ctx.effect(()=>()=>{for(const child of running.values())stop(child);},'research-ppt-cleanup');
  return { command, view: (id:string)=>view(get(id)), busy:()=>Boolean(active),
    async importFile(name:string,stream:AsyncIterable<Uint8Array>,expectedBytes:number) {
      if(receipts.size>=32||[...receipts.values()].reduce((n,r)=>n+r.bytes,0)+expectedBytes>512*1024*1024)throw Error('上传留存额度已满，请管理员归档');
      if(!name||name.length>255||/[\x00-\x1f\\/]/.test(name)||!['.pdf','.pptx'].includes(extname(name).toLowerCase()))throw Error('只接收PDF/PPTX');
      if(!Number.isSafeInteger(expectedBytes)||expectedBytes<=0||expectedBytes>MAX_FILE)throw Error('单文件超过100 MiB或为空');
      const id=randomUUID(),path=join(directory,id+extname(name).toLowerCase());let n=0;const h=createHash('sha256');writeFileSync(path,'',{mode:0o600});
      try{for await(const chunk of stream){n+=chunk.length;if(n>MAX_FILE||n>expectedBytes)throw Error('上传大小变化');h.update(chunk);writeFileSync(path,chunk,{flag:'a'});}if(n!==expectedBytes)throw Error('上传大小变化');}
      catch(e){unlinkSync(path);throw e;}
      const receipt={id,name,path,bytes:n,sha256:h.digest('hex')};receipts.set(id,receipt);persist();return receipt;
    } };
}
