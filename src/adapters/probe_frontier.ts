/** Bounded subset diagnosis. Observed failure witnesses, never a causal proof.
 * Caller owns schema/effect/source guards and the native tool lifecycle. */
import {digest} from '../motif_core/online_skill_runtime.mjs';
const clone=(x:any)=>JSON.parse(JSON.stringify(x));
export function probeOutcome(contract:any,result:any){
 if(!result||typeof result!=='object'||result.error||result.validation_error)return 'other';
 if(Object.entries(contract.failure).every(([k,v])=>digest(result[k]??null)===digest(v)))return 'failure';
 if(contract.success_fields.every((k:string)=>result[k]===true))return 'success';
 return 'other';
}
function locations(value:any,path:string[],prefix:(string|number)[]=[]):any[]{
 if(!path.length)return Array.isArray(value)&&value.length>1?[{path:prefix,value}]:[];
 const [key,...tail]=path;
 if(key==='*')return Array.isArray(value)?value.flatMap((v,i)=>locations(v,tail,[...prefix,i])):[];
 if(['__proto__','prototype','constructor'].includes(key)||!value||!Object.hasOwn(value,key))return [];
 return locations(value[key],tail,[...prefix,key]);
}
function replace(value:any,path:(string|number)[],items:any[]){
 if(!path.length)return clone(items);const result=clone(value);let parent=result;
 for(const key of path.slice(0,-1))parent=parent[key];parent[path.at(-1)!]=clone(items);return result;
}
export function createProbeFrontier(contract:any,args:any){
 let witness=clone(args),waiting:any=null,group:any=null,stopped='',count=0;
 const visited=new Set<string>(),history:any[]=[];
 const limit=Math.min(24,contract.max_probes);
 function next(){
  if(waiting||stopped)return null;
  if(count>=limit){stopped='probe_limit';return null;}
  if(!group){
   const found=contract.axes.flatMap((a:any)=>locations(witness,a.path)).find((l:any)=>!visited.has(digest([witness,l.path])));
   if(!found){stopped='learned_axes_exhausted';return null;}
   visited.add(digest([witness,found.path]));
   const mid=Math.ceil(found.value.length/2);
   group={path:found.path,halves:[found.value.slice(0,mid),found.value.slice(mid)],index:0};
  }
  const proposed=replace(witness,group.path,group.halves[group.index]);
  waiting={args:proposed,path:group.path,subset:group.halves[group.index],half:group.index};count++;
  return clone(proposed);
 }
 function observe(result:any){
  if(!waiting)throw Error('probe_without_dispatch');
  const outcome=probeOutcome(contract,result);
  history.push({number:count,path:waiting.path,size:waiting.subset.length,outcome,arguments_sha256:digest(waiting.args)});
  if(outcome==='failure'){witness=waiting.args;group=null;}
  else if(outcome==='success'){
   if(group.index===0)group.index=1;
   else{history.push({path:group.path,outcome:'both_halves_pass_interaction_or_unstable'});group=null;}
  }else stopped='different_failure_or_unverifiable_result';
  waiting=null;
 }
 function stop(reason:string){stopped=reason;waiting=null;}
 function report(){return {kind:'subset_diagnostic_evidence',reason:stopped,probes:count,history,witness_arguments_sha256:digest(witness),witness:clone(witness),
  limitation:'仅证明实际试验过的子集回执；未证明单调性、唯一原因或修复正确。所有成功子集导出均为诊断产物，不能作为完整报告交付。'};}
 return {next,observe,stop,report};
}
