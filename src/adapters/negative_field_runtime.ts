/** Bounded data IR, not Python/JS evaluation. Unknown/type changes fall back. */
export function validateFieldGuard(guard:any){
 let nodes=0;
 const path=(p:any)=>Array.isArray(p)&&p.length<=12&&p.every(k=>typeof k==='string'&&!['__proto__','prototype','constructor'].includes(k));
 function check(n:any,depth=0):void{
  if(!n||++nodes>256||depth>32)throw Error('invalid_field_guard');
  if(['root','item'].includes(n.op))return;
  if(n.op==='const'&&(n.value===null||['string','boolean'].includes(typeof n.value)||Number.isSafeInteger(n.value)))return;
  if(n.op==='get'&&typeof n.key==='string'&&path([n.key]))return check(n.base,depth+1);
  if(n.op==='map'){check(n.input,depth+1);return check(n.body,depth+1);}
  if(['len','set'].includes(n.op))return check(n.value,depth+1);
  if(n.op==='compare'&&['eq','ne','lt','le','gt','ge'].includes(n.cmp)){check(n.left,depth+1);return check(n.right,depth+1);}
  throw Error('unsupported_field_guard');
 }
 if(guard?.version!==1||!path(guard.state_root)||!Array.isArray(guard.read_paths)||!guard.read_paths.length||guard.read_paths.length>32||!guard.read_paths.every(path)||
  !guard.certification?.failure_state_sha256?.length||!guard.certification?.success_state_sha256?.length||!Array.isArray(guard.certification?.unrelated_edit_paths)||guard.certification.unrelated_edit_paths.length<2)throw Error('uncertified_field_guard');
 check(guard.predicate);return guard;
}
export function evaluateFieldGuard(guard:any,document:any):boolean|null{
 try{
  let root=document;for(const key of guard.state_root){if(!root||!Object.hasOwn(root,key))return null;root=root[key];}
  let steps=0;
  function run(n:any,item?:any):any{
   if(++steps>100000)throw Error('field_guard_step_limit');
   switch(n.op){
    case 'root':return root;
    case 'item':return item;
    case 'const':return n.value;
    case 'get':{const v=run(n.base,item);if(!v||Array.isArray(v)||typeof v!=='object'||!Object.hasOwn(v,n.key))throw Error('field_guard_missing_field');return v[n.key];}
    case 'map':{const a=run(n.input,item);if(!Array.isArray(a)||a.length>10000)throw Error('field_guard_array_type');return a.map(v=>run(n.body,v));}
    case 'set':{const a=run(n.value,item);if(!Array.isArray(a)||a.some(v=>typeof v!=='string'))throw Error('field_guard_set_type');return [...new Set(a)];}
    case 'len':{const a=run(n.value,item);if(Array.isArray(a))return a.length;if(typeof a==='string')return [...a].length;throw Error('field_guard_length_type');}
    case 'compare':{const a=run(n.left,item),b=run(n.right,item);if(!Number.isSafeInteger(a)||!Number.isSafeInteger(b))throw Error('field_guard_compare_type');return {eq:a===b,ne:a!==b,lt:a<b,le:a<=b,gt:a>b,ge:a>=b}[n.cmp];}
    default:throw Error('unsupported_field_guard');
   }
  }
  const answer=run(guard.predicate);return typeof answer==='boolean'?answer:null;
 }catch{return null;}
}
