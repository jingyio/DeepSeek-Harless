/** Generic trace-tool contracts over the existing bounded, pure-data interpreter.
 * Hash validation checks artifact integrity and declared evidence structure. It
 * does not authenticate the producer or establish that witnesses are genuine.
 */
import { canonical, digest, runProgram, validateProgram } from './paper_rsi_program.ts';

const unsafeFields=new Set(['__proto__','prototype','constructor']);
const schemaTypes=new Set(['object','array','string','number','integer','boolean','null']);
const schemaKeywords=new Set(['type','properties','required','additionalProperties','items',
  'minItems','maxItems','minLength','maxLength','enum']);
const contractFields=['name','description','input_schema','output_schema'];
const candidateFields=['schema_version','name','description','input_schema','output_schema','program'];
const frozenFields=['schema_version','kind','candidate','candidate_sha256','provenance',
  'provenance_sha256','certification','certification_sha256','manifest_digest'];
const has=(value:any,key:string)=>Object.hasOwn(value,key);
const record=(value:any)=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const sha256=(value:any)=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const safeField=(key:string)=>key.length>0&&key.length<=128&&!unsafeFields.has(key)&&!/[\u0000-\u001f\u007f]/.test(key);
const childPath=(path:string,key:string|number)=>path+'/'+String(key).replace(/~/g,'~0').replace(/\//g,'~1');
function invalid(reason:string,path:string):never {throw Error(`${reason} at ${path}`);}

/** Accept JSON data only, before hashing, schema inspection or interpretation.
 * The limits apply to values independently of any schema supplied by a model.
 */
function boundedJson(value:any,label:string,maxBytes=192000,path='/'+label):void {
  let nodes=0;const ancestors=new Set<any>();
  function walk(v:any,depth:number,currentPath:string):void {
    if(++nodes>20000||depth>48)invalid(`${label}_too_complex`,currentPath);
    if(v===null||typeof v==='boolean'||typeof v==='string')return;
    if(typeof v==='number'){if(!Number.isFinite(v))invalid(`${label}_non_json_number`,currentPath);return;}
    if(typeof v!=='object')invalid(`${label}_non_json_value`,currentPath);
    if(ancestors.has(v))invalid(`${label}_cyclic`,currentPath);
    const prototype=Object.getPrototypeOf(v);
    if(Array.isArray(v)){
      if(prototype!==Array.prototype||v.length>2000)invalid(`${label}_bounded_array_required`,currentPath);
    }else if(prototype!==Object.prototype&&prototype!==null)invalid(`${label}_plain_object_required`,currentPath);
    const keys=Reflect.ownKeys(v);
    if(keys.some(k=>typeof k!=='string'))invalid(`${label}_non_json_key`,currentPath);
    if(Array.isArray(v)&&keys.length!==v.length+1)invalid(`${label}_dense_array_required`,currentPath);
    ancestors.add(v);
    for(const key of keys as string[]){
      if(Array.isArray(v)&&key==='length')continue;
      const fieldPath=childPath(currentPath,key);
      if(!safeField(key))invalid(`${label}_unsafe_field`,fieldPath);
      if(Array.isArray(v)&&(!/^(0|[1-9][0-9]*)$/.test(key)||Number(key)>=v.length))invalid(`${label}_non_json_key`,fieldPath);
      const descriptor=Object.getOwnPropertyDescriptor(v,key)!;
      if(!descriptor.enumerable||!has(descriptor,'value'))invalid(`${label}_non_json_property`,fieldPath);
      walk(descriptor.value,depth+1,fieldPath);
    }
    ancestors.delete(v);
  }
  walk(value,0,path);
  if(Buffer.byteLength(JSON.stringify(value))>maxBytes)invalid(`${label}_too_large`,path);
}
function exactFields(value:any,fields:string[],label:string,path='/'):void {
  if(!record(value)||Object.keys(value).length!==fields.length||fields.some(k=>!has(value,k)))invalid(label,path);
}

function validateSchema(schema:any,path:string):void {
  boundedJson(schema,'schema',32000,path);let nodes=0;
  function walk(s:any,depth:number,currentPath:string):void {
    if(++nodes>512||depth>16||!record(s)||!schemaTypes.has(s.type))invalid('invalid_trace_schema',currentPath);
    for(const key of Object.keys(s))if(!schemaKeywords.has(key))invalid('unknown_schema_keyword',childPath(currentPath,key));
    const allowed=new Set(['type','enum']);
    if(s.type==='object'){
      for(const key of ['properties','required','additionalProperties'])allowed.add(key);
      if(s.additionalProperties!==false)invalid('closed_object_schema_required',childPath(currentPath,'additionalProperties'));
      if(!record(s.properties)||Object.keys(s.properties).length>64)invalid('closed_object_schema_required',childPath(currentPath,'properties'));
      if(has(s,'required')&&(!Array.isArray(s.required)||s.required.length>64||
        s.required.some((key:any)=>typeof key!=='string'||!safeField(key)||!has(s.properties,key))||
        new Set(s.required).size!==s.required.length))invalid('invalid_schema_required',childPath(currentPath,'required'));
      for(const [key,child]of Object.entries(s.properties)){
        const fieldPath=childPath(childPath(currentPath,'properties'),key);
        if(!safeField(key))invalid('unsafe_schema_field',fieldPath);walk(child,depth+1,fieldPath);
      }
    }else if(s.type==='array'){
      for(const key of ['items','minItems','maxItems'])allowed.add(key);
      if(!has(s,'items'))invalid('array_items_schema_required',childPath(currentPath,'items'));walk(s.items,depth+1,childPath(currentPath,'items'));
      bounds(s,'minItems','maxItems',2000,currentPath);
    }else if(s.type==='string'){
      for(const key of ['minLength','maxLength'])allowed.add(key);
      bounds(s,'minLength','maxLength',192000,currentPath);
    }
    for(const key of Object.keys(s))if(!allowed.has(key))invalid('schema_keyword_type_mismatch',childPath(currentPath,key));
    if(has(s,'enum')){
      if(!Array.isArray(s.enum)||s.enum.length<1||s.enum.length>64||new Set(s.enum.map(canonical)).size!==s.enum.length)invalid('invalid_schema_enum',childPath(currentPath,'enum'));
      // Enum members must satisfy the rest of their schema, not merely be JSON.
      for(const [index,value]of s.enum.entries())validateValue({...s,enum:undefined},value,'schema_enum',false,childPath(childPath(currentPath,'enum'),index));
    }
  }
  function bounds(s:any,min:string,max:string,limit:number,currentPath:string):void {
    for(const key of [min,max])if(has(s,key)&&(!Number.isInteger(s[key])||s[key]<0||s[key]>limit))invalid('invalid_schema_bounds',childPath(currentPath,key));
    if(has(s,min)&&has(s,max)&&s[min]>s[max])invalid('invalid_schema_bounds',childPath(currentPath,max));
  }
  walk(schema,0,path);
}

function validateValue(schema:any,value:any,label:string,enforceEnum=true,path='/'+label):void {
  const type=schema.type;
  const valid=type==='object'?record(value):type==='array'?Array.isArray(value):type==='null'?value===null:
    type==='integer'?typeof value==='number'&&Number.isInteger(value):typeof value===type;
  if(!valid)invalid(`${label}_schema_type`,path);
  if(enforceEnum&&has(schema,'enum')&&!schema.enum.some((choice:any)=>canonical(choice)===canonical(value)))invalid(`${label}_schema_enum`,path);
  if(type==='object'){
    for(const key of schema.required??[])if(!has(value,key))invalid(`${label}_schema_required`,childPath(path,key));
    for(const [key,child]of Object.entries(value)){
      if(!has(schema.properties,key))invalid(`${label}_schema_additional_property`,childPath(path,key));
      validateValue(schema.properties[key],child,label,true,childPath(path,key));
    }
  }else if(type==='array'){
    if(value.length<(schema.minItems??0)||value.length>(schema.maxItems??2000))invalid(`${label}_schema_items`,path);
    for(const [index,child]of value.entries())validateValue(schema.items,child,label,true,childPath(path,index));
  }else if(type==='string'){
    // JSON Schema length counts Unicode code points rather than UTF-16 units.
    const length=Array.from(value).length;
    if(length<(schema.minLength??0)||length>(schema.maxLength??192000))invalid(`${label}_schema_length`,path);
  }
}

function validateContract(contract:any,path:string):void {
  if(typeof contract.name!=='string'||!/^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$/.test(contract.name)||
    contract.name.length>64||unsafeFields.has(contract.name))invalid('invalid_trace_tool_contract',childPath(path,'name'));
  if(typeof contract.description!=='string'||contract.description.length<1||contract.description.length>800)
    invalid('invalid_trace_tool_contract',childPath(path,'description'));
  validateSchema(contract.input_schema,childPath(path,'input_schema'));validateSchema(contract.output_schema,childPath(path,'output_schema'));
}

/** Verify source projections before any program exists. The four-field proposal
 * contract uses the same schema and bounded JSON rules as executable candidates.
 * Errors contain only a constraint name and an escaped field path, never values.
 */
export function validateTraceContractValues(contract:any,input:any,output:any):any {
  boundedJson(contract,'contract',128000);exactFields(contract,contractFields,'invalid_trace_tool_contract','/contract');
  validateContract(contract,'/contract');
  boundedJson(input,'input');validateValue(contract.input_schema,input,'input');
  boundedJson(output,'output');validateValue(contract.output_schema,output,'output');
  return contract;
}

export function validateTraceCandidate(candidate:any):any {
  boundedJson(candidate,'candidate',128000);exactFields(candidate,candidateFields,'invalid_trace_tool_contract','/candidate');
  if(candidate.schema_version!==1)invalid('invalid_trace_tool_contract','/candidate/schema_version');
  validateContract(candidate,'/candidate');validateProgram(candidate.program);
  return candidate;
}

/** No host capability is supplied: only schema-checked JSON reaches runProgram. */
export function runTraceTool(candidate:any,input:any):any {
  validateTraceCandidate(candidate);boundedJson(input,'input');validateValue(candidate.input_schema,input,'input');
  const output=runProgram(candidate.program,input);
  boundedJson(output,'output');validateValue(candidate.output_schema,output,'output');return output;
}

/** A valid hash is an integrity check, never a source signature or permission. */
export function validateTraceFrozen(artifact:any):any {
  boundedJson(artifact,'artifact',192000);exactFields(artifact,frozenFields,'unverified_trace_frozen_tool');
  const {manifest_digest,...body}=artifact;
  if(artifact.schema_version!==1||artifact.kind!=='model_generated_trace_tool'||!sha256(manifest_digest)||
    manifest_digest!==digest(body)||!sha256(artifact.candidate_sha256)||artifact.candidate_sha256!==digest(artifact.candidate)||
    !sha256(artifact.provenance_sha256)||artifact.provenance_sha256!==digest(artifact.provenance)||
    !sha256(artifact.certification_sha256)||artifact.certification_sha256!==digest(artifact.certification))throw Error('unverified_trace_frozen_tool');
  validateTraceCandidate(artifact.candidate);
  const provenance=artifact.provenance,certification=artifact.certification;
  if(!record(provenance)||!sha256(provenance.trace_bundle_sha256)||!Array.isArray(provenance.source_witnesses)||
    provenance.source_witnesses.length<1||provenance.source_witnesses.length>64)throw Error('invalid_trace_provenance');
  const witnesses=new Set<string>();
  for(const witness of provenance.source_witnesses){
    if(!record(witness)||!sha256(witness.events_sha256)||['run_id','session_id','call_id'].some(key=>
      typeof witness[key]!=='string'||witness[key].length<1||witness[key].length>256))throw Error('invalid_trace_source_witness');
    const key=canonical([witness.run_id,witness.session_id,witness.call_id]);
    if(witnesses.has(key))throw Error('duplicate_trace_source_witness');witnesses.add(key);
  }
  if(!record(certification)||certification.status!=='passed'||certification.kind!=='source_replay'||
    !Number.isInteger(certification.heldout_cases)||certification.heldout_cases<2||certification.heldout_cases>2000)throw Error('invalid_trace_certification');
  return artifact;
}
