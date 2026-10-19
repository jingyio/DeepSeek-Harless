/** Negative Motifs warn first, then quarantine only an unchanged failed retry.
 * They never mark an audit complete, invent repairs or suppress new evidence.
 */
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,relative,isAbsolute,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest,observation} from '../motif_core/online_skill_runtime.mjs';
const sha=(b:any)=>createHash('sha256').update(b).digest('hex');
const root=fileURLToPath(new URL('../../',import.meta.url));
const at=(v:any,path:string[])=>path.reduce((v,k)=>v?.[k],v);
const safe=(base:string,p:string)=>{const r=relative(base,p);return !isAbsolute(r)&&r!=='..'&&!r.startsWith('../');};
export function loadNegativeLibrary(path:string){
 const library=JSON.parse(readFileSync(path,'utf8'));const {digest:claimed,...body}=library;
 if(library.kind!=='negative_tool_motif_library'||library.version!==1||digest(body)!==claimed||
  !Array.isArray(library.rules)||library.rules.length>32||!Object.keys(library.implementation_locks??{}).length||
  !['src/adapters/script_negative_compiler.py','src/adapters/script_negative_runtime.ts','src/adapters/script_motif_web.ts'].every(k=>library.runtime_locks?.[k]))throw Error('invalid_negative_library');
 for(const [name,hash] of Object.entries({...library.implementation_locks,...library.runtime_locks})){
  const p=resolve(root,name);if(!safe(root,p)||sha(readFileSync(p))!==hash)throw Error('negative_implementation_changed');
 }
 for(const r of library.rules){
  const {id,...body}=r;
  if(id!=='negative_'+digest(body).slice(0,16)||!/^mcp__\w+$/.test(r.tool)||!/^\w[\w:-]{0,127}$/.test(r.failure_code)||
   !/^[a-f0-9]{64}$/.test(r.tools_sha256)||!['prompt_only','warn_then_exact_version_block'].includes(r.retry_policy)||
   !Array.isArray(r.version_slots)||r.version_slots.length>8||r.version_slots.some((s:any)=>![s.argument_path,s.result_path].every(p=>Array.isArray(p)&&p.length>0&&p.length<9&&p.every(k=>typeof k==='string'&&!['__proto__','constructor','prototype'].includes(k))))||
   !Array.isArray(r.certification?.failures)||r.certification.failures.length<2||
   new Set(r.certification.failures.map((f:any)=>JSON.stringify([f.task_id,f.call_id]))).size!==r.certification.failures.length||
   !Array.isArray(r.failure_flags)||r.failure_flags.length>8||r.failure_flags.some((p:any)=>!Array.isArray(p)||!p.length||p.length>8||p.some((k:any)=>typeof k!=='string'||['__proto__','constructor','prototype'].includes(k)))||
   r.retry_policy==='warn_then_exact_version_block'&&(!r.failure_flags.length||!r.version_slots.length||!Array.isArray(r.certification.success_contrasts)||!r.certification.success_contrasts.length))throw Error('uncertified_negative_motif');
 }
 return library;
}

export function createNegativeRuntime({library,workspace,mode='prompt',audit=()=>{}}:any){
 if(!['prompt','enforce'].includes(mode))throw Error('invalid_negative_mode');
 let active:any=null,schema:string|null=null,humans:string|undefined;const denied=new Set<string>();
 function sourceVersion(){
  const p=join(workspace,'approved-inputs.json'),raw=readFileSync(p),manifest=JSON.parse(raw.toString());
  const files=Object.entries(manifest.files??{});if(files.length>16)throw Error('negative_source_limit');
  return digest([sha(raw),files.map(([name,expected])=>{
   const p=resolve(workspace,'inputs',name);if(!safe(resolve(workspace,'inputs'),p)||realpathSync(p)!==p||lstatSync(p).size>16_000_000)throw Error('negative_source_not_fixed');
   const version=sha(readFileSync(p));if(version!==expected)throw Error('negative_source_version_changed');
   return [name,version];
  })]);
 }
 function fixed(path:string,version:string){
  try{return safe(workspace,path)&&realpathSync(path)===path&&lstatSync(path).isFile()&&lstatSync(path).size<=2_000_000&&sha(readFileSync(path))===version;}catch{return false;}
 }
 function bind(version:string){
  const matches:string[]=[];let count=0;
  function visit(dir:string,depth=0){
   if(depth>6)return;
   for(const entry of readdirSync(dir,{withFileTypes:true})){
    if(++count>512)throw Error('negative_evidence_scan_limit');
    if(entry.name.startsWith('.')||entry.isSymbolicLink())continue;
    const p=join(dir,entry.name);
    if(entry.isDirectory())visit(p,depth+1);
    else if(entry.isFile()&&entry.name.endsWith('.json')&&fixed(p,version))matches.push(p);
   }
  }
  try{visit(join(workspace,'outputs'));}catch{return null;}
  return matches.length===1?matches[0]:null;
 }
 function current(){
  try{return active&&active.scope===sourceVersion()&&active.anchors.length>0&&active.anchors.every((a:any)=>fixed(a.path,a.version));}catch{return false;}
 }
 return {
  beforeRequest(request:any){
   const envelope=digest((request.messages??[]).filter((m:any)=>m.role==='user'&&m.source?.kind==='user').map((m:any)=>({id:m.id,content:m.content})));
   if(humans!==undefined&&humans!==envelope)active=null;
   humans=envelope;
   schema=digest(request.tools??[]);
   if(active&&active.rule.tools_sha256!==schema)active=null;
   // The warning must be in the actual immutable request, not just generated
   // by a prompt accessor which might never reach the provider.
   if(active&&JSON.stringify([request.system,request.messages?.filter((m:any)=>m.role==='system')]).includes(active.notice)){
    if(!active.warned)audit({kind:'negative_prompt_delivered',motif_id:active.rule.id,notice:active.notice});active.warned=true;
   }
  },
  observe(execution:any,result:any){
   if(execution.name==='bash')return;
   if(result.isError||result.value?.isError){
    if(denied.delete(execution.callId))return;
    if(active?.rule.tool===execution.name)active=null;
    return;
   }
   const value=observation(result,execution.name)??(result.value&&!result.value.content?result.value:null);
   const rule=library.rules.find((r:any)=>r.tool===execution.name&&r.tools_sha256===schema&&r.failure_code===value?.validation_error&&r.failure_flags.every((p:any)=>at(value,p)===false));
   if(!rule){if(active?.rule.tool===execution.name)active=null;return;}
   const args=execution.arguments??{},binding=digest(args);
   if(active?.rule.id===rule.id&&active.binding===binding&&current())return;
   let scope;try{scope=sourceVersion();}catch{return;}
   const anchors=rule.version_slots.map((s:any)=>{const version=at(args,s.argument_path);return typeof version==='string'&&/^[a-f0-9]{64}$/.test(version)&&version===at(value,s.result_path)?{version,path:bind(version)}:null;});
   active={rule,binding,scope,notice:'negative-notice-'+randomUUID(),warned:false,anchors:anchors.every((a:any)=>a?.path)?anchors:[]};
   audit({kind:'negative_current_failure',motif_id:rule.id,binding_sha256:binding,version_bound:active.anchors.length>0});
  },
  prompt(){
   if(!active)return '';
   try{if(active.scope!==sourceVersion()){active=null;return '';}}catch{active=null;return '';}
   if(active.anchors.length&&!current()){active=null;return '';}
   return '\n'+active.notice+'：当前工具 '+active.rule.tool+' 已返回 '+active.rule.failure_code+'；历史真实轨迹也复现了该失败。不要在参数和相关证据版本未变时重复同一调用。先检查并修复上游状态，或改用满足相同验收要求的合法路径；无法修复则说明未完成的交付与证据缺口。不得降低核验要求或声称已完成。'+
    (mode==='enforce'&&active.rule.retry_policy==='warn_then_exact_version_block'&&active.anchors.length?'已提示后，同版本原样重试将被局部早停；新版本、新参数及其他工具仍可用。':'本模式仅提示，不阻止工具。');
  },
  guard(execution:any){
   if(mode!=='enforce'||!active?.warned||active.rule.retry_policy!=='warn_then_exact_version_block'||schema!==active.rule.tools_sha256||
    execution.name!==active.rule.tool||digest(execution.arguments??{})!==active.binding||!current())return;
   audit({kind:'negative_retry_early_stopped',motif_id:active.rule.id,binding_sha256:active.binding,model_requests_skipped:0});
   if(typeof execution.callId==='string'){if(denied.size>=64)denied.clear();denied.add(execution.callId);}
   return 'Negative Motif 已早停同参数、同证据版本的失败重试：'+active.rule.failure_code+'。请修复上游状态或选择合格的替代路径；其他操作仍可用，当前任务不因早停而视为完成。';
  },
 };
}
