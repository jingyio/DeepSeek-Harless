/** Bounded pure-data tool programs. No JavaScript evaluation or host capabilities. */
import { createHash } from 'node:crypto';
export function canonical(v:any):string {
  if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';
  if(v!==null&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
  return JSON.stringify(v);
}
export const digest=(v:any)=>createHash('sha256').update(canonical(v)).digest('hex');
const bad=new Set(['__proto__','prototype','constructor']);
const arities:any={lit:1,var:1,get:2,array:-1,object:1,map:3,filter:3,unique:1,difference:2,
  concat:-1,count:1,eq:2,not:1,and:-1,or:-1,if:3,type:1,gt:2,join:2,let:3,
  sort:1,split:2,at:2,keys:1};
const identifier=(x:any)=>typeof x==='string'&&/^[a-zA-Z_][a-zA-Z0-9_]{0,31}$/.test(x)&&!bad.has(x);
export function validateProgram(program:any):void {
  if(Buffer.byteLength(JSON.stringify(program)??'')>64000)throw Error('program_too_large');
  let nodes=0;
  function walk(x:any,depth:number){
    if(++nodes>1500||depth>40||!Array.isArray(x)||!Object.hasOwn(arities,x[0])||
      (arities[x[0]]>=0&&x.length!==arities[x[0]]+1)||x.length>64)throw Error('invalid_program_node');
    const op=x[0];
    if(op==='lit'){if(Buffer.byteLength(JSON.stringify(x[1]))>4000)throw Error('literal_too_large');return;}
    if(op==='var'){if(!identifier(x[1]))throw Error('invalid_variable');return;}
    if(op==='object'){
      if(!x[1]||typeof x[1]!=='object'||Array.isArray(x[1])||Object.keys(x[1]).length>32)throw Error('invalid_object');
      for(const [key,v]of Object.entries(x[1])){if(!identifier(key))throw Error('unsafe_field');walk(v,depth+1);}return;
    }
    if(['let','map','filter'].includes(op)){
      const pos=op==='let'?1:2;if(!identifier(x[pos]))throw Error('invalid_binding');
      for(let i=1;i<x.length;i++)if(i!==pos)walk(x[i],depth+1);return;
    }
    for(const child of x.slice(1))walk(child,depth+1);
  }
  walk(program,0);
}
/** A finite operation counter bounds nested maps; input and every output are bounded. */
export function runProgram(program:any,input:any):any {
  validateProgram(program);
  if(Buffer.byteLength(JSON.stringify(input)??'')>192000)throw Error('input_too_large');
  let fuel=200000;
  const array=(v:any)=>{if(!Array.isArray(v)||v.length>2000)throw Error('bounded_array_required');return v;};
  function ev(x:any,env:any):any {
    if(--fuel<0)throw Error('operation_limit');const [op,...a]=x;
    if(op==='lit')return a[0];
    if(op==='var'){if(!Object.hasOwn(env,a[0]))throw Error('unknown_variable');return env[a[0]];}
    if(op==='let')return ev(a[2],{...env,[a[0]]:ev(a[1],env)});
    if(op==='if')return ev(ev(a[0],env)?a[1]:a[2],env);
    if(op==='and')return a.every((e:any)=>Boolean(ev(e,env)));
    if(op==='or')return a.some((e:any)=>Boolean(ev(e,env)));
    if(op==='map'||op==='filter'){
      const xs=array(ev(a[0],env));const f=(v:any)=>ev(a[2],{...env,[a[1]]:v});
      return op==='map'?xs.map(f):xs.filter(f);
    }
    if(op==='object')return Object.fromEntries(Object.entries(a[0]).map(([k,v])=>[k,ev(v,env)]));
    const v=a.map((e:any)=>ev(e,env));
    switch(op){
      case 'get':if((typeof v[1]!=='string'&&!Number.isInteger(v[1]))||bad.has(v[1]))throw Error('unsafe_get');
        return v[0]!==null&&typeof v[0]==='object'&&Object.hasOwn(v[0],v[1])?v[0][v[1]]:null;
      case 'array':return v;
      case 'unique':return [...new Map(array(v[0]).map((e:any)=>[canonical(e),e])).values()];
      case 'difference':{const ys=new Set(array(v[1]).map(canonical));return array(v[0]).filter((e:any)=>!ys.has(canonical(e)));}
      case 'concat':return array(v.flatMap(array));
      case 'count':return array(v[0]).length;
      case 'eq':return canonical(v[0])===canonical(v[1]);
      case 'not':return !v[0];
      case 'type':return v[0]===null?'null':Array.isArray(v[0])?'array':typeof v[0];
      case 'gt':if(v.some((n:any)=>typeof n!=='number'))throw Error('number_required');return v[0]>v[1];
      case 'join':if(typeof v[1]!=='string'||array(v[0]).some((s:any)=>typeof s!=='string'))throw Error('string_array_required');return v[0].join(v[1]);
      case 'sort':{
        const xs=array(v[0]);const kind=typeof xs[0];
        if(xs.some((e:any)=>typeof e!==kind||(kind!=='string'&&kind!=='number')||(kind==='number'&&!Number.isFinite(e))))throw Error('sortable_array_required');
        return xs.slice().sort((a:any,b:any)=>a<b?-1:a>b?1:0);
      }
      case 'split':{
        if(typeof v[0]!=='string'||typeof v[1]!=='string'||v[1].length===0)throw Error('string_separator_required');
        return array(v[0].split(v[1],2001));
      }
      case 'at':{
        const xs=array(v[0]);if(!Number.isInteger(v[1]))throw Error('integer_index_required');
        const index=v[1]<0?xs.length+v[1]:v[1];return index>=0&&index<xs.length?xs[index]:null;
      }
      case 'keys':{
        const value=v[0];
        if(value===null||typeof value!=='object'||Array.isArray(value)||
          (Object.getPrototypeOf(value)!==Object.prototype&&Object.getPrototypeOf(value)!==null))throw Error('plain_object_required');
        const fields=Reflect.ownKeys(value);
        if(fields.length>2000)throw Error('bounded_object_required');
        if(fields.some(key=>typeof key!=='string'||bad.has(key)||
          !Object.hasOwn(Object.getOwnPropertyDescriptor(value,key)!,'value')))throw Error('unsafe_object_fields');
        return Object.keys(value);
      }
      default:throw Error('unknown_op');
    }
  }
  const value=ev(program,{input});
  if(Buffer.byteLength(JSON.stringify(value)??'')>192000)throw Error('output_too_large');return value;
}
export function validateCandidate(c:any){
  if(c?.schema_version!==1||c.name!=='check_report_structure'||typeof c.description!=='string'||c.description.length>800)
    throw Error('invalid_tool_contract');
  validateProgram(c.program);return c;
}
export function runReportCheck(c:any,input:any){
  const value=runProgram(c.program,input),keys=['missing_pairs','unexpected_pairs','duplicate_pairs','source_mismatch','scope_mismatch','malformed'];
  if(!value||typeof value!=='object'||canonical(Object.keys(value).sort())!==canonical(keys.sort()))throw Error('invalid_check_output');
  for(const k of keys.slice().filter(k=>k.endsWith('_pairs'))){
    if(!Array.isArray(value[k])||value[k].length>2000||value[k].some((p:any)=>!Array.isArray(p)||p.length!==2||p.some((s:any)=>typeof s!=='string'||s.length>1000)))throw Error('invalid_check_pairs');
  }
  for(const k of ['source_mismatch','scope_mismatch','malformed'])if(typeof value[k]!=='boolean')throw Error('invalid_check_flags');
  return value;
}
export function validateFrozen(lib:any){
  const {manifest_digest,...body}=lib??{};
  if(lib?.schema_version!==1||lib.kind!=='model_generated_pure_tool'||manifest_digest!==digest(body)||
    lib.certification?.status!=='passed'||lib.certification?.heldout_cases<6||
    !/^[a-f0-9]{64}$/.test(lib.provenance?.cordis_source_sha256??'')||
    lib.candidate_sha256!==digest(lib.candidate))throw Error('unverified_frozen_tool');
  validateCandidate(lib.candidate);return lib;
}
