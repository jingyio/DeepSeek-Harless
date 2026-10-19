/** Task lifecycle notification only; Python seals provenance and learns off the Agent loop. */
import {readFileSync,writeFileSync,mkdirSync,appendFileSync,lstatSync,existsSync} from 'node:fs';
import {resolve,dirname,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest} from '../motif_core/online_skill_runtime.mjs';
export const name='sss-continuous-rsi-events';
export const inject=['agents','llm'];
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const raw=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
function privatePath(p:string){
 const file=resolve(p),base=resolve(root,'.local');
 if(!file.startsWith(base+sep))throw Error('RSI event files must be private');
 for(let q=file;q.startsWith(base+sep);q=dirname(q))if(existsSync(q)&&lstatSync(q).isSymbolicLink())throw Error('RSI symlink refused');
 return file;
}
export function createTaskObserver(binding:any,emit:(v:any)=>void){
 let session:string|null=null,results=0,disposed=false,schemas:any=null;
 const end=(event:string)=>{
  if(disposed||session===null)return;disposed=true;
  emit({kind:'task_lifecycle_end',schema_version:1,format:'sss-rsi-task-event-v1',session_id:session,
    task_sha256:binding.task_sha256,binding_sha256:binding.binding_sha256,tool_results:results,
    runtime_schema_sha256:schemas===null?null:digest(schemas),event});
 };
 return {
  created(id:string){if(session!==null||id!==binding.session_id)throw Error('RSI task/session binding changed');session=id;},
  result(){results++;},
  tools(id:string,tools:any[]){
   if(id!==session||disposed)return;
   const rows=tools.filter(t=>binding.allowed_tools.includes(t.name)).map(t=>({name:t.name,parameters:t.parameters}));
   if(rows.length!==binding.allowed_tools.length||new Set(rows.map(t=>t.name)).size!==rows.length)throw Error('RSI actual tool surface changed');
   if(schemas!==null&&digest(rows)!==digest(schemas))throw Error('RSI schema changed within task');
   if(schemas===null){schemas=rows;emit({kind:'runtime_schema',schemas:rows});}
  },
  disposed(){end('agent_disposed');},
  taskFinalized(){end('web_task_terminal');}
 };
}
export function apply(ctx:any){
 const file=process.env.SSS_CONTINUOUS_RSI_BINDING;if(!file)return;
 const p=privatePath(file),binding=JSON.parse(readFileSync(p,'utf8'));
 if(raw(privatePath(binding.task_file))!==binding.task_sha256||raw(fileURLToPath(import.meta.url))!==binding.observer_sha256)throw Error('RSI task/runtime changed');
 binding.binding_sha256=raw(p);
 const eventFile=privatePath(binding.event_file),schemaFile=privatePath(binding.schema_file);
 mkdirSync(dirname(eventFile),{recursive:true,mode:0o700});
 const observer=createTaskObserver(binding,row=>{
  if(row.kind==='runtime_schema'){
   if(existsSync(schemaFile)){if(digest(JSON.parse(readFileSync(schemaFile,'utf8')))!==digest(row.schemas))throw Error('resumed task schema changed');}
   else writeFileSync(schemaFile,JSON.stringify(row.schemas),{flag:'wx',mode:0o600});return;
  }
  appendFileSync(eventFile,JSON.stringify(row)+'\n',{mode:0o600});
 });
 ctx.on('agent/created',({agent}:any)=>{
  observer.created(agent.session.id);agent.ctx.on('tools/result',()=>observer.result());
 });
 ctx.on('agent/disposed',()=>observer.disposed());
 ctx.on('llm/stream',(options:any,next:()=>any)=>{
  if(isAgentLoopRequest(options))observer.tools(options.sessionId,options.tools??[]);
  return next();
 },{global:true});
}
