/** V9 有限条件只读协议。不是 Agent 循环；无轨迹及独立认证不等于 RSI。 */
import { createHash } from 'node:crypto';

type Obj = Record<string, unknown>;
type Scalar = string | boolean | number;
export type Mode = 'off' | 'shadow' | 'execute';
export type Binding = { from: 'task'; field: string } | { from: 'anchor'; field: string }
  | { from: 'node'; node_id: string; field: string };
export type ConditionalNode = { id: string; tool: string; bindings: Record<string, Binding>;
  output_contract: 'pinned_pages' | 'read_pages' };
export type ConditionalCandidate = {
  schema_version: 1; primitive_version: 'ppt-conditional-read-v1'; candidate_id: string;
  origin: 'manual' | 'learned'; candidate_digest: string;
  anchor: { tool: string; input_version_field: 'input_version' | 'version_sha256';
    predicate: { op: 'field_equals'; field: string; value: Scalar } };
  branches: { on_equal: ConditionalNode[]; on_unequal: ConditionalNode[] };
  contracts: Record<string, { read_only: true; replay_stable: true; input_schema: Obj }>;
  dependencies: Record<string, string>;
  training: { task_fingerprints: string[]; trace_sha256: string[] };
};
/** 由宿主从可信冻结配置加载，不能从模型消息或候选 JSON 推导权限。 */
export type ConditionalGuard = { schema_version: 1; session_id: string; task_fingerprint: string;
  input_version: string; deck_id: string; deck_sha256: string; pages_csv: string;
  job_sha256: string; permission_sha256: string; dependencies: Record<string, string>;
  allowed_tools: string[] };
/** 必须由调用方从独立 Python 认证输出的可信路径加载。摘要只是版本绑定，不是签名。 */
export type ConditionalAdmission = { schema_version: 1; certifier: 'python-independent-v1';
  status: 'passed'; candidate_digest: string; certificate_digest: string;
  training_task_fingerprints: string[]; validation_task_fingerprints: string[];
  validation_evidence_sha256: string[]; branches_tested: string[]; negative_cases: string[] };
export type ToolObservation = { name: string; callId?: string; ok: boolean; barrier?: boolean;
  arguments: Obj; output: Obj | null; sourceVersion?: string; inputVersion?: string };
export type ConditionalProposal = { motif_id: string; certified_digest: string;
  validation_task_fingerprint: string; tool: string; arguments: Obj; expected_version: string;
  version_relation: 'same_source'; prefix_key: string; root_key: string; prefix_length: number;
  supporting_task_count: number; code_node_ids: []; code_program_digests: [];
  similarity: null; selection_basis: 'certified_conditional_read'; protocol: 'ppt-conditional-read-v1';
  branch: 'on_equal' | 'on_unequal'; node_id: string; output_contract: ConditionalNode['output_contract'];
  guard_digest: string; scope: ConditionalGuard };
export type ConditionalDecision = { kind: 'abstain'; reason: string }
  | { kind: 'shadow' | 'propose'; reason: string; proposals: ConditionalProposal[] };

const obj = (v: unknown): v is Obj => v !== null && typeof v === 'object' && !Array.isArray(v);
const sha = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0 && v.length <= 500 && !/[\x00-\x1f]/.test(v);
const uniqueStrings = (v: unknown, minimum = 0): v is string[] => Array.isArray(v) && v.length >= minimum
  && v.every(text) && new Set(v).size === v.length;
const canonical = (v: unknown): string => Array.isArray(v) ? '[' + v.map(canonical).join(',') + ']'
  : obj(v) ? '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}'
    : JSON.stringify(v) ?? 'null';
export const conditionalDigest = (v: unknown): string => createHash('sha256').update(canonical(v)).digest('hex');
const without = (v: Obj, key: string): Obj => Object.fromEntries(Object.entries(v).filter(([k]) => k !== key));
const exact = (v: Obj, keys: string[]): boolean => Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const fieldName = (v: unknown): v is string => typeof v === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(v)
  && !['constructor', 'prototype', '__proto__'].includes(v);
const dependencies = (v: unknown): v is Record<string, string> => obj(v) && Object.keys(v).length > 0
  && Object.keys(v).length <= 40 && Object.entries(v).every(([k, val]) => text(k) && sha(val));
const PIN = 'mcp__ppt__pin_deck_pages', READ = 'mcp__ppt__read_pinned_deck_pages';
const ANCHORS = [PIN, READ, 'mcp__ppt__inspect_deck', 'mcp__ppt__read_deck_plan'];
const lastIndex = <T>(rows: T[], matches: (row: T) => boolean): number => {
  for (let i = rows.length - 1; i >= 0; i--) if (matches(rows[i])) return i;
  return -1;
};
export const REQUIRED_NEGATIVE_CASES = ['missing_state', 'conflicting_arguments', 'permission_changed',
  'dependency_changed', 'source_changed', 'schema_changed', 'tool_failure', 'result_scope_changed'] as const;

export function validateConditionalCandidate(value: unknown): asserts value is ConditionalCandidate {
  if (!obj(value) || !exact(value, ['schema_version', 'primitive_version', 'candidate_id', 'origin', 'candidate_digest',
    'anchor', 'branches', 'contracts', 'dependencies', 'training']) || value.schema_version !== 1
    || value.primitive_version !== 'ppt-conditional-read-v1' || !text(value.candidate_id)
    || !['manual', 'learned'].includes(String(value.origin)) || !sha(value.candidate_digest)
    || value.candidate_digest !== conditionalDigest(without(value, 'candidate_digest'))
    || !dependencies(value.dependencies) || !obj(value.training)
    || !exact(value.training, ['task_fingerprints', 'trace_sha256'])
    || !uniqueStrings(value.training.task_fingerprints, value.origin === 'learned' ? 2 : 0)
    || !uniqueStrings(value.training.trace_sha256, value.origin === 'learned' ? 2 : 0)
    || !value.training.trace_sha256.every(sha)) throw new TypeError('invalid conditional candidate provenance');
  const a = value.anchor, b = value.branches, c = value.contracts;
  if (!obj(a) || !exact(a, ['tool', 'input_version_field', 'predicate']) || !ANCHORS.includes(String(a.tool))
    || !['input_version', 'version_sha256'].includes(String(a.input_version_field)) || !obj(a.predicate)
    || !exact(a.predicate, ['op', 'field', 'value']) || a.predicate.op !== 'field_equals' || !fieldName(a.predicate.field)
    || !(['string', 'boolean'].includes(typeof a.predicate.value) || (typeof a.predicate.value === 'number'
      && Number.isSafeInteger(a.predicate.value))) || (typeof a.predicate.value === 'string' && !text(a.predicate.value))
    || !obj(b) || !exact(b, ['on_equal', 'on_unequal']) || !Array.isArray(b.on_equal) || !Array.isArray(b.on_unequal)
    || !obj(c)) throw new TypeError('invalid bounded conditional branches');
  const nodes = [...b.on_equal, ...b.on_unequal];
  if (nodes.length < 1 || nodes.length > 3) throw new TypeError('conditional graph must contain 1–3 read nodes');
  const allIds = new Set<string>();
  for (const branch of [b.on_equal, b.on_unequal]) {
    const seen = new Set<string>();
    for (const n of branch) {
      if (!obj(n) || !exact(n, ['id', 'tool', 'bindings', 'output_contract']) || !text(n.id)
        || allIds.has(n.id) || ![PIN, READ].includes(String(n.tool)) || !obj(n.bindings)
        || n.output_contract !== (n.tool === PIN ? 'pinned_pages' : 'read_pages')) throw new TypeError('unsupported conditional node');
      const required = n.tool === PIN ? ['deck_id', 'pages_csv'] : ['source_id'];
      if (!exact(n.bindings, required)) throw new TypeError('conditional bindings must fill the entire typed input');
      for (const [key, binding] of Object.entries(n.bindings)) {
        if (!obj(binding) || !fieldName(binding.field) || !['task', 'anchor', 'node'].includes(String(binding.from))
          || !exact(binding, binding.from === 'node' ? ['from', 'node_id', 'field'] : ['from', 'field'])
          || (binding.from === 'node' && (!text(binding.node_id) || !seen.has(binding.node_id)))
          || (key === 'source_id' ? (binding.from === 'task' || binding.field !== 'source_id')
            : (binding.from !== 'task' || binding.field !== key))) throw new TypeError('unwitnessed or forward conditional binding');
      }
      seen.add(n.id); allIds.add(n.id);
    }
  }
  const tools = new Set([String(a.tool), ...nodes.map(n => String(n.tool))]);
  if (Object.keys(c).length !== tools.size) throw new TypeError('conditional contract set changed');
  for (const tool of tools) {
    const contract = c[tool];
    if (!obj(contract) || !exact(contract, ['read_only', 'replay_stable', 'input_schema']) || contract.read_only !== true
      || contract.replay_stable !== true || !obj(contract.input_schema) || contract.input_schema.type !== 'object'
      || !obj(contract.input_schema.properties)
      || !uniqueStrings(contract.input_schema.required, 1)) throw new TypeError('conditional tool is not frozen read-only schema');
    if ([PIN, READ].includes(tool)) {
      const input = contract.input_schema as Obj, properties = input.properties as Obj;
      const required = tool === PIN ? ['deck_id', 'pages_csv'] : ['source_id'];
      if (input.additionalProperties !== false || conditionalDigest(input.required) !== conditionalDigest(required)
        || !exact(properties, required)
        || required.some(k => !obj(properties[k]) || properties[k].type !== 'string')) throw new TypeError('conditional primitive input changed');
    }
  }
}

export function validateConditionalGuard(v: unknown): asserts v is ConditionalGuard {
  if (!obj(v) || !exact(v, ['schema_version', 'session_id', 'task_fingerprint', 'input_version', 'deck_id', 'deck_sha256',
    'pages_csv', 'job_sha256', 'permission_sha256', 'dependencies', 'allowed_tools']) || v.schema_version !== 1
    || ![v.session_id, v.task_fingerprint, v.deck_id].every(text) || ![v.input_version, v.deck_sha256, v.job_sha256, v.permission_sha256].every(sha)
    || !dependencies(v.dependencies) || !uniqueStrings(v.allowed_tools, 1) || typeof v.pages_csv !== 'string'
    || !/^[1-9][0-9]?(?:,[1-9][0-9]?){0,29}$/.test(v.pages_csv)
    || new Set(v.pages_csv.split(',')).size !== v.pages_csv.split(',').length || v.pages_csv.split(',').some(p => Number(p) > 30))
    throw new TypeError('conditional scope must be explicitly authorized and versioned');
}

function admissionMatches(v: unknown, c: ConditionalCandidate): v is ConditionalAdmission {
  if (!obj(v) || !exact(v, ['schema_version', 'certifier', 'status', 'candidate_digest', 'certificate_digest',
    'training_task_fingerprints', 'validation_task_fingerprints', 'validation_evidence_sha256', 'branches_tested', 'negative_cases'])
    || v.schema_version !== 1 || v.certifier !== 'python-independent-v1' || v.status !== 'passed'
    || v.candidate_digest !== c.candidate_digest || !sha(v.certificate_digest)
    || v.certificate_digest !== conditionalDigest(without(v, 'certificate_digest'))
    || conditionalDigest(v.training_task_fingerprints) !== conditionalDigest(c.training.task_fingerprints)
    || !uniqueStrings(v.validation_task_fingerprints, 1) || !uniqueStrings(v.validation_evidence_sha256, 1)
    || !v.validation_evidence_sha256.every(sha) || v.validation_task_fingerprints.some(x => c.training.task_fingerprints.includes(x))
    || !uniqueStrings(v.branches_tested, 2) || conditionalDigest([...v.branches_tested].sort()) !== conditionalDigest(['on_equal', 'on_unequal'])
    || !uniqueStrings(v.negative_cases, REQUIRED_NEGATIVE_CASES.length)
    || conditionalDigest([...v.negative_cases].sort()) !== conditionalDigest([...REQUIRED_NEGATIVE_CASES].sort())) return false;
  return true;
}

function scopeMatches(output: Obj, scope: ConditionalGuard, versionField: string): boolean {
  return output.deck_id === scope.deck_id && output.file_sha256 === scope.deck_sha256 && output[versionField] === scope.input_version
    && (!Object.hasOwn(output, 'pages_csv') || output.pages_csv === scope.pages_csv);
}
function resultMatches(output: Obj | null, node: Pick<ConditionalNode, 'output_contract'>, args: Obj, scope: ConditionalGuard): boolean {
  if (!output || output.isError === true || output.ok === false || output.error || !scopeMatches(output, scope, 'version_sha256')
    || !text(output.source_id)) return false;
  if (node.output_contract === 'pinned_pages') return output.pages_csv === scope.pages_csv
    && output.scope === 'explicit_pages_from_current_persisted_plan';
  return output.source_id === args.source_id && output.scope === 'explicit_pages_only_no_semantic_selection'
    && Number.isSafeInteger(output.total_slides) && Number(output.total_slides) >= Math.max(...scope.pages_csv.split(',').map(Number))
    && Array.isArray(output.slides) && output.slides.every(x => obj(x) && obj(x.slide))
    && conditionalDigest(output.slides.map(x => (x as Obj).page)) === conditionalDigest(scope.pages_csv.split(',').map(Number));
}
function argsMatch(args: Obj, schema: Obj): boolean {
  if (!obj(schema.properties) || !Array.isArray(schema.required) || !exact(args, schema.required as string[])) return false;
  const properties = schema.properties;
  return Object.entries(args).every(([key, value]) => {
    const p = properties[key] as Obj;
    if (!text(value) || !obj(p) || p.type !== 'string' || (typeof p.minLength === 'number' && value.length < p.minLength)
      || (typeof p.maxLength === 'number' && value.length > p.maxLength) || (Array.isArray(p.enum) && !p.enum.includes(value))) return false;
    if (p.pattern !== undefined) {
      // Only the existing, fixed pin-page primitive pattern is supported.
      if (key !== 'pages_csv' || p.pattern !== '^[1-9][0-9]?(?:,[1-9][0-9]?){0,29}$') return false;
      if (!/^[1-9][0-9]?(?:,[1-9][0-9]?){0,29}$/.test(value)) return false;
    }
    return true;
  });
}

/** 在公共 llm/stream 可信会话/prompt gate 内调用；只返回一个已有证据的下一节点。 */
export function proposeConditionalContinuation({ candidate, task, liveGuard, history, availableTools, admission,
  mode = 'off', usedPrefixes = new Set<string>() }: { candidate: unknown; task: unknown; liveGuard: unknown;
  history: ToolObservation[]; availableTools: Map<string, { parameters?: Obj; annotations?: Obj }>;
  admission?: unknown; mode?: Mode; usedPrefixes?: Set<string> }): ConditionalDecision {
  const abstain = (reason: string): ConditionalDecision => ({ kind: 'abstain', reason });
  if (mode === 'off') return abstain('disabled');
  if (!['shadow', 'execute'].includes(mode)) return abstain('invalid_mode');
  try { validateConditionalCandidate(candidate); validateConditionalGuard(task); validateConditionalGuard(liveGuard); }
  catch { return abstain('invalid_protocol'); }
  if (conditionalDigest(task) !== conditionalDigest(liveGuard)) return abstain('live_guard_changed');
  if (conditionalDigest(candidate.dependencies) !== conditionalDigest(task.dependencies)) return abstain('dependency_changed');
  const admitted = admissionMatches(admission, candidate);
  if (mode === 'execute' && !admitted) return abstain('independent_admission_required');
  for (const [name, contract] of Object.entries(candidate.contracts)) {
    const offered = availableTools.get(name);
    if (!task.allowed_tools.includes(name) || !offered || conditionalDigest(offered.parameters) !== conditionalDigest(contract.input_schema)
      || offered.annotations?.readOnlyHint === false) return abstain('permission_or_schema_changed');
  }
  const clean = history.slice(lastIndex(history, row => row.barrier === true) + 1);
  const anchorIndex = lastIndex(clean, row => row.name === candidate.anchor.tool);
  if (anchorIndex < 0) return abstain('missing_anchor');
  const anchor = clean[anchorIndex];
  if (!anchor.ok || !anchor.output || !scopeMatches(anchor.output, task, candidate.anchor.input_version_field)
    || !argsMatch(anchor.arguments, candidate.contracts[candidate.anchor.tool].input_schema)
    || (anchor.inputVersion !== undefined && anchor.inputVersion !== task.input_version)
    || (anchor.arguments.deck_id !== undefined && anchor.arguments.deck_id !== task.deck_id)
    || (anchor.arguments.pages_csv !== undefined && anchor.arguments.pages_csv !== task.pages_csv)) return abstain('anchor_scope_conflict');
  const predicate = anchor.output[candidate.anchor.predicate.field];
  if (!Object.hasOwn(anchor.output, candidate.anchor.predicate.field) || typeof predicate !== typeof candidate.anchor.predicate.value)
    return abstain('missing_predicate_state');
  if ((typeof predicate === 'number' && !Number.isSafeInteger(predicate)) || (typeof predicate === 'string' && !text(predicate)))
    return abstain('invalid_predicate_state');
  if ([PIN, READ].includes(candidate.anchor.tool) && !resultMatches(anchor.output,
    { output_contract: candidate.anchor.tool === PIN ? 'pinned_pages' : 'read_pages' }, anchor.arguments, task))
    return abstain('anchor_result_contract_changed');
  const branch = predicate === candidate.anchor.predicate.value ? 'on_equal' : 'on_unequal';
  const nodes = candidate.branches[branch];
  const witnessed = new Map<string, ToolObservation>();
  let cursor = anchorIndex;
  for (const [index, node] of nodes.entries()) {
    const args: Obj = {};
    for (const [key, binding] of Object.entries(node.bindings)) {
      const output = binding.from === 'task' ? task : binding.from === 'anchor' ? anchor.output : witnessed.get(binding.node_id)?.output;
      const value = output?.[binding.field as keyof typeof output];
      if (!text(value)) return abstain('missing_binding_evidence');
      args[key] = value;
    }
    if (!argsMatch(args, candidate.contracts[node.tool].input_schema)) return abstain('argument_schema_mismatch');
    const matches = clean.slice(cursor + 1).map((row, i) => ({ row, i: cursor + i + 1 }))
      .filter(({ row }) => row.name === node.tool && conditionalDigest(row.arguments) === conditionalDigest(args));
    if (matches.length) {
      if (matches.some(({ row }) => !row.ok || !resultMatches(row.output, node, args, task))
        || new Set(matches.map(({ row }) => conditionalDigest(row.output))).size !== 1) return abstain('conflicting_or_failed_result');
      const match = matches.at(-1)!; cursor = match.i; witnessed.set(node.id, match.row); continue;
    }
    const key = conditionalDigest([candidate.candidate_digest, anchor.callId ?? anchorIndex, branch, node.id, args, task]);
    if (usedPrefixes.has(key)) return abstain('already_attempted');
    const proposal: ConditionalProposal = { motif_id: candidate.candidate_id,
      certified_digest: admitted ? admission.certificate_digest : candidate.candidate_digest,
      validation_task_fingerprint: admitted ? admission.validation_task_fingerprints.join(',') : 'uncertified-shadow',
      tool: node.tool, arguments: args, expected_version: task.input_version, version_relation: 'same_source',
      prefix_key: key, root_key: String(anchor.callId ?? anchorIndex), prefix_length: index + 1,
      supporting_task_count: candidate.training.task_fingerprints.length, code_node_ids: [], code_program_digests: [],
      similarity: null, selection_basis: 'certified_conditional_read', protocol: 'ppt-conditional-read-v1',
      branch, node_id: node.id, output_contract: node.output_contract, guard_digest: conditionalDigest(task), scope: structuredClone(task) };
    return { kind: mode === 'shadow' ? 'shadow' : 'propose', reason: admitted ? 'certified_branch' : 'uncertified_shadow', proposals: [proposal] };
  }
  return abstain(nodes.length ? 'branch_complete' : 'condition_deferred');
}

/** 既有 tools/result lifecycle 必须调用；结果失败不能记作 verified bypass。 */
export function verifyConditionalResult(proposal: ConditionalProposal, execution: { name: string; arguments: Obj },
  output: Obj | null, liveGuard: unknown): { verified: boolean; reason: string } {
  try { validateConditionalGuard(liveGuard); } catch { return { verified: false, reason: 'invalid_live_guard' }; }
  const verified = conditionalDigest(liveGuard) === proposal.guard_digest && conditionalDigest(proposal.scope) === proposal.guard_digest
    && execution.name === proposal.tool && conditionalDigest(execution.arguments) === conditionalDigest(proposal.arguments)
    && resultMatches(output, proposal, execution.arguments, liveGuard);
  return { verified, reason: verified ? 'version_scope_and_result_verified' : 'result_or_live_guard_changed' };
}
