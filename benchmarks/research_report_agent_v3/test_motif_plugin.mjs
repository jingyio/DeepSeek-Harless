import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterceptor, digest, validateLibrary } from './motif_plugin.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const source = 'mcp__research_report__approve_analysis';
const target = 'mcp__research_report__run_analysis';
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'rra-plugin-'));
  const workspace = join(root, 'workspace'); mkdirSync(workspace);
  const input = join(root, 'data.csv'); writeFileSync(input, 'x,y\n1,2\n');
  const csvHash = sha(readFileSync(input));
  const request = join(root, 'task.txt'); writeFileSync(request, 'Please analyze this CSV.');
  const requestHash = sha(readFileSync(request));
  const planId = 'rra-plan-' + 'a'.repeat(32);
  const receiptPath = join(workspace, planId + '.json');
  function output(id = planId, authorized = ['run_analysis']) {
    const path = id === planId ? receiptPath : join(workspace, id + '.json');
    const value = { id, workspace_id: 'w', source_version: 'v', authorized_tools: authorized };
    writeFileSync(path, JSON.stringify(value));
    return { ok: true, plan_id: id, source_version: 'v', _provenance: {
      workspace_id: 'w', data_sha256: csvHash, study_sha256: 'v', record_path: path,
      record_sha256: sha(readFileSync(path)), authorized_tools: authorized } };
  }
  const contracts = {
    [source]: { required_params: ['plan'], output_fields: ['plan_id'], execution: 'semantic' },
    [target]: { required_params: ['plan_id'], output_fields: ['analysis_id'], execution: 'workspace_idempotent' },
  };
  const artifact = { from_tool: source, from_field: 'plan_id', to_tool: target, to_param: 'plan_id',
    training_evidence: [{ case_id: 'one' }, { case_id: 'two' }], certification_evidence: { case_id: 'three' } };
  artifact.certified_digest = digest(artifact); artifact.motif_id = 'receipt-' + artifact.certified_digest.slice(0, 16);
  const library = { schema_version: 1, benchmark_version: 3, kind: 'benchmark_workspace_receipt_motifs', contracts,
    contracts_digest: digest(contracts), artifacts: [artifact],
    tool_schemas: { [target]: { type: 'object', required: ['plan_id'], properties: { plan_id: { type: 'string' } } } } };
  library.tool_schemas_digest = digest(library.tool_schemas);
  library.library_digest = digest(library);
  const task = { workspace, workspace_id: 'w', study_version: 'v', csv_sha256: csvHash, source_files: [{ path: input, sha256: csvHash }, { path: request, sha256: requestHash }] };
  const options = { tools: [{ name: target, parameters: { type: 'object', required: ['plan_id'], properties: { plan_id: { type: 'string' } } } }] };
  const audit = [];
  const api = createInterceptor({ library, task, mode: 'execute', audit: row => audit.push(row) });
  const observe = value => api.observe({ name: source, callId: 'original', arguments: { plan: {} } }, { value: { structuredContent: value } });
  return { root, input, request, receiptPath, planId, output, library, task, options, audit, api, observe,
    close: () => rmSync(root, { recursive: true, force: true }) };
}

test('learned authorized continuation bypasses provider and verifies real receipt; logical failure halts', async () => {
  const f = fixture();
  try {
    let providerCalls = 0;
    f.observe(f.output());
    const blocks = [];
    for await (const block of await f.api.intercept(f.options, () => { providerCalls++; return (async function*(){})(); })) blocks.push(block);
    const call = blocks.find(row => row.type === 'block-end' && row.block.type === 'tool-call').block;
    assert.equal(providerCalls, 0);
    assert.equal(call.name, target);
    assert.deepEqual(JSON.parse(call.arguments), { plan_id: f.planId });
    const result = f.output('rra-analysis-' + 'b'.repeat(32), []);
    result.ok = false;
    f.api.observe({ name: target, callId: call.id, arguments: JSON.parse(call.arguments) }, { value: { structuredContent: result } });
    assert.equal(f.audit.at(-1).kind, 'motif_result_unverified');
    await f.api.intercept(f.options, () => { providerCalls++; return []; });
    assert.equal(providerCalls, 1);
  } finally { f.close(); }
});

for (const reason of ['source_changed', 'receipt_content_changed', 'not_authorized', 'schema_changed', 'optional_schema_changed', 'workspace_changed', 'study_version_changed', 'quality_failed', 'request_changed', 'delivery_failed']) {
  test('falls back for ' + reason, async () => {
    const f = fixture();
    try {
      const value = f.output(f.planId, reason === 'not_authorized' ? [] : ['run_analysis']);
      f.observe(value);
      if (reason === 'quality_failed') { value.quality_passed = false; f.observe(value); }
      if (reason === 'request_changed') writeFileSync(f.request, 'A different user task');
      if (reason === 'delivery_failed') { value.delivered = false; f.observe(value); }
      if (reason === 'source_changed') writeFileSync(f.input, 'x,y\n1,9\n');
      if (reason === 'receipt_content_changed') writeFileSync(f.receiptPath, '{}');
      if (reason === 'schema_changed') f.options.tools[0].parameters.required.push('semantic_choice');
      if (reason === 'optional_schema_changed') f.options.tools[0].parameters.properties.new_default = { type: 'string', default: 'changed' };
      if (reason === 'workspace_changed') f.task.workspace_id = 'another-workspace';
      if (reason === 'study_version_changed') f.task.study_version = 'another-version';
      let providerCalls = 0;
      await f.api.intercept(f.options, () => { providerCalls++; return []; });
      assert.equal(providerCalls, 1);
      assert.equal(f.audit.some(row => row.kind === 'motif_bypass_attempt'), false);
    } finally { f.close(); }
  });
}

test('independent certification and library digest are enforced', () => {
  const f = fixture();
  try {
    f.library.artifacts[0].certification_evidence.case_id = 'one';
    assert.throws(() => validateLibrary(f.library), /digest/);
  } finally { f.close(); }
});

test('two witnessed edges execute separately then yield at semantic frontier', async () => {
  const f = fixture();
  try {
    const verify = 'mcp__research_report__verify_analysis';
    const edge = { from_tool: target, from_field: 'analysis_id', to_tool: verify, to_param: 'analysis_id',
      training_evidence: [{ case_id: 'one' }, { case_id: 'two' }], certification_evidence: { case_id: 'three' } };
    edge.certified_digest = digest(edge); edge.motif_id = 'receipt-' + edge.certified_digest.slice(0, 16);
    f.library.artifacts.push(edge);
    f.library.contracts[verify] = { required_params: ['analysis_id'], output_fields: [], execution: 'workspace_idempotent' };
    f.library.tool_schemas[verify] = { type: 'object', required: ['analysis_id'], properties: { analysis_id: { type: 'string' } } };
    f.library.contracts_digest = digest(f.library.contracts);
    f.library.tool_schemas_digest = digest(f.library.tool_schemas);
    delete f.library.library_digest;
    f.library.library_digest = digest(f.library);
    const options = { tools: [...f.options.tools, { name: verify, parameters: f.library.tool_schemas[verify] }] };
    const audits = [];
    const api = createInterceptor({ library: f.library, task: f.task, mode: 'execute', audit: row => audits.push(row) });
    let providerCalls = 0;
    const next = () => { providerCalls++; return (async function*(){})(); };
    api.observe({ name: source, callId: 'plan', arguments: { plan: {} } }, { value: { structuredContent: f.output() } });
    async function instruction() {
      const blocks = [];
      for await (const row of await api.intercept(options, next)) blocks.push(row);
      return blocks.find(row => row.type === 'block-end' && row.block.type === 'tool-call')?.block;
    }
    const first = await instruction();
    assert.equal(first.name, target);
    const analysisId = 'rra-analysis-' + 'b'.repeat(32);
    const computed = f.output(analysisId, ['verify_analysis']);
    computed.analysis_id = analysisId; delete computed.plan_id;
    api.observe({ name: target, callId: first.id, arguments: JSON.parse(first.arguments) }, { value: { structuredContent: computed } });
    const second = await instruction();
    assert.equal(second.name, verify);
    assert.deepEqual(JSON.parse(second.arguments), { analysis_id: analysisId });
    const verified = f.output('rra-verified-' + 'c'.repeat(32), []);
    api.observe({ name: verify, callId: second.id, arguments: JSON.parse(second.arguments) }, { value: { structuredContent: verified } });
    assert.equal(await instruction(), undefined);
    assert.equal(providerCalls, 1);
    assert.equal(audits.filter(row => row.kind === 'model_request_skipped_verified').length, 2);
  } finally { f.close(); }
});

const canonical = value => Array.isArray(value) ? value.map(canonical) :
  value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort()
    .map(key => [key, canonical(value[key])])) : value;

function approval(f, bareTool = 'approve_analysis', permitted = true) {
  const spec = {
    approve_analysis: { field: 'plan_id', argument: 'plan', kind: 'analysis_plan', successor: 'run_analysis', input: { study_id: 'sample' } },
    approve_presentation: { field: 'presentation_id', argument: 'presentation', kind: 'presentation', successor: 'render_figures', input: { evidence_id: 'rra-evidence-' + 'e'.repeat(32) } },
    submit_report_text: { field: 'text_id', argument: 'report_text', kind: 'text', successor: 'compose_report', input: { packet_id: 'rra-packet-' + 'f'.repeat(32) } },
  }[bareTool];
  const args = { ...spec.input, [spec.argument]: { allow_deterministic_continuation: permitted, choice: 'The actual model decision' } };
  const body = { kind: spec.kind, workspace_id: 'w', source_version: 'v',
    authorized_tools: permitted ? [spec.successor] : [], payload: { semantic_approval: { tool: bareTool, arguments: structuredClone(args) } } };
  const id = `rra-${body.kind}-${digest(body).slice(0, 32)}`;
  const path = join(f.task.workspace, id + '.json');
  writeFileSync(path, JSON.stringify(canonical({ id, ...body })));
  return { name: 'mcp__research_report__' + bareTool, args, path,
    output: { ok: true, [spec.field]: id, source_version: 'v', _provenance: {
      workspace_id: 'w', data_sha256: f.task.csv_sha256, study_sha256: 'v', record_path: path,
      record_sha256: sha(readFileSync(path)), authorized_tools: body.authorized_tools } } };
}

function observeApproval(f, item, callId = 'fresh-LLM-approval') {
  f.api.observe({ name: item.name, callId, arguments: item.args }, { value: { structuredContent: item.output } });
}

function malformed(f) {
  f.api.observe({ name: source, callId: 'bad-model-json', arguments: '{"plan":' }, { value: { structuredContent: f.output() } });
}

async function instruction(f) {
  let providerCalls = 0;
  const blocks = [];
  for await (const block of await f.api.intercept(f.options, () => {
    providerCalls++; return (async function*(){})();
  })) blocks.push(block);
  return { providerCalls, call: blocks.find(row => row.type === 'block-end' && row.block.type === 'tool-call')?.block };
}

for (const tool of ['approve_analysis', 'approve_presentation', 'submit_report_text']) {
  test('malformed model args need an actual fresh bound approval: ' + tool, async () => {
    const f = fixture();
    try {
      malformed(f);
      assert.equal((await instruction(f)).providerCalls, 1);
      const item = approval(f, tool);
      observeApproval(f, item);
      assert.equal(f.audit.at(-1).kind, 'motif_recovery_verified');
      const next = await instruction(f);
      // Only the analysis continuation is present in this witnessed test library.
      assert.equal(next.providerCalls, tool === 'approve_analysis' ? 0 : 1);
      if (next.call) assert.equal(next.call.name, target);
    } finally { f.close(); }
  });
}

for (const problem of ['changed_arguments', 'unapproved', 'replayed_receipt', 'synthetic_call', 'forged_id', 'tampered_content']) {
  test('semantic recovery rejects ' + problem, async () => {
    const f = fixture();
    try {
      const item = approval(f, 'approve_analysis', problem !== 'unapproved');
      if (problem === 'replayed_receipt') observeApproval(f, item, 'prior-approved');
      malformed(f);
      if (problem === 'changed_arguments') item.args.plan.choice = 'Not the approved text';
      if (problem === 'forged_id') {
        const receipt = JSON.parse(readFileSync(item.path)); receipt.id = 'rra-analysis_plan-' + '9'.repeat(32);
        writeFileSync(item.path, JSON.stringify(canonical(receipt)));
        item.output.plan_id = receipt.id;
        item.output._provenance.record_sha256 = sha(readFileSync(item.path));
      }
      if (problem === 'tampered_content') writeFileSync(item.path, '{}');
      observeApproval(f, item, problem === 'synthetic_call' ? 'rra-motif-fake' : 'fresh-LLM-approval');
      assert.equal((await instruction(f)).providerCalls, 1);
      assert.equal(f.audit.some(row => row.kind === 'motif_recovery_verified'), false);
    } finally { f.close(); }
  });
}

test('semantic barriers do not turn into execution edges just because the receipt is valid', async () => {
  const f = fixture();
  try {
    for (const barrier of ['build_evidence', 'verify_figures']) {
      const output = f.output('rra-barrier-' + barrier.padEnd(32, '0'), []);
      f.api.observe({ name: 'mcp__research_report__' + barrier, callId: barrier, arguments: {} }, { value: { structuredContent: output } });
      assert.equal((await instruction(f)).providerCalls, 1);
    }
    assert.equal(f.audit.some(row => row.kind === 'motif_bypass_attempt'), false);
  } finally { f.close(); }
});

test('deployed JavaScript is generated byte-for-byte from the TypeScript source', () => {
  assert.equal(readFileSync(new URL('./motif_plugin.ts', import.meta.url), 'utf8'),
               readFileSync(new URL('./motif_plugin.mjs', import.meta.url), 'utf8'));
});
