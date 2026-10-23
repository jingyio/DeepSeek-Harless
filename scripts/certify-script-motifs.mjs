/** Private offline sandbox certification, never executes source on the host. */
import {readFileSync,writeFileSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {scriptArgv} from '../src/adapters/script_motif_shell.ts';
import {bindScript,scriptCommand,programIdentity,scriptCodeLocks,fixedInput,compatibleInput,witnessedOutputSchema,decodeScriptReceipt} from '../src/adapters/script_motif_runtime.ts';
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
  if(seen.has(p.id))continue;
  const sourceWorkspace=p.witness.workspace??task.workspace;
  try{
   if(p.argv_contract){
    const variants=rows.flatMap(t=>[...t.argument_witnesses??[],...t.candidates.filter(c=>c.id===p.id).map(c=>({source_sha256:c.source_sha256,argv:c.observed_argv,call_id:c.witness.call_id,stdout:c.witness.stdout}))])
      .filter(v=>v.source_sha256===p.source_sha256&&digest(v.argv)!==digest(p.observed_argv));
    if(!variants.length)throw Error('distinct_real_argument_invocation_required');
    const results=[];
    for(const args of [p.observed_argv,variants[0].argv]){
     const job={workspace:sourceWorkspace,program:p,paths:[],versions:[],nonce:'certification',argv:args};
     const result=runCertifiedScript(job);
     const original=runCertifiedScript({...job,program:{...p,template:p.source}});
     if(result.output!==original.output)throw Error('argv_parameterization_changed_behavior');
     if(!results.length&&!p.witness.stdout.includes(original.output.trim()))throw Error('historical_stdout_not_reproduced');
     results.push(result);
    }
    if(results[0].output===results[1].output)throw Error('argument_dependency_not_demonstrated');
    const {source,witness,original_paths,observed_argv,...program}=p;
    seen.add(p.id);programs.push({...program,certification:{passed:true,cases:2,source_equivalent:true,program_sha256:digest(programIdentity(p)),
     source_task_id:task.task_id,source_call_id:witness.call_id,events_sha256:witness.events_sha256,
     argument_witness_call:variants[0].call_id,scope:'distinct_real_argument_invocations_not_independent_task_quality',
     outputs:results.map(r=>r.output_sha256)}});
    continue;
   }
   // Source inputs come from the witnessed literal bindings, not a suffix
   // search over the final workspace (which can contain other valid files).
   const own=p.original_paths.map((name,i)=>{
    const w=p.witness.files[name],host=resolve(sourceWorkspace,w.relative),data=fixedInput(sourceWorkspace,host);
    if(sha(data)!==w.sha256||!compatibleInput(p.inputs[i],host,data))throw Error('source_binding_changed');
    const virtual=w.relative.startsWith('inputs/')?'/work/'+w.relative:w.relative.startsWith('outputs/code/')?'/work/outputs/'+w.relative.slice(13):'/work/'+w.relative.slice(5);
    return {host,path:virtual,data,sha256:w.sha256};
   });
   let other,heldWorkspace,lastBindingError;
   for(const workspace of (held.replay_workspaces?.length?held.replay_workspaces:[held.workspace]))try{
    const candidate=bindScript(p,workspace);
    if(digest(own.map(b=>b.sha256))===digest(candidate.map(b=>b.sha256)))continue;
    other=candidate;heldWorkspace=workspace;break;
   }catch(error){lastBindingError=error;}
   if(!other)throw Error(lastBindingError?.message??'distinct_heldout_input_required');
   const ownText=own.map(b=>b.data.toString('utf8')).join('\n'),heldText=other.map(b=>b.data.toString('utf8')).join('\n');
   // A literal copied from this task's data is not an input parameter. Retain
   // such programs as rejected evidence instead of silently caching old keys.
   if((p.literal_selectors??[]).some(s=>ownText.includes(s)&&!heldText.includes(s)))throw Error('task_specific_literal_requires_binding');
   if(digest(own.map(b=>b.sha256))===digest(other.map(b=>b.sha256)))throw Error('distinct_heldout_input_required');
   if(p.original_paths.some((name,i)=>p.witness.files[name].sha256!==own[i].sha256))throw Error('source_binding_changed');
   const original=sandboxRun(sourceWorkspace,"python3 - <<'SOURCE_EQUIVALENCE_BOUNDARY'\n"+(p.expression_witness?.prefix_source??p.source)+'\nSOURCE_EQUIVALENCE_BOUNDARY',p.witness.cwd);
   // Bash adds execution metadata around stdout; require the complete actual
   // stdout as a contiguous exact block, never a hand-picked output field.
   if(!original.trim()||!p.expression_witness&&!p.witness.stdout.includes(original.trim()))throw Error('historical_stdout_not_reproduced');
   const outputs=[];const cases=[];
   for(const [role,row,bound] of [['source',{...task,workspace:sourceWorkspace},own],['heldout',{...held,workspace:heldWorkspace},other]]){
    const cmd=scriptCommand(p,bound.map(b=>b.path),bound.map(b=>b.sha256),'certification');
    const first=JSON.parse(sandboxRun(row.workspace,cmd)),second=JSON.parse(sandboxRun(row.workspace,cmd));
    const compact=decodeScriptReceipt(JSON.parse(sandboxRun(row.workspace,scriptCommand(p,bound.map(b=>b.path),bound.map(b=>b.sha256),'certification',{compactReceipt:true}))));
    if(digest(compact)!==digest(first))throw Error('compact_receipt_changed_evidence');
    if(Buffer.byteLength(first.output)>16000)throw Error('script_output_exceeds_context_budget');
    if(first.output!==second.output||sha(first.output)!==first.output_sha256)throw Error('nondeterministic_script');
    if(role==='source'&&first.output!==original)throw Error('parameterization_changed_behavior');
    if(p.expression_witness){
     const prefix=p.expression_witness.prefix_program,prefixBound=bindScript(prefix,row.workspace);
     const reference=JSON.parse(sandboxRun(row.workspace,scriptCommand(prefix,prefixBound.map(b=>b.path),prefixBound.map(b=>b.sha256),'expression-reference')));
     if(first.output!==reference.output)throw Error('dependency_slice_changed_behavior');
    }
    outputs.push(first.output);cases.push({role,task_id:row.task_id,input_sha256:bound.map(b=>b.sha256),output_sha256:first.output_sha256});
   }
   if(outputs[0]===outputs[1])throw Error('input_dependency_not_demonstrated');
   const {source,witness,original_paths,expression_witness,...program}=p;
   const programSha=digest(programIdentity(p));
   seen.add(p.id);programs.push({...program,certification:{passed:true,cases:cases.length,source_equivalent:true,program_sha256:programSha,
     source_bytes:Buffer.byteLength(p.source),output_bytes:outputs.map(x=>Buffer.byteLength(x)),
     witnesses:cases,source_task_id:task.task_id,source_call_id:witness.call_id,events_sha256:witness.events_sha256,
     ...(expression_witness?{expression:{target:expression_witness.target,lines:expression_witness.lines,source_sha256:expression_witness.original_source_sha256}}:{}),
     ...(witnessedOutputSchema(outputs)?{output_schema:witnessedOutputSchema(outputs)}:{}),
     receipt_protocol:'bounded_zlib_v1',
     scope:expression_witness?'source_prefix_and_dependency_slice_equivalence_on_distinct_inputs_not_historical_stdout_or_semantic_quality':'deterministic_source_equivalence_on_distinct_inputs_not_semantic_quality_proof'}});
  }catch(error){rejected.push({id:p.id,call_id:p.witness.call_id,reason:error.message,...(error.cause?{diagnostic:error.cause}:{})});}
 }
 const locks=Object.fromEntries(scriptCodeLocks.map(p=>[p,sha(readFileSync(join(root,p)))]));
 // Bounded catalogue should not crowd out substantial computation with early
 // identity reads. This is code-size prioritization, not a cost saving claim.
 programs.sort((a,b)=>b.template.length-a.template.length||a.id.localeCompare(b.id));
 const selected=programs.slice(0,12);
 for(const p of programs.slice(12))rejected.push({id:p.id,reason:'bounded_library_capacity'});
 const body={version:1,kind:'sandboxed_script_motif_library',programs:selected,code_locks:locks,compilation_model_requests:0,heldout_task_id:held.task_id};
 return {library:{...body,digest:digest(body)},report:{published:selected.length,rejected,scope:'real_trace_replay_certification'}};
}
if(process.argv[1]&&resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const rows=JSON.parse(readFileSync(process.argv[2],'utf8'));const {library,report}=certify(rows);
 for(const [name,value] of [['library.json',library],['certification.json',report]])writeFileSync(join(process.argv[3],name),JSON.stringify(value,null,2)+'\n',{mode:0o600});
 console.log(JSON.stringify(report));
}
