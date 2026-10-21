/** Opt-in Script Motif protocol. Internal operators keep the native Bash schema. */
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,readdirSync,lstatSync,realpathSync,existsSync} from 'node:fs';
import {join,relative,resolve,isAbsolute,extname} from 'node:path';
import {digest,syntheticToolStreamBatch} from '../motif_core/online_skill_runtime.mjs';
import {loopbackSimilarity} from './dsh_online_motif.mjs';
import {fileURLToPath} from 'node:url';
import {createScriptExecutionFrontier} from './script_execution_frontier.ts';
import {validateJsonSchemaValue} from '@deepseek-ai/dsh-tools';

const sha=(s:any)=>createHash('sha256').update(s).digest('hex');
const grants=new Map<string,{session:string;versions:any[];body:any;expires:number}>();
const consumed=new Set<string>();
const caches=new Map<string,any>();
const reuseMediators=new Map<string,any>();
export function registerReuseMediation(session:string,runtime:any){if(runtime)reuseMediators.set(session,runtime);else reuseMediators.delete(session);}
const inside=(root:string,path:string)=>{const r=relative(root,path);return !r.startsWith('..')&&!isAbsolute(r);};
export function scriptVirtualHost(workspace:string,path:string){
 if(resolve(path)!==path||!inside('/work',resolve(path)))throw Error('script_input_not_fixed');
 const part=relative('/work',resolve(path));
 return resolve(workspace,part==='inputs'||part.startsWith('inputs/')?part:
  part==='outputs'||part.startsWith('outputs/')?'outputs/code/'+part.slice('outputs'.length):'code/'+part);
}
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
export function registerScriptCache(options:any){
 const {library,session}=options;caches.set(session,{...options,pending:new Map()});
 if(options.frontier){
  const notice=options.frontier.takeNotice('initial_stable_prefix'),offered=new Set(options.frontier.offeredProgramIds?.()??[]);
  const fallback=library.programs.filter((p:any)=>!offered.has(p.id));
  return (options.compactContext?'只读执行候选如下；其余工作仍可用原生工具。\n':'可复用检查由 Runtime 按本次文件绑定，详细候选见当前选择通知；只选择本次任务确实需要的操作。执行回执是证据，最终判断仍由你完成。其他需要的检查可使用原生工具。必要时原有 bash 可调用 geneloop-cache '+
  "'{\"calls\":[{\"id\":\"当前候选中的 script_ID\",\"paths\":[\"/work/实际文件\"],\"argv\":[]}]}'"+
  '；paths按算子inputs顺序，禁止附加管道或重定向。不要重做已有且版本未变的检查。\n')+
  (fallback.length?(options.compactContext?'显式缓存格式：geneloop-cache '+JSON.stringify({calls:[{id:'script_ID',paths:['/work/实际文件'],argv:[]}]})+'。必须独立命令，不能追加管道。\n':'')+'仍可由你显式绑定和选择的缓存算子（未进入当前自动选择）：'+JSON.stringify(fallback.map((p:any)=>({id:p.id,operation:p.interface??p.description,inputs:p.inputs,argv_contract:p.argv_contract,network_policy:p.network_policy})))+'\n':'')+notice;
 }
 return '可复用脚本库（真实历史代码；输出是证据，不代表文献判断正确）。按当前任务选择需要的操作，用原有 bash 调用，不必重写等价脚本。允许批量 calls，仍由你选择查询对象、判断来源与撰写最终报告。命令格式：geneloop-cache '+
  "'{\"calls\":[{\"id\":\"script_ID\",\"paths\":[\"/work/实际文件\"],\"argv\":[]}]}'"+
  '\n命令可带 cd /work/... &&，不要附加 head、重定向或其他管道；输出已受限，完整回执用于验证。文件 paths 对应 inputs 顺序；argv 仅供 argv_contract 程序，传本任务中取得的标识符等标量，不能沿用历史值。程序描述由代码的参数变量、输出字段与 URL 字面量生成，适用于本任务的新数据，并非限定历史论文。网络程序只能获取固定 arXiv/Crossref 元数据，其他网络请求会拒绝。已取得的相同证据无需重新计算，失败或信息不足仍可用普通工具。\n'+
  JSON.stringify(library.programs.map((p:any)=>({id:p.id,operation:p.interface??p.description,inputs:p.inputs,argv_contract:p.argv_contract,network_policy:p.network_policy})));
}
export function prepareCacheInvocation(session:string,command:string){
 if(/\bgeneloop-reuse\s/.test(command)){
  const reuse=reuseMediators.get(session);if(!reuse)throw Error('reuse_mediation_not_admitted');return reuse.prepare(command);
 }
 if(command.trim().startsWith('geneloop-resolve ')){
  const frontier=caches.get(session)?.frontier;
  if(!frontier)throw Error('semantic_frontier_not_admitted');
  return frontier.prepare(command);
 }
 if(!/\bgeneloop-cache\s/.test(command))return false;
 const entry=caches.get(session);if(!entry)throw Error('script_cache_not_admitted');
 let invocation=command.trim();
 const prefix=/^cd\s+('[^']*'|"[^"]*"|[^\s]+)\s*&&\s*(geneloop-cache\s+[\s\S]+)$/.exec(invocation);
 if(prefix){
  let cwd=prefix[1];if(cwd.startsWith("'")||cwd.startsWith('"'))cwd=cwd.slice(1,-1);
  if(!cwd.startsWith('/work')||!inside('/work',resolve(cwd))||/[`$\\]/.test(cwd))throw Error('cache_cwd_must_be_current_workspace');
  const host=scriptVirtualHost(entry.workspace,cwd);
  if(!inside(entry.workspace,host)||realpathSync(host)!==host||!lstatSync(host).isDirectory())throw Error('cache_cwd_not_fixed');
  invocation=prefix[2];
 }
 if(!invocation.startsWith('geneloop-cache ')||/\s\|\s*head\b/.test(invocation))throw Error('缓存调用必须是独立 geneloop-cache JSON 命令，可带 cd /work/... &&，不要附加 head 或其他管道；回执必须完整，输出已受限。请去掉管道后重试。');
 let raw=invocation.slice('geneloop-cache '.length).trim();if(raw.startsWith("'")&&raw.endsWith("'"))raw=raw.slice(1,-1);
 let parsed;try{parsed=JSON.parse(raw);}catch{throw Error('缓存参数必须是有效 JSON；不要附加重定向、管道或其他 shell 操作。');}
 const {calls}=parsed;
 if(!Array.isArray(calls)||calls.length<1||calls.length>16)throw Error('bounded_script_batch_required');
 const jobs=calls.map((call:any)=>{
  const program=entry.library.programs.find((p:any)=>p.id===call.id);if(!program)throw Error('unknown_cached_program');
  const argv=call.argv??[];
  if(!Array.isArray(argv)||argv.length>(program.argv_contract?.max_items??0)||argv.some((s:any)=>typeof s!=='string'||!s||s.length>256||s.startsWith('/')||s.startsWith('..')||/[\r\n\x00]/.test(s))||program.argv_contract&&!argv.length)throw Error('invalid_scalar_arguments');
  const paths=call.paths??[];
  if(!Array.isArray(paths)||paths.length!==program.inputs.length)throw Error('explicit_script_paths_required');
  const bound=paths.map((p:string,i:number)=>{
   if(typeof p!=='string'||!p.startsWith('/work/')||p.includes('\n'))throw Error('invalid_script_path');
   const host=scriptVirtualHost(entry.workspace,p),data=fixedInput(entry.workspace,host);
   if(!compatibleInput(program.inputs[i],host,data))throw Error('incompatible_script_input');
   return {root:entry.workspace,host,path:p,sha256:sha(data)};
  });
  const nonce=randomUUID(),job={workspace:entry.workspace,program,paths,versions:bound.map((b:any)=>b.sha256),argv,nonce};
  entry.pending.set(nonce,{job,bound,command,count:calls.length,expires:Date.now()+120000});return job;
 });
 entry.audit({kind:'script_cache_dispatched',program_ids:jobs.map((j:any)=>j.program.id),model_owned_selection:true});
 return {jobs};
}
export function observeScriptCache(session:string,execution:any,result:any){
 const entry=caches.get(session);if(!entry||execution.name!=='bash')return [];
 const facts=[];
 try{
  const text=(result.content??[]).filter((p:any)=>p.type==='text').map((p:any)=>p.text).join('\n');
  const batch=text.split('\n').map((s:string)=>{try{return JSON.parse(s);}catch{return null;}}).find((p:any)=>p?.kind==='script_cache_batch_receipt');
  if(batch&&(!Array.isArray(batch.receipts)||new Set(batch.receipts.map((r:any)=>r.nonce)).size!==batch.receipts.length))throw Error('cache_batch_invalid');
  for(const receipt of batch?.receipts??[]){
   const pending=entry.pending.get(receipt.nonce);entry.pending.delete(receipt.nonce);
   if(!pending||pending.count!==batch.receipts.length||execution.arguments?.command!==pending.command||Date.now()>pending.expires||result.isError===true||receipt.program_id!==pending.job.program.id||sha(receipt.output)!==receipt.output_sha256||digest(receipt.versions)!==digest(pending.job.versions)||pending.bound.some((b:any)=>sha(fixedInput(entry.workspace,b.host))!==b.sha256))throw Error('cache_receipt_invalid');
   facts.push({program:pending.job.program,bound:pending.bound,argv:pending.job.argv,output:receipt.output,network_requests:receipt.network_evidence?.length??0});
  }
 }catch{entry.audit({kind:'script_cache_result_unverified'});return [];}
 for(const fact of facts)entry.audit({kind:'script_cache_verified',program_id:fact.program.id,network_requests:fact.network_requests,semantic_quality_accepted:false});
 return facts;
}
export function programIdentity(p:any){return {version:p.version,language:p.language,template:p.template,inputs:p.inputs,...(p.argv_contract?{argv_contract:p.argv_contract}:{}),...(p.network_policy?{network_policy:p.network_policy}:{})};}
/** Infer transport shape from BOTH independent executions, never field truth.
 * Different object keys stay opaque; do not publish source-specific data keys.
 */
export function witnessedOutputSchema(outputs:string[]){
 try{
  const values=outputs.map(s=>JSON.parse(s));if(values.length<2)return;
  function schema(rows:any[],depth=0):any{
   const types=rows.map(v=>v===null?'null':Array.isArray(v)?'array':typeof v);
   if(new Set(types).size!==1||!['object','array','string','number','boolean','null'].includes(types[0]))throw Error('unstable_output_type');
   const type=types[0];if(type!=='object')return {type};
   const keys=Object.keys(rows[0]).sort();
   if(depth>=4||!keys.length||keys.length>32||keys.some(k=>k.length>80||['__proto__','constructor','prototype'].includes(k))||rows.some(r=>digest(Object.keys(r).sort())!==digest(keys)))return {type:'object'};
   return {type:'object',required:keys,additionalProperties:false,properties:Object.fromEntries(keys.map(k=>[k,schema(rows.map(r=>r[k]),depth+1)]))};
  }
  const result=schema(values);
  if(result.type==='object'&&result.properties&&Buffer.byteLength(JSON.stringify(result))<=8000)return result;
 }catch{}
}
export function scriptCommand(program:any,paths:string[],versions:string[],nonce:string,options:any={}){
  if(paths.length!==program.inputs.length||paths.some(p=>!p.startsWith('/work/')||p.includes('\n')))throw Error('invalid_script_binding');
  let source=program.template;
  paths.forEach((p,i)=>{source=source.split("'__MOTIF_INPUT_"+i+"__'").join(JSON.stringify(p));});
  if(source.includes('__MOTIF_INPUT_'))throw Error('unbound_script_slot');
  // Source is inserted as syntax, never passed to eval/exec. The outer trusted
  // receipt binds current file bytes and captures this invocation's stdout.
  const http=program.network_policy?`import urllib.request as _sm_http\n_sm_cache=${JSON.stringify(options.http??{})}\n_sm_pending=[]\nclass _sm_Demand(BaseException): pass\ndef _sm_fetch(request, data=None, timeout=None, **kwargs):\n    url=request.full_url if isinstance(request,_sm_http.Request) else request\n    assert data is None and (not isinstance(request,_sm_http.Request) or request.get_method()=='GET'), 'GET_only'\n    assert isinstance(url,str) and len(url)<=4096, 'bounded_url'\n    if url not in _sm_cache:\n        _sm_pending.append(url)\n        raise _sm_Demand()\n    row=_sm_cache[url]\n    payload=open(row['file'],'rb').read()\n    assert _sm_hash.sha256(payload).hexdigest()==row['sha256'], 'http_evidence_changed'\n    return _sm_io.BytesIO(payload)\n_sm_http.urlopen=_sm_fetch\n`:'';
  const header=`import io as _sm_io, contextlib as _sm_context, hashlib as _sm_hash, json as _sm_json, resource as _sm_resource, sys as _sm_sys\n_sm_resource.setrlimit(_sm_resource.RLIMIT_CPU, (20,20))\nif _sm_sys.platform != 'darwin':\n    _sm_resource.setrlimit(_sm_resource.RLIMIT_AS, (536870912,536870912))\n_sm_sys.argv=${JSON.stringify(['cached-script',...(options.argv??[])])}\n_sm_paths=${JSON.stringify(paths)}\n_sm_expected=${JSON.stringify(versions)}\ndef _sm_versions():\n    return [_sm_hash.sha256(open(p,'rb').read()).hexdigest() for p in _sm_paths]\nassert _sm_versions()==_sm_expected, 'input_changed'\n${http}def _sm_program():\n`;
  const invoke=program.network_policy?`try:\n    with _sm_context.redirect_stdout(_sm_buffer):\n        _sm_program()\nexcept _sm_Demand: pass\nif _sm_pending:\n    print(_sm_json.dumps({'kind':'script_http_demand','url':_sm_pending[0]}))\n    _sm_sys.exit(0)\n`:`with _sm_context.redirect_stdout(_sm_buffer):\n    _sm_program()\n`;
  const footer=`\n_sm_buffer=_sm_io.StringIO()\n${invoke}assert _sm_versions()==_sm_expected, 'input_changed'\n_sm_output=_sm_buffer.getvalue()\nassert 0<len(_sm_output.encode())<=16000, 'output_bound'\nprint(_sm_json.dumps({'kind':'script_motif_receipt','nonce':${JSON.stringify(nonce)},'program_id':${JSON.stringify(program.id)},'versions':_sm_expected,'output':_sm_output,'output_sha256':_sm_hash.sha256(_sm_output.encode()).hexdigest()},ensure_ascii=False))\n`;
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
export function bindScript(program:any,workspace:string,predecessorBindings:any[]=[]){
  // Prefer the current explicit predecessor's parameter flow over unrelated
  // files with the same suffix elsewhere in the workspace.
  if(predecessorBindings.length){
    const current=predecessorBindings.map(b=>{const data=fixedInput(workspace,b.host);if(sha(data)!==b.sha256)throw Error('script_predecessor_input_changed');return {...b,data};});
    const selected=program.inputs.map((c:any)=>current.filter(b=>compatibleInput(c,b.host,b.data)));
    if(selected.every((matches:any[])=>matches.length===1)){
      const bound=selected.map((matches:any[])=>matches[0]);
      if(new Set(bound.map((b:any)=>b.host)).size!==bound.length)throw Error('aliased_script_inputs');
      return bound;
    }
  }
  const files:any[]=[];
  function visit(dir:string,virtual:string,depth=0){
    if(depth>3||files.length>128)return;
    // Uploaded inputs already exist before the first command. Missing optional
    // scratch/output directories must not hide an otherwise complete binding.
    if(!existsSync(dir))return;
    for(const row of readdirSync(dir,{withFileTypes:true})){
      if(row.name.startsWith('.')||row.isSymbolicLink())continue;
      const host=join(dir,row.name),path=virtual+'/'+row.name;
      if(row.isDirectory())visit(host,path,depth+1);
      else if(row.isFile())try{const data=fixedInput(workspace,host);files.push({root:workspace,host,path,data,sha256:sha(data)});}catch{}
    }
  }
  visit(join(workspace,'inputs'),'/work/inputs');visit(join(workspace,'code'),'/work');
  const outputs=join(workspace,'outputs/code');if(existsSync(outputs)&&realpathSync(outputs)===resolve(outputs))visit(outputs,'/work/outputs');
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
  const locked=scriptCodeLocks;
  if(!library.code_locks||locked.some(p=>sha(readFileSync(join(root,p)))!==library.code_locks[p]))throw Error('script_runtime_changed');
  for(const p of library.programs){
    if(!p.certification?.passed||p.certification.cases<2||p.certification.source_equivalent!==true||
       p.certification.program_sha256!==digest(programIdentity(p))||
       p.id!=='script_'+p.certification.program_sha256.slice(0,24))throw Error('uncertified_script');
  }
  return library;
}
export const scriptCodeLocks=['src/adapters/script_learning_store.ts','src/adapters/reuse_snapshot.py','scripts/learn-script-motifs.py','src/adapters/script_motif_compiler.py','src/adapters/script_dataflow_compiler.py','src/adapters/reuse_mediation.ts','src/adapters/script_motif_runtime.ts','src/adapters/script_execution_frontier.ts','src/adapters/script_negative_runtime.ts','src/adapters/negative_field_runtime.ts','src/adapters/geneloop_shell.ts','src/adapters/script_motif_shell.ts','src/adapters/script_motif_macos.ts','src/adapters/script_motif_web.ts','scripts/script-motif-web.py','scripts/certify-script-motifs.mjs','scripts/run-certified-script.mjs','scripts/fetch-script-evidence.py'];
export function createScriptInterceptor({library,workspace,session,goal,mode,endpoint,model,minSimilarity=.88,minMargin=.04,minGoalSimilarity=.6,negativeGoals=[],audit,similarity,demandBound=false,executionFrontier=false,compactContext=false}:any){
  if(!['cache','shadow','execute'].includes(mode))throw Error('invalid_script_mode');
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
  const used=new Set();let pending:any=null;let halted=false;let history:any[]=[];let userEnvelope:string|undefined;
  if(executionFrontier&&mode!=='execute')throw Error('frontier_requires_explicit_execute');
  const frontier=executionFrontier?createScriptExecutionFrontier({library,goal,audit,compactContext,
    bind:(program:any)=>bindScript(program,workspace),verify:(b:any)=>{
      try{return sha(fixedInput(workspace,b.host))===b.sha256;}catch{return false;}
    }}):null;
  function issue(winner:any,origin='matched'){
    const nonce=randomUUID(),callId='sss-script-'+randomUUID();
    const body=scriptCommand(winner.program,winner.bound.map((b:any)=>b.path),winner.bound.map((b:any)=>b.sha256),nonce);
    const command='geneloop-script '+winner.program.id+' '+nonce;
    used.add(winner.key);pending={...winner,nonce,callId,command,origin};grants.set(sha(command),{session,versions:winner.bound,body,expires:Date.now()+30000});
    audit({kind:'script_bypass_attempt',program_id:winner.program.id,input_versions:winner.bound.map((b:any)=>b.sha256),score:winner.score,origin,fragment_id:winner.fragment_id});
    return syntheticToolStreamBatch([{callId,proposal:{tool:'bash',arguments:{command,description:compactContext?'执行当前已选择的只读检查':'复用已认证的只读脚本：'+JSON.stringify(winner.program.interface??winner.program.description)}}}]);
  }
  function verifiedReceipt(p:any,execution:any,result:any){
   try{
    if(!p||!consumed.has(sha(p.command))||result.isError===true||execution.name!=='bash'||execution.callId!==p.callId||execution.arguments?.command!==p.command)return null;
    const text=(result.content??[]).filter((b:any)=>b.type==='text').map((b:any)=>b.text).join('\n');
    const receipt=p.projection&&digest(result.content)===p.projection.content_digest?p.projection.receipt:
     text.split('\n').map((line:string)=>{try{return JSON.parse(line);}catch{return null;}}).find((r:any)=>r?.kind==='script_motif_receipt');
    if(!(receipt?.nonce===p.nonce&&receipt.program_id===p.program.id&&sha(receipt.output)===receipt.output_sha256&&
     digest(receipt.versions)===digest(p.bound.map((b:any)=>b.sha256))&&p.bound.every((b:any)=>sha(fixedInput(workspace,b.host))===b.sha256)))return null;
    if(p.program.certification?.output_schema&&validateJsonSchemaValue(p.program.certification.output_schema,JSON.parse(receipt.output)).length){audit({kind:'script_result_schema_mismatch',program_id:p.program.id});return null;}
    return receipt;
   }catch{return null;}
  }
  return {
    frontier,
    frontierPrompt(){return frontier?.prompt()??'';},
    frontierNotice(){return frontier?.takeNotice()??'';},
    dispose(){if(pending){const key=sha(pending.command);grants.delete(key);consumed.delete(key);}caches.delete(session);pending=null;halted=true;},
    projectResult(execution:any,result:any){
      if(!compactContext)return;
      const receipt=verifiedReceipt(pending,execution,result);if(!receipt)return;
      // Do not change the canonical Bash value or any stdout. Full proof is
      // durably audited BEFORE the public post-execute content replacement.
      const content=[{type:'text',text:JSON.stringify({kind:'verified_script_evidence',program:pending.program.id,inputs:pending.bound.map((b:any)=>({path:b.path,sha256:b.sha256})),stdout:receipt.output,semantic_quality_accepted:false})}];
      const saved=Buffer.byteLength(JSON.stringify(result.content))-Buffer.byteLength(JSON.stringify(content));
      if(saved<=0)return;
      audit({kind:'script_evidence_raw',call_id:execution.callId,program_id:pending.program.id,content:result.content,content_sha256:digest(result.content)});
      pending.projection={receipt,content_digest:digest(content)};
      audit({kind:'script_evidence_context_projected',call_id:execution.callId,utf8_bytes_removed:saved,stdout_complete:true,scope:'model_content_only_canonical_value_and_raw_audit_preserved'});
      return content;
    },
    observe(id:string,execution:any,result:any){
      if(id!==session)return;
      frontier?.observe(execution,result);
      const facts=observeScriptCache(session,execution,result);
      for(const fact of facts){used.add(digest([fact.program.id,fact.bound.map((b:any)=>b.sha256)]));frontier?.recordEvidence(fact.program.id,fact.bound);}
      const anchor=facts.at(-1)?.program??(pending&&pending.callId===execution.callId?pending.program:null);
      history.push({tool:execution.name,program_id:anchor?.id,bound:facts.at(-1)?.bound??(pending&&pending.callId===execution.callId?pending.bound:[]),ok:result?.isError!==true,intent:anchor?.intent??(typeof execution.arguments?.description==='string'?execution.arguments.description.slice(0,240):execution.name)});history=history.slice(-6);
      if(!pending||execution.callId!==pending.callId)return facts;
      const p=pending;pending=null;grants.delete(sha(p.command));
      const receipt=verifiedReceipt(p,execution,result),verified=!!receipt;
      consumed.delete(sha(p.command));
      audit({kind:verified?'script_model_request_skipped_verified':'script_result_unverified',program_id:p.program.id,library_digest:library.digest});
      if(p.origin==='frontier')frontier?.finish(p.program.id,verified);
      if(!verified)halted=true;
      if(verified)facts.push({program:p.program,bound:p.bound,output:receipt.output});
      return facts;
    },
    async intercept(id:string,options:any,next:any){
      if(id!==session||halted||pending||mode==='cache'||!options.tools?.some((t:any)=>t.name==='bash'))return next();
      if(options.messages?.some((m:any)=>m.source?.kind?.includes('repair')))return next();
      if(frontier){
        const envelope=digest((options.messages??[]).filter((m:any)=>m.role==='user'&&m.source?.kind==='user').map((m:any)=>({id:m.id,content:m.content})));
        if(userEnvelope!==undefined&&userEnvelope!==envelope){frontier.halt('user_goal_changed');return next();}
        userEnvelope=envelope;
        const ready=frontier.ready();
        if(ready)return issue(ready,'frontier');
        return next();
      }
      const candidates:any[]=[];
      for(const program of library.programs)try{
        // Scalar/network targets always require a current semantic choice.
        if(program.argv_contract||program.network_policy)continue;
        if(demandBound&&(!program.predecessor?.program_id||history.at(-1)?.program_id!==program.predecessor.program_id))continue;
        if(program.predecessor&&(!history.length||history.at(-1)?.ok!==true||history.at(-1)?.tool!==program.predecessor.tool))continue;
        const bound=bindScript(program,workspace,demandBound?history.at(-1)?.bound:[]),key=digest([program.id,bound.map((b:any)=>b.sha256)]);
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
        return issue(winner);
      }catch(error:any){audit({kind:'script_fallback',reason:error.name});return next();}
    },
  };
}
