/** Frozen experimental perturbations only; never loaded by the default SDK/Web. */
import {existsSync,readFileSync,writeFileSync,lstatSync} from 'node:fs';
import {resolve,join,sep} from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {observation} from '../motif_core/online_skill_runtime.mjs';
export const name='sss-workflow-experiment';export const inject=['agents','llm'];
const root=resolve(fileURLToPath(new URL('../../',import.meta.url)));
const sha=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
export function experimentBoundary(control:any,spec:any){
 const work=resolve(spec.workspace),marker=resolve(control.marker),privateRoot=resolve(root,'.local')+sep;
 if(!work.startsWith(resolve(root,'testpdf/file-management-experiment')+sep)||!existsSync(join(work,'.experiment-copy'))
  ||!marker.startsWith(privateRoot)||!['none','version','cold_success','cold_crash'].includes(control.mode))throw Error('invalid frozen experiment boundary');
 const prior=()=>existsSync(marker)?JSON.parse(readFileSync(marker,'utf8')):null;
 const save=(v:any)=>writeFileSync(marker,JSON.stringify(v,null,2),{mode:0o600});
 return {
  observe(exec:any,result:any){
   if(prior())return;const out=observation(result,exec.name),name=exec.name.replace('mcp__file_management__','');
   if(control.mode==='version'){
    const trigger=control.workflow_id==='FM38'?name==='execute_plan'&&!out:
     name==='preview_actions'&&out?.status==='validated_copy_plan'&&(control.workflow_id!=='FM17'||out.actions?.some((a:any)=>a.destination.startsWith('recovery-drill/')));
    if(!trigger)return;
    if(control.workflow_id==='FM38'){
     const pid=exec.arguments?.plan_id;
     if(typeof pid!=='string'||!/^result-[a-f0-9]{32}$/.test(pid))return;
     const journal=resolve(process.env.FM_OUTPUT!,'journals',pid+'.json');
     if(!existsSync(journal)||!['executing','partial_failure'].includes(JSON.parse(readFileSync(journal,'utf8')).status))return;
    }
    const target=resolve(work,control.target);
    if(!target.startsWith(work+sep)||lstatSync(target).isSymbolicLink()||sha(target)!==control.before_sha256)throw Error('frozen version perturbation preimage changed');
    writeFileSync(target,control.replacement,'utf8');save({mode:'version',target:control.target,before_sha256:control.before_sha256,
      after_sha256:sha(target),boundary_call_id:exec.callId,interrupted:false});
   }else if(name==='execute_plan'&&((control.mode==='cold_success'&&out?.status==='executed_verified')||(control.mode==='cold_crash'&&!out))){
    const pid=exec.arguments?.plan_id;
    if(typeof pid!=='string'||!/^result-[a-f0-9]{32}$/.test(pid))return;
    const journal=resolve(process.env.FM_OUTPUT!,'journals',pid+'.json');
    if(!existsSync(journal))return;
    const j=JSON.parse(readFileSync(journal,'utf8'));
    if(control.mode==='cold_crash'&&!['executing','partial_failure'].includes(j.status))return;
    save({mode:control.mode,plan_id:pid,authorization_id:exec.arguments.authorization_id,boundary_call_id:exec.callId,
      actual_receipt:out,journal_sha256:sha(journal),interrupted:false});
   }
  },
  interrupt(){const m=prior();if(m&&!m.interrupted){save({...m,interrupted:true});throw Error('FROZEN_WORKFLOW_BOUNDARY_'+m.mode);}},
 };
}
export function apply(ctx:any){
 const path=process.env.FM_WORKFLOW_CONTROL;if(!path)return;
 if(!resolve(path).startsWith(resolve(root,'.local')+sep)||lstatSync(path).isSymbolicLink())throw Error('private frozen control required');
 const spec=JSON.parse(readFileSync(process.env.FM_TASK_FILE!,'utf8')),control=JSON.parse(readFileSync(path,'utf8'));
 const boundary=experimentBoundary(control,spec);
 ctx.on('agent/created',({agent}:any)=>agent.ctx.on('tools/result',boundary.observe));
 ctx.on('llm/stream',(_options:any,next:()=>any)=>{boundary.interrupt();return next();},{global:true});
}
