/** Private offline sandbox certification, never executes source on the host. */
import {readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {scriptArgv} from '../src/adapters/script_motif_shell.ts';
import {bindScript,scriptCommand,programIdentity,scriptCodeLocks} from '../src/adapters/script_motif_runtime.ts';
import {runCertifiedScript} from './run-certified-script.mjs';
import {digest} from '../src/motif_core/online_skill_runtime.mjs';
const root=fileURLToPath(new URL('../',import.meta.url));
const sha=b=>createHash('sha256').update(b).digest('hex');
export function sandboxRun(workspace,command,cwd='/work'){
 const layout={work:workspace,scratch:join(workspace,'code'),inputs:join(workspace,'inputs'),outputs:join(workspace,'outputs/code'),temp:join(workspace,'command-tmp')};
 const argv=scriptArgv(layout,command,cwd,true,{network:'none',ephemeralTemp:true});
 const run=spawnSync(argv[0],argv.slice(1),{encoding:'utf8',timeout:30000,maxBuffer:256000});
 if(run.error||run.status!==0)throw Error('sandbox_replay_failed',{cause:{status:run.status,signal:run.signal,stderr:run.stderr}});
 return run.stdout;
}
function certify(rows){
 const held=rows[0],rejected=[],programs=[],seen=new Set();
 for(const task of rows.slice(1))for(const p of task.candidates){
  if(seen.has(p.id))continue;seen.add(p.id);
  try{
   if(p.argv_contract){
    const variants=rows.flatMap(t=>[...t.argument_witnesses??[],...t.candidates.filter(c=>c.id===p.id).map(c=>({source_sha256:c.source_sha256,argv:c.observed_argv,call_id:c.witness.call_id,stdout:c.witness.stdout}))])
      .filter(v=>v.source_sha256===p.source_sha256&&digest(v.argv)!==digest(p.observed_argv));
    if(!variants.length)throw Error('distinct_real_argument_invocation_required');
    const results=[];
    for(const args of [p.observed_argv,variants[0].argv]){
     const job={workspace:task.workspace,program:p,paths:[],versions:[],nonce:'certification',argv:args};
     const result=runCertifiedScript(job);
     const original=runCertifiedScript({...job,program:{...p,template:p.source}});
     if(result.output!==original.output)throw Error('argv_parameterization_changed_behavior');
     if(!results.length&&!p.witness.stdout.includes(original.output.trim()))throw Error('historical_stdout_not_reproduced');
     results.push(result);
    }
    if(results[0].output===results[1].output)throw Error('argument_dependency_not_demonstrated');
    const {source,witness,original_paths,observed_argv,...program}=p;
    programs.push({...program,certification:{passed:true,cases:2,source_equivalent:true,program_sha256:digest(programIdentity(p)),
     source_task_id:task.task_id,source_call_id:witness.call_id,events_sha256:witness.events_sha256,
     argument_witness_call:variants[0].call_id,scope:'distinct_real_argument_invocations_not_independent_task_quality',
     outputs:results.map(r=>r.output_sha256)}});
    continue;
   }
   const own=bindScript(p,task.workspace),other=bindScript(p,held.workspace);
   const ownText=own.map(b=>b.data.toString('utf8')).join('\n'),heldText=other.map(b=>b.data.toString('utf8')).join('\n');
   // A literal copied from this task's data is not an input parameter. Retain
   // such programs as rejected evidence instead of silently caching old keys.
   if((p.literal_selectors??[]).some(s=>ownText.includes(s)&&!heldText.includes(s)))throw Error('task_specific_literal_requires_binding');
   if(digest(own.map(b=>b.sha256))===digest(other.map(b=>b.sha256)))throw Error('distinct_heldout_input_required');
   if(p.original_paths.some((name,i)=>p.witness.files[name].sha256!==own[i].sha256))throw Error('source_binding_changed');
   const original=sandboxRun(task.workspace,"python3 - <<'SOURCE_EQUIVALENCE_BOUNDARY'\n"+p.source+'\nSOURCE_EQUIVALENCE_BOUNDARY',p.witness.cwd);
   // Bash adds execution metadata around stdout; require the complete actual
   // stdout as a contiguous exact block, never a hand-picked output field.
   if(!original.trim()||!p.witness.stdout.includes(original.trim()))throw Error('historical_stdout_not_reproduced');
   const outputs=[];const cases=[];
   for(const [role,row,bound] of [['source',task,own],['heldout',held,other]]){
    const cmd=scriptCommand(p,bound.map(b=>b.path),bound.map(b=>b.sha256),'certification');
    const first=JSON.parse(sandboxRun(row.workspace,cmd)),second=JSON.parse(sandboxRun(row.workspace,cmd));
    if(Buffer.byteLength(first.output)>16000)throw Error('script_output_exceeds_context_budget');
    if(first.output!==second.output||sha(first.output)!==first.output_sha256)throw Error('nondeterministic_script');
    if(role==='source'&&first.output!==original)throw Error('parameterization_changed_behavior');
    outputs.push(first.output);cases.push({role,task_id:row.task_id,input_sha256:bound.map(b=>b.sha256),output_sha256:first.output_sha256});
   }
   if(outputs[0]===outputs[1])throw Error('input_dependency_not_demonstrated');
   const {source,witness,original_paths,...program}=p;
   const programSha=digest(programIdentity(p));
   programs.push({...program,certification:{passed:true,cases:cases.length,source_equivalent:true,program_sha256:programSha,
     witnesses:cases,source_task_id:task.task_id,source_call_id:witness.call_id,events_sha256:witness.events_sha256,
     scope:'deterministic_source_equivalence_on_distinct_inputs_not_semantic_quality_proof'}});
  }catch(error){rejected.push({id:p.id,reason:error.message});}
 }
 const locks=Object.fromEntries(scriptCodeLocks.map(p=>[p,sha(readFileSync(join(root,p)))]));
 const body={version:1,kind:'sandboxed_script_motif_library',programs,code_locks:locks,compilation_model_requests:0,heldout_task_id:held.task_id};
 return {library:{...body,digest:digest(body)},report:{published:programs.length,rejected,scope:'real_trace_replay_certification'}};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const rows=JSON.parse(readFileSync(process.argv[2],'utf8'));const {library,report}=certify(rows);
 for(const [name,value] of [['library.json',library],['certification.json',report]])writeFileSync(join(process.argv[3],name),JSON.stringify(value,null,2)+'\n',{mode:0o600});
 console.log(JSON.stringify(report));
}
