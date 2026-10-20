/** An account-local meter around the same installed provider adapter. */
import {spawn} from 'node:child_process';
import {mkdirSync,writeFileSync,renameSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {WebDeepSeekAdapter} from './harless_reasoning.ts';

export class ManagementRoutedAdapter extends WebDeepSeekAdapter {
  private base: any; private route: (session: string)=>string|undefined;
  private delegates=new Map<string,WebDeepSeekAdapter>();
  constructor(config:any,models:any[],route:(session:string)=>string|undefined){super(config,models);this.base=config;this.route=route;}
  private select(request:any){
    const endpoint=this.route(request.sessionId);if(!endpoint)return;
    if(!this.delegates.has(endpoint))this.delegates.set(endpoint,new WebDeepSeekAdapter({...this.base,options:()=>({...this.base.options(),baseURL:endpoint})}));
    return this.delegates.get(endpoint);
  }
  override async prepareCall(...args:Parameters<WebDeepSeekAdapter['prepareCall']>){
    const prepared=await super.prepareCall(...args);
    return {...prepared,stream:(request:any)=>this.select(request)?.stream(request)??prepared.stream(request)};
  }
  override stream(request:any){return this.select(request)?.stream(request)??super.stream(request);}
}

export function startManagementGate(config:any,upstream:string,broker:boolean){
  const routes=join(config.private_root,'model-routes');mkdirSync(routes,{recursive:true,mode:0o700});
  const child=spawn(config.python??'python3',[fileURLToPath(new URL('./management_model_gate.py',import.meta.url))],
    {stdio:['pipe','pipe','pipe'],env:{...process.env,HARLESS_MANAGEMENT_PRIVATE_ROOT:config.private_root,PYTHONUNBUFFERED:'1'}});
  let stderr='';child.stderr.on('data',chunk=>{stderr=(stderr+chunk).slice(-2000);});
  const ready=new Promise<string>((resolve,reject)=>{
    let text='';const timer=setTimeout(()=>{child.kill();reject(Error('management budget start timed out'));},30000);
    child.once('error',error=>{clearTimeout(timer);reject(error);});
    child.once('exit',()=>{clearTimeout(timer);reject(Error('management budget process exited: '+stderr));});
    child.stdout.on('data',chunk=>{text+=chunk;if(text.includes('\n')){clearTimeout(timer);try{resolve(JSON.parse(text.split('\n')[0]).endpoint);}catch(error){reject(error);}}});
  });
  child.stdin.end(JSON.stringify({routes,upstream,broker,owner_pid:process.pid})+'\n');
  return {ready,close:()=>child.kill(),bind(task:any){
    const file=join(routes,task.request.session_id+'.json'),value={task_id:task.request.task_id,budget_session_id:task.budget_session_id,
      job_file:task.management.binding.job_file,ledger_file:join(task.output,'ledger.jsonl')};
    writeFileSync(file+'.tmp',JSON.stringify(value),{mode:0o600});renameSync(file+'.tmp',file);
  }};
}
