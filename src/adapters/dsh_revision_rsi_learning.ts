/** Revision learning exposes registered normal packets; generated algorithms
 * remain JSON ASTs executed by the existing bounded, pure-data interpreter.
 */
import { appendFileSync, lstatSync, readFileSync, realpathSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import { digest } from './paper_rsi_program.ts';
import { createTraceLearning } from './dsh_trace_rsi_learning.ts';
import { lowerRevisionProgram } from './revision_rsi_macros.ts';

export const name = 'sss-revision-rsi-learning';
export const inject = ['tools', 'agents'];
const learningNames = ['rsi_packet_list','rsi_packet_read','rsi_propose','rsi_test','rsi_trial'];
const cordisNames = ['cordis_inspect_list','cordis_inspect_query','cordis_inspect_self',
  'cordis_define','cordis_run','cordis_stop','cordis_undefine'];
const object = (v:any) => v !== null && typeof v === 'object' && !Array.isArray(v);
const clone = (v:any) => JSON.parse(JSON.stringify(v));
const bytesHash = (v:any) => createHash('sha256').update(v).digest('hex');
const unsafeFields = new Set(['__proto__','prototype','constructor']);
export function revisionInputPatch(before:any,after:any,path=''):any[] {
  if(digest(before)===digest(after))return [];
  if(Array.isArray(before)&&Array.isArray(after)) {
    const patches=[];for(let i=0;i<Math.min(before.length,after.length);i++)patches.push(...revisionInputPatch(before[i],after[i],path+'/'+i));
    for(let i=before.length-1;i>=after.length;i--)patches.push({op:'remove',path:path+'/'+i});
    for(let i=before.length;i<after.length;i++)patches.push({op:'add',path:path+'/'+i,value:after[i]});
    return patches;
  }
  if(object(before)&&object(after)) {
    const patches=[];
    for(const key of [...new Set([...Object.keys(before),...Object.keys(after)])].sort()) {
      const p=path+'/'+key.replaceAll('~','~0').replaceAll('/','~1');
      if(!Object.hasOwn(after,key))patches.push({op:'remove',path:p});
      else if(!Object.hasOwn(before,key))patches.push({op:'add',path:p,value:after[key]});
      else patches.push(...revisionInputPatch(before[key],after[key],p));
    }
    return patches;
  }
  return [{op:'replace',path,value:after}];
}
function fileBytes(path:string, limit:number):Buffer {
  const stat = lstatSync(path);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.size > limit) throw Error('regular_bounded_revision_file_required');
  const bytes = readFileSync(path);
  if (bytes.length > limit) throw Error('revision_file_too_large');
  return bytes;
}
function exactArgs(args:any, required:string[], optional:string[]=[]):void {
  if (!object(args) || required.some(k => !Object.hasOwn(args,k)) ||
      Object.keys(args).some(k => !required.includes(k) && !optional.includes(k))) throw Error('invalid_revision_arguments');
}

/** Packet facts, bindings, output schemas and test expectations come from the
 * configured source/controller. This adapter does not implement revision rules.
 * The old learning host owns immutable accepted contracts, candidate artifacts,
 * cross-realm JSON normalization, trials and development-test auditing.
 */
export function createRevisionLearning(config:any) {
  if (!object(config) || ['work','session_id','training_packets_path','experiment_path','python_command','controller_path']
      .some(k => typeof config[k] !== 'string' || !config[k])) throw Error('invalid_revision_learning_config');
  const bytes = fileBytes(config.training_packets_path,16000000), packetBytesSha = bytesHash(bytes);
  if (Object.hasOwn(config,'training_packets_sha256') && config.training_packets_sha256 !== packetBytesSha)
    throw Error('revision_training_packets_digest_mismatch');
  const bundle = JSON.parse(bytes.toString('utf8'));
  if (!object(bundle) || bundle.schema_version !== 1 || bundle.kind !== 'revision_tool_trace_packets' ||
      !Array.isArray(bundle.entries) || !Array.isArray(bundle.packets) || !bundle.packets.length || bundle.packets.length > 2000)
    throw Error('invalid_revision_training_packets');
  const packets = new Map<string,any>();
  for (const packet of bundle.packets) {
    if (!object(packet) || typeof packet.packet_id !== 'string' || !packet.packet_id || packet.packet_id.length > 200 ||
        typeof packet.run_id !== 'string' || !packet.run_id || !object(packet.before_report) ||
        !object(packet.after_report) || !object(packet.catalog) || !Array.isArray(packet.trace_records))
      throw Error('invalid_revision_packet');
    if (packets.has(packet.packet_id)) throw Error('duplicate_revision_packet');
    packets.set(packet.packet_id,packet);
  }
  const work = realpathSync(config.work);
  const host = createTraceLearning({...config,trace_bundle_path:config.training_packets_path});
  function guard():void {
    if (bytesHash(fileBytes(config.training_packets_path,16000000)) !== packetBytesSha)
      throw Error('revision_training_packets_changed');
  }
  function guarded(fn:(...args:any[])=>any) {
    return (...args:any[]) => { guard();try { return fn(...args); } finally { guard(); } };
  }
  const audit = (row:any) => appendFileSync(join(work,'learning.jsonl'),JSON.stringify({
    timestamp:new Date().toISOString(),session_id:config.session_id,training_packets_sha256:packetBytesSha,...row})+'\n',{mode:0o600});
  function list(args:any={}) {
    exactArgs(args,[]);
    const rows = [...packets.values()].map(packet => ({
      packet_id:packet.packet_id,run_id:packet.run_id,session_id:packet.session_id,case_id:packet.case_id,
      classification:packet.classification,learning_eligible:packet.learning_eligible,
      motif_training_eligible:packet.motif_training_eligible,packet_sha256:digest(packet),
      sections:Object.keys(packet),trace_record_count:packet.trace_records.length,
      before_report_sha256:packet.before_report_sha256,after_report_sha256:packet.after_report_sha256,
      catalog_sha256:packet.catalog_sha256,
    }));
    audit({kind:'revision_packets_listed',packet_count:rows.length});
    return clone({schema_version:1,training_packets_sha256:packetBytesSha,packets:rows});
  }
  function read(args:any) {
    exactArgs(args,['packet_id'],['sections']);
    if (typeof args.packet_id !== 'string' || !packets.has(args.packet_id)) throw Error('unknown_revision_packet');
    const packet = packets.get(args.packet_id), sections = args.sections ?? Object.keys(packet);
    if (!Array.isArray(sections) || !sections.length || sections.length > 64 || new Set(sections).size !== sections.length ||
        sections.some(k => typeof k !== 'string' || unsafeFields.has(k) || !Object.hasOwn(packet,k)))
      throw Error('invalid_revision_packet_sections');
    const selected = Object.fromEntries(sections.map(k => [k,packet[k]]));
    audit({kind:'revision_packet_read',packet_id:packet.packet_id,packet_sha256:digest(packet),sections});
    return clone({schema_version:1,packet_id:packet.packet_id,packet_sha256:digest(packet),
      training_packets_sha256:packetBytesSha,packet:selected});
  }
  return {list:guarded(list),read:guarded(read),propose:guarded((args:any)=> {
    const result=host.propose(args), example=result.training[0].input;
    const compact={...result,example_input:example,
      training:result.training.map((row:any)=>({id:row.id,expected:row.expected,input_sha256:digest(row.input),
        input_changes:revisionInputPatch(example,row.input)})),
      training_protocol:'Apply each RFC6902 input_changes to a fresh clone of example_input; verify input_sha256. Full training values remain immutable in the controller.'};
    audit({kind:'development_inputs_projected',case_count:result.training.length,
      full_feedback_bytes:Buffer.byteLength(JSON.stringify(result)),projected_feedback_bytes:Buffer.byteLength(JSON.stringify(compact))});
    return compact;
  }),
    install:guarded(host.install),installProgram:guarded((program:any)=> {
      const lowered=lowerRevisionProgram(program);
      audit({kind:'program_lowered',submitted_program_sha256:digest(program),lowered_program_sha256:digest(lowered)});
      return host.installProgram(lowered);
    }),
    test:guarded(host.test),trial:guarded(host.trial)};
}

export function apply(ctx:any):void {
  const path = process.env.SSS_REVISION_RSI_LEARNING;
  if (!path) throw Error('explicit_revision_learning_config_required');
  const config = JSON.parse(fileBytes(path,32000).toString('utf8'));
  if (realpathSync(config.work) !== realpathSync(process.cwd())) throw Error('revision_learning_workspace_mismatch');
  const learning = createRevisionLearning(config), empty = {type:'object',properties:{},additionalProperties:false};
  const proposalGates = new WeakMap<object,()=>void>();
  const definitions = [
    {name:'rsi_packet_list',description:'列出已登记的真实正常报告读/写/检查训练包及失败反例、字段和来源摘要。不执行历史工具；失败来源的Motif训练资格单列。',parameters:empty,run:learning.list},
    {name:'rsi_packet_read',description:'读取指定训练packet。sections可选已登记顶层字段，例如before_report、after_report、catalog、trace_records、oracle_facts；不接受路径。保留实际来源与过程证据，独立留出样例不在训练包中。',
      parameters:{type:'object',properties:{packet_id:{type:'string'},sections:{type:'array',items:{type:'string'}}},required:['packet_id'],additionalProperties:false},run:learning.read},
    {name:'rsi_propose',description:'自主选择可复用的工具目标、字段绑定、名称和契约，由固定控制器核验正常轨迹与独立事实、返回开发样例。可探索计数、修订差异、字段保留等方向；具体输入输出由提案决定。接受后目标冻结。',
      parameters:{type:'object',properties:{proposal:{type:'object'}},required:['proposal'],additionalProperties:false},run:learning.propose},
    {name:'rsi_test',description:'运行已安装候选的开发样例，逐项比较完整输出及所选输出schema。不展示独立留出样例；开发通过不等于晋级或科研质量认证。',parameters:empty,run:learning.test},
    {name:'rsi_trial',description:'对调用方提供的JSON输入运行已安装纯JSON AST候选，输出按模型选择的契约验证；没有文件、网络、eval或宿主执行能力。',
      parameters:{type:'object',properties:{input:{}},required:['input'],additionalProperties:false},run:learning.trial},
  ];
  // Harness checks restrict allow-lists at creation, so register all five first.
  for (const definition of definitions) ctx.tools.register({
    name:definition.name,description:definition.description,parameters:definition.parameters,
    output:{schema:{type:'object'},render:(_:any,value:any) => [{type:'text',text:JSON.stringify(value)}]},
    async execute(args:any,exec:any) {
      if (exec?.agent?.session?.id !== config.session_id) throw Error('revision_learning_session_not_authorized');
      if (exec.signal?.aborted) throw Error('revision_learning_cancelled');
      const result = definition.run(args);
      if (definition.name === 'rsi_propose') {
        // Creating probe tools before a contract is accepted wastes learning
        // calls and can bypass the intended bounded submission path.
        proposalGates.get(exec.agent)?.();proposalGates.delete(exec.agent);
      }
      return result;
    },
  });
  ctx.provide('sssRevisionRsi',{install:learning.install,installProgram:learning.installProgram});
  ctx.on('agent/created',({agent}:any) => {
    if (agent.session.id === config.session_id) {
      agent.ctx.tools.restrict({allow:[...cordisNames,...learningNames]});
      const dispose = agent.ctx.tools.restrict({deny:cordisNames});
      if (typeof dispose === 'function') proposalGates.set(agent,dispose);
    }
    else agent.ctx.tools.restrict({deny:learningNames});
  });
}
