/** Isolated trace-derived tool learning. Generated programs remain pure JSON data. */
import { appendFileSync, existsSync, lstatSync, readFileSync, realpathSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { canonical, digest } from './paper_rsi_program.ts';
import { runTraceTool, validateTraceCandidate } from './trace_rsi_program.ts';

export const name = 'sss-trace-rsi-learning';
export const inject = ['tools', 'agents'];
const learningNames = ['rsi_trace_list', 'rsi_trace_read', 'rsi_propose', 'rsi_test', 'rsi_trial'];
const cordisNames = ['cordis_inspect_list', 'cordis_inspect_query', 'cordis_inspect_self',
  'cordis_define', 'cordis_run', 'cordis_stop', 'cordis_undefine'];
const object = (value:any) => value !== null && typeof value === 'object' && !Array.isArray(value);
const hash = (value:any) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const bytesHash = (bytes:any) => createHash('sha256').update(bytes).digest('hex');
function readJson(path:string, limit:number):any {
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > limit) throw Error('regular_bounded_file_required');
  const bytes = readFileSync(path);
  if (bytes.length > limit) throw Error('file_too_large');
  return JSON.parse(bytes.toString('utf8'));
}
function exactArgs(args:any, keys:string[]):void {
  if (!object(args) || Object.keys(args).length !== keys.length || keys.some(key => !Object.hasOwn(args,key)))
    throw Error('invalid_arguments');
}
function candidateContract(candidate:any):any {
  return {name:candidate.name, description:candidate.description,
    input_schema:candidate.input_schema, output_schema:candidate.output_schema};
}
function validateContract(contract:any):void {
  exactArgs(contract, ['name','description','input_schema','output_schema']);
  validateTraceCandidate({schema_version:1,...contract,program:['lit',null]});
}
/** Native Cordis objects may belong to another realm. Normalize only JSON data
 * at this submission boundary; the interpreter retains its strict local checks.
 */
function normalizeCandidateSubmission(value:any):any {
  const ancestors = new Set<any>();let nodes = 0;
  function walk(value:any,depth:number):void {
    if (++nodes > 20000 || depth > 48) throw Error('candidate_submission_too_complex');
    if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
    if (typeof value === 'number') {
      if (!Number.isFinite(value)) throw Error('candidate_submission_non_json_number');
      return;
    }
    if (typeof value !== 'object') throw Error('candidate_submission_non_json_value');
    if (ancestors.has(value)) throw Error('candidate_submission_cyclic');
    const array = Array.isArray(value), prototype = Object.getPrototypeOf(value);
    // Object.prototype has a null parent in both the host and native Cordis VM.
    if (!array && prototype !== null && Object.getPrototypeOf(prototype) !== null)
      throw Error('candidate_submission_plain_object_required');
    const keys = Reflect.ownKeys(value);
    if (keys.some(key => typeof key !== 'string')) throw Error('candidate_submission_non_json_key');
    if (array && (value.length > 2000 || keys.length !== value.length + 1)) throw Error('candidate_submission_dense_array_required');
    ancestors.add(value);
    for (const key of keys as string[]) {
      if (array && key === 'length') continue;
      if (array && (!/^(0|[1-9][0-9]*)$/.test(key) || Number(key) >= value.length)) throw Error('candidate_submission_non_json_key');
      const descriptor = Object.getOwnPropertyDescriptor(value,key)!;
      if (!descriptor.enumerable || !Object.hasOwn(descriptor,'value')) throw Error('candidate_submission_non_json_property');
      walk(descriptor.value,depth+1);
    }
    ancestors.delete(value);
  }
  walk(value,0);
  let text:string;
  try { text = JSON.stringify(value); } catch { throw Error('invalid_candidate_json_submission'); }
  if (typeof text !== 'string' || Buffer.byteLength(text) > 128000) throw Error('candidate_submission_too_large');
  try { return JSON.parse(text); } catch { throw Error('invalid_candidate_json_submission'); }
}
const jsonType = (value:any) => value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value;
/** Shape reveals field names and value kinds, never scalar values. */
function jsonShape(value:any,budget:{remaining:number},depth=1):any {
  if (budget.remaining <= 0) return undefined;
  budget.remaining--;
  const type = jsonType(value), shape:any = {type};
  if (type !== 'object' && type !== 'array') return shape;
  if (depth >= 6) return {...shape,truncated:true};
  if (type === 'object') {
    const fields:[string,any][] = [], keys = Object.keys(value);
    for (const key of keys) {
      if (budget.remaining <= 0) break;
      fields.push([key,jsonShape(value[key],budget,depth+1)]);
    }
    shape.fields = Object.fromEntries(fields);
    if (fields.length < keys.length) shape.truncated = true;
  } else {
    const items:any[] = [], seen = new Set<string>(), objectKeys = new Set<string>();
    let sampled = 0;
    for (const item of value.slice(0,3)) {
      if (budget.remaining <= 0) break;
      const itemShape = jsonShape(item,budget,depth+1), signature = canonical(itemShape);
      sampled++;
      if (!seen.has(signature)) { seen.add(signature);items.push(itemShape); }
      if (itemShape.fields) for (const key of Object.keys(itemShape.fields)) objectKeys.add(key);
    }
    shape.items = items;shape.object_keys = [...objectKeys];shape.sampled_items = sampled;
    if (sampled < Math.min(3,value.length)) shape.truncated = true;
  }
  return shape;
}

/** Only configured artifact paths are read. No trace command is executed here. */
export function createTraceLearning(config:any) {
  if (!object(config) || ['work','session_id','trace_bundle_path','experiment_path','python_command','controller_path']
    .some(key => typeof config[key] !== 'string' || !config[key])) throw Error('invalid_trace_learning_config');
  const work = realpathSync(config.work);
  if (!lstatSync(work).isDirectory()) throw Error('learning_work_directory_required');
  const acceptedPath = join(work,'accepted-proposal.json'), trainingPath = join(work,'training.json');
  const bundle = readJson(config.trace_bundle_path,16000000);
  if (!object(bundle) || bundle.schema_version !== 1 || !Array.isArray(bundle.entries) || bundle.entries.length > 2000)
    throw Error('invalid_trace_bundle');
  const entryKeys = new Set<string>();
  for (const entry of bundle.entries) {
    if (!object(entry) || typeof entry.run_id !== 'string' || typeof entry.call_id !== 'string') throw Error('invalid_trace_entry');
    const key = canonical([entry.run_id,entry.call_id]);
    if (entryKeys.has(key)) throw Error('duplicate_trace_entry');
    entryKeys.add(key);
  }
  const bundleSha = digest(bundle);
  let current:any = null, acceptedSha:string|null = null, trainingSha:string|null = null, proposalSha:string|null = null;
  const audit = (row:any) => appendFileSync(join(work,'learning.jsonl'), JSON.stringify({
    timestamp:new Date().toISOString(), session_id:config.session_id, ...row})+'\n',{mode:0o600});
  function accepted() {
    const proposal = readJson(acceptedPath,256000), training = readJson(trainingPath,2000000);
    if (!object(proposal) || proposal.schema_version !== 1) throw Error('invalid_accepted_proposal');
    validateContract(proposal.contract);
    if (!Array.isArray(training) || !training.length || training.length > 2000 || training.some(row =>
      !object(row) || !Object.hasOwn(row,'input') || !Object.hasOwn(row,'expected'))) throw Error('invalid_development_training');
    const nextAcceptedSha = digest(proposal), nextTrainingSha = digest(training);
    if (acceptedSha && (nextAcceptedSha !== acceptedSha || nextTrainingSha !== trainingSha)) throw Error('accepted_proposal_or_training_changed');
    if (!proposalSha) {
      if (!hash(proposal.proposal_sha256)) throw Error('accepted_proposal_digest_required');
      proposalSha = proposal.proposal_sha256;
    } else if (Object.hasOwn(proposal,'proposal_sha256') && proposal.proposal_sha256 !== proposalSha) throw Error('proposal_digest_mismatch');
    acceptedSha = nextAcceptedSha; trainingSha = nextTrainingSha;
    return {proposal,training,proposal_sha256:proposalSha};
  }
  function installed() {
    if (!current) throw Error('install_candidate_first');
    const state = accepted();
    if (canonical(candidateContract(current)) !== canonical(state.proposal.contract)) throw Error('candidate_contract_mismatch');
    return state;
  }
  function list() {
    return JSON.parse(JSON.stringify({schema_version:1,trace_bundle_sha256:bundleSha,records:bundle.entries.map((entry:any) => ({
      run_id:entry.run_id,call_id:entry.call_id,line:entry.line,step:entry.step,tool:entry.tool,
      description:entry.arguments?.description,command_preview:typeof entry.arguments?.command === 'string' ? entry.arguments.command.slice(0,200) : null,
      ok:entry.ok,replay_status:entry.replay_status,replay_reason:entry.replay_reason,output_labels:entry.output_labels}))}));
  }
  function read(args:any) {
    exactArgs(args,['run_id','call_id']);
    if (typeof args.run_id !== 'string' || typeof args.call_id !== 'string') throw Error('trace_identifiers_required');
    const entry = bundle.entries.find((row:any) => row.run_id === args.run_id && row.call_id === args.call_id);
    if (!entry) throw Error('unknown_trace_entry');
    const {memory_files,...visible} = entry;
    const shapeBudget = {remaining:2000};
    const json_files = Object.entries(memory_files ?? {}).map(([filename,content]:[string,any]) => {
      let parsed:any;
      try { parsed = JSON.parse(content); } catch { return null; }
      return {filename,file_sha256:entry.file_sha256?.[filename] ?? bytesHash(content),
        top_level_type:jsonType(parsed),top_level_fields:object(parsed) ? Object.keys(parsed).slice(0,2000) : [],
        ...(shapeBudget.remaining > 0 ? {shape:jsonShape(parsed,shapeBudget)} : {shape_status:'node_limit'})};
    }).filter(Boolean);
    return {...JSON.parse(JSON.stringify(visible)),json_files,trace_bundle_sha256:bundleSha,
      shape_limits:{max_depth:6,max_nodes:2000,array_sample_items:3},
      note:'ok 为工具事件状态；不表示 shell 退出码。只有 observed_replay_match 可作为提案来源。'};
  }
  function propose(args:any) {
    exactArgs(args,['proposal']);
    if (!object(args.proposal)) throw Error('proposal_object_required');
    if (existsSync(acceptedPath)) throw Error('proposal_already_accepted');
    const input = JSON.stringify(args.proposal);
    if (Buffer.byteLength(input) > 256000) throw Error('proposal_too_large');
    const child = spawnSync(config.python_command,[config.controller_path,'--phase','prepare-proposal','--experiment',config.experiment_path],
      {cwd:work,input,encoding:'utf8',timeout:30000,maxBuffer:2000000,windowsHide:true});
    if (child.error) throw Error('proposal_controller_error:'+child.error.message);
    if (child.status !== 0) throw Error('proposal_rejected:'+String(child.stderr || child.stdout || child.signal).slice(0,12000));
    let feedback:any;
    try { feedback = JSON.parse(child.stdout); } catch { throw Error('invalid_proposal_controller_feedback'); }
    if (!object(feedback) || !hash(feedback.proposal_sha256)) throw Error('invalid_proposal_controller_feedback');
    validateContract(feedback.contract);
    proposalSha = feedback.proposal_sha256;
    const state = accepted();
    if (canonical(state.proposal.contract) !== canonical(feedback.contract) || canonical(state.training) !== canonical(feedback.training))
      throw Error('proposal_controller_artifact_mismatch');
    current = null;
    audit({kind:'proposal_accepted',proposal_sha256:proposalSha,contract_sha256:digest(feedback.contract),
      training_sha256:trainingSha,trace_bundle_sha256:bundleSha});
    return feedback;
  }
  function install(candidate:any) {
    candidate = normalizeCandidateSubmission(candidate);
    validateTraceCandidate(candidate);
    const state = accepted();
    if (canonical(candidateContract(candidate)) !== canonical(state.proposal.contract)) throw Error('candidate_contract_mismatch');
    const copy = JSON.parse(JSON.stringify(candidate)), sha = digest(copy), path = join(work,sha+'.candidate.json');
    if (existsSync(path)) {
      if (canonical(readJson(path,128000)) !== canonical(copy)) throw Error('candidate_artifact_collision');
    } else writeFileSync(path,JSON.stringify(copy,null,2)+'\n',{mode:0o600,flag:'wx'});
    const currentPath = join(work,'current-candidate.json');
    if (existsSync(currentPath) && (!lstatSync(currentPath).isFile() || lstatSync(currentPath).isSymbolicLink())) throw Error('invalid_current_candidate_file');
    writeFileSync(currentPath,JSON.stringify(copy,null,2)+'\n',{mode:0o600});
    current = copy;
    audit({kind:'candidate_installed',candidate_sha256:sha,proposal_sha256:proposalSha});
    return {candidate_sha256:sha,proposal_sha256:proposalSha,tool:'rsi_trial'};
  }
  function installProgram(program:any) {
    const state = accepted();
    return install({schema_version:1,...state.proposal.contract,program});
  }
  function test(args:any) {
    exactArgs(args,[]);
    const state = installed();
    const cases = state.training.map((row:any,index:number) => {
      try {
        const actual = runTraceTool(current,row.input);
        return {id:row.id ?? index,passed:canonical(actual) === canonical(row.expected),actual,expected:row.expected};
      } catch (error) { return {id:row.id ?? index,passed:false,error:String(error)}; }
    });
    const result = {candidate_sha256:digest(current),proposal_sha256:proposalSha,passed:cases.every(row => row.passed),cases};
    audit({kind:'development_test',candidate_sha256:result.candidate_sha256,proposal_sha256:proposalSha,passed:result.passed,
      cases:cases.map((row:any,index:number) => ({id:row.id,passed:row.passed,input_sha256:digest(state.training[index].input),
        expected_sha256:digest(state.training[index].expected),...(Object.hasOwn(row,'actual') ? {output_sha256:digest(row.actual)} : {error:row.error})}))});
    return result;
  }
  function trial(args:any) {
    exactArgs(args,['input']); installed();
    const candidateSha = digest(current), inputSha = digest(args.input);
    try {
      const output = runTraceTool(current,args.input);
      audit({kind:'trial',candidate_sha256:candidateSha,proposal_sha256:proposalSha,input_sha256:inputSha,output_sha256:digest(output)});
      return {output,candidate_sha256:candidateSha,proposal_sha256:proposalSha};
    } catch (error) {
      audit({kind:'trial',candidate_sha256:candidateSha,proposal_sha256:proposalSha,input_sha256:inputSha,error:String(error)});
      throw error;
    }
  }
  return {list,read,propose,install,installProgram,test,trial};
}

export function apply(ctx:any):void {
  const path = process.env.SSS_TRACE_RSI_LEARNING;
  if (!path) throw Error('explicit_trace_learning_config_required');
  const config = readJson(path,32000), learning = createTraceLearning(config);
  if (realpathSync(config.work) !== realpathSync(process.cwd())) throw Error('learning_workspace_mismatch');
  const empty = {type:'object',properties:{},additionalProperties:false};
  const definitions = [
    {name:'rsi_trace_list',description:'列出私有正常轨迹的全部工具记录及重放状态，包含不支持重放的记录；不运行历史命令。',parameters:empty,run:learning.list},
    {name:'rsi_trace_read',description:'按 run_id/call_id 读取已登记轨迹的完整命令、结果与重放标签。JSON文件展示有界字段类型shape及摘要，字符串不展示原文；据此选择输入投影，不接受任意路径。',
      parameters:{type:'object',properties:{run_id:{type:'string'},call_id:{type:'string'}},required:['run_id','call_id'],additionalProperties:false},run:learning.read},
    {name:'rsi_propose',description:'提交一个从 observed_replay_match 轨迹抽象的工具名称、说明和输入输出绑定；schema可提供或由固定控制器推导。接受后返回完整契约与开发样例，目标冻结不可更换。',
      parameters:{type:'object',properties:{proposal:{type:'object'}},required:['proposal'],additionalProperties:false},run:learning.propose},
    {name:'rsi_test',description:'对当前已安装候选运行开发样例，返回逐项期望和实际值；不展示独立验收样例。',parameters:empty,run:learning.test},
    {name:'rsi_trial',description:'用调用方提供的JSON运行当前候选纯数据工具；不访问文件、网络或执行宿主代码。',
      parameters:{type:'object',properties:{input:{}},required:['input'],additionalProperties:false},run:learning.trial}
  ];
  // This Harness validates allow-lists against global tools at agent creation.
  for (const definition of definitions) ctx.tools.register({
    name:definition.name,description:definition.description,parameters:definition.parameters,
    output:{schema:{type:'object'},render:(_:any,value:any) => [{type:'text',text:JSON.stringify(value)}]},
    async execute(args:any,exec:any) {
      if (exec?.agent?.session?.id !== config.session_id) throw Error('trace_learning_session_not_authorized');
      if (exec.signal?.aborted) throw Error('trace_learning_cancelled');
      if (definition.name === 'rsi_trace_list') exactArgs(args,[]);
      return definition.run(args);
    }});
  ctx.provide('sssTraceRsi',{install:learning.install,installProgram:learning.installProgram});
  ctx.on('agent/created',({agent}:any) => {
    if (agent.session.id === config.session_id) agent.ctx.tools.restrict({allow:[...cordisNames,...learningNames]});
    else agent.ctx.tools.restrict({deny:learningNames});
  });
}
