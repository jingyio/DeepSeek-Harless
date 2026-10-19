/** Data-only validation IR. Unknown input or resource limits always release. */
const sequenceKind=Symbol('python_sequence_kind');
const kind=(v:any)=>v?.[sequenceKind]??'list';
function sequence(values:any[],type:string){const copy=[...values];if(type!=='list')Object.defineProperty(copy,sequenceKind,{value:type});return copy;}
export function validateFieldGuard(guard:any,expectedFailureCode?:string) {
  let nodes=0;
  const path=(p:any)=>Array.isArray(p)&&p.length<=12&&p.every(k=>typeof k==='string'&&!['__proto__','prototype','constructor'].includes(k));
  const binding=(v:any)=>typeof v==='string'&&/^v[1-9][0-9]{0,5}$/.test(v);
  function check(n:any,scope=new Set<string>(),depth=0):void {
    if(!n||++nodes>256||depth>32)throw Error('invalid_field_guard');
    if(n.op==='root'||n.op==='item'&&guard.version===1)return;
    if(n.op==='var'&&binding(n.name)&&scope.has(n.name))return;
    if(n.op==='const'&&(n.value===null||['string','boolean'].includes(typeof n.value)||Number.isSafeInteger(n.value)))return;
    if(['get','get_default'].includes(n.op)&&typeof n.key==='string'&&path([n.key])) {
      check(n.base,scope,depth+1);if(n.op==='get_default')check(n.default,scope,depth+1);return;
    }
    if(['map','exists'].includes(n.op)) {
      check(n.input,scope,depth+1);
      if(guard.version!==1&&!binding(n.binding))throw Error('invalid_field_binding');
      const local=new Set(scope);if(n.binding){if(local.has(n.binding))throw Error('shadowed_field_binding');local.add(n.binding);}
      return check(n.body,local,depth+1);
    }
    if(['array','bool','range'].includes(n.op)) {
      if(n.op==='array'&&n.kind!==undefined&&!['list','tuple'].includes(n.kind))throw Error('invalid_sequence_kind');
      if(!Array.isArray(n.values)||n.values.length>10000||n.op==='bool'&&(!['and','or'].includes(n.mode)||!n.values.length)||n.op==='range'&&(n.values.length<1||n.values.length>3))throw Error('invalid_field_values');
      for(const v of n.values)check(v,scope,depth+1);return;
    }
    if(['len','set','not','keys','any','all','is_type','sequence'].includes(n.op)) {
      if(n.op==='sequence'&&!['list','tuple'].includes(n.kind))throw Error('invalid_sequence_kind');
      if(n.op==='is_type'&&!['str','bool','list','dict'].includes(n.kind))throw Error('ambiguous_json_type');
      return check(n.value,scope,depth+1);
    }
    if(n.op==='compare'&&['eq','ne','lt','le','gt','ge','in','not_in'].includes(n.cmp)||n.op==='arithmetic'&&['add','sub'].includes(n.mode)) {
      check(n.left,scope,depth+1);return check(n.right,scope,depth+1);
    }
    throw Error('unsupported_field_guard');
  }
  const hashes=(v:any)=>Array.isArray(v)&&v.length>0&&v.every(h=>typeof h==='string'&&/^[a-f0-9]{64}$/.test(h));
  const cert=guard?.certification;
  if(![1,2].includes(guard?.version)||!path(guard.state_root)||!Array.isArray(guard.read_paths)||!guard.read_paths.length||guard.read_paths.length>32||!guard.read_paths.every(path)||
    !hashes(cert?.failure_state_sha256)||!hashes(cert?.success_state_sha256)||!Array.isArray(cert?.unrelated_edit_paths)||cert.unrelated_edit_paths.length<2)throw Error('uncertified_field_guard');
  if(guard.version===2) {
    if(typeof guard.failure_code!=='string'||!/^[A-Za-z][A-Za-z0-9_:-]{0,127}$/.test(guard.failure_code)||
      expectedFailureCode!==undefined&&guard.failure_code!==expectedFailureCode||
      cert.cause_interventions?.repair?.result_error===guard.failure_code||cert.cause_interventions?.reintroduction?.result_error!==guard.failure_code)throw Error('inconsistent_cause_error');
    for(const mode of ['repair','reintroduction']) {
      const c=cert.cause_interventions?.[mode];
      if(!hashes([c?.changed_state_sha256])||!Array.isArray(c.changed_paths)||!c.changed_paths.length||c.changed_paths.length>256||
        c.changed_paths.some((p:any)=>!Array.isArray(p)||!p.length||p.length>12||p.some((k:any)=>typeof k!=='string'&&!Number.isSafeInteger(k))))throw Error('uncertified_cause_intervention');
    }
  }
  check(guard.predicate);return guard;
}

function truth(value:any):boolean {
  if(value===null||value===false||value===0||value==='')return false;
  if(Array.isArray(value)||typeof value==='string')return value.length>0;
  if(value instanceof Set)return value.size>0;
  if(typeof value==='object')return Object.keys(value).length>0;
  return true;
}
function equal(a:any,b:any):boolean {
  if(typeof a!==typeof b||(a===null)!==(b===null)||Array.isArray(a)!==Array.isArray(b)||Array.isArray(a)&&kind(a)!==kind(b)||(a instanceof Set)!==(b instanceof Set))throw Error('field_comparison_type');
  if(a instanceof Set)return a.size===b.size&&[...a].every(v=>b.has(v));
  if(Array.isArray(a))return a.length===b.length&&a.every((v,i)=>equal(v,b[i]));
  if(a!==null&&typeof a==='object')throw Error('unsupported_object_comparison');
  return a===b;
}
export function evaluateFieldGuard(guard:any,document:any):boolean|null {
  try {
    let root=document;
    for(const key of guard.state_root){if(!root||typeof root!=='object'||!Object.hasOwn(root,key))return null;root=root[key];}
    let steps=0;
    function run(n:any,variables=new Map<string,any>(),item?:any):any {
      if(++steps>100000)throw Error('field_guard_step_limit');
      const unary=()=>run(n.value,variables,item);
      switch(n.op) {
        case 'root':return root;
        case 'item':return item;
        case 'var':{if(!variables.has(n.name))throw Error('unbound_field_variable');return variables.get(n.name);}
        case 'const':return n.value;
        case 'array':return sequence(n.values.map((v:any)=>run(v,variables,item)),n.kind??'list');
        case 'sequence':{const a=unary();if(!Array.isArray(a)||a.length>10000)throw Error('field_guard_sequence_type');return sequence(a,n.kind);}
        case 'get':case 'get_default': {
          const v=run(n.base,variables,item);
          if(!v||Array.isArray(v)||typeof v!=='object'||v instanceof Set)throw Error('field_guard_object_type');
          if(!Object.hasOwn(v,n.key)){if(n.op==='get_default')return run(n.default,variables,item);throw Error('field_guard_missing_field');}
          return v[n.key];
        }
        case 'map':case 'exists': {
          const a=run(n.input,variables,item);
          if(!Array.isArray(a)||a.length>10000)throw Error('field_guard_array_type');
          const body=(v:any)=>{const local=new Map(variables);if(n.binding)local.set(n.binding,v);return run(n.body,local,v);};
          return n.op==='exists'?a.some(v=>truth(body(v))):a.map(body);
        }
        case 'bool': {
          let answer:any=n.mode==='and';
          for(const v of n.values){answer=run(v,variables,item);if(truth(answer)===(n.mode==='or'))break;}
          return answer;
        }
        case 'not':return !truth(unary());
        case 'any':case 'all':{const a=unary();if(!Array.isArray(a)||a.length>10000)throw Error('field_guard_array_type');return n.op==='any'?a.some(truth):a.every(truth);}
        case 'is_type': {
          const v=unary();return {str:typeof v==='string',bool:typeof v==='boolean',list:Array.isArray(v)&&kind(v)==='list',dict:v!==null&&typeof v==='object'&&!Array.isArray(v)&&!(v instanceof Set)}[n.kind];
        }
        case 'keys':{const a=unary();if(!a||typeof a!=='object'||Array.isArray(a)||a instanceof Set)throw Error('field_guard_object_type');return new Set(Object.keys(a));}
        case 'set':{const a=unary();if(a instanceof Set)return a;if(!Array.isArray(a)||a.some(v=>typeof v!=='string'))throw Error('field_guard_set_type');return new Set(a);}
        case 'len':{const a=unary();if(a instanceof Set)return a.size;if(Array.isArray(a))return a.length;if(typeof a==='string')return [...a].length;throw Error('field_guard_length_type');}
        case 'range': {
          const args=n.values.map((v:any)=>run(v,variables,item));
          if(args.some((v:any)=>!Number.isSafeInteger(v)||Math.abs(v)>10000))throw Error('field_guard_range_bounds');
          const [start,stop,step]=args.length===1?[0,args[0],1]:[args[0],args[1],args[2]??1];
          if(!step)throw Error('field_guard_range_step');
          const result=[];for(let v=start;step>0?v<stop:v>stop;v+=step){if(result.length>=10000)throw Error('field_guard_range_bounds');result.push(v);}return sequence(result,'range');
        }
        case 'arithmetic': {
          const a=run(n.left,variables,item),b=run(n.right,variables,item),result=n.mode==='add'?a+b:a-b;
          if(!Number.isSafeInteger(a)||!Number.isSafeInteger(b)||!Number.isSafeInteger(result))throw Error('field_guard_arithmetic_type');return result;
        }
        case 'compare': {
          const a=run(n.left,variables,item),b=run(n.right,variables,item);
          if(['in','not_in'].includes(n.cmp)) {
            const values=b instanceof Set?[...b]:b;
            if(typeof a!=='string'||!Array.isArray(values)||values.some(v=>typeof v!=='string'))throw Error('field_guard_membership_type');
            return n.cmp==='in'?values.includes(a):!values.includes(a);
          }
          if(['eq','ne'].includes(n.cmp)){const same=equal(a,b);return n.cmp==='eq'?same:!same;}
          if(a instanceof Set&&b instanceof Set) {
            const subset=[...a].every(v=>b.has(v)),superset=[...b].every(v=>a.has(v));
            return {le:subset,lt:subset&&a.size<b.size,ge:superset,gt:superset&&a.size>b.size}[n.cmp];
          }
          if(!Number.isSafeInteger(a)||!Number.isSafeInteger(b))throw Error('field_guard_compare_type');
          return {lt:a<b,le:a<=b,gt:a>b,ge:a>=b}[n.cmp];
        }
        default:throw Error('unsupported_field_guard');
      }
    }
    const answer=run(guard.predicate);return typeof answer==='boolean'?answer:null;
  } catch {return null;}
}
