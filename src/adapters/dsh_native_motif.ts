/** Frozen repeated-run native reads; uses shared Harness lifecycle and stream. */
import { readFileSync, realpathSync, appendFileSync, mkdirSync, existsSync } from 'node:fs';
import { resolve, relative, join, isAbsolute } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { digest, syntheticToolStreamBatch } from '../motif_core/online_skill_runtime.mjs';
import { attachMotifInterceptor } from './dsh_online_motif.mjs';

export const name = 'sss-native-motif-diagnostic';
export const inject = ['llm', 'agents', 'jobs'];
const fileHash = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');
const programs = new Set(['pwd','echo','cat','head','tail','grep','wc','sha256sum','file','pdfinfo','pdffonts','sort','uniq']);
const options: Record<string, string[]> = {
  cat:['-n','-b','-s','-v','-E','-T','-A','--'],head:['-n','-c','--'],tail:['-n','-c','--'],
  grep:['-n','-i','-E','-F','-c','-o','-H','-h','-v','-s','-e','--'],wc:['-l','-w','-c','-m','-L','--'],
  sha256sum:['-b','-t','--'],file:['-b','-i','--'],sort:['-n','-r','-u','-h','-f','-b','--'],
  uniq:['-c','-d','-u','-i','--'],pdfinfo:[],pdffonts:[],pwd:[],echo:[],
};

function normalize(value: any, work: string): any {
  if (typeof value === 'string') return value.split(work).join('${WORK}');
  if (Array.isArray(value)) return value.map(v => normalize(v,work));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value)
    .filter(([key])=>key!=='description').map(([key,v])=>[key,normalize(v,work)]));
  return value;
}
function expand(value: any, work: string): any {
  if (typeof value === 'string') return value.split('${WORK}').join(work);
  if (Array.isArray(value)) return value.map(v=>expand(v,work));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,expand(v,work)]));
  return value;
}
function localPath(work: string, path: string): string {
  if (typeof path!=='string' || isAbsolute(path) || path.split('/').includes('..')) throw Error('external native path');
  const actual=realpathSync(resolve(work,path));const rel=relative(work,actual);
  if (rel.startsWith('..') || isAbsolute(rel)) throw Error('native symlink escape');
  return actual;
}
const quote = (value: string) => "'"+value.replaceAll("'","'\\''")+"'";
export function nativeArguments(node: any, work: string): any {
  if (node.protocol==='native-file-read-v1') {
    if (node.tool!=='read' || Object.keys(node.arguments).some(k=>!['file_path','offset','limit'].includes(k))) throw Error('unsupported read');
    const args=expand(node.arguments,work);
    const rel=relative(work,localPath(work,relative(work,resolve(work,args.file_path))));
    if (!Object.hasOwn(node.dependencies??{},rel)) throw Error('unwitnessed native read file');
    return args;
  }
  if (node.protocol!=='native-read-argv-v1' || node.tool!=='bash' || !node.program?.stages?.length || node.program.stages.length>12) throw Error('unsupported native node');
  const cwd=localPath(work,node.program.cwd);
  const pieces=node.program.stages.map((stage: any,index: number)=>{
    const argv=stage.argv;
    if (!Array.isArray(argv) || argv.length>64 || !programs.has(argv[0]) || argv.some((a: any)=>typeof a!=='string' || a.length>2000 || /[\x00\n]/.test(a))) throw Error('unbounded argv');
    if (argv.slice(1).some((a: string)=>a.startsWith('-') && argv[0]!=='echo' && !options[argv[0]].includes(a) &&
       !(['head','tail'].includes(argv[0]) && /^-(?:n|c)?[0-9]{1,7}$/.test(a)))) throw Error('unsafe read option');
    if (![';','&&','|'].includes(stage.separator)) throw Error('unsafe operator');
    for (const value of argv.slice(1)) {
      if (argv[0]==='echo' || value.startsWith('-')) continue;
      const expanded=expand(value,work);
      if (isAbsolute(expanded) && !expanded.startsWith(work+'/')) throw Error('external operand');
      if (expanded.split('/').includes('..')) throw Error('parent operand');
      const path=resolve(cwd,expanded);
      if (existsSync(path)) {
        const rel=relative(work,localPath(work,relative(work,path)));
        if (!Object.hasOwn(node.dependencies??{},rel)) throw Error('unwitnessed native operand');
      }
    }
    const command=argv.map((v: string)=>quote(expand(v,work))).join(' ');
    return command+(index<node.program.stages.length-1 ? ' '+stage.separator+' ' : '');
  });
  // Regenerate from the bounded argv IR. Never evaluate the mined shell text.
  return {command:'cd '+quote(cwd)+' && '+pieces.join(''),description:'Motif: witnessed read-only continuation',timeoutMs:30000};
}

export function createNativeInterceptor({manifest,work,sessionId,audit,jobs}: any): any {
  const body=Object.fromEntries(Object.entries(manifest).filter(([key])=>key!=='manifest_digest'));
  if (manifest.manifest_digest!==digest(body) || manifest.certification_scope!=='same_task_repeated_runs' || !Array.isArray(manifest.motifs)) throw Error('invalid diagnostic native manifest');
  let recent: any[]=[];let pending: any=null;let halted=false;const used=new Set();
  const ownedJobs=new Map();
  const verifiedFiles=(motif: any)=>motif.nodes.every((node: any)=>Object.entries(node.dependencies).every(([path,hash])=>fileHash(localPath(work,path))===hash));
  return {
    observe(id: string,exec: any,result: any) {
      if (id!==sessionId) return;
      const output=result?.content ?? [];
      const row={call:{name:exec.name,arguments:normalize(exec.arguments,work)},output_sha256:digest(normalize(output,work)),ok:result?.isError!==true};
      recent.push(row);
      if (row.ok && exec.name==='bash' && exec.arguments?.run_in_background===true && exec.agent?.session?.id===sessionId) {
        const id=result.value?.kind==='background' && typeof result.value.jobId==='string' ? result.value.jobId : null;
        if (id) {try {const job=jobs?.get(id,exec.agent);if(job?.kind==='bash')ownedJobs.set(id,exec.agent);}catch {}}
      }
      if (pending?.job_id && pending.call_id===exec.callId) {
        let ok=row.ok && exec.name==='job_output' && digest(exec.arguments)===digest(pending.args) &&
          result.value?.job?.id===pending.job_id && typeof result.value?.text==='string' &&
          ['completed','failed','killed'].includes(result.value.job.status);
        try {ok &&= jobs.get(pending.job_id,ownedJobs.get(pending.job_id)).id===pending.job_id;}catch {ok=false;}
        audit({kind:ok?'model_request_skipped_verified':'bypass_result_unverified',tool_count:1,protocol:'native_owned_job_read'});
        halted ||= !ok;ownedJobs.delete(pending.job_id);pending=null;return;
      }
      // A successful model-directed read already consumes the terminal job's
      // delta output; do not turn that into an unnecessary second read.
      if (row.ok && exec.name==='job_output' && ownedJobs.has(exec.arguments?.job_id)) {
        try {if (['completed','failed','killed'].includes(jobs.get(exec.arguments.job_id,ownedJobs.get(exec.arguments.job_id)).status)) ownedJobs.delete(exec.arguments.job_id);}catch {}
      }
      if (pending?.calls.has(exec.callId)) {
        const expected=pending.calls.get(exec.callId);
        pending.failed ||= !row.ok || exec.name!==expected.node.tool || digest(exec.arguments)!==digest(expected.args) || row.output_sha256!==expected.node.expected_output_sha256;
        pending.calls.delete(exec.callId);
        audit({kind:'native_motif_result',verified:!pending.failed,call_id:exec.callId});
        if (!pending.calls.size) {
          try {pending.failed ||= !verifiedFiles(pending.motif);} catch {pending.failed=true;}
          audit({kind:pending.failed?'bypass_result_unverified':'model_request_skipped_verified',tool_count:pending.motif.nodes.length});
          halted ||= pending.failed;pending=null;
        }
      }
    },
    async intercept(id: string,request: any,next: any) {
      if (id!==sessionId) return next();
      const prefix=recent;recent=[];
      if (halted || pending || !prefix.length || prefix.some(r=>!r.ok)) return next();
      try {
        if (fileHash(localPath(work,'submission.zip'))!==manifest.input_sha256) throw Error('input changed');
        if (manifest.tool_order && digest((request.tools??[]).map((t:any)=>t.name))!==digest(manifest.tool_order)) throw Error('native tool order changed');
        const anchor=prefix.map(({call,output_sha256}:any)=>({call,output_sha256}));
        const offered=new Map((request.tools??[]).map((t:any)=>[t.name,t]));
        const ready: any[]=[];
        for (const [id,owner] of ownedJobs) {
          let job;try {job=jobs.get(id,owner);}catch {continue;}
          if (!['completed','failed','killed'].includes(job.status)) continue;
          for (const m of manifest.job_motifs??[]) {
            if (m.source_tool!=='bash' || m.source_field!=='jobId' || m.target_tool!=='job_output' || m.target_param!=='job_id' || m.only_when_terminal!==true) continue;
            if (digest((offered.get('bash') as any)?.parameters)!==manifest.tool_schema_hashes.bash) continue;
            const extra=m.extra_arguments;
            if (!extra || Object.keys(extra).some(k=>!['wait','timeout_ms'].includes(k)) ||
                ('wait' in extra && typeof extra.wait!=='boolean') ||
                ('timeout_ms' in extra && !(extra.timeout_ms>=1 && extra.timeout_ms<=600000))) continue;
            if (digest((offered.get('job_output') as any)?.parameters)!==manifest.tool_schema_hashes.job_output) continue;
            ready.push({id,m});
          }
        }
        if (ready.length===1) {
          const {id,m}=ready[0];const args={job_id:id,...m.extra_arguments};const callId='sss-native-'+randomUUID();
          pending={job_id:id,call_id:callId,args};audit({kind:'motif_bypass_attempt',motif_id:m.motif_id,tool_count:1,protocol:'native_owned_job_read'});
          return syntheticToolStreamBatch([{callId,proposal:{tool:'job_output',arguments:args}}]);
        }
        const candidates=manifest.motifs.filter((m:any)=>digest(m.anchor)===digest(anchor) && !used.has(m.motif_id) &&
          m.nodes.every((n:any)=>digest((offered.get(n.tool) as any)?.parameters)===manifest.tool_schema_hashes[n.tool]) && verifiedFiles(m));
        if (candidates.length!==1) {audit({kind:'native_motif_deferred',reason:candidates.length?'ambiguous':'no_guarded_candidate'});return next();}
        const motif=candidates[0];const calls=motif.nodes.map((node:any)=>{
          const args=nativeArguments(node,work);return {callId:'sss-native-'+randomUUID(),node,args,proposal:{tool:node.tool,arguments:args}};
        });
        used.add(motif.motif_id);pending={motif,calls:new Map(calls.map((c:any)=>[c.callId,{node:c.node,args:c.args}])),failed:false};
        audit({kind:'motif_bypass_attempt',motif_id:motif.motif_id,tool_count:calls.length});
        return syntheticToolStreamBatch(calls);
      } catch (error: any) {audit({kind:'native_motif_deferred',reason:error.name});return next();}
    },
  };
}

export function apply(ctx: any): void {
  const path=process.env.SSS_NATIVE_MOTIF_MANIFEST;
  if (!path) return;
  const work=realpathSync(process.env.SSS_NATIVE_MOTIF_WORK!);
  const sessionId=process.env.SSS_NATIVE_MOTIF_SESSION!;const promptHash=process.env.SSS_NATIVE_MOTIF_PROMPT_SHA256;
  const manifest=JSON.parse(readFileSync(path,'utf8'));
  if (manifest.prompt_sha256!==promptHash || manifest.input_sha256!==process.env.SSS_NATIVE_MOTIF_INPUT_SHA256) throw Error('native task binding changed');
  const dir=join(work,'..','native-motif');mkdirSync(dir,{recursive:true,mode:0o700});
  const audit=(row:any)=>appendFileSync(join(dir,'audit.jsonl'),JSON.stringify({session_id:sessionId,...row})+'\n',{mode:0o600});
  const interceptor=createNativeInterceptor({manifest,work,sessionId,audit,jobs:ctx.jobs});
  attachMotifInterceptor(ctx,{task:{session_id:sessionId},promptHash,interceptor,audit:(kind:string,reason:string)=>audit({kind,reason})});
}
