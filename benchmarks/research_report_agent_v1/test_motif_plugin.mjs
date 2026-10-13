import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterceptor, digest, validateLibrary } from './motif_plugin.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const source = 'mcp__research_report__plan_analysis';
const target = 'mcp__research_report__run_analysis';
function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'rra-plugin-'));
  const workspace = join(root, 'workspace'); mkdirSync(workspace);
  const input = join(root, 'data.csv'); writeFileSync(input, 'x,y\n1,2\n');
  const csvHash = sha(readFileSync(input));
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
  const library = { schema_version: 1, kind: 'benchmark_workspace_receipt_motifs', contracts,
    contracts_digest: digest(contracts), artifacts: [artifact],
    tool_schemas: { [target]: { type: 'object', required: ['plan_id'], properties: { plan_id: { type: 'string' } } } } };
  library.tool_schemas_digest = digest(library.tool_schemas);
  library.library_digest = digest(library);
  const task = { workspace, workspace_id: 'w', study_version: 'v', csv_sha256: csvHash, source_files: [{ path: input, sha256: csvHash }] };
  const options = { tools: [{ name: target, parameters: { type: 'object', required: ['plan_id'], properties: { plan_id: { type: 'string' } } } }] };
  const audit = [];
  const api = createInterceptor({ library, task, mode: 'execute', audit: row => audit.push(row) });
  const observe = value => api.observe({ name: source, callId: 'original', arguments: { plan: {} } }, { value: { structuredContent: value } });
  return { root, input, receiptPath, planId, output, library, task, options, audit, api, observe,
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

for (const reason of ['source_changed', 'receipt_content_changed', 'not_authorized', 'schema_changed', 'optional_schema_changed', 'workspace_changed', 'study_version_changed', 'quality_failed']) {
  test('falls back for ' + reason, async () => {
    const f = fixture();
    try {
      const value = f.output(f.planId, reason === 'not_authorized' ? [] : ['run_analysis']);
      f.observe(value);
      if (reason === 'quality_failed') { value.quality_passed = false; f.observe(value); }
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
