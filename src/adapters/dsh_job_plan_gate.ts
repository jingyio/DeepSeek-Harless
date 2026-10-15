/** Explicit certified plan activation on an existing durable job. No new permission or budget. */
import {createHash} from 'node:crypto';
import {readFileSync,lstatSync,existsSync} from 'node:fs';
import {resolve,dirname,sep} from 'node:path';
import {FileJob,digest} from './file_workflow_job.ts';

const sha=(p:string)=>createHash('sha256').update(readFileSync(p)).digest('hex');
function privateFile(root:string,path:string){
  const p=resolve(path),base=resolve(root,'.local')+sep;
  if(!p.startsWith(base)||!lstatSync(p).isFile())throw Error('composition artifact must be a private regular file');
  for(let q=p;q!==resolve(root);q=dirname(q))if(existsSync(q)&&lstatSync(q).isSymbolicLink())throw Error('composition symlink refused');
  return p;
}
export function createJobPlanGuard(root:string,bindingPath:string,policyPath:string,task:any,audit:(r:any)=>void){
  root=resolve(root);bindingPath=privateFile(root,bindingPath);policyPath=privateFile(root,policyPath);
  const binding=JSON.parse(readFileSync(bindingPath,'utf8')),bindingSha=sha(bindingPath);
  if(binding.format!=='sss-durable-plan-binding-v1'||binding.schema_version!==1
    ||typeof binding.job_file!=='string'||!binding.runtime_source||Object.keys(binding.runtime_source).sort().join(',')!==
      'src/adapters/dsh_entry_motif.ts,src/adapters/dsh_job_plan_gate.ts,src/motif_core/authorized_plan_policy.ts,src/motif_core/online_skill_runtime.mjs')throw Error('invalid durable plan binding');
  const job=new FileJob(root,privateFile(root,binding.job_file));
  const check=()=>{
    if(sha(bindingPath)!==bindingSha)throw Error('composition_binding_changed');
    const state=job.load();job.validateBinding(state);
    if(state.status!=='running')throw Error('job_inactive_'+state.status);
    if(state.task_sha256!==binding.task_sha256||state.execution_version_sha256!==binding.service_execution_version_sha256
      ||digest(state.limits)!==binding.limits_sha256||state.delivery_root!==binding.delivery_root)throw Error('original_job_binding_changed');
    const input=JSON.parse(readFileSync(state.task_file,'utf8'));
    if(task.input_version!==digest(input)||task.task_id!==input.task_id||task.grant_sha256!==digest(input.write_grant)
      ||digest(task.grant)!==digest(input.write_grant)||task.snapshot_sha256!==digest(input.initial_snapshot))throw Error('original_task_or_permission_changed');
    const lockPath=privateFile(root,binding.library_lock_file);
    if(sha(lockPath)!==binding.library_lock_sha256)throw Error('library_lock_changed');
    const lock=JSON.parse(readFileSync(lockPath,'utf8')),group=lock.groups?.recovery15;
    const record=lock.artifacts?.find((r:any)=>r.kind==='plan'&&r.group==='recovery15');
    if(!group||!record||resolve(dirname(lockPath),'libraries',record.path)!==policyPath||sha(policyPath)!==record.sha256
      ||record.sha256!==binding.policy_sha256||group.execution_version_sha256!==state.execution_version_sha256
      ||group.plan_component_version_sha256!==task.execution_version_sha256)throw Error('library_service_or_component_version_changed');
    for(const [path,hash] of Object.entries({...group.dependencies,...binding.runtime_source})){
      const full=resolve(root,path);if(!full.startsWith(root+sep)||sha(full)!==hash)throw Error('execution_dependency_changed:'+path);
    }
    if(state.repairs>0)throw Error('acceptance_repair_requires_ordinary_harness');
    if(state.spent_units>=Math.floor(state.limits.budget_usd*1e9)||state.requests>=state.limits.max_requests
      ||state.steps>=state.limits.max_steps||Object.keys(state.pending).length)throw Error('original_budget_or_request_limit');
    return state;
  };
  const disable=(reason:string)=>{
    const state=job.load();
    if(state.status==='running'&&!state.motif_disabled&&state.motif_binding_sha256===bindingSha){
      state.motif_disabled=true;job.commit(state,'motif_disabled',{reason,binding_sha256:bindingSha});
    }
    audit({kind:'durable_plan_deferred',reason,binding_sha256:bindingSha});
  };
  return {
    validate(){return check();},
    activate(){
      try{
        const state=check();
        if(state.motif_binding_sha256){
          if(state.motif_binding_sha256!==bindingSha||state.motif_disabled)throw Error('durable_motif_disabled_or_binding_changed');
        }else{
          if(state.requests||state.steps||state.checks)throw Error('activation_requires_unstarted_job');
          state.motif_disabled=false;state.motif_binding_sha256=bindingSha;
          job.commit(state,'motif_activated',{binding_sha256:bindingSha,policy_sha256:binding.policy_sha256,
            library_lock_sha256:binding.library_lock_sha256,limits_sha256:binding.limits_sha256});
        }
        audit({kind:'durable_plan_active',binding_sha256:bindingSha});return true;
      }catch(e:any){disable(e.message);return false;}
    },
    allow(){
      try{const state=check();if(state.motif_disabled||state.motif_binding_sha256!==bindingSha)throw Error('durable_motif_disabled');return true;}
      catch(e:any){disable(e.message);return false;}
    },disable,
  };
}
