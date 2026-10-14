import assert from 'node:assert/strict';
import test from 'node:test';
import { BlockAssembler } from '@deepseek-ai/dsh-llm';
import { createOnlineInterceptor } from '../src/adapters/dsh_online_motif.mjs';
import { compileLocalPrograms, digest, validateOnlineManifest, parseStructuredTask, proposeReadyBatch }
  from '../src/motif_core/online_skill_runtime.mjs';

// Synthetic compiler-shaped fixture: tests authorization, not learning quality.
function fixture() {
  const names = ['mcp__test__extract', 'mcp__test__verify', 'mcp__test__assemble'];
  const params = ['plan', 'extraction_id', 'verification_id'];
  const receipts = ['extraction_id', 'verification_id', 'packet_id'];
  const statuses = ['extracted', 'verified', 'packet_ready'];
  const offered = names.map((name, i) => ({ name, parameters: { type: 'object',
    required: [params[i]], properties: { [params[i]]: { type: 'string' } } } }));
  const p = { schema_version: 1, kind: 'approved_plan_continuation', steps: names.map((tool, i) =>
    ({ tool, param: params[i], receipt_field: receipts[i], success_status: statuses[i],
      input_schema_sha256: digest(offered[i].parameters) })) };
  const artifact = { motif_id: 'test-only-chain', certified_digest: 'a'.repeat(64), tools: names,
    continuation_policy_digest: digest(p), supporting_task_count: 2,
    validation_task_fingerprint: 'test-heldout', transfer_evidence: [1, 2].map(i =>
      ({ from_tool: names[i - 1], from_field: receipts[i - 1], to_tool: names[i], to_param: params[i] })) };
  artifact.local_programs = compileLocalPrograms(artifact);
  const manifest = { schema_version: 2, source_library_digest: 'b'.repeat(64), artifacts: [artifact],
    contracts: Object.fromEntries(names.map((n, i) => [n, { read_only: true,
      required_params: [params[i]], default_params: {}, output_fields: [receipts[i], 'execution_version_sha256'],
      description: 'Bounded mechanical preparation', continuation_policy: p }])),
    slot_rules: {}, version_fields: Object.fromEntries(names.map(n => [n, 'execution_version_sha256'])) };
  const seal = () => manifest.manifest_digest = digest(Object.fromEntries(Object.entries(manifest)
    .filter(([k]) => k !== 'manifest_digest')));
  seal();
  const task = { schema_version: 1, task_id: 'test-task', session_id: 'test-session', intent: 'Prepare evidence',
    input_version: 'c'.repeat(64), bindings: {}, source_versions: Object.fromEntries(names.map(n => [n, 'd'.repeat(64)])),
    continuation_policy_digests: [digest(p)] };
  const plan = 'source-' + '1'.repeat(32);
  const ids = ['source-' + '2'.repeat(32), 'dataset-' + '3'.repeat(32), 'result-' + '4'.repeat(32)];
  const outputs = names.map((n, i) => ({ status: statuses[i], task_sha256: task.input_version,
    execution_version_sha256: 'd'.repeat(64), [receipts[i]]: ids[i], continuation_grant: {
      schema_version: 1, policy_sha256: digest(p), task_input_version: task.input_version,
      execution_version: 'd'.repeat(64), plan_id: plan, completed_steps: i + 1, receipt: ids[i] } }));
  const argumentsFor = i => ({ [params[i]]: i === 0 ? plan : ids[i - 1] });
  const row = i => ({ name: names[i], callId: 'model-' + i, ok: true,
    arguments: argumentsFor(i), output: outputs[i], sourceVersion: 'd'.repeat(64), inputVersion: task.input_version });
  return { manifest, task, offered, names, outputs, row, argumentsFor, seal };
}
async function propose(f, history = [f.row(0)]) {
  return proposeReadyBatch({ manifest: f.manifest, task: f.task, history,
    availableTools: new Map(f.offered.map(t => [t.name, t])), minSimilarity: 0.8, minMargin: 0.1,
    similarity: async () => { throw new Error('approved chain must not invoke embeddings'); } });
}
async function calls(stream) {
  const assembler = new BlockAssembler();
  for await (const chunk of stream) assembler.push(chunk);
  return assembler.blocks().filter(b => b.type === 'tool-call').map(b =>
    ({ callId: b.id, name: b.name, arguments: JSON.parse(b.arguments) }));
}

test('native interceptor verifies two skips, then hands interpretation to model', async () => {
  const f = fixture(), audit = [];
  validateOnlineManifest(f.manifest); parseStructuredTask(f.task, f.manifest);
  const plugin = createOnlineInterceptor({ manifest: f.manifest, task: f.task, mode: 'execute',
    audit: r => audit.push(r), similarity: async () => { throw new Error('no embeddings'); } });
  plugin.observe(f.task.session_id, { name: f.names[0], callId: 'anchor', arguments: f.argumentsFor(0) },
    { structuredContent: f.outputs[0] });
  let modelCalls = 0;
  for (let i = 1; i < 3; i++) {
    const call = (await calls(await plugin.intercept(f.task.session_id, { tools: f.offered },
      () => { modelCalls++; return null; })))[0];
    assert.equal(call.name, f.names[i]); assert.deepEqual(call.arguments, f.argumentsFor(i));
    assert.equal(audit.filter(r => r.kind === 'model_request_skipped_verified').length, i - 1);
    plugin.observe(f.task.session_id, call, { structuredContent: f.outputs[i] });
  }
  await plugin.intercept(f.task.session_id, { tools: f.offered }, () => { modelCalls++; });
  assert.equal(modelCalls, 1);
  assert.equal(audit.filter(r => r.kind === 'model_request_skipped_verified').length, 2);
  assert.ok(audit.filter(r => r.kind === 'motif_bypass_attempt')
    .every(r => r.selection_bases[0] === 'closed_approved_plan_continuation'));
});

for (const bad of ['missing', 'permission', 'task', 'version', 'plan', 'status', 'receipt', 'step', 'policy', 'schema', 'extra']) {
  test(`unsafe ${bad} grant cannot be rescued by similarity`, async () => {
    const f = fixture();
    const g = f.outputs[0].continuation_grant;
    if (bad === 'missing') delete f.outputs[0].continuation_grant;
    if (bad === 'permission') delete f.task.continuation_policy_digests;
    if (bad === 'task') g.task_input_version = 'e'.repeat(64);
    if (bad === 'version') g.execution_version = 'e'.repeat(64);
    if (bad === 'plan') g.plan_id = 'source-' + '9'.repeat(32);
    if (bad === 'status') f.outputs[0].status = 'needs_review';
    if (bad === 'receipt') g.receipt = 'source-' + '9'.repeat(32);
    if (bad === 'step') g.completed_steps = 2;
    if (bad === 'policy') g.policy_sha256 = 'e'.repeat(64);
    if (bad === 'schema') f.offered[2].parameters.properties.verification_id.type = 'number';
    if (bad === 'extra') g.allow_all = true;
    assert.deepEqual(await propose(f), []);
  });
}

test('revocation or needs_review after bypass stops continuation and is not counted verified', async () => {
  for (const kind of ['grant', 'low_text', 'wrong_plan', 'tool_error']) {
    const f = fixture(), audit = [];
    const plugin = createOnlineInterceptor({ manifest: f.manifest, task: f.task, mode: 'execute',
      audit: r => audit.push(r), similarity: async () => { throw new Error('no embeddings'); } });
    plugin.observe(f.task.session_id, { name: f.names[0], callId: 'anchor', arguments: f.argumentsFor(0) },
      { structuredContent: f.outputs[0] });
    const call = (await calls(await plugin.intercept(f.task.session_id, { tools: f.offered }, () => null)))[0];
    if (kind === 'grant') delete f.outputs[1].continuation_grant;
    if (kind === 'low_text') f.outputs[1].status = 'needs_review';
    if (kind === 'wrong_plan') f.outputs[1].continuation_grant.plan_id = 'source-' + '9'.repeat(32);
    plugin.observe(f.task.session_id, call, { structuredContent: f.outputs[1], isError: kind === 'tool_error' });
    let fallback = 0;
    await plugin.intercept(f.task.session_id, { tools: f.offered }, () => fallback++);
    assert.equal(fallback, 1);
    assert.equal(audit.filter(r => r.kind === 'model_request_skipped_verified').length, 0);
    assert.ok(audit.some(r => r.kind === 'bypass_result_unverified'));
  }
});

test('shadow never executes and a prefix with a different plan defers', async () => {
  const f = fixture();
  // A different plan in the second observation cannot extend the first grant.
  f.outputs[1].continuation_grant.plan_id = 'source-' + '9'.repeat(32);
  assert.deepEqual(await propose(f, [f.row(0), f.row(1)]), []);
  const plugin = createOnlineInterceptor({ manifest: f.manifest, task: f.task, mode: 'shadow',
    similarity: async () => { throw new Error('no embeddings'); } });
  plugin.observe(f.task.session_id, { name: f.names[0], callId: 'anchor', arguments: f.argumentsFor(0) },
    { structuredContent: f.outputs[0] });
  let normal = 0;
  await plugin.intercept(f.task.session_id, { tools: f.offered }, () => normal++);
  assert.equal(normal, 1);
});

test('manifest cannot silently widen the grant policy or unbind an edge', () => {
  for (const bad of ['digest', 'edge', 'contract', 'version']) {
    const f = fixture();
    if (bad === 'digest') delete f.manifest.artifacts[0].continuation_policy_digest;
    if (bad === 'edge') f.manifest.artifacts[0].transfer_evidence[0].from_field = 'execution_version_sha256';
    if (bad === 'contract') f.manifest.contracts[f.names[1]].continuation_policy = { ...f.manifest.contracts[f.names[1]].continuation_policy, kind: 'any_tool' };
    if (bad === 'version') f.manifest.schema_version = 1;
    f.seal(); assert.throws(() => validateOnlineManifest(f.manifest));
  }
  const f = fixture(); f.task.continuation_policy_digests = ['e'.repeat(64)];
  assert.throws(() => parseStructuredTask(f.task, f.manifest), /outside certified scope/);
});
