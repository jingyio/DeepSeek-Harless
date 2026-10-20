/** Add recovery/structural-step bookkeeping to the original immutable task ledger. */
import {FileJob} from './file_workflow_job.ts';
import {readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
export class OperationJob extends FileJob {
 apply(command:string,arg:any={}){
  if(!['recover','motif-step','provider-retry','owner'].includes(command))return super.apply(command,arg);
  let s=this.load();this.validateBinding(s);
  if(command==='recover'){
   if(!['running','paused'].includes(s.status)||arg.execution_version_sha256!==s.execution_version_sha256)throw Error('original task/version is not recoverable');
   if(s.owner_pid&&s.owner_pid!==arg.owner_pid){try{process.kill(s.owner_pid,0);throw Error('original task owner is still active');}catch(e:any){if(e.code!=='ESRCH')throw e;}}
   const recovered=[];
   for(const [id,p] of Object.entries(s.pending) as any){super.apply('settle',{request_id:Number(id),model:p.model,observed_usd:null});recovered.push({request_id:Number(id),model:p.model,reserved_upper_usd:p.amount/1e9});}
   s=this.load();s.status='running';s.owner_pid=arg.owner_pid;
   return {recovered,state:this.commit(s,'recovered_without_reset',{recovered})};
  }
  if(s.status!=='running')throw Error('original task inactive');
  if(command==='owner')s.owner_pid=arg.pid;
  if(command==='provider-retry'){if((s.provider_retries??0)>=2)return {admitted:false,state:s};s.provider_retries=(s.provider_retries??0)+1;}
  if(command==='motif-step'){if(s.steps>=s.limits.max_steps)throw Error('original task step limit exhausted');s.steps++;}
  return {admitted:true,state:this.commit(s,command,arg)};
 }
}
const entry=fileURLToPath(import.meta.url);
if(process.argv[1]&&resolve(process.argv[1])===entry){
 try{const v=new OperationJob(resolve(dirname(entry),'../..'),process.argv[2]).apply(process.argv[3],JSON.parse(readFileSync(0,'utf8')||'{}'));process.stdout.write(JSON.stringify(v)+'\n');}
 catch(e:any){process.stdout.write(JSON.stringify({error:e.message})+'\n');process.exitCode=2;}
}
