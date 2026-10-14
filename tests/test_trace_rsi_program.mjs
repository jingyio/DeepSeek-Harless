import test from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { digest, runProgram, validateProgram } from '../src/adapters/paper_rsi_program.ts';
import { validateTraceCandidate, validateTraceContractValues, runTraceTool, validateTraceFrozen } from '../src/adapters/trace_rsi_program.ts';

const string={type:'string',maxLength:100};
const object=(properties,required=Object.keys(properties))=>({type:'object',properties,required,additionalProperties:false});
const array=items=>({type:'array',items,maxItems:2000});
const clone=value=>JSON.parse(JSON.stringify(value));

function candidate(){
  // This is a handwritten, synthetic replay fixture. It is not evidence that a
  // model generated a tool or that a real trace has been independently reviewed.
  return {schema_version:1,name:'summarize_trace_records',description:'合成轨迹重放诊断',
    input_schema:object({records:array(object({status:string,source_path:string}))}),
    output_schema:object({statuses:array(string),files:array(string),count:{type:'integer'}}),
    program:['object',{
      statuses:['sort',['unique',['map',['get',['var','input'],['lit','records']],'row',['get',['var','row'],['lit','status']]]]],
      files:['map',['get',['var','input'],['lit','records']],'row',['at',['split',['get',['var','row'],['lit','source_path']],['lit','/']],['lit',-1]]],
      count:['count',['get',['var','input'],['lit','records']]]
    }]};
}
function frozen(tool=candidate()){
  // Synthetic witness declarations test integrity only; these IDs are not real.
  const provenance={trace_bundle_sha256:'a'.repeat(64),source_witnesses:[{
    run_id:'synthetic-run',session_id:'synthetic-session',call_id:'synthetic-call',events_sha256:'b'.repeat(64)
  }],fixture_type:'synthetic_diagnostic'};
  const certification={status:'passed',heldout_cases:2,kind:'source_replay',fixture_type:'synthetic_diagnostic'};
  const body={schema_version:1,kind:'model_generated_trace_tool',candidate:tool,candidate_sha256:digest(tool),
    provenance,provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)};
  return {...body,manifest_digest:digest(body)};
}
function rehash(artifact){
  artifact.candidate_sha256=digest(artifact.candidate);artifact.provenance_sha256=digest(artifact.provenance);
  artifact.certification_sha256=digest(artifact.certification);
  const {manifest_digest,...body}=artifact;artifact.manifest_digest=digest(body);return artifact;
}
function contract(){
  const {schema_version,program,...value}=candidate();return value;
}

test('source projections validate against a four-field contract before a program exists',()=>{
  const value=contract(),input={records:[{status:'ready',source_path:'input/a.json'}]},
    output={statuses:['ready'],files:['a.json'],count:1};
  assert.equal(validateTraceContractValues(value,input,output),value);
  assert.throws(()=>validateTraceContractValues({...value,program:['var','input']},input,output),/invalid_trace_tool_contract at \/contract$/);
  assert.throws(()=>validateTraceContractValues({...value,schema_version:1},input,output),/invalid_trace_tool_contract at \/contract$/);
  assert.throws(()=>validateTraceContractValues({...value,name:'invalid-name'},input,output),/invalid_trace_tool_contract at \/contract\/name$/);
});

test('projection value errors identify nested field paths without including private values',()=>{
  const value=contract(),input={records:[]},output={statuses:[],files:[],count:0};
  const failures=[
    [{records:[{status:17,source_path:'private-path-value'}]},output,'input_schema_type at /input/records/0/status'],
    [{records:[{status:'private-status-value'}]},output,'input_schema_required at /input/records/0/source_path'],
    [input,{...output,count:'private-count-value'},'output_schema_type at /output/count'],
    [input,{...output,statuses:[true]},'output_schema_type at /output/statuses/0'],
    [input,{...output,extra:'private-extra-value'},'output_schema_additional_property at /output/extra']
  ];
  for(const [data,result,message]of failures)assert.throws(()=>validateTraceContractValues(value,data,result),error=>{
    assert.equal(error.message,message);assert.doesNotMatch(error.message,/private-|17/);return true;
  });
  const escaped={name:'inspect_fields',description:'字段路径诊断',input_schema:object({'x/y~z':{type:'integer'}}),output_schema:{type:'null'}};
  assert.throws(()=>validateTraceContractValues(escaped,{'x/y~z':'private-value'},null),
    error=>error.message==='input_schema_type at /input/x~1y~0z');
  const enumValue={...escaped,input_schema:{type:'string',enum:['ready']}};
  assert.throws(()=>validateTraceContractValues(enumValue,'private-value',null),
    error=>error.message==='input_schema_enum at /input');
});

test('projection schema errors use schema paths and bounded JSON errors use data paths',()=>{
  const value=contract(),input={records:[]},output={statuses:[],files:[],count:0};
  const unknown=clone(value);unknown.input_schema.properties.records.items.properties.status.format='private-format';
  assert.throws(()=>validateTraceContractValues(unknown,input,output),error=>{
    assert.equal(error.message,'unknown_schema_keyword at /contract/input_schema/properties/records/items/properties/status/format');
    assert.doesNotMatch(error.message,/private-format/);return true;
  });
  assert.throws(()=>validateTraceContractValues(value,{records:[{status:undefined,source_path:'x'}]},output),
    /input_non_json_value at \/input\/records\/0\/status$/);
  assert.throws(()=>validateTraceContractValues(value,input,{...output,count:Infinity}),/output_non_json_number at \/output\/count$/);
  const accessor={};Object.defineProperty(accessor,'records',{enumerable:true,get(){throw Error('getter_must_not_run');}});
  assert.throws(()=>validateTraceContractValues(value,accessor,output),/input_non_json_property at \/input\/records$/);
});

test('projection contract and values keep strict current-realm plain-object validation',()=>{
  const value=contract(),input={records:[]},output={statuses:[],files:[],count:0};
  const foreign=source=>runInNewContext('('+JSON.stringify(source)+')');
  assert.throws(()=>validateTraceContractValues(foreign(value),input,output),/contract_plain_object_required at \/contract$/);
  assert.throws(()=>validateTraceContractValues(value,foreign(input),output),/input_plain_object_required at \/input$/);
  assert.throws(()=>validateTraceContractValues(value,input,foreign(output)),/output_plain_object_required at \/output$/);
  assert.throws(()=>validateTraceContractValues(value,{records:foreign([])},output),/input_bounded_array_required at \/input\/records$/);
});

test('generic handwritten fixture replays two data inputs against an independent oracle',()=>{
  const tool=candidate();assert.equal(validateTraceCandidate(tool),tool);
  // Independent direct-data calculation, not interpreter replay or cached output.
  const oracle=records=>({statuses:[...new Set(records.map(row=>row.status))].sort(),
    files:records.map(row=>row.source_path.split('/').at(-1)),count:records.length});
  for(const records of [[{status:'ready',source_path:'input/a.json'},{status:'pending',source_path:'other/b.json'},
    {status:'ready',source_path:'c.json'}],[]])assert.deepEqual(runTraceTool(tool,{records}),oracle(records));
  const named={...tool,name:'inspect_another_result'};
  assert.equal(validateTraceCandidate(named).name,'inspect_another_result');
});

test('sort, split and at remain bounded pure-data operators and preserve inputs',()=>{
  const input={values:[3,1,2]};
  assert.deepEqual(runProgram(['sort',['get',['var','input'],['lit','values']]],input),[1,2,3]);
  assert.deepEqual(input.values,[3,1,2]);
  assert.deepEqual(runProgram(['sort',['lit',['b','a','b']]],{}),['a','b','b']);
  assert.deepEqual(runProgram(['sort',['lit',[]]],{}),[]);
  assert.deepEqual(runProgram(['split',['lit','a/b/'],['lit','/']],{}),['a','b','']);
  assert.equal(runProgram(['at',['lit',[1,2]],['lit',-1]],{}),2);
  for(const index of [-3,2,999])assert.equal(runProgram(['at',['lit',[1,2]],['lit',index]],{}),null);
  assert.equal(runProgram(['at',['lit',[]],['lit',0]],{}),null);
  assert.throws(()=>runProgram(['sort',['lit',[1,'2']]],{}),/sortable_array/);
  assert.throws(()=>runProgram(['sort',['lit',[{}]]],{}),/sortable_array/);
  assert.throws(()=>runProgram(['sort',['var','input']],Array(2001).fill(0)),/bounded_array/);
  assert.throws(()=>runProgram(['split',['lit','abc'],['lit','']],{}),/separator/);
  assert.throws(()=>runProgram(['split',['lit',123],['lit','/']],{}),/separator/);
  assert.throws(()=>runProgram(['split',['var','input'],['lit','/']],Array(2001).fill('x').join('/')),/bounded_array/);
  assert.throws(()=>runProgram(['at',['lit',[1]],['lit',0.5]],{}),/integer_index/);
  assert.throws(()=>runProgram(['at',['lit','a'],['lit',0]],{}),/bounded_array/);
  assert.throws(()=>validateProgram(['sort',['lit',[]],['lit',1]]),/invalid_program/);
});

test('keys returns only own plain-object fields and rejects dangerous or oversized objects',()=>{
  assert.deepEqual(runProgram(['keys',['var','input']],{status:'ready',count:2}),['status','count']);
  assert.deepEqual(runProgram(['keys',['var','input']],Object.assign(Object.create(null),{x:1})),['x']);
  for(const value of [[],null,'abc',new Date()])assert.throws(()=>runProgram(['keys',['var','input']],value),/plain_object/);
  for(const key of ['__proto__','constructor','prototype'])
    assert.throws(()=>runProgram(['keys',['var','input']],JSON.parse(`{"${key}":1}`)),/unsafe_object_fields/);
  assert.throws(()=>runProgram(['keys',['var','input']],Object.fromEntries(Array.from({length:2001},(_,i)=>[`x${i}`,i]))),/bounded_object/);
  const hidden={};Object.defineProperty(hidden,'x',{get(){throw Error('getter_must_not_run');}});
  assert.throws(()=>runProgram(['keys',['var','input']],hidden),/unsafe_object_fields/);
  const tool={...candidate(),input_schema:object({x:{type:'integer'}}),output_schema:array(string),program:['keys',['var','input']]};
  assert.deepEqual(runTraceTool(tool,{x:1}),['x']);
  const accessor={};Object.defineProperty(accessor,'x',{enumerable:true,get(){throw Error('getter_must_not_run');}});
  assert.throws(()=>runTraceTool(tool,accessor),/non_json_property/);
});

test('candidate contracts and JSON schemas reject unknown or incompatible fields',()=>{
  for(const field of ['$ref','format','pattern','default','oneOf','unknown']){
    const tool=candidate();tool.input_schema[field]='unsupported';
    assert.throws(()=>validateTraceCandidate(tool),/unknown_schema_keyword/);
  }
  for(const name of ['fixed-name','_private','BadName','a__b','constructor','a'.repeat(65)])
    assert.throws(()=>validateTraceCandidate({...candidate(),name}),/invalid_trace_tool/);
  assert.throws(()=>validateTraceCandidate({...candidate(),host_permissions:['filesystem']}),/invalid_trace_tool/);
  assert.throws(()=>validateTraceCandidate({...candidate(),description:''}),/invalid_trace_tool/);
  const badSchemas=[{type:'any'},{type:['string','null']},{type:'array'},
    {type:'object',properties:{},additionalProperties:true},{type:'string',items:string},
    {type:'string',minLength:2,maxLength:1},{type:'array',items:string,maxItems:2001},
    object({x:string},['missing']),object({x:string},['x','x']),
    {type:'integer',enum:[1,1]},{type:'integer',enum:[1.5]},{type:'string',enum:[]}];
  for(const input_schema of badSchemas)assert.throws(()=>validateTraceCandidate({...candidate(),input_schema}));
});

test('schema, literal and runtime inputs reject dangerous keys and non-JSON objects',()=>{
  for(const field of ['__proto__','prototype','constructor']){
    const input_schema=JSON.parse(`{"type":"object","properties":{"${field}":{"type":"string"}},"additionalProperties":false}`);
    assert.throws(()=>validateTraceCandidate({...candidate(),input_schema}),/unsafe_field/);
    const tool=candidate();tool.program=['lit',JSON.parse(`{"${field}":true}`)];
    assert.throws(()=>validateTraceCandidate(tool),/unsafe_field/);
    assert.throws(()=>runTraceTool(candidate(),JSON.parse(`{"${field}":true}`)),/unsafe_field/);
  }
  assert.throws(()=>runTraceTool(candidate(),new Date()),/plain_object/);
  assert.throws(()=>runTraceTool(candidate(),{records:undefined}),/non_json_value/);
  assert.throws(()=>runTraceTool(candidate(),{records:Array(1)}),/dense_array/);
  const accessor={};Object.defineProperty(accessor,'records',{enumerable:true,get(){throw Error('getter_must_not_run');}});
  assert.throws(()=>runTraceTool(candidate(),accessor),/non_json_property/);
  const cycle={};cycle.records=cycle;assert.throws(()=>runTraceTool(candidate(),cycle),/cyclic/);
  assert.throws(()=>validateTraceCandidate({...candidate(),program:['eval',['lit','process.exit()']]}),/invalid_program/);
  assert.throws(()=>runTraceTool({...candidate(),program:['get',['var','input'],['lit','constructor']]},{records:[]}),/unsafe_get/);
});

test('runtime checks input and output schemas, size limits and finite numbers',()=>{
  const tool=candidate();
  assert.throws(()=>runTraceTool(tool,{}),/input_schema_required/);
  assert.throws(()=>runTraceTool(tool,{records:[],other:true}),/input_schema_additional_property/);
  assert.throws(()=>runTraceTool(tool,{records:[{status:1,source_path:'x'}]}),/input_schema_type/);
  assert.throws(()=>runTraceTool(tool,{records:[{status:'x'.repeat(101),source_path:'x'}]}),/input_schema_length/);
  assert.throws(()=>runTraceTool(tool,{records:Array(2001).fill({status:'x',source_path:'x'})}),/bounded_array/);
  assert.throws(()=>runTraceTool({...tool,program:['lit',{statuses:[],files:[],count:'wrong'}]},{records:[]}),/output_schema_type/);
  assert.throws(()=>runTraceTool({...tool,program:['lit',{statuses:[],files:[]}]},{records:[]}),/output_schema_required/);
  assert.throws(()=>runTraceTool({...tool,program:['lit',{statuses:[],files:[],count:0,other:1}]},{records:[]}),/output_schema_additional_property/);
  const identity={...tool,input_schema:{type:'number'},output_schema:{type:'number'},program:['var','input']};
  assert.equal(runTraceTool(identity,2.5),2.5);
  for(const value of [Infinity,NaN])assert.throws(()=>runTraceTool(identity,value),/non_json_number/);
  const text={...identity,input_schema:{type:'string'},output_schema:{type:'string'}};
  assert.throws(()=>runTraceTool(text,'x'.repeat(192000)),/input_too_large/);
});

test('supported schemas enforce enum, numeric kinds, string codepoints, null and array bounds',()=>{
  const input_schema=object({mode:{type:'string',enum:['ready','done']},value:{type:'number'},
    count:{type:'integer'},ok:{type:'boolean'},missing:{type:'null'},label:{type:'string',minLength:1,maxLength:1},
    values:{type:'array',items:{type:'integer'},minItems:1,maxItems:2}});
  const tool={...candidate(),input_schema,output_schema:input_schema,program:['var','input']};
  const input={mode:'ready',value:1.2,count:2,ok:true,missing:null,label:'😀',values:[1,2]};
  assert.deepEqual(runTraceTool(tool,input),input);
  for(const [key,value,reason]of [['mode','other','enum'],['count',1.5,'type'],['ok',0,'type'],
    ['missing',false,'type'],['label','ab','length'],['values',[],'items'],['values',[1,2,3],'items']])
    assert.throws(()=>runTraceTool(tool,{...input,[key]:value}),new RegExp(`input_schema_${reason}`));
  assert.throws(()=>runTraceTool({...tool,output_schema:{type:'string',enum:['x']},program:['lit','y']},input),/output_schema_enum/);
});

test('schema depth and breadth limits reject excessive structures',()=>{
  let input_schema=string;
  for(let i=0;i<18;i++)input_schema={type:'array',items:input_schema};
  assert.throws(()=>validateTraceCandidate({...candidate(),input_schema}),/invalid_trace_schema/);
  const properties=Object.fromEntries(Array.from({length:65},(_,i)=>[`field_${i}`,string]));
  assert.throws(()=>validateTraceCandidate({...candidate(),input_schema:object(properties)}),/closed_object/);
});

test('frozen artifacts bind candidate, provenance, certification and manifest hashes',()=>{
  const lib=frozen();assert.equal(validateTraceFrozen(lib),lib);
  for(const field of ['candidate_sha256','provenance_sha256','certification_sha256','manifest_digest'])
    assert.throws(()=>validateTraceFrozen({...lib,[field]:'f'.repeat(64)}),/unverified_trace_frozen/);
  for(const mutate of [x=>{x.candidate.description='changed';},x=>{x.provenance.source_witnesses[0].call_id='changed';},
    x=>{x.certification.heldout_cases=3;}]){
    const altered=clone(lib);mutate(altered);assert.throws(()=>validateTraceFrozen(altered),/unverified_trace_frozen/);
  }
  assert.throws(()=>validateTraceFrozen({...lib,unexpected:true}),/unverified_trace_frozen/);
});

test('rehashing cannot bypass required provenance, witnesses or heldout certification structure',()=>{
  for(const mutate of [x=>{x.kind='another_kind';},x=>{x.provenance.trace_bundle_sha256='bad';},
    x=>{x.provenance.source_witnesses=[];},x=>{x.provenance.source_witnesses[0].events_sha256='bad';},
    x=>{x.provenance.source_witnesses[0].run_id='';},x=>{x.provenance.source_witnesses.push(clone(x.provenance.source_witnesses[0]));},
    x=>{x.certification.status='failed';},x=>{x.certification.heldout_cases=1;},
    x=>{x.certification.heldout_cases=2.5;},x=>{delete x.certification.kind;},x=>{x.certification.kind='self_asserted';}]){
    const altered=clone(frozen());mutate(altered);assert.throws(()=>validateTraceFrozen(rehash(altered)));
  }
  // Rehashed metadata may pass integrity; this deliberately demonstrates why
  // these checks do not substitute for authenticating/replaying real evidence.
  const claimed=clone(frozen());claimed.provenance.source_witnesses[0].run_id='another-synthetic-run';
  assert.equal(validateTraceFrozen(rehash(claimed)),claimed);
});
