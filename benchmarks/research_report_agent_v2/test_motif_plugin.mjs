import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createInterceptor, digest, validateLibrary } from './motif_plugin.mjs';

const sha = value => createHash('sha256').update(value).digest('hex');
const source = 'mcp__research_report__approve_workflow';
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
  const library = { schema_version: 1, benchmark_version: 2, kind: 'benchmark_workspace_receipt_motifs', contracts,
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

function semanticApproval(f, { interpretation = false, title = 'Fresh plan', authorized, version = 'v', workspace = 'w',
  researchOptions, comparisonSummary } = {}) {
  const plan = { analysis: { design: 'regression', predictor_column: 'x', outcome_column: 'y' },
    figures: [{ kind: 'scatter_fit' }], report: { title, outline: [{ heading: 'Result', role: 'results' }] },
    interpretation_mode: interpretation ? 'custom' : 'standard', allow_deterministic_continuation: true };
  const workflow = { ...plan, figures: [{ kind: 'scatter_fit', title: '' }],
    report: { title, outline: [{ heading: 'Result', roles: ['results'] }], page_mode: 'auto', pages: null, style: 'technical' } };
  const args = interpretation ? { evidence_id: 'rra-evidence-' + 'f'.repeat(32),
    commentary: { paragraphs: ['Bound interpretation {{estimate}}'], allow_deterministic_continuation: true,
      ...(researchOptions ? { research_options: researchOptions } : {}),
      ...(comparisonSummary ? { comparison_summary: comparisonSummary } : {}) } } :
    { study_id: 'a_study', plan };
  const body = { kind: interpretation ? 'evidence' : 'analysis_plan', workspace_id: workspace, source_version: version,
    authorized_tools: authorized ?? [interpretation ? 'render_figures' : 'run_analysis'],
    payload: interpretation ? { workflow, parent_evidence_id: args.evidence_id,
      interpretation_approved: true, custom_commentary_template: args.commentary.paragraphs,
      research_options_template: args.commentary.research_options ?? [],
      comparison_summary_template: args.commentary.comparison_summary ?? null } :
      { study_id: args.study_id, plan: plan.analysis, workflow } };
  const id = `rra-${body.kind}-${digest(body).slice(0, 32)}`;
  const path = join(f.task.workspace, id + '.json');
  const canonical = value => Array.isArray(value) ? value.map(canonical) :
    value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort()
      .map(key => [key, canonical(value[key])])) : value;
  writeFileSync(path, JSON.stringify(canonical({ id, ...body })));
  const output = { ok: true, [interpretation ? 'evidence_id' : 'plan_id']: id,
    ...(!interpretation ? { approved_workflow: workflow } : {}), source_version: version,
    _provenance: { workspace_id: workspace, data_sha256: f.task.csv_sha256, study_sha256: version,
      record_path: path, record_sha256: sha(readFileSync(path)), authorized_tools: body.authorized_tools } };
  return { args, output, path, name: interpretation ? 'mcp__research_report__approve_interpretation' : source };
}

function observeApproval(f, approval, callId = 'fresh-llm-approval') {
  f.api.observe({ name: approval.name, arguments: approval.args, callId }, { value: { structuredContent: approval.output } });
}

function badModelArguments(f) {
  // A success-looking payload attached to malformed arguments must not survive.
  f.api.observe({ name: source, arguments: '{"plan":', callId: 'bad-model-json' },
    { value: { structuredContent: f.output() } });
}

async function nextInstruction(f) {
  let providerCalls = 0;
  const blocks = [];
  for await (const block of await f.api.intercept(f.options, () => {
    providerCalls++; return (async function*(){})();
  })) blocks.push(block);
  return { providerCalls, call: blocks.find(row => row.type === 'block-end' && row.block.type === 'tool-call')?.block };
}

test('bad model JSON is audited and cannot reuse the earlier result or an ordinary successful tool', async () => {
  const f = fixture();
  try {
    f.observe(f.output());
    badModelArguments(f);
    assert.equal(f.audit.at(-1).reason, 'model_arguments_invalid_json');
    assert.equal((await nextInstruction(f)).providerCalls, 1);
    const approval = semanticApproval(f);
    f.api.observe({ name: target, arguments: {}, callId: 'ordinary-success' },
      { value: { structuredContent: approval.output } });
    assert.equal((await nextInstruction(f)).providerCalls, 1);
    assert.equal(f.audit.at(-1).reason, 'new_semantic_approval_required');
    assert.equal(f.audit.some(row => row.kind === 'motif_recovery_verified'), false);
  } finally { f.close(); }
});

test('only a fresh verified semantic approval restores witnessed execution after model JSON failure', async () => {
  const f = fixture();
  try {
    badModelArguments(f);
    const approval = semanticApproval(f);
    observeApproval(f, approval);
    const recovered = f.audit.at(-1);
    assert.equal(recovered.kind, 'motif_recovery_verified');
    assert.equal(recovered.blocked_after_call_id, 'bad-model-json');
    assert.equal(recovered.receipt_id, approval.output.plan_id);
    const result = await nextInstruction(f);
    assert.equal(result.providerCalls, 0);
    assert.equal(result.call.name, target);
    assert.deepEqual(JSON.parse(result.call.arguments), { plan_id: approval.output.plan_id });
  } finally { f.close(); }
});

test('verified custom approval clears the model-error barrier without inventing an unlearned edge', async () => {
  const f = fixture();
  try {
    badModelArguments(f);
    observeApproval(f, semanticApproval(f, { interpretation: true,
      researchOptions: [{ name: 'A', rationale: 'Review the residuals', tradeoff: 'Requires more measurements' }],
      comparisonSummary: 'Compare precision and measurement effort' }));
    assert.equal(f.audit.at(-1).kind, 'motif_recovery_verified');
    assert.equal((await nextInstruction(f)).providerCalls, 1);
    assert.equal(f.audit.at(-1).reason, 'semantic_or_unlearned_frontier');
    // A later existing edge can run: recovery did not silently hard-disable Motif.
    observeApproval(f, semanticApproval(f));
    assert.equal((await nextInstruction(f)).call.name, target);
  } finally { f.close(); }
});

test('recovery hashes original server bytes without reformatting Python floating-point values', async () => {
  const f = fixture();
  try {
    badModelArguments(f);
    const approval = semanticApproval(f);
    const oldId = approval.output.plan_id;
    // Python emits 1e-06 while JSON.stringify emits 0.000001. The receipt ID
    // belongs to the original canonical byte string, not to JS's re-encoding.
    const raw = readFileSync(approval.path, 'utf8').replace('"payload":{', '"payload":{"auxiliary":1e-06,');
    const body = raw.replace(`"id":"${oldId}",`, '');
    const id = 'rra-analysis_plan-' + sha(body).slice(0, 32);
    const path = join(f.task.workspace, id + '.json');
    writeFileSync(path, raw.replace(oldId, id));
    approval.output.plan_id = id;
    approval.output._provenance.record_path = path;
    approval.output._provenance.record_sha256 = sha(readFileSync(path));
    observeApproval(f, approval);
    assert.equal(f.audit.at(-1).kind, 'motif_recovery_verified');
    assert.equal((await nextInstruction(f)).call.name, target);
  } finally { f.close(); }
});

for (const reason of ['forged_hash', 'forged_identity', 'no_authorization', 'wrong_workspace', 'old_source_version',
  'request_changed', 'stale_receipt', 'replayed_call', 'motif_call_id', 'plan_arguments_mismatch', 'interpretation_arguments_mismatch',
  'research_options_arguments_mismatch', 'comparison_summary_arguments_mismatch']) {
  test('model-error recovery rejects ' + reason, async () => {
    const f = fixture();
    try {
      let approval = semanticApproval(f, { interpretation: ['interpretation_arguments_mismatch',
        'research_options_arguments_mismatch', 'comparison_summary_arguments_mismatch'].includes(reason) });
      if (reason === 'stale_receipt') observeApproval(f, approval, 'old-approval');
      if (reason === 'replayed_call') observeApproval(f, semanticApproval(f, { title: 'Earlier' }), 'fresh-llm-approval');
      badModelArguments(f);
      if (reason === 'forged_hash') approval.output._provenance.record_sha256 = '0'.repeat(64);
      if (reason === 'forged_identity') {
        const receipt = JSON.parse(readFileSync(approval.path, 'utf8'));
        receipt.payload.workflow.report.title = 'Forged content with original ID';
        writeFileSync(approval.path, JSON.stringify(receipt));
        approval.output._provenance.record_sha256 = sha(readFileSync(approval.path));
      }
      if (reason === 'no_authorization') approval = semanticApproval(f, { authorized: [] });
      if (reason === 'wrong_workspace') approval = semanticApproval(f, { workspace: 'old-workspace' });
      if (reason === 'old_source_version') approval = semanticApproval(f, { version: 'old-request-version' });
      if (reason === 'request_changed') writeFileSync(f.request, 'A different request');
      if (reason === 'plan_arguments_mismatch') approval.args.plan.report.title = 'An unapproved title';
      if (reason === 'interpretation_arguments_mismatch') approval.args.evidence_id = 'another-evidence';
      if (reason === 'research_options_arguments_mismatch') approval.args.commentary.research_options = [{ name: 'Unapproved option' }];
      if (reason === 'comparison_summary_arguments_mismatch') approval.args.commentary.comparison_summary = 'Unapproved comparison';
      observeApproval(f, approval, reason === 'motif_call_id' ? 'rra-motif-fake-approval' : 'fresh-llm-approval');
      assert.equal((await nextInstruction(f)).providerCalls, 1);
      assert.equal(f.audit.at(-1).kind, 'motif_recovery_blocked');
      assert.equal(f.audit.some(row => row.kind === 'motif_recovery_verified'), false);
      assert.equal(f.audit.some(row => row.kind === 'motif_bypass_attempt'), false);
    } finally { f.close(); }
  });
}

test('a failed Motif result remains hard halted even after a fresh valid LLM approval', async () => {
  const f = fixture();
  try {
    f.observe(f.output());
    const { call } = await nextInstruction(f);
    f.api.observe({ name: call.name, arguments: call.arguments, callId: call.id },
      { value: { structuredContent: { ok: false } } });
    badModelArguments(f);
    observeApproval(f, semanticApproval(f));
    assert.equal((await nextInstruction(f)).providerCalls, 1);
    assert.equal(f.audit.some(row => row.kind === 'motif_recovery_verified'), false);
    assert.equal(f.audit.filter(row => row.kind === 'motif_bypass_attempt').length, 1);
  } finally { f.close(); }
});

test('malformed arguments on the pending Motif call are audited and remain hard halted', async () => {
  const f = fixture();
  try {
    f.observe(f.output());
    const { call } = await nextInstruction(f);
    f.api.observe({ name: call.name, arguments: '{', callId: call.id },
      { value: { structuredContent: f.output() } });
    assert.equal(f.audit.at(-1).kind, 'motif_result_unverified');
    assert.equal(f.audit.at(-1).reason, 'motif_arguments_invalid_json');
    observeApproval(f, semanticApproval(f));
    assert.equal((await nextInstruction(f)).providerCalls, 1);
    assert.equal(f.audit.some(row => row.kind === 'motif_recovery_verified'), false);
  } finally { f.close(); }
});
