/** Versioned JSON edit plans. Algorithms come from a frozen RSI program;
 * this module supplies row addressing, permissions and bounded application.
 */
import {canonical,digest} from './paper_rsi_program.ts';
import {runTraceTool,validateTraceFrozen,validateTraceCandidate} from './trace_rsi_program.ts';

const object=(v:any)=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const clone=(v:any)=>JSON.parse(JSON.stringify(v));
const unsafe=new Set(['__proto__','prototype','constructor']);
function exact(v:any,keys:string[],label:string):void {
  if(!object(v)||canonical(Object.keys(v).sort())!==canonical(keys.slice().sort()))throw Error(label);
}
function bounded(v:any):void {
  let nodes=0;const seen=new Set<any>();
  function visit(x:any,depth:number):void {
    if(++nodes>20000||depth>48)throw Error('patch_data_limit');
    if(x===null||typeof x==='string'||typeof x==='boolean'||(typeof x==='number'&&Number.isFinite(x)))return;
    if(typeof x!=='object'||seen.has(x))throw Error('patch_json_required');
    const proto=Object.getPrototypeOf(x);
    if(Array.isArray(x)?proto!==Array.prototype||x.length>2000||Reflect.ownKeys(x).length!==x.length+1:
      proto!==Object.prototype&&proto!==null)throw Error('patch_plain_json_required');
    seen.add(x);
    for(const k of Reflect.ownKeys(x)){
      if(typeof k!=='string'||unsafe.has(k))throw Error('patch_unsafe_field');
      if(Array.isArray(x)&&k==='length')continue;
      const d=Object.getOwnPropertyDescriptor(x,k)!;
      if(!d.enumerable||!Object.hasOwn(d,'value'))throw Error('patch_data_fields_required');
      visit(d.value,depth+1);
    }
    seen.delete(x);
  }
  visit(v,0);if(Buffer.byteLength(JSON.stringify(v))>192000)throw Error('patch_data_too_large');
}
export function validateRevisionPlan(plan:any):any {
  bounded(plan);exact(plan,['set_ids','keep_once_keys','remove_keys','add_records'],'invalid_revision_plan');
  for(const k of ['set_ids','keep_once_keys','remove_keys','add_records'])
    if(!Array.isArray(plan[k])||plan[k].length>256)throw Error('bounded_revision_plan_required');
  const key=(v:any)=>typeof v==='string'&&v.length>0&&v.length<=1000&&!unsafe.has(v);
  for(const row of plan.set_ids){exact(row,['key','arxiv_id'],'invalid_id_update');if(!key(row.key)||!key(row.arxiv_id))throw Error('invalid_id_update');}
  for(const k of ['keep_once_keys','remove_keys'])if(plan[k].some((v:any)=>!key(v))||new Set(plan[k]).size!==plan[k].length)throw Error('unique_plan_keys_required');
  for(const row of plan.add_records){
    exact(row,['key','arxiv_id','status'],'minimal_placeholder_required');
    if(!key(row.key)||!key(row.arxiv_id)||row.status!=='待进一步核验')throw Error('minimal_placeholder_required');
  }
  if(new Set(plan.set_ids.map((r:any)=>r.key)).size!==plan.set_ids.length||
    new Set(plan.add_records.map((r:any)=>r.key)).size!==plan.add_records.length||
    plan.remove_keys.some((k:string)=>plan.keep_once_keys.includes(k)||plan.set_ids.some((r:any)=>r.key===k)))throw Error('conflicting_revision_plan');
  return plan;
}
/** Enumeration is data addressing; no repair or selection is decided here. */
export function revisionPatchInput(report:any,plan:any):any {
  bounded(report);validateRevisionPlan(plan);
  if(!object(report)||!Array.isArray(report.references)||report.references.some((r:any)=>!object(r)||typeof r.key!=='string'))throw Error('reference_records_required');
  const rows=report.references.map((r:any,i:number)=>({key:r.key,path:'/references/'+i,id_path:'/references/'+i+'/arxiv_id'}));
  const keys=new Set(rows.map((r:any)=>r.key));
  if([...plan.keep_once_keys,...plan.remove_keys,...plan.set_ids.map((r:any)=>r.key)].some(k=>!keys.has(k)))throw Error('unknown_plan_key');
  if(plan.add_records.some((r:any)=>keys.has(r.key)))throw Error('placeholder_key_already_present');
  for(const k of plan.keep_once_keys){
    const same=report.references.filter((r:any)=>r.key===k).map((r:any)=>canonical(Object.fromEntries(Object.entries(r).filter(([field])=>field!=='arxiv_id'))));
    if(new Set(same).size>1)throw Error('duplicate_versions_require_semantic_resolution');
  }
  return {rows,rows_reverse:rows.slice().reverse(),plan:clone(plan)};
}
/** The model supplies paths/order. Invalid output cannot alter the original.
 * Fixed permissions allow ID replacement, row deletion and minimal append only.
 */
export function applyGeneratedRevision(report:any,plan:any,frozen:any):any {
  const tool=validateTraceFrozen(frozen);
  return applyPublishedRevision(report,plan,tool.candidate);
}
/** Only administrator-pinned published candidates reach this entry; permissions remain identical. */
export function applyPublishedRevision(report:any,plan:any,candidate:any):any {
  const input=revisionPatchInput(report,plan);
  validateTraceCandidate(candidate);
  const out=runTraceTool(candidate,input);
  exact(out,['replacements','removals','additions'],'invalid_generated_patch_output');
  for(const k of ['replacements','removals','additions'])if(!Array.isArray(out[k])||out[k].length>2000)throw Error('bounded_generated_patch_required');
  const current=clone(report),replaced=new Set(),removed=new Set();
  for(const op of out.replacements){
    exact(op,['path','value'],'invalid_generated_replacement');
    const match=typeof op.path==='string'&&/^\/references\/(0|[1-9][0-9]*)\/arxiv_id$/.exec(op.path);
    const i=match?Number(match[1]):-1,old=current.references[i];
    if(!old||replaced.has(i)||!plan.set_ids.some((r:any)=>r.key===old.key&&r.arxiv_id===op.value))throw Error('replacement_outside_plan');
    replaced.add(i);old.arxiv_id=op.value;
  }
  let previous=Infinity;
  for(const path of out.removals){
    const match=typeof path==='string'&&/^\/references\/(0|[1-9][0-9]*)$/.exec(path);
    const i=match?Number(match[1]):-1,old=report.references[i];
    if(!old||i>=previous||removed.has(i)||!(plan.remove_keys.includes(old.key)||
      (plan.keep_once_keys.includes(old.key)&&report.references.findIndex((r:any)=>r.key===old.key)!==i)))throw Error('removal_outside_plan_or_wrong_order');
    previous=i;removed.add(i);current.references.splice(i,1);
  }
  if(canonical(out.additions)!==canonical(plan.add_records))throw Error('addition_outside_plan');
  current.references.push(...clone(out.additions));
  // Check requested postconditions. This is a verifier, never a fallback repair.
  for(const r of plan.set_ids)if(current.references.some((v:any)=>v.key===r.key&&v.arxiv_id!==r.arxiv_id))throw Error('generated_id_update_incomplete');
  for(const k of plan.keep_once_keys)if(current.references.filter((v:any)=>v.key===k).length!==1)throw Error('generated_dedup_incomplete');
  for(const k of plan.remove_keys)if(current.references.some((v:any)=>v.key===k))throw Error('generated_removal_incomplete');
  bounded(current);return {report:current,patch_output:clone(out),plan_sha256:digest(plan),program_sha256:digest(candidate)};
}

/** Complete structured contents remain in the artifact. No fact is synthesized. */
export function renderRevisionMarkdown(before:any,after:any,check:any):string {
  bounded(before);bounded(after);bounded(check);
  const count=(r:any)=>Array.isArray(r?.references)?r.references.length:0;
  return ['# 参考文献结构修订报告','',
    '> 范围：配对覆盖、去重、标识修订和字段保留。本阶段未核验文献真实性或正式发表版本。','',
    '## 结构检查','',`- 修订前对象数：${count(before)}`,`- 当前对象数：${count(after)}`,
    '- 下列指标来自当前版本的生成检查工具；false 或未提供的指标不视为通过。','',
    '```json',JSON.stringify(check,null,2),'```','',
    '## 修订依据与全部当前内容','',
    '目录中的源稿标识用于配对；去重只允许等价已有版本，缺失条目保留“待进一步核验”占位。',
    '已有判断和来源按当前报告完整列出，并不代表本阶段重新核验这些科研结论。','',
    '```json',JSON.stringify(after,null,2),'```','',
    '## 修订前快照','',
    '```json',JSON.stringify(before,null,2),'```',''].join('\n');
}
