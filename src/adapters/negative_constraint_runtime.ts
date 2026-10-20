/** A portable data-contract predicate; no evaluation of learned Python code. */
export function currentShapeIssues(expected:any,actual:any):any[]|null{
 let steps=0;
 const type=(v:any)=>v===null?'NoneType':Array.isArray(v)?'list':typeof v==='object'?'dict':typeof v==='string'?'str':typeof v==='boolean'?'bool':Number.isInteger(v)?'int':'float';
 function walk(a:any,b:any,path:string,depth:number):any[]{
  if(++steps>30000||depth>32||typeof a==='number'||a===undefined||b===undefined)throw Error('unsupported_current_shape');
  if(type(a)!==type(b))return [{pointer:path,expected_type:type(a),actual_type:type(b)}];
  if(Array.isArray(a)){
   if(a.length!==b.length)return [{pointer:path,expected_items:a.length,actual_items:b.length}];
   return a.flatMap((v,i)=>walk(v,b[i],path+'/'+i,depth+1)).slice(0,32);
  }
  if(a&&typeof a==='object'){
   const ak=Object.keys(a).sort(),bk=Object.keys(b).sort();
   if(JSON.stringify(ak)!==JSON.stringify(bk))return [{pointer:path,expected_keys:ak,actual_keys:bk}];
   return Object.keys(a).flatMap(k=>walk(a[k],b[k],path+'/'+k.replaceAll('~','~0').replaceAll('/','~1'),depth+1)).slice(0,32);
  }return [];
 }
 try{return walk(expected,actual,'',0);}catch{return null;}
}
export function validateCurrentConstraint(guard:any){
 const c=guard?.certification,hash=(v:any)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
 const witness=(r:any)=>typeof r?.task_id==='string'&&r.task_id.length>0&&typeof r.call_id==='string'&&r.call_id.length>0&&hash(r.events_sha256);
 if(guard?.version!==1||guard.kind!=='current_scope_shape'||guard.scope_file!=='review-recovery-scope.json'||typeof guard.tool!=='string'||typeof guard.failure_code!=='string'||!Array.isArray(c?.failures)||!c.failures.every(witness)||new Set(c.failures.map((r:any)=>JSON.stringify([r.task_id,r.call_id]))).size<2||!c.successes?.length||!c.successes.every(witness)||c.interventions?.length!==c.failures.length||!c.interventions.every((i:any)=>i.repair_passed===true&&i.reintroduction_failed===true&&[i.failure_state_sha256,i.repair_state_sha256,i.reintroduction_state_sha256].every(hash)&&i.unrelated_edit_paths?.length>=2))throw Error('uncertified_current_constraint');
 return guard;
}
