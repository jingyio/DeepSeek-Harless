/** Generic syntax sugar for pure object comparisons. No domain algorithm or IO.
 * Lowered artifacts still execute in the unchanged bounded JSON interpreter.
 */
import { validateProgram } from './paper_rsi_program.ts';

export function lowerRevisionProgram(value:any):any {
  const names=new Set<string>(), ancestors=new Set<any>();let count=0;
  function normalize(v:any,depth=0):any {
    if (++count>20000 || depth>48) throw Error('macro_submission_too_complex');
    if (typeof v==='string') {names.add(v);return v;}
    if(v===null || typeof v==='boolean' || (typeof v==='number' && Number.isFinite(v))) return v;
    if(typeof v!=='object' || ancestors.has(v)) throw Error('macro_json_data_required');
    const array=Array.isArray(v), proto=Object.getPrototypeOf(v), keys=Reflect.ownKeys(v);
    if(!array && proto!==null && Object.getPrototypeOf(proto)!==null) throw Error('macro_plain_data_required');
    if(keys.some(k=>typeof k!=='string') || (array && (v.length>2000 || keys.length!==v.length+1)))
      throw Error('macro_dense_json_required');
    ancestors.add(v);const result:any=array?[]:{};
    for(const key of keys as string[]) {
      if(array && key==='length')continue;
      if(['__proto__','prototype','constructor'].includes(key))throw Error('unsafe_macro_field');
      const d=Object.getOwnPropertyDescriptor(v,key)!;
      if(!d.enumerable || !Object.hasOwn(d,'value'))throw Error('macro_data_property_required');
      result[key]=normalize(d.value,depth+1);
    }
    ancestors.delete(v);return result;
  }
  const program=normalize(value);if(Buffer.byteLength(JSON.stringify(program))>64000)throw Error('macro_program_too_large');
  let serial=0;
  const fresh=()=>{let n;do{n='_rsi_m'+serial++;}while(names.has(n));names.add(n);return n;};
  function lower(node:any,depth=0):any {
    if(depth>40 || !Array.isArray(node))throw Error('macro_expression_array_required');
    if(node[0]==='pairs_without') {
      if(node.length!==3)throw Error('invalid_pairs_without_arity');
      const obj=fresh(),key=fresh(),source=lower(node[1],depth+1),excluded=lower(node[2],depth+1);
      return ['let',obj,source,['map',['sort',['difference',['keys',['var',obj]],excluded]],key,
        ['array',['var',key],['get',['var',obj],['var',key]]]]];
    }
    if(node[0]==='lit' || node[0]==='var')return node;
    if(node[0]==='object')return ['object',Object.fromEntries(Object.entries(node[1]).map(([k,v])=>[k,lower(v,depth+1)]))];
    const binding=node[0]==='let'?1:['map','filter'].includes(node[0])?2:-1;
    return node.map((v,i)=>i===0||i===binding?v:lower(v,depth+1));
  }
  const result=lower(program);validateProgram(result);return result;
}
