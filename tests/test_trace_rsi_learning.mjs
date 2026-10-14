import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { runInNewContext } from 'node:vm';
import { assertSupportedJsonSchema } from '@deepseek-ai/dsh-tools';
import { digest } from '../src/adapters/paper_rsi_program.ts';
import { runTraceTool, validateTraceCandidate } from '../src/adapters/trace_rsi_program.ts';
import { apply, createTraceLearning } from '../src/adapters/dsh_trace_rsi_learning.ts';
import { createTraceRsiTools } from '../scenarios/paper-submission/trace-rsi-server.ts';

const learningNames = ['rsi_trace_list','rsi_trace_read','rsi_propose','rsi_test','rsi_trial'];
const cordisNames = ['cordis_inspect_list','cordis_inspect_query','cordis_inspect_self',
  'cordis_define','cordis_run','cordis_stop','cordis_undefine'];
const clone = value => JSON.parse(JSON.stringify(value));

function fixture(t) {
  const work = realpathSync(mkdtempSync(join(tmpdir(),'sss-trace-learning-test-')));
  t.after(() => rmSync(work,{recursive:true,force:true}));
  // Handwritten synthetic echo program and witnesses test integration guards.
  // They do not represent model authorship, genuine trace certification or savings.
  const schema = {type:'object',properties:{values:{type:'array',items:{type:'string'}}},
    required:['values'],additionalProperties:false};
  const contract = {name:'echo_trace_values',description:'合成协议诊断',input_schema:schema,output_schema:schema};
  const candidate = {schema_version:1,...contract,program:['var','input']};
  const training = [{id:'synthetic-development',input:{values:['development']},expected:{values:['development']}}];
  const bundle = {schema_version:1,entries:[{
    run_id:'synthetic-run',call_id:'supported-call',tool:'bash',line:10,step:2,
    arguments:{command:'print registered data',description:'合成支持记录'},text:'values: development',ok:true,
    replay_status:'observed_replay_match',output_labels:['values'],allowed_files:['fixture.json'],
    memory_files:{'fixture.json':'{"values":["development"],"secret":"private synthetic fixture"}'},
    file_sha256:{'fixture.json':'a'.repeat(64)}
  },{
    run_id:'synthetic-run',call_id:'unsupported-call',tool:'bash',line:20,step:3,
    arguments:{command:'unsupported command'},text:'failure retained',ok:false,
    replay_status:'unsupported',replay_reason:'unsupported_source_call',output_labels:[]
  }]};
  const bundlePath = join(work,'trace-bundle.json');
  writeFileSync(bundlePath,JSON.stringify(bundle));
  const config = {work,session_id:'synthetic-learning-session',trace_bundle_path:bundlePath,
    experiment_path:work,python_command:process.execPath,controller_path:join(work,'diagnostic-controller.cjs')};
  const proposal = {contract,source:{run_id:'synthetic-run',call_id:'supported-call'}};
  const accepted = {schema_version:1,contract,proposal_sha256:digest(proposal)};
  function seedAccepted() {
    writeFileSync(join(work,'accepted-proposal.json'),JSON.stringify(accepted));
    writeFileSync(join(work,'training.json'),JSON.stringify(training));
  }
  const provenance = {trace_bundle_sha256:digest(bundle),fixture_type:'synthetic_diagnostic',source_witnesses:[{
    run_id:'synthetic-run',session_id:'synthetic-session',call_id:'supported-call',events_sha256:'b'.repeat(64)}]};
  const certification = {status:'passed',kind:'source_replay',heldout_cases:2,fixture_type:'synthetic_diagnostic'};
  const body = {schema_version:1,kind:'model_generated_trace_tool',candidate,candidate_sha256:digest(candidate),
    provenance,provenance_sha256:digest(provenance),certification,certification_sha256:digest(certification)};
  const frozen = {...body,manifest_digest:digest(body)}, libraryPath = join(work,'library.json');
  writeFileSync(libraryPath,JSON.stringify(frozen));
  return {work,config,bundle,contract,candidate,training,proposal,accepted,seedAccepted,frozen,libraryPath};
}

function mount(config) {
  const registry = new Map(), services = new Map(), handlers = new Map();
  const ctx = {
    tools:{register(definition) {
      assertSupportedJsonSchema(definition.parameters);assertSupportedJsonSchema(definition.output.schema);
      assert.equal(registry.has(definition.name),false);registry.set(definition.name,definition);
    }},
    provide(name,service) { services.set(name,service); },
    on(name,handler) {
      // Registration must finish before this creation listener can restrict tools.
      assert.deepEqual([...registry.keys()],learningNames);handlers.set(name,handler);
    }
  };
  const originalCwd = process.cwd(), originalEnv = process.env.SSS_TRACE_RSI_LEARNING;
  const configPath = join(config.work,'learning-config.json');writeFileSync(configPath,JSON.stringify(config));
  try { process.chdir(config.work);process.env.SSS_TRACE_RSI_LEARNING=configPath;apply(ctx); }
  finally {
    process.chdir(originalCwd);
    if (originalEnv === undefined) delete process.env.SSS_TRACE_RSI_LEARNING;
    else process.env.SSS_TRACE_RSI_LEARNING=originalEnv;
  }
  const exec = {agent:{session:{id:config.session_id}},signal:new AbortController().signal};
  return {registry,services,handlers,exec};
}

test('trace inventory retains unsupported evidence; fixed-ID reading hides memory file contents',t => {
  const f = fixture(t), learning = createTraceLearning(f.config), inventory = learning.list();
  assert.equal(inventory.records.length,2);
  assert.equal(inventory.records[1].replay_status,'unsupported');
  assert.equal(inventory.records[1].replay_reason,'unsupported_source_call');
  const read = learning.read({run_id:'synthetic-run',call_id:'supported-call'});
  assert.equal(read.arguments.command,'print registered data');assert.equal(read.text,'values: development');
  assert.deepEqual(read.output_labels,['values']);assert.deepEqual(read.allowed_files,['fixture.json']);
  assert.equal(Object.hasOwn(read,'memory_files'),false);
  assert.equal(JSON.stringify(read).includes('private synthetic fixture'),false);
  assert.deepEqual(read.json_files,[{filename:'fixture.json',file_sha256:'a'.repeat(64),
    top_level_type:'object',top_level_fields:['values','secret'],shape:{type:'object',fields:{
      values:{type:'array',items:[{type:'string'}],object_keys:[],sampled_items:1},secret:{type:'string'}}}}]);
  assert.match(read.note,/不表示 shell 退出码/);
  const unsupported = learning.read({run_id:'synthetic-run',call_id:'unsupported-call'});
  assert.equal(unsupported.text,'failure retained');assert.equal(unsupported.replay_status,'unsupported');
  assert.throws(() => learning.read({run_id:'synthetic-run',call_id:'supported-call',path:'/etc/passwd'}),/invalid_arguments/);
  assert.throws(() => learning.read({run_id:'another-run',call_id:'supported-call'}),/unknown_trace_entry/);
  inventory.records[0].output_labels.push('caller-mutated');read.output_labels.push('caller-mutated');
  assert.deepEqual(learning.list().records[0].output_labels,['values']);
});

test('JSON shape exposes nested kinds and combines the first three array items without scalar values',t => {
  const f = fixture(t), raw = {rows:[{key:'secret-one',metadata:{ok:true,count:123}},
    {key:'secret-two',extra:null},{key:'secret-three',metadata:{ok:false,count:456}},
    {outside_sample:'must-not-be-sampled'}],label:'private scalar',score:99};
  f.bundle.entries[0].memory_files['fixture.json']=JSON.stringify(raw);
  writeFileSync(f.config.trace_bundle_path,JSON.stringify(f.bundle));
  const read = createTraceLearning(f.config).read({run_id:'synthetic-run',call_id:'supported-call'});
  const shape = read.json_files[0].shape;
  assert.deepEqual(shape.fields.label,{type:'string'});assert.deepEqual(shape.fields.score,{type:'number'});
  assert.equal(shape.fields.rows.type,'array');assert.equal(shape.fields.rows.sampled_items,3);
  assert.equal(shape.fields.rows.items.length,2);
  assert.deepEqual(shape.fields.rows.object_keys,['key','metadata','extra']);
  assert.deepEqual(shape.fields.rows.items[0].fields.metadata,{type:'object',fields:{ok:{type:'boolean'},count:{type:'number'}}});
  for (const secret of ['secret-one','secret-two','secret-three','private scalar','must-not-be-sampled','outside_sample'])
    assert.equal(JSON.stringify(shape).includes(secret),false);
  assert.deepEqual(read.shape_limits,{max_depth:6,max_nodes:2000,array_sample_items:3});
});

test('shape output stops at six levels and shares a 2000-node budget across memory files',t => {
  const f = fixture(t);let deep = 'private deep scalar';
  for (let i=0;i<20;i++) deep={child:deep};
  const wide = Object.fromEntries(Array.from({length:2500},(_,index) => ['field_'+index,'private wide scalar']));
  f.bundle.entries[0].memory_files={'deep.json':JSON.stringify(deep),'wide.json':JSON.stringify(wide),
    'later.json':'{"later":"private later scalar"}'};
  writeFileSync(f.config.trace_bundle_path,JSON.stringify(f.bundle));
  const read = createTraceLearning(f.config).read({run_id:'synthetic-run',call_id:'supported-call'});
  let nodes=0,maxDepth=0;
  function count(shape,depth=1) {
    if (!shape) return;
    nodes++;maxDepth=Math.max(maxDepth,depth);
    for (const child of Object.values(shape.fields??{})) count(child,depth+1);
    for (const child of shape.items??[]) count(child,depth+1);
  }
  for (const file of read.json_files) count(file.shape);
  assert.ok(nodes<=2000);assert.equal(maxDepth,6);
  let leaf=read.json_files[0].shape;for(let i=1;i<6;i++)leaf=leaf.fields.child;
  assert.deepEqual(leaf,{type:'object',truncated:true});
  assert.equal(read.json_files[1].shape.truncated,true);assert.equal(read.json_files[1].top_level_fields.length,2000);
  assert.equal(read.json_files[2].shape_status,'node_limit');
  assert.equal(JSON.stringify(read.json_files).includes('private deep scalar'),false);
  assert.equal(JSON.stringify(read.json_files).includes('private wide scalar'),false);
});

test('candidate installation requires the accepted full contract and preserves hash artifacts',t => {
  const f = fixture(t), learning = createTraceLearning(f.config);
  assert.throws(() => learning.install(f.candidate));f.seedAccepted();
  for (const altered of [{...f.candidate,name:'different_name'},{...f.candidate,description:'different description'},
    {...f.candidate,input_schema:{...f.contract.input_schema,required:[]}},
    {...f.candidate,output_schema:{...f.contract.output_schema,required:[]}}])
    assert.throws(() => learning.install(altered),/candidate_contract_mismatch/);
  const installed = learning.install(f.candidate), candidatePath = join(f.work,digest(f.candidate)+'.candidate.json');
  assert.equal(installed.candidate_sha256,digest(f.candidate));assert.equal(installed.proposal_sha256,f.accepted.proposal_sha256);
  assert.deepEqual(JSON.parse(readFileSync(candidatePath,'utf8')),f.candidate);
  learning.install(f.candidate);
  writeFileSync(candidatePath,JSON.stringify({...f.candidate,description:'tampered'}));
  assert.throws(() => learning.install(f.candidate),/candidate_artifact_collision/);
  assert.equal(JSON.parse(readFileSync(candidatePath,'utf8')).description,'tampered');
});

test('accepted proposal digests and development examples cannot drift after installation',t => {
  const f = fixture(t);f.seedAccepted();const learning = createTraceLearning(f.config);learning.install(f.candidate);
  writeFileSync(join(f.work,'accepted-proposal.json'),JSON.stringify({...f.accepted,proposal_sha256:'f'.repeat(64)}));
  assert.throws(() => learning.test({}),/accepted_proposal_or_training_changed/);
  assert.throws(() => learning.trial({input:{values:[]}}),/accepted_proposal_or_training_changed/);
  f.seedAccepted();const changed = clone(f.training);changed[0].expected.values=['changed'];
  writeFileSync(join(f.work,'training.json'),JSON.stringify(changed));
  assert.throws(() => learning.test({}),/accepted_proposal_or_training_changed/);
  assert.throws(() => learning.install(f.candidate),/accepted_proposal_or_training_changed/);
  assert.throws(() => learning.installProgram(['var','input']),/accepted_proposal_or_training_changed/);
});

test('program-only installation uses the fixed accepted contract and grants no host capability',t => {
  const f = fixture(t);f.seedAccepted();const mounted = mount(f.config), service = mounted.services.get('sssTraceRsi');
  assert.equal(typeof service.install,'function');assert.equal(typeof service.installProgram,'function');
  assert.deepEqual(Object.keys(service).sort(),['install','installProgram']);
  const result = service.installProgram(['var','input']);
  const saved = JSON.parse(readFileSync(join(f.work,'current-candidate.json'),'utf8'));
  assert.deepEqual(saved,f.candidate);assert.equal(result.candidate_sha256,digest(f.candidate));
  for (const program of [['eval',['lit','process.exit()']],['host',['lit','readFile']],['spawn',['lit','bash']]])
    assert.throws(() => service.installProgram(program),/invalid_program_node/);
  // A syntactically valid unknown variable is denied when the pure interpreter runs.
  const learning = createTraceLearning(f.config);learning.installProgram(['var','process']);
  assert.throws(() => learning.trial({input:{values:[]}}),/unknown_variable/);
  learning.installProgram(['get',['var','input'],['lit','constructor']]);
  assert.throws(() => learning.trial({input:{values:[]}}),/unsafe_get/);
  assert.deepEqual([...mounted.registry.keys()],learningNames);
});

test('native Cordis cross-realm candidate and program submissions normalize to local JSON',t => {
  const f = fixture(t);f.seedAccepted();const learning = createTraceLearning(f.config);
  const foreignCandidate = runInNewContext('('+JSON.stringify(f.candidate)+')');
  assert.throws(() => validateTraceCandidate(foreignCandidate),/plain_object_required/);
  const installed = learning.install(foreignCandidate);
  assert.equal(installed.candidate_sha256,digest(f.candidate));assert.equal(learning.test({}).passed,true);
  const foreignProgram = runInNewContext('(["var","input"])');
  assert.equal(learning.installProgram(foreignProgram).candidate_sha256,digest(f.candidate));
  assert.deepEqual(learning.trial({input:{values:['realm-normalized']}}).output,{values:['realm-normalized']});
  foreignProgram[1]='process';foreignCandidate.description='caller mutation';
  assert.equal(learning.test({}).passed,true);
  const ClassValue = class { constructor() { this.values=[]; } };
  assert.throws(() => runTraceTool(f.candidate,new ClassValue()),/plain_object_required/);
  assert.throws(() => runTraceTool(f.candidate,{values:undefined}),/non_json_value/);
  for (const program of [['lit',undefined],['lit',Infinity],['lit',1n],['lit',()=>true],
    ['lit',Symbol('bad')],['lit',Array(1)]]) assert.throws(() => learning.installProgram(program),/candidate_submission_/);
  const cycle=[];cycle.push(cycle);assert.throws(() => learning.installProgram(cycle),/candidate_submission_cyclic/);
  const accessor={};Object.defineProperty(accessor,'program',{enumerable:true,get(){throw Error('getter_must_not_run');}});
  assert.throws(() => learning.install(accessor),/candidate_submission_non_json_property/);
  assert.throws(() => learning.installProgram(['lit','x'.repeat(128000)]),/candidate_submission_too_large/);
});

test('five tools register before restrictions and every execution rejects foreign or missing sessions',async t => {
  const f = fixture(t), mounted = mount(f.config), known = new Set([...learningNames,...cordisNames]);
  let allow, deny;
  const created = mounted.handlers.get('agent/created');
  created({agent:{session:{id:f.config.session_id},ctx:{tools:{restrict(filter) {
    assert.equal(mounted.registry.size,5);assert.ok(filter.allow.every(name => known.has(name)));allow=filter.allow;
  }}}}});
  created({agent:{session:{id:'foreign-session'},ctx:{tools:{restrict(filter) { deny=filter.deny; }}}}});
  assert.deepEqual(allow,[...cordisNames,...learningNames]);assert.deepEqual(deny,learningNames);
  const args = {rsi_trace_list:{},rsi_trace_read:{run_id:'synthetic-run',call_id:'supported-call'},
    rsi_propose:{proposal:f.proposal},rsi_test:{},rsi_trial:{input:{values:[]}}};
  for (const name of learningNames) {
    const definition = mounted.registry.get(name);
    await assert.rejects(definition.execute(args[name],{agent:{session:{id:'foreign-session'}}}),/session_not_authorized/);
    await assert.rejects(definition.execute(args[name],{}),/session_not_authorized/);
    const cancelled = new AbortController();cancelled.abort();
    await assert.rejects(definition.execute(args[name],{...mounted.exec,signal:cancelled.signal}),/cancelled/);
  }
  const result = await mounted.registry.get('rsi_trace_list').execute({},mounted.exec);
  assert.equal(result.records.length,2);assert.ok(mounted.services.get('sssTraceRsi'));
});

test('fixed diagnostic controller receives proposal via stdin and accepted target cannot be reproposed',t => {
  const f = fixture(t);
  // Deterministic subprocess fixture verifies transport only. This is not a
  // substitute for the Python replay controller or real-model acceptance.
  writeFileSync(f.config.controller_path,`
const fs=require('fs');let text='';process.stdin.on('data',v=>text+=v);
process.stdin.on('end',()=>{
  const proposal=JSON.parse(text);
  fs.writeFileSync('controller-invocation.json',JSON.stringify({args:process.argv.slice(2),proposal}));
  fs.writeFileSync('accepted-proposal.json',JSON.stringify(${JSON.stringify(f.accepted)}));
  fs.writeFileSync('training.json',JSON.stringify(${JSON.stringify(f.training)}));
  process.stdout.write(JSON.stringify({proposal_sha256:${JSON.stringify(f.accepted.proposal_sha256)},contract:proposal.contract,
    training:${JSON.stringify(f.training)},heldout_cases:2,source_replay_kind:'same_source_counterfactual'}));
});`);
  const learning = createTraceLearning(f.config), feedback = learning.propose({proposal:f.proposal});
  assert.equal(feedback.proposal_sha256,digest(f.proposal));
  const invocation = JSON.parse(readFileSync(join(f.work,'controller-invocation.json'),'utf8'));
  assert.deepEqual(invocation.args,['--phase','prepare-proposal','--experiment',f.config.experiment_path]);
  assert.deepEqual(invocation.proposal,f.proposal);
  assert.throws(() => learning.propose({proposal:{...f.proposal,contract:{...f.contract,name:'another_tool'}}}),/proposal_already_accepted/);
  learning.install(f.candidate);assert.equal(learning.test({}).passed,true);
  assert.deepEqual(learning.trial({input:{values:['trial']}}).output,{values:['trial']});
  assert.throws(() => learning.trial({input:{values:[1]}}),/input_schema_type/);
  const rows = readFileSync(join(f.work,'learning.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  for (const kind of ['proposal_accepted','candidate_installed','development_test','trial'])assert.ok(rows.some(row => row.kind === kind));
  assert.ok(rows.every(row => row.proposal_sha256 === digest(f.proposal)));
  const trials = rows.filter(row => row.kind === 'trial');assert.equal(trials.length,2);
  assert.equal(trials[0].input_sha256,digest({values:['trial']}));assert.equal(trials[0].output_sha256,digest({values:['trial']}));
  assert.match(trials[1].error,/input_schema_type/);
});

test('proposal controller digest mismatch cannot install a candidate',t => {
  const f = fixture(t), badAccepted = {...f.accepted,proposal_sha256:'c'.repeat(64)};
  writeFileSync(f.config.controller_path,`
const fs=require('fs');process.stdin.resume();process.stdin.on('end',()=>{
  fs.writeFileSync('accepted-proposal.json',JSON.stringify(${JSON.stringify(badAccepted)}));
  fs.writeFileSync('training.json',JSON.stringify(${JSON.stringify(f.training)}));
  process.stdout.write(JSON.stringify({proposal_sha256:${JSON.stringify(f.accepted.proposal_sha256)},contract:${JSON.stringify(f.contract)},training:${JSON.stringify(f.training)}}));
});`);
  const learning = createTraceLearning(f.config);
  assert.throws(() => learning.propose({proposal:f.proposal}),/proposal_digest_mismatch/);
  assert.throws(() => learning.install(f.candidate),/proposal_digest_mismatch/);
});

test('dynamic frozen service rejects unknown calls, mutable schema copies and library drift',t => {
  const f = fixture(t), tools = createTraceRsiTools({library_path:f.libraryPath});
  assert.equal(tools.definitions.length,1);assert.equal(tools.definitions[0].name,f.candidate.name);
  assert.deepEqual(tools.definitions[0].inputSchema,f.contract.input_schema);
  assert.deepEqual(tools.call(f.candidate.name,{values:['dynamic']}),{
    output:{values:['dynamic']},candidate_sha256:digest(f.candidate)});
  assert.throws(() => tools.call('read_file',{path:'/etc/passwd'}),/unknown_tool/);
  tools.definitions[0].inputSchema.properties.path={type:'string'};
  assert.throws(() => tools.call(f.candidate.name,{values:[],path:'/etc/passwd'}),/input_schema_additional_property/);
  const changed = clone(f.frozen);changed.candidate.description='changed';
  writeFileSync(f.libraryPath,JSON.stringify(changed));
  assert.throws(() => tools.call(f.candidate.name,{values:[]}),/frozen_trace_library_changed/);
  assert.throws(() => createTraceRsiTools({library_path:f.libraryPath}),/unverified_trace_frozen_tool/);
  assert.throws(() => createTraceRsiTools({library_path:f.libraryPath,work:f.work}),/explicit_frozen_trace_library_required/);
});

test('frozen dynamic tool speaks real MCP stdio with no model calls',t => {
  const f = fixture(t), configPath = join(f.work,'mcp-config.json');
  writeFileSync(configPath,JSON.stringify({library_path:f.libraryPath}));
  const requests = [
    {jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18'}},
    {jsonrpc:'2.0',id:2,method:'tools/list'},
    {jsonrpc:'2.0',id:3,method:'tools/call',params:{name:f.candidate.name,arguments:{values:['stdio']}}},
    {jsonrpc:'2.0',id:4,method:'tools/call',params:{name:'unknown_tool',arguments:{}}},
    {jsonrpc:'2.0',id:5,method:'tools/call',params:{name:f.candidate.name,arguments:{values:[],file_path:'/etc/passwd'}}},
    {jsonrpc:'2.0',id:6,method:'ping'}
  ];
  const serverPath = fileURLToPath(new URL('../scenarios/paper-submission/trace-rsi-server.ts',import.meta.url));
  const child = spawnSync(process.execPath,['--experimental-strip-types',serverPath],{
    env:{...process.env,SSS_TRACE_RSI_CONFIG:configPath},input:requests.map(JSON.stringify).join('\n')+'\n',
    encoding:'utf8',timeout:5000,maxBuffer:1000000});
  assert.equal(child.status,0,child.stderr);
  const rows = child.stdout.trim().split('\n').map(JSON.parse);assert.equal(rows.length,requests.length);
  assert.equal(rows[0].result.protocolVersion,'2025-06-18');assert.equal(rows[1].result.tools.length,1);
  assert.equal(rows[1].result.tools[0].name,f.candidate.name);
  assert.deepEqual(JSON.parse(rows[2].result.content[0].text),{output:{values:['stdio']},candidate_sha256:digest(f.candidate)});
  assert.equal(rows[3].result.isError,true);assert.match(rows[3].result.content[0].text,/unknown_tool/);
  assert.equal(rows[4].result.isError,true);assert.match(rows[4].result.content[0].text,/input_schema_additional_property/);
  assert.deepEqual(rows[5].result,{});
});
