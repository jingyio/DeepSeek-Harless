/** Generic operation graph retrieval; scene contracts own scope and authority. */
import {readFileSync,appendFileSync,lstatSync,existsSync} from 'node:fs';
import {resolve,dirname,sep} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {isAgentLoopRequest} from '@deepseek-ai/dsh-llm';
import {digest,syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {validateOperationPolicy,createOperationController} from '../motif_core/operation_graph_policy.ts';
import {OperationJob} from './operation_job.ts';
export const name='sss-operation-motif';export const inject=['agents','llm'];
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const raw=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
const read=(p:string)=>JSON.parse(readFileSync(p,'utf8'));
function privatePath(p:string){
 const f=resolve(p),base=resolve(root,'.local');if(!f.startsWith(base+sep))throw Error('private operation binding required');
 for(let q=f;q.startsWith(base+sep);q=dirname(q))if(existsSync(q)&&lstatSync(q).isSymbolicLink())throw Error('operation symlink refused');return f;
}
function object(base:string,p:string){if(typeof p!=='string'||p.startsWith('/')||p.includes('\\')||p.split('/').some(v=>!v||v==='.'||v==='..'))throw Error('invalid immutable object');return privatePath(resolve(base,p));}
export function loadOperationEntries(b:any){
 const file=privatePath(b.registry_file);if(raw(file)!==b.registry_sha256)throw Error('library snapshot changed');
 const state=read(file);if(state.registry_digest!==digest(Object.fromEntries(Object.entries(state).filter(([k])=>k!=='registry_digest'))))throw Error('library digest changed');
 const entries=[];
 for(const e of state.entries){
  if(e.kind!=='operation_graph'||!(e.state==='active'||b.role==='certify'&&e.state==='candidate'))continue;
  if(Object.entries(e.runtime_source).some(([n,h])=>raw(resolve(root,n))!==h))continue;
  const payload=object(b.registry_root,e.payload);if(raw(payload)!==e.sha256)throw Error('operation payload mutated');
  const p=validateOperationPolicy(read(payload));
  if(e.certificate){
   const cfile=object(b.registry_root,e.certificate.file);if(raw(cfile)!==e.certificate.sha256)throw Error('operation certificate mutated');const c=read(cfile);
   if(c.status!==(p.format==='sss-operation-graph-v2'?'certified_motif_v2':'certified_motif_v1')||c.policy_digest!==p.policy_digest||c.payload_sha256!==e.sha256||c.holdout_used!==false
    ||raw(privatePath(c.candidate_lock_file))!==c.candidate_lock_sha256)throw Error('uncertified operation');
   for(const review of [c.native_review,...c.reviews])if(raw(privatePath(review.record_file))!==review.record_sha256)throw Error('operation proof mutated');
  }else if(b.role!=='certify')throw Error('independent operation certificate required');
  entries.push({...e,policy:p});
 }return entries;
}
export function createOperationRuntime(b:any,audit:(r:any)=>void){
 const entries=loadOperationEntries(b);let controller:any=null,choice:any=null,halted=false;
 audit({kind:'experience_runtime_ready',entries:entries.length,catalog_sha256:digest(b.catalog),scope_sha256:digest(b.scope)});
 const fail=(reason:string)=>{halted=true;controller?.fail(reason);audit({kind:'experience_deferred',reason,entry_id:choice?.entry_id??null});};
 return {get halted(){return halted;},fail,
  observe(exec:any,result:any){
   if(halted)return;
   if(controller?.done){controller=null;choice=null;}
   if(!controller){
    const candidates=entries.filter(e=>e.policy.artifact.nodes[0].tool===exec.name&&e.policy.execution_version_sha256===b.scope.execution_version
     &&Object.entries({...e.policy.artifact.tool_contracts,...e.policy.artifact.interleaving_contracts}).every(([n,t]:any)=>digest(b.catalog[n])===digest(t)
       &&Object.entries(t.contract.scope_requirements??{}).every(([k,v])=>b.scope[k]===v)));
    if(!candidates.length)return;
    choice=candidates.sort((a,b)=>b.policy.artifact.nodes.length-a.policy.artifact.nodes.length||b.activated_generation-a.activated_generation)[0];
    controller=createOperationController(choice.policy,b.scope,audit);
    audit({kind:'experience_selected',entry_id:choice.entry_id,experience_kind:'operation_graph',activated_generation:choice.activated_generation});
   }
   controller.observe(exec,result);if(controller.halted)fail('operation_guard_failed');
  },propose(tools:any[],messages:any[]){
   const ids=new Set<string>();
   for(const m of messages)if(m.role==='assistant'&&m.source?.kind==='model')for(const c of m.content??[])if(c.type==='tool-call')ids.add(c.id);
   return controller&&!halted?controller.propose(tools,randomUUID,ids):[];
  }
 };
}
export function apply(ctx:any){
 const file=process.env.SSS_OPERATION_BINDING;if(!file)return;const b=read(privatePath(file));
 if(raw(privatePath(b.task_file))!==b.task_sha256)throw Error('operation task changed');
 for(const [n,h] of Object.entries(b.runtime_source))if(raw(resolve(root,n))!==h)throw Error('operation runtime changed');
 const audit=(v:any)=>appendFileSync(privatePath(b.audit_file),JSON.stringify({...v,session_id:b.session_id})+'\n',{mode:0o600});
 const c=createOperationRuntime(b,audit);let live=false,envelope:string|null=null;
 ctx.on('agent/created',({agent}:any)=>{if(live||agent.session.id!==b.session_id){c.fail('operation_session_changed');return;}live=true;agent.ctx.on('tools/result',c.observe);});
 ctx.on('agent/disposed',()=>{live=false;});
 ctx.on('llm/stream',(o:any,next:()=>any)=>{
  if(!live||o.sessionId!==b.session_id||!isAgentLoopRequest(o)||c.halted)return next();
  if(o.messages.some((m:any)=>m.source?.kind==='task-acceptance-repair')){c.fail('repair_requires_ordinary_harness');return next();}
  const users=o.messages.filter((m:any)=>m.role==='user'&&m.source?.kind==='user');const now=digest(users.map((m:any)=>({id:m.id,content:m.content})));
  const match=users.filter((m:any)=>m.content?.length===1&&m.content[0].type==='text'&&createHash('sha256').update(m.content[0].text).digest('hex')===b.prompt_sha256);
  if(match.length!==1||envelope!==null&&envelope!==now){c.fail('operation_user_envelope_changed');return next();}
  envelope=now;const calls=c.propose(o.tools??[],o.messages);
  if(calls.length&&b.job_file)new OperationJob(root,b.job_file).apply('motif-step');
  return calls.length?syntheticToolStreamBatch(calls):next();
 },{global:true});
}
