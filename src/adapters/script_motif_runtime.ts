/** Opt-in Script Motif protocol. Internal operators keep the native Bash schema. */
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {join,relative,resolve,isAbsolute,extname} from 'node:path';
import {digest,syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {loopbackSimilarity} from './dsh_online_motif.mjs';
import {fileURLToPath} from 'node:url';

const sha=(s:any)=>createHash('sha256').update(s).digest('hex');
const grants=new Map<string,{session:string;versions:any[];body:string;expires:number}>();
const consumed=new Set<string>();
const inside=(root:string,path:string)=>{const r=relative(root,path);return !r.startsWith('..')&&!isAbsolute(r);};
export function fixedInput(root:string,path:string){
  if(!inside(root,path)||realpathSync(path)!==resolve(path)||!lstatSync(path).isFile()||lstatSync(path).size>16_000_000)throw Error('script_input_not_fixed');
  return readFileSync(path);
}
export function consumeScriptGrant(session:string,command:string){
  const key=sha(command),grant=grants.get(key);if(!grant)return false;
  grants.delete(key);
  if(grant.session!==session||Date.now()>grant.expires||grant.versions.some(v=>sha(fixedInput(v.root,v.host))!==v.sha256))throw Error('script_binding_changed');
  consumed.add(key);
  return grant.body;
}
export function scriptCommand(program:any,paths:string[],versions:string[],nonce:string){
  if(paths.length!==program.inputs.length||paths.some(p=>!p.startsWith('/work/')||p.includes('\n')))throw Error('invalid_script_binding');
  let source=program.template;
  paths.forEach((p,i)=>{source=source.split("'__MOTIF_INPUT_"+i+"__'").join(JSON.stringify(p));});
  if(source.includes('__MOTIF_INPUT_'))throw Error('unbound_script_slot');
  // Source is inserted as syntax, never passed to eval/exec. The outer trusted
  // receipt binds current file bytes and captures this invocation's stdout.
  const header=`import io as _sm_io, contextlib as _sm_context, hashlib as _sm_hash, json as _sm_json, resource as _sm_resource, sys as _sm_sys\n_sm_resource.setrlimit(_sm_resource.RLIMIT_CPU, (20,20))\nif _sm_sys.platform != 'darwin':\n    _sm_resource.setrlimit(_sm_resource.RLIMIT_AS, (536870912,536870912))\n_sm_paths=${JSON.stringify(paths)}\n_sm_expected=${JSON.stringify(versions)}\ndef _sm_versions():\n    return [_sm_hash.sha256(open(p,'rb').read()).hexdigest() for p in _sm_paths]\nassert _sm_versions()==_sm_expected, 'input_changed'\ndef _sm_program():\n`;
  const footer=`\n_sm_buffer=_sm_io.StringIO()\nwith _sm_context.redirect_stdout(_sm_buffer):\n    _sm_program()\nassert _sm_versions()==_sm_expected, 'input_changed'\n_sm_output=_sm_buffer.getvalue()\nassert 0<len(_sm_output.encode())<=16000, 'output_bound'\nprint(_sm_json.dumps({'kind':'script_motif_receipt','nonce':${JSON.stringify(nonce)},'program_id':${JSON.stringify(program.id)},'versions':_sm_expected,'output':_sm_output,'output_sha256':_sm_hash.sha256(_sm_output.encode()).hexdigest()},ensure_ascii=False))\n`;
  return "python3 - <<'SCRIPT_MOTIF_BOUNDARY'\n"+header+source.split('\n').map((s:string)=>'    '+s).join('\n')+footer+'SCRIPT_MOTIF_BOUNDARY';
}
function shape(v:any,depth=0):any{
  if(v===null)return 'null';if(Array.isArray(v))return v.length&&depth<3?{array:shape(v[0],depth+1)}:'array';
  if(typeof v==='object')return depth<3?{object:Object.fromEntries(Object.keys(v).sort().map(k=>[k,shape(v[k],depth+1)]))}:'object';
  return typeof v;
}
export function compatibleInput(contract:any,path:string,data:Buffer){
  if(extname(path).toLowerCase()!==contract.suffix)return false;
  try{
    if(contract.format==='zip')return data.subarray(0,4).equals(Buffer.from([80,75,3,4]));
    if(contract.format==='json')return digest(shape(JSON.parse(data.toString('utf8').replace(/^\uFEFF/,''))))===digest(contract.shape);
    if(contract.format==='text'){new TextDecoder('utf-8',{fatal:true}).decode(data);return true;}
  }catch{}return false;
}
export function bindScript(program:any,workspace:string){
  const files:any[]=[];
  function visit(dir:string,virtual:string,depth=0){
    if(depth>3||files.length>128)return;
    for(const row of readdirSync(dir,{withFileTypes:true})){
      if(row.name.startsWith('.')||row.isSymbolicLink())continue;
      const host=join(dir,row.name),path=virtual+'/'+row.name;
      if(row.isDirectory())visit(host,path,depth+1);
      else if(row.isFile())try{const data=fixedInput(workspace,host);files.push({root:workspace,host,path,data,sha256:sha(data)});}catch{}
    }
  }
  visit(join(workspace,'inputs'),'/work/inputs');visit(join(workspace,'code'),'/work');
  if(files.length>128)throw Error('script_input_frontier_limit');
  const bound=program.inputs.map((c:any)=>{
    const matches=files.filter(f=>compatibleInput(c,f.path,f.data));
    if(matches.length!==1)throw Error(matches.length?'ambiguous_script_binding':'missing_script_input');return matches[0];
  });
  if(new Set(bound.map((b:any)=>b.host)).size!==bound.length)throw Error('aliased_script_inputs');
  return bound;
}
export function loadScriptLibrary(path:string){
  const library=JSON.parse(readFileSync(path,'utf8'));const {digest:claimed,...body}=library;
  if(library.kind!=='sandboxed_script_motif_library'||library.version!==1||digest(body)!==claimed||!Array.isArray(library.programs)||library.programs.length>12)throw Error('invalid_script_library');
  const root=fileURLToPath(new URL('../../',import.meta.url));
  const locked=['src/adapters/script_motif_compiler.py','src/adapters/script_motif_runtime.ts','src/adapters/geneloop_shell.ts','src/adapters/script_motif_shell.ts','src/adapters/script_motif_macos.ts','src/adapters/script_motif_web.ts','scripts/script-motif-web.py','scripts/certify-script-motifs.mjs'];
  if(!library.code_locks||locked.some(p=>sha(readFileSync(join(root,p)))!==library.code_locks[p]))throw Error('script_runtime_changed');
  for(const p of library.programs){
    if(!p.certification?.passed||p.certification.cases<2||p.certification.source_equivalent!==true||
       p.certification.program_sha256!==digest({version:p.version,language:p.language,template:p.template,inputs:p.inputs})||
       p.id!=='script_'+p.certification.program_sha256.slice(0,24))throw Error('uncertified_script');
  }
  return library;
}
export function createScriptInterceptor({library,workspace,session,goal,mode,endpoint,model,minSimilarity=.88,minMargin=.04,minGoalSimilarity=.6,negativeGoals=[],audit,similarity}:any){
  if(!['shadow','execute'].includes(mode))throw Error('invalid_script_mode');
  if(!Number.isFinite(minSimilarity)||minSimilarity<.5||minSimilarity>1||!Number.isFinite(minMargin)||minMargin<.01||minMargin>1)throw Error('invalid_script_threshold');
  if(!Number.isFinite(minGoalSimilarity)||minGoalSimilarity<.5||minGoalSimilarity>1||!Array.isArray(negativeGoals)||negativeGoals.length>9||negativeGoals.some((s:any)=>typeof s!=='string'||!s.trim()||s.length>16000))throw Error('invalid_script_goal_policy');
  const scorer=similarity??loopbackSimilarity(endpoint,model),cache=new Map<string,number[]>();
  async function rank(query:string,descriptions:string[]){
    const unique=[...new Set(descriptions)],key=JSON.stringify([query,unique]);
    if(!cache.has(key)){
      const start=performance.now(),scores=await scorer(query,unique);
      if(scores.length!==unique.length||scores.some((s:any)=>!Number.isFinite(s)))throw Error('invalid_semantic_scores');
      if(cache.size>=128)cache.delete(cache.keys().next().value!);cache.set(key,scores);
      audit({kind:'script_embedding',elapsed_ms:performance.now()-start,descriptions:unique.length});
    }
    return descriptions.map(d=>cache.get(key)![unique.indexOf(d)]);
  }
  const used=new Set();let pending:any=null;let halted=false;let history:any[]=[];
  return {
    dispose(){if(pending){const key=sha(pending.command);grants.delete(key);consumed.delete(key);}pending=null;halted=true;},
    observe(id:string,execution:any,result:any){
      if(id!==session)return;
      history.push({tool:execution.name,ok:result?.isError!==true,intent:pending?.callId===execution.callId?pending.program.intent:typeof execution.arguments?.description==='string'?execution.arguments.description.slice(0,240):execution.name});history=history.slice(-6);
      if(!pending||execution.callId!==pending.callId)return;
      const p=pending;pending=null;grants.delete(sha(p.command));
      let verified=false;
      try{
        const text=(result.content??[]).filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('\n');
        const receipt=text.split('\n').map((line:string)=>{try{return JSON.parse(line);}catch{return null;}}).find((r:any)=>r?.kind==='script_motif_receipt');
        verified=consumed.has(sha(p.command))&&result.isError!==true&&execution.name==='bash'&&execution.arguments?.command===p.command&&
          receipt?.nonce===p.nonce&&receipt.program_id===p.program.id&&sha(receipt.output)===receipt.output_sha256&&
          digest(receipt.versions)===digest(p.bound.map((b:any)=>b.sha256))&&p.bound.every((b:any)=>sha(fixedInput(workspace,b.host))===b.sha256);
      }catch{}
      consumed.delete(sha(p.command));
      audit({kind:verified?'script_model_request_skipped_verified':'script_result_unverified',program_id:p.program.id,library_digest:library.digest});
      if(!verified)halted=true;
    },
    async intercept(id:string,options:any,next:any){
      if(id!==session||halted||pending||!options.tools?.some((t:any)=>t.name==='bash'))return next();
      if(options.messages?.some((m:any)=>m.source?.kind?.includes('repair')))return next();
      const candidates:any[]=[];
      for(const program of library.programs)try{
        if(program.predecessor&&(!history.length||history.at(-1)?.ok!==true||history.at(-1)?.tool!==program.predecessor.tool))continue;
        const bound=bindScript(program,workspace),key=digest([program.id,bound.map((b:any)=>b.sha256)]);
        if(!used.has(key))candidates.push({program,bound,key});
      }catch{}
      if(!candidates.length)return next();
      try{
        // Full goal is hashed in audit. Overlength goals are rejected by the
        // local service rather than silently removing scope or negations.
        const contextual=candidates.every(c=>typeof c.program.source_goal==='string'&&c.program.predecessor);
        const query=contextual?history.at(-1).intent:'Instruct: Retrieve a read-only program that is needed for the current document task.\nQuery: '+goal+'\nRecent tools: '+JSON.stringify(history);
        const scores=await rank(query,candidates.map(c=>contextual?c.program.predecessor.intent:c.program.description));
        const goals=contextual?await rank(goal,[...candidates.map(c=>c.program.source_goal),...negativeGoals]):[];
        const negative=negativeGoals.length?Math.max(...goals.slice(candidates.length)):-1;
        const ordered=candidates.map((c,i)=>({...c,score:scores[i],goal_score:goals[i]}))
          .filter(c=>!contextual||Number.isFinite(c.goal_score)&&c.goal_score>=minGoalSimilarity&&c.goal_score>=negative+.03).sort((a,b)=>b.score-a.score);
        if(!ordered.length){audit({kind:'script_goal_rejected',scores:goals});return next();}
        const winner=ordered[0],margin=ordered.length>1?winner.score-ordered[1].score:1;
        audit({kind:'script_candidates_ranked',library_digest:library.digest,goal_sha256:sha(goal),candidates:ordered.map(c=>({id:c.program.id,score:c.score,goal_score:c.goal_score})),margin});
        if(!Number.isFinite(winner.score)||winner.score<minSimilarity||margin<minMargin)return next();
        if(mode==='shadow'){audit({kind:'script_shadow_candidate',program_id:winner.program.id,input_versions:winner.bound.map((b:any)=>b.sha256)});return next();}
        const nonce=randomUUID(),callId='sss-script-'+randomUUID();
        const body=scriptCommand(winner.program,winner.bound.map((b:any)=>b.path),winner.bound.map((b:any)=>b.sha256),nonce);
        // Only an opaque invocation is visible to the LLM. The registered
        // executor expands it once, so cached source does not bloat context.
        const command='geneloop-script '+winner.program.id+' '+nonce;
        used.add(winner.key);pending={...winner,nonce,callId,command};grants.set(sha(command),{session,versions:winner.bound,body,expires:Date.now()+30000});
        audit({kind:'script_bypass_attempt',program_id:winner.program.id,input_versions:winner.bound.map((b:any)=>b.sha256),score:winner.score});
        return syntheticToolStreamBatch([{callId,proposal:{tool:'bash',arguments:{command,description:'复用已认证的只读脚本：'+winner.program.description}}}]);
      }catch(error:any){audit({kind:'script_fallback',reason:error.name});return next();}
    },
  };
}
