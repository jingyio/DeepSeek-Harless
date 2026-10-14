import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { runInNewContext } from 'node:vm';
import { assertSupportedJsonSchema } from '@deepseek-ai/dsh-tools';
import { digest } from '../src/adapters/paper_rsi_program.ts';
import { runTraceTool, validateTraceCandidate } from '../src/adapters/trace_rsi_program.ts';
import { apply, createRevisionLearning, revisionInputPatch } from '../src/adapters/dsh_revision_rsi_learning.ts';

const names = ['rsi_packet_list','rsi_packet_read','rsi_propose','rsi_test','rsi_trial'];
const cordis = ['cordis_inspect_list','cordis_inspect_query','cordis_inspect_self',
  'cordis_define','cordis_run','cordis_stop','cordis_undefine'];
const clone = v => JSON.parse(JSON.stringify(v));
const hashBytes = v => createHash('sha256').update(v).digest('hex');

function fixture(t) {
  const work = realpathSync(mkdtempSync(join(tmpdir(),'sss-revision-learning-test-')));
  t.after(() => rmSync(work,{recursive:true,force:true}));
  // Synthetic transport witnesses and echo AST only: no model authorship,
  // real trajectory certification, heldout promotion or savings are claimed.
  const before = {rows:[{key:'synthetic-a',value:'private-before'}],context:'private-context'};
  const after = {rows:[{key:'synthetic-a',value:'private-after'}],context:'private-context'};
  const packet = {packet_id:'packet-normal',run_id:'synthetic-normal',session_id:'prior-normal-session',
    case_id:'synthetic-case',classification:'normal_success',learning_eligible:true,motif_training_eligible:true,
    before_report:before,after_report:after,catalog:{records:[{key:'synthetic-a'}]},
    trace_records:[{tool:'read_state',arguments:{},result:{report:before}},
      {tool:'write_report',arguments:{report:after},result:{saved:true}},
      {tool:'frozen_check',arguments:{input_id:'synthetic-handle'},result:{output:{ok:true}}}],
    before_report_sha256:digest(before),after_report_sha256:digest(after),catalog_sha256:digest({records:[{key:'synthetic-a'}]}),
    oracle_facts:{selected_values:['development-a','development-b']}};
  const failed = {...clone(packet),packet_id:'packet-failed',run_id:'synthetic-failed',
    classification:'normal_failed_tool_counterexample',motif_training_eligible:false,
    trace_records:[{tool:'write_report',arguments:{},isError:true,result:'synthetic retained failure'}]};
  const bundle = {schema_version:1,kind:'revision_tool_trace_packets',entries:[],packets:[packet,failed]};
  const packetPath = join(work,'training-packets.json');writeFileSync(packetPath,JSON.stringify(bundle));
  const input_schema = {type:'object',properties:{selected_values:{type:'array',items:{type:'string'}}},
    required:['selected_values'],additionalProperties:false};
  const output_schema = {type:'array',items:{type:'string'}};
  const contract = {name:'selected_revision_values',description:'合成自由字段协议诊断',input_schema,output_schema};
  const candidate = {schema_version:1,...contract,program:['get',['var','input'],['lit','selected_values']]};
  const proposal = {contract,source_packet_ids:['packet-normal'],
    input_bindings:{selected_values:{packet_id:'packet-normal',section:'oracle_facts',pointer:'/selected_values'}},
    output_bindings:{packet_id:'packet-normal',section:'oracle_facts',pointer:'/selected_values'}};
  const training = [{id:'synthetic-development',input:{selected_values:['development-a','development-b']},
    expected:['development-a','development-b']}];
  const accepted = {schema_version:1,contract,proposal_sha256:digest(proposal)};
  const config = {work,session_id:'revision-learning-session',training_packets_path:packetPath,
    experiment_path:work,python_command:process.execPath,controller_path:join(work,'diagnostic-controller.cjs')};
  function seedAccepted(a=accepted, rows=training) {
    writeFileSync(join(work,'accepted-proposal.json'),JSON.stringify(a));
    writeFileSync(join(work,'training.json'),JSON.stringify(rows));
  }
  function controller({reject=false,changedDigest=false,mutatePackets=false}={}) {
    writeFileSync(config.controller_path,`
const fs=require('fs');let body='';process.stdin.on('data',v=>body+=v);process.stdin.on('end',()=>{
 const proposal=JSON.parse(body);
 fs.writeFileSync('controller-invocation.json',JSON.stringify({args:process.argv.slice(2),proposal}));
 ${mutatePackets ? "fs.appendFileSync('training-packets.json','\\n');" : ''}
 ${reject ? "process.stderr.write('synthetic rejection');process.exitCode=1;return;" : ''}
 fs.writeFileSync('accepted-proposal.json',JSON.stringify(${JSON.stringify({...accepted,...(changedDigest ? {proposal_sha256:'f'.repeat(64)} : {})})}));
 fs.writeFileSync('training.json',JSON.stringify(${JSON.stringify(training)}));
 process.stdout.write(JSON.stringify({proposal_sha256:${JSON.stringify(accepted.proposal_sha256)},
  contract:proposal.contract,training:${JSON.stringify(training)},heldout_cases:7}));
});`);
  }
  return {work,config,bundle,packet,failed,contract,candidate,proposal,training,accepted,seedAccepted,controller};
}

function mount(config) {
  const registry = new Map(), services = new Map(), handlers = new Map();
  const ctx = {tools:{register(d) {
    assertSupportedJsonSchema(d.parameters);assertSupportedJsonSchema(d.output.schema);
    assert.equal(registry.has(d.name),false);registry.set(d.name,d);
  }},provide(n,s) {services.set(n,s);},on(n,h) {
    assert.deepEqual([...registry.keys()],names);handlers.set(n,h);
  }};
  const cwd = process.cwd(), previous = process.env.SSS_REVISION_RSI_LEARNING;
  const path = join(config.work,'revision-config.json');writeFileSync(path,JSON.stringify(config));
  try { process.chdir(config.work);process.env.SSS_REVISION_RSI_LEARNING=path;apply(ctx); }
  finally { process.chdir(cwd);if(previous===undefined)delete process.env.SSS_REVISION_RSI_LEARNING;
    else process.env.SSS_REVISION_RSI_LEARNING=previous; }
  return {registry,services,handlers,exec:{agent:{session:{id:config.session_id}},signal:new AbortController().signal}};
}

test('registered packet inventory retains failed traces and reading preserves actual normal evidence',t => {
  const f=fixture(t), learning=createRevisionLearning(f.config), listed=learning.list({});
  assert.equal(listed.packets.length,2);assert.equal(listed.packets[1].motif_training_eligible,false);
  assert.equal(listed.packets[1].classification,'normal_failed_tool_counterexample');
  assert.equal(JSON.stringify(listed).includes('private-before'),false);
  const read=learning.read({packet_id:'packet-normal'});
  assert.deepEqual(read.packet,f.packet);assert.equal(read.packet_sha256,digest(f.packet));
  assert.equal(read.training_packets_sha256,hashBytes(readFileSync(f.config.training_packets_path)));
  assert.deepEqual(learning.read({packet_id:'packet-failed',sections:['trace_records']}).packet.trace_records,
    f.failed.trace_records);
  const projected=learning.read({packet_id:'packet-normal',sections:['before_report','after_report','oracle_facts']});
  assert.deepEqual(Object.keys(projected.packet),['before_report','after_report','oracle_facts']);
  read.packet.before_report.context='caller mutation';projected.packet.oracle_facts.selected_values.push('caller mutation');
  assert.deepEqual(learning.read({packet_id:'packet-normal'}).packet,f.packet);
});

test('packet lookup accepts only registered IDs and top-level sections, never file paths',t => {
  const f=fixture(t), learning=createRevisionLearning(f.config);
  for(const args of [{packet_id:'/etc/passwd'},{packet_id:'packet-normal',path:'/etc/passwd'},
    {packet_id:'packet-normal',sections:['/before_report/rows']},{packet_id:'packet-normal',sections:['constructor']},
    {packet_id:'packet-normal',sections:[]},{packet_id:'packet-normal',sections:['catalog','catalog']},
    {packet_id:'packet-normal',sections:'catalog'}]) assert.throws(()=>learning.read(args));
  assert.throws(()=>learning.list({path:'/etc/passwd'}),/invalid_revision_arguments/);
  writeFileSync(f.config.training_packets_path,JSON.stringify({...f.bundle,packets:[f.packet,f.packet]}));
  assert.throws(()=>createRevisionLearning(f.config),/duplicate_revision_packet/);
});

test('all installed operations guard the exact training-packet bytes against drift',t => {
  const f=fixture(t);f.seedAccepted();const learning=createRevisionLearning(f.config);
  learning.installProgram(f.candidate.program);
  const bytes=readFileSync(f.config.training_packets_path);
  writeFileSync(f.config.training_packets_path,Buffer.concat([bytes,Buffer.from('\n')]));
  for(const operation of [()=>learning.list({}),()=>learning.read({packet_id:'packet-normal'}),
    ()=>learning.propose({proposal:f.proposal}),()=>learning.install(f.candidate),
    ()=>learning.installProgram(f.candidate.program),()=>learning.test({}),
    ()=>learning.trial({input:{selected_values:[]}})]) assert.throws(operation,/revision_training_packets_changed/);
  writeFileSync(f.config.training_packets_path,bytes);assert.equal(learning.test({}).passed,true);
  assert.throws(()=>createRevisionLearning({...f.config,training_packets_sha256:'0'.repeat(64)}),/digest_mismatch/);
});

test('chosen field bindings and array outputs are not replaced by a fixed revision-check schema',t => {
  const f=fixture(t);f.controller();const learning=createRevisionLearning(f.config);
  const feedback=learning.propose({proposal:f.proposal});assert.deepEqual(feedback.contract,f.contract);
  assert.deepEqual(feedback.example_input,f.training[0].input);
  assert.equal(feedback.training[0].input_sha256,digest(f.training[0].input));
  assert.deepEqual(feedback.training[0].input_changes,[]);
  assert.equal(Object.hasOwn(feedback.training[0],'input'),false);
  const invocation=JSON.parse(readFileSync(join(f.work,'controller-invocation.json'),'utf8'));
  assert.deepEqual(invocation.args,['--phase','prepare-proposal','--experiment',f.config.experiment_path]);
  assert.deepEqual(invocation.proposal,f.proposal);
  learning.installProgram(f.candidate.program);assert.equal(learning.test({}).passed,true);
  assert.deepEqual(learning.trial({input:{selected_values:['trial']}}).output,['trial']);
  assert.throws(()=>learning.trial({input:{selected_values:[123]}}),/input_schema_type/);
  assert.throws(()=>learning.propose({proposal:f.proposal}),/proposal_already_accepted/);
  const rows=readFileSync(join(f.work,'learning.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  for(const kind of ['proposal_accepted','candidate_installed','development_test','trial'])
    assert.ok(rows.some(row=>row.kind===kind));
  assert.ok(rows.filter(r=>r.candidate_sha256).every(r=>r.candidate_sha256===digest(f.candidate)));
  assert.equal(Object.hasOwn(feedback,'heldout'),false);
});

test('development feedback patches reproduce full inputs including arrays, null and escaped fields',()=> {
  function applyPatch(base,patches) {
    let result=clone(base);
    for(const patch of patches) {
      if(patch.path===''){result=clone(patch.value);continue;}
      const keys=patch.path.slice(1).split('/').map(k=>k.replaceAll('~1','/').replaceAll('~0','~'));
      const key=keys.pop();let obj=result;for(const part of keys)obj=obj[part];
      if(Array.isArray(obj))obj.splice(Number(key),patch.op==='add'?0:1,...(patch.op==='remove'?[]:[clone(patch.value)]));
      else if(patch.op==='remove')delete obj[key];else obj[key]=clone(patch.value);
    }
    return result;
  }
  const base={'a/b':[1,{x:null},3],remove:'old'};
  for(const target of [{'a/b':[2,{new:'added'}]}, {'a/b':[1,{x:null},3,4],empty:[]},null,[1,2]]) {
    assert.deepEqual(applyPatch(base,revisionInputPatch(base,target)),target);
    assert.deepEqual(base,{'a/b':[1,{x:null},3],remove:'old'});
  }
});

test('boolean, string, integer and null output schemas also use generic validation',t => {
  for(const [type,value] of [['boolean',true],['string','synthetic'],['integer',7],['null',null]]) {
    const f=fixture(t), contract={...f.contract,output_schema:{type}}, candidate={schema_version:1,...contract,program:['lit',value]};
    f.seedAccepted({...f.accepted,contract},[{input:{selected_values:[]},expected:value}]);
    const learning=createRevisionLearning(f.config);learning.installProgram(candidate.program);
    assert.equal(learning.test({}).passed,true);assert.deepEqual(learning.trial({input:{selected_values:[]}}).output,value);
  }
});

test('native Cordis submissions normalize across realms while generated ASTs grant no host access',t => {
  const f=fixture(t);f.seedAccepted();const mounted=mount(f.config), service=mounted.services.get('sssRevisionRsi');
  assert.deepEqual(Object.keys(service).sort(),['install','installProgram']);
  const foreign=runInNewContext('('+JSON.stringify(f.candidate)+')');
  assert.throws(()=>validateTraceCandidate(foreign),/plain_object_required/);
  assert.equal(service.install(foreign).candidate_sha256,digest(f.candidate));
  service.installProgram(runInNewContext('('+JSON.stringify(f.candidate.program)+')'));
  for(const program of [['eval',['lit','process.exit()']],['spawn',['lit','sh']],['host',['lit','readFile']]])
    assert.throws(()=>service.installProgram(program),/invalid_program_node/);
  assert.throws(()=>service.installProgram(['lit',undefined]),/candidate_submission_|macro_/);
  const learning=createRevisionLearning(f.config);learning.installProgram(['var','process']);
  assert.throws(()=>learning.trial({input:{selected_values:[]}}),/unknown_variable/);
  learning.installProgram(['get',['var','input'],['lit','constructor']]);
  assert.throws(()=>learning.trial({input:{selected_values:[]}}),/unsafe_get/);
  class NonJson {constructor(){this.selected_values=[];}}
  assert.throws(()=>runTraceTool(f.candidate,new NonJson()),/plain_object_required/);
});

test('fixed accepted contracts and training digests cannot drift after installation',t => {
  const f=fixture(t);f.seedAccepted();const learning=createRevisionLearning(f.config);
  for(const candidate of [{...f.candidate,name:'other_name'},
    {...f.candidate,output_schema:{type:'boolean'}},{...f.candidate,description:'changed'}])
    assert.throws(()=>learning.install(candidate),/candidate_contract_mismatch/);
  learning.install(f.candidate);
  writeFileSync(join(f.work,'accepted-proposal.json'),JSON.stringify({...f.accepted,proposal_sha256:'c'.repeat(64)}));
  assert.throws(()=>learning.test({}),/accepted_proposal_or_training_changed/);
  f.seedAccepted();writeFileSync(join(f.work,'training.json'),JSON.stringify([{...f.training[0],expected:['changed']}]))
  assert.throws(()=>learning.trial({input:{selected_values:[]}}),/accepted_proposal_or_training_changed/);
});

test('controller rejection or digest mismatch cannot install or silently promote a tool',t => {
  for(const options of [{reject:true},{changedDigest:true}]) {
    const f=fixture(t);f.controller(options);const learning=createRevisionLearning(f.config);
    assert.throws(()=>learning.propose({proposal:f.proposal}),options.reject?/proposal_rejected/:/proposal_digest_mismatch/);
    assert.throws(()=>learning.install(f.candidate));
  }
  const f=fixture(t);f.seedAccepted();const learning=createRevisionLearning(f.config);
  learning.installProgram(['lit',[]]);assert.equal(learning.test({}).passed,false);
  assert.equal(Object.hasOwn(learning,'promote'),false);
});

test('packet version guard also runs after controller success or rejection',t => {
  for(const reject of [false,true]) {
    const f=fixture(t);f.controller({mutatePackets:true,reject});const learning=createRevisionLearning(f.config);
    assert.throws(()=>learning.propose({proposal:f.proposal}),/revision_training_packets_changed/);
    assert.throws(()=>learning.install(f.candidate),/revision_training_packets_changed/);
  }
});

test('all five tools register before creation restrictions and reject cross-session execution',async t => {
  const f=fixture(t), mounted=mount(f.config), created=mounted.handlers.get('agent/created');let allow,deny;
  created({agent:{session:{id:f.config.session_id},ctx:{tools:{restrict(filter){if(filter.allow)allow=filter.allow;}}}}});
  created({agent:{session:{id:'foreign'},ctx:{tools:{restrict(filter){deny=filter.deny;}}}}});
  assert.deepEqual(allow,[...cordis,...names]);assert.deepEqual(deny,names);
  const args={rsi_packet_list:{},rsi_packet_read:{packet_id:'packet-normal'},rsi_propose:{proposal:f.proposal},
    rsi_test:{},rsi_trial:{input:{selected_values:[]}}};
  for(const name of names) {
    const d=mounted.registry.get(name);
    await assert.rejects(d.execute(args[name],{agent:{session:{id:'foreign'}}}),/session_not_authorized/);
    await assert.rejects(d.execute(args[name],{}),/session_not_authorized/);
    const cancelled=new AbortController();cancelled.abort();
    await assert.rejects(d.execute(args[name],{...mounted.exec,signal:cancelled.signal}),/cancelled/);
  }
  assert.equal((await mounted.registry.get('rsi_packet_list').execute({},mounted.exec)).packets.length,2);
  await mounted.registry.get('rsi_packet_read').execute({packet_id:'packet-normal',sections:['trace_records']},mounted.exec);
  const audit=readFileSync(join(f.work,'learning.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(audit.some(row=>row.kind==='revision_packet_read' && row.packet_sha256===digest(f.packet)));
  assert.ok(audit.every(row=>row.session_id===f.config.session_id));
});

test('Cordis definition gate opens only after a successful immutable proposal',async t => {
  const f=fixture(t);f.controller({reject:true});const mounted=mount(f.config);let released=0;const masks=[];
  const agent={session:{id:f.config.session_id},ctx:{tools:{restrict(filter){masks.push(filter);return()=>released++;}}}};
  mounted.handlers.get('agent/created')({agent});
  assert.deepEqual(masks[1],{deny:cordis});
  const exec={...mounted.exec,agent};
  await assert.rejects(mounted.registry.get('rsi_propose').execute({proposal:f.proposal},exec),/proposal_rejected/);
  assert.equal(released,0);
  f.controller();await mounted.registry.get('rsi_propose').execute({proposal:f.proposal},exec);
  assert.equal(released,1);
  await assert.rejects(mounted.registry.get('rsi_propose').execute({proposal:f.proposal},exec),/proposal_already_accepted/);
  assert.equal(released,1);
});
