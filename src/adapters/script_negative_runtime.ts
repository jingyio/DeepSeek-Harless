/** Negative Motifs warn first, then quarantine only an unchanged failed retry.
 * They never mark an audit complete, invent repairs or suppress new evidence.
 */
import {createHash,randomUUID} from 'node:crypto';
import {readFileSync,readdirSync,lstatSync,realpathSync} from 'node:fs';
import {resolve,relative,isAbsolute,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {digest,observation} from '../motif_core/online_skill_runtime.mjs';
import {validateFieldGuard,evaluateFieldGuard} from './negative_field_runtime.ts';
import {negativeOutcome} from './negative_outcome.ts';
import {currentShapeIssues,validateCurrentConstraint} from './negative_constraint_runtime.ts';
const sha=(b:any)=>createHash('sha256').update(b).digest('hex');
const root=fileURLToPath(new URL('../../',import.meta.url));
const at=(v:any,path:string[])=>path.reduce((v,k)=>v?.[k],v);
const safe=(base:string,p:string)=>{const r=relative(base,p);return !isAbsolute(r)&&r!=='..'&&!r.startsWith('../');};
export function loadNegativeLibrary(path:string){
 const library=JSON.parse(readFileSync(path,'utf8'));const {digest:claimed,...body}=library;
 if(library.kind!=='negative_tool_motif_library'||library.version!==1||digest(body)!==claimed||
  !Array.isArray(library.rules)||library.rules.length>32||!Object.keys(library.implementation_locks??{}).length||
   !['src/adapters/script_negative_compiler.py','src/adapters/script_negative_runtime.ts','src/adapters/script_motif_web.ts','src/adapters/negative_field_compiler.py','src/adapters/negative_field_runtime.ts','src/adapters/negative_outcome.py','src/adapters/negative_outcome.ts','src/adapters/negative_constraint_compiler.py','src/adapters/negative_constraint_runtime.ts'].every(k=>library.runtime_locks?.[k]))throw Error('invalid_negative_library');
 for(const [name,hash] of Object.entries({...library.implementation_locks,...library.runtime_locks})){
  const p=resolve(root,name);if(!safe(root,p)||sha(readFileSync(p))!==hash)throw Error('negative_implementation_changed');
 }
 for(const r of library.rules){
  const {id,...body}=r;
  if(id!=='negative_'+digest(body).slice(0,16)||!/^mcp__\w+$/.test(r.tool)||!/^\w[\w:-]{0,127}$/.test(r.failure_code)||
   !/^[a-f0-9]{64}$/.test(r.tools_sha256)||!['prompt_only','warn_then_exact_version_block','warn_then_field_guard','warn_then_current_constraint'].includes(r.retry_policy)||
   r.failure_source!==undefined&&!['validation_error','failed_checks'].includes(r.failure_source)||
   !Array.isArray(r.version_slots)||r.version_slots.length>8||r.version_slots.some((s:any)=>![s.argument_path,s.result_path].every(p=>Array.isArray(p)&&p.length>0&&p.length<9&&p.every(k=>typeof k==='string'&&!['__proto__','constructor','prototype'].includes(k))))||
   !Array.isArray(r.certification?.failures)||r.certification.failures.length<2||
   new Set(r.certification.failures.map((f:any)=>JSON.stringify([f.task_id,f.call_id]))).size!==r.certification.failures.length||
   !Array.isArray(r.failure_flags)||r.failure_flags.length>8||r.failure_flags.some((p:any)=>!Array.isArray(p)||!p.length||p.length>8||p.some((k:any)=>typeof k!=='string'||['__proto__','constructor','prototype'].includes(k)))||
   !['prompt_only','warn_then_current_constraint'].includes(r.retry_policy)&&(!r.failure_flags.length||!r.version_slots.length||!Array.isArray(r.certification.success_contrasts)||!r.certification.success_contrasts.length))throw Error('uncertified_negative_motif');
  if(r.retry_policy==='warn_then_current_constraint'){
   validateCurrentConstraint(r.argument_guard);
   const file=r.argument_guard.validator?.split(':')[0];
   const pairs=new Set(r.certification.failures.map((w:any)=>JSON.stringify([w.task_id,w.call_id,w.events_sha256])));
   if(r.failure_source!=='failed_checks'||r.argument_guard.tool!==r.tool||r.argument_guard.failure_code!==r.failure_code||r.argument_guard.certification.failures.some((w:any)=>!pairs.has(JSON.stringify([w.task_id,w.call_id,w.events_sha256])))||!file||library.implementation_locks[file]!==r.argument_guard.validator_sha256)throw Error('unbound_current_constraint');
  }
  if(r.guidance!==undefined&&(typeof r.guidance!=='string'||r.guidance.trim()!==r.guidance||r.guidance.length<24||r.guidance.length>600||/[\x00-\x1f]/.test(r.guidance)||
    r.retry_policy!=='prompt_only'||r.guidance_review?.scope!=='reviewed_historical_advice_not_causal_proof_or_execution_authority'||
    !/^[a-f0-9]{64}$/.test(r.guidance_review?.evidence_digest)||!/^[a-f0-9]{64}$/.test(r.guidance_review?.review_cache_digest)))throw Error('unreviewed_negative_guidance');
  if(r.tool_schema_sha256!==undefined||r.schema_scope!==undefined){
   if(r.retry_policy!=='prompt_only'||r.schema_scope!=='exact_tool_schema_prompt_only'||!/^[a-f0-9]{64}$/.test(r.tool_schema_sha256)||
      r.certification.failures.some((w:any)=>w.tool_schema_sha256!==r.tool_schema_sha256))throw Error('unbound_prompt_tool_schema');
  }
  if(r.retry_policy==='warn_then_field_guard'){
   validateFieldGuard(r.field_guard,r.failure_code);
   const file=r.field_guard.validator?.split(':')[0];
   if(r.version_slots.length!==1||library.implementation_locks[file]!==r.field_guard.validator_sha256)throw Error('unbound_field_validator');
  }
 }
 return library;
}

export function createNegativeRuntime({library,workspace,mode='prompt',audit=()=>{}}:any){
 if(!['prompt','enforce'].includes(mode))throw Error('invalid_negative_mode');
 let active:any=null,schema:string|null=null,humans:string|undefined,noticeSent='';const denied=new Set<string>(),toolSchemas=new Map<string,string>();
 const compatible=(rule:any)=>rule.tool_schema_sha256?rule.tool_schema_sha256===toolSchemas.get(rule.tool):rule.tools_sha256===schema;
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
  try{
   if(!active||active.scope!==sourceVersion())return false;
   if(active.rule.retry_policy==='warn_then_current_constraint')return goalState()?.context===active.goal_context;
   if(!active.anchors.length)return false;
   if(active.rule.retry_policy!=='warn_then_field_guard')return active.anchors.every((a:any)=>fixed(a.path,a.version));
   const state=fieldState();return state?.holds===true&&state.context===active.field_context;
  }catch{return false;}
 }
 function goalState():any{
  try{
   const read=(name:string)=>{const path=join(workspace,name);if(realpathSync(path)!==path||!lstatSync(path).isFile()||lstatSync(path).size>1_000_000)throw Error('current_goal_not_fixed');return readFileSync(path);};
   const raw=read('review-recovery-scope.json'),goal=JSON.parse(raw.toString()),grantRaw=read('paper-output-grant.json'),grant=JSON.parse(grantRaw.toString()),approved=JSON.parse(read('approved-inputs.json').toString()).files;
   if(goal.kind!=='current_review_recovery_scope'||goal.version!==1||goal.policy!=='preserve_structure_allow_semantic_leaf_revisions'||!['explicit_current_recovery_requirement_not_inferred_from_history','observed_current_export_operation_not_semantic_approval'].includes(goal.origin)||!goal.task_id||grant.schema_version!==1||grant.task_id!==goal.task_id||grant.allow_output!==true||digest(goal.source_versions)!==digest(approved)||digest(goal.arguments?.source_versions)!==digest(approved))return null;
   if(goal.origin==='observed_current_export_operation_not_semantic_approval'){
    const policyRaw=read('report-state-policy.json'),policy=JSON.parse(policyRaw.toString());
    if(policy.kind!=='capture_current_report_policy'||policy.version!==1||policy.task_id!==goal.task_id||digest(policy.source_versions)!==digest(approved)||policy.user_envelope_sha256!==humans||policy.tool!==active?.rule.tool||policy.schema_sha256!==toolSchemas.get(policy.tool)||goal.capture?.arguments_sha256!==digest(goal.arguments)||goal.capture?.policy_sha256!==sha(policyRaw)||goal.capture?.tool!==policy.tool||goal.capture?.schema_sha256!==policy.schema_sha256||goal.capture?.user_envelope_sha256!==policy.user_envelope_sha256)return null;
   }
   return {goal,grant,hash:sha(raw),context:digest([sha(raw),sha(grantRaw),approved])};
  }catch{return null;}
 }
 function update(request:any){
  const envelope=digest((request.messages??[]).filter((m:any)=>m.role==='user'&&m.source?.kind==='user').map((m:any)=>({id:m.id,content:m.content})));
  if(humans!==undefined&&humans!==envelope)active=null;humans=envelope;schema=digest(request.tools??[]);
  toolSchemas.clear();for(const tool of request.tools??[])toolSchemas.set(tool.name,digest(tool.parameters));
  if(active&&!compatible(active.rule))active=null;
 }
 function fieldState():any{
  try{
   if(active?.anchors.length!==1)return null;
   const path=active.anchors[0].path;
   if(!safe(workspace,path)||realpathSync(path)!==path||!lstatSync(path).isFile()||lstatSync(path).size>2_000_000)return null;
   const raw=readFileSync(path);if(raw.length>2_000_000)return null;
   const document=JSON.parse(raw.toString('utf8')),context=JSON.parse(JSON.stringify(document)),pathToRoot=active.rule.field_guard.state_root;
   let parent=context;
   for(const key of pathToRoot.slice(0,-1)){if(!parent||!Object.hasOwn(parent,key))return null;parent=parent[key];}
   if(pathToRoot.length){const key=pathToRoot.at(-1);if(!parent||!Object.hasOwn(parent,key))return null;parent[key]='__GUARDED_DOCUMENT__';}
   return {holds:evaluateFieldGuard(active.rule.field_guard,document),version:sha(raw),context:digest(pathToRoot.length?context:'__GUARDED_DOCUMENT__')};
  }catch{return null;}
 }
 function nonVersionBinding(args:any,rule:any){
  const copy=JSON.parse(JSON.stringify(args));
  for(const slot of rule.version_slots){
   let parent=copy;for(const key of slot.argument_path.slice(0,-1)){if(!parent||!Object.hasOwn(parent,key))throw Error('missing_version_binding');parent=parent[key];}
   const key=slot.argument_path.at(-1);if(!parent||!Object.hasOwn(parent,key))throw Error('missing_version_binding');parent[key]='__CURRENT_VERIFIED_VERSION__';
  }
  return digest(copy);
 }
 return {
  update,
  beforeRequest(request:any){
   update(request);
   // The warning must be in the actual immutable request, not just generated
   // by a prompt accessor which might never reach the provider.
   if(active&&JSON.stringify([request.system,request.messages?.filter((m:any)=>m.role==='system'||m.source?.kind==='plugin'&&m.source?.plugin==='script-motif-negative')]).includes(active.notice)){
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
   const outcome=negativeOutcome(value);
   const rule=library.rules.find((r:any)=>r.tool===execution.name&&compatible(r)&&outcome.failures.some(f=>f.code===r.failure_code&&f.source===(r.failure_source??'validation_error'))&&r.failure_flags.every((p:any)=>at(value,p)===false));
   if(!rule){if(active?.rule.tool===execution.name)active=null;return;}
   const args=execution.arguments??{},binding=digest(args);
   if(active?.rule.id===rule.id&&active.binding===binding&&current())return;
   let scope;try{scope=sourceVersion();}catch{return;}
   const anchors=rule.version_slots.map((s:any)=>{const version=at(args,s.argument_path);return typeof version==='string'&&/^[a-f0-9]{64}$/.test(version)&&version===at(value,s.result_path)?{version,path:bind(version)}:null;});
   let basis=null;try{basis=nonVersionBinding(args,rule);}catch{}
   active={rule,binding,binding_basis:basis,scope,notice:'negative-notice-'+randomUUID(),warned:false,anchors:anchors.every((a:any)=>a?.path)?anchors:[]};
   if(rule.retry_policy==='warn_then_current_constraint'){
    const state=goalState(),e=value?.execution_evidence,issues=state&&currentShapeIssues(state.goal.arguments,args);
    let valid=false;try{valid=!!state&&!!issues?.length&&digest(issues)===digest(value.scope_issues)&&e?.version===1&&e.kind==='review_execution_evidence'&&e.arguments_sha256===digest(args)&&e.recovery_scope_sha256===state.hash&&e.task_id===state.goal.task_id&&digest(e.source_versions)===digest(state.goal.source_versions)&&digest(args.source_versions)===digest(state.goal.source_versions)&&e.grant_sha256===digest(state.grant);}catch{}
    if(!valid){active=null;return;}
    active.goal_context=state.context;active.issues=issues;
   }
   active.observation=value?.validation_context?{page_count:value.validation_context.page_count,checks:value.validation_context.checks,reason:value.validation_context.reason}:undefined;
   if(rule.retry_policy==='warn_then_field_guard')active.field_context=fieldState()?.context;
   audit({kind:'negative_current_failure',motif_id:rule.id,library_digest:library.digest,guidance_reviewed:!!rule.guidance,binding_sha256:binding,version_bound:active.anchors.length>0});
  },
  prompt(){
   if(!active)return '';
   try{if(active.scope!==sourceVersion()){active=null;return '';}}catch{active=null;return '';}
   if((active.anchors.length||active.goal_context)&&!current()){active=null;return '';}
   return '\n'+active.notice+'：当前工具 '+active.rule.tool+' 已返回 '+active.rule.failure_code+'；历史真实轨迹也复现了该失败。不要在参数和相关证据版本未变时重复同一调用。先检查并修复上游状态，或改用满足相同验收要求的合法路径；无法修复则说明未完成的交付与证据缺口。不得降低核验要求或声称已完成。'+
    (active.rule.guidance?'经审核的历史修复建议（仅供检查，不代表当前根因）：'+active.rule.guidance+'。':'')+
    (active.issues?'经双向认证并绑定当前完整目标的必要约束：'+JSON.stringify(active.issues)+'。只改其他字段不会消除这些结构错误；请保持完整原稿，仅提交必要叶子patch。改变报告结构需要新的明确任务范围，不要重复提交相同不满足条件的形状。':'')+
    (active.observation?'当前校验观测（不等于根因）：'+JSON.stringify(active.observation)+'。只有当前检查确证的约束可用于修订；未知原因不得编造。':'')+
    (active.rule.retry_policy==='warn_then_field_guard'?'自动编译的相关字段为 '+JSON.stringify(active.rule.field_guard.read_paths)+(active.anchors.length?'；Runtime 已重算失败条件，它仍成立。仅改无关字段或更换版本号不会修复该条件；条件消失、参数语义变化或证据不足时放行。':'；当前状态无法唯一绑定，仅提示，不自动拦截。'):'')+
    (mode==='enforce'&&active.rule.retry_policy!=='prompt_only'&&(active.anchors.length||active.goal_context)?'已提示后，不满足已验证条件的重试将被局部早停；其他工具仍可用。':'没有可执行原因条件，仅提示，不阻止工具。');
  },
  takeNotice(){if(!active||noticeSent===active.notice)return '';const text=this.prompt();if(!text)return '';noticeSent=active.notice;return text;},
  currentConstraint(){
   if(active?.rule.retry_policy!=='warn_then_current_constraint'||!current())return null;
   return {motif_id:active.rule.id,failure_code:active.rule.failure_code,failure_arguments_sha256:active.binding,scope_sha256:goalState()?.hash,issues:active.issues};
  },
  guard(execution:any){
   if(mode!=='enforce'||!active?.warned||active.rule.retry_policy==='prompt_only'||schema!==active.rule.tools_sha256||execution.name!==active.rule.tool||!current())return;
   let state:any=null;
   try{
    if(active.rule.retry_policy==='warn_then_current_constraint'){
     const goal=goalState();if(!goal||goal.context!==active.goal_context||digest(execution.arguments?.source_versions)!==digest(goal.goal.source_versions))return;
     const issues=currentShapeIssues(goal.goal.arguments,execution.arguments);if(!issues?.length)return;active.issues=issues;
     state={version:digest(execution.arguments),issues};
    }else if(active.rule.retry_policy==='warn_then_field_guard'){
     state=fieldState();
     if(state?.holds!==true||state.context!==active.field_context||at(execution.arguments,active.rule.version_slots[0].argument_path)!==state.version||nonVersionBinding(execution.arguments,active.rule)!==active.binding_basis)return;
    }else if(digest(execution.arguments??{})!==active.binding)return;
   }catch{return;}
   if(!denied.has(execution.callId))audit({kind:'negative_retry_early_stopped',call_id:execution.callId,motif_id:active.rule.id,binding_sha256:digest(execution.arguments),guard_kind:active.rule.retry_policy,state_sha256:state?.version,dependent_fields:active.rule.field_guard?.read_paths,model_requests_skipped:0});
   if(typeof execution.callId==='string'){if(denied.size>=64)denied.clear();denied.add(execution.callId);}
   return 'Negative Motif 已早停失败条件仍成立的重试：'+active.rule.failure_code+(state?.issues?'。当前必要约束：'+JSON.stringify(state.issues):'')+'。请修复相关字段或选择合格的替代路径；其他操作仍可用，当前任务不因早停而视为完成。';
  },
 };
}
