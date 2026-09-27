import assert from 'node:assert/strict';
import test from 'node:test';
import { BlockAssembler } from '@deepseek-ai/dsh-llm';
import { createOnlineInterceptor } from '../src/adapters/dsh_online_motif.mjs';
import { compileLocalPrograms, digest, parseStructuredTask, proposeNext, proposeReadyBatch,
  validateOnlineManifest }
  from '../src/adapters/online_motif_frontier.mjs';

function sealManifest(manifest) {
  for (const artifact of manifest.artifacts) {
    artifact.local_programs = compileLocalPrograms(artifact);
  }
  manifest.manifest_digest = digest(Object.fromEntries(Object.entries(manifest)
    .filter(([key]) => key !== 'manifest_digest')));
  return manifest;
}

function fixture() {
  const pin = 'mcp__research__pin_source';
  const read = 'mcp__research__read_source';
  const manifest = {
    schema_version: 1,
    source_library_digest: 'a'.repeat(64),
    artifacts: [{
      motif_id: 'certified-pin-read', certified_digest: 'b'.repeat(64),
      tools: [pin, read], supporting_task_count: 3,
      validation_task_fingerprint: 'heldout-research-task',
      transfer_evidence: [{ from_tool: pin, from_field: 'source_id',
        to_tool: read, to_param: 'source_id' }],
    }],
    contracts: {
      [pin]: { read_only: true, required_params: ['path'],
        default_params: {}, output_fields: ['source_id', 'version'],
        description: 'Pin a research source' },
      [read]: { read_only: true, required_params: ['source_id'],
        default_params: {}, output_fields: ['text', 'version'],
        description: 'Read a pinned research source' },
    },
    slot_rules: { [pin]: { path: 'source:[A-Za-z0-9_-]+' } },
    version_fields: { [pin]: 'version', [read]: 'version' },
  };
  sealManifest(manifest);
  const task = { schema_version: 1, task_id: 'research-1', session_id: 's1',
    intent: 'Read the pinned paper source for my research decision',
    input_version: 'snapshot-1',
    bindings: { [pin]: { path: 'source:PAPER_1' } },
    source_versions: { [pin]: 'v1', [read]: 'v1' } };
  return { pin, read, manifest, task };
}

const offered = (name, required) => ({ name, parameters: { type: 'object',
  required, properties: Object.fromEntries(required.map((key) =>
    [key, { type: 'string' }])) } });

test('strict structured input accepts only approved identifier slots', () => {
  const { pin, manifest, task } = fixture();
  validateOnlineManifest(manifest);
  assert.equal(parseStructuredTask(JSON.stringify(task), manifest).bindings[pin].path,
    'source:PAPER_1');
  assert.throws(() => parseStructuredTask({ ...task,
    bindings: { [pin]: { path: 'source:../../secret' } } }, manifest), /approved slot/);
  assert.throws(() => validateOnlineManifest({ ...manifest,
    contracts: { ...manifest.contracts, [pin]: { ...manifest.contracts[pin], read_only: false } } }),
  /changed certified/);
  const changedProgram = structuredClone(manifest);
  changedProgram.artifacts[0].local_programs[changedProgram.artifacts[0].tools[1]]
    .steps[0].from_field = 'invented';
  sealManifestDigestOnly(changedProgram);
  assert.throws(() => validateOnlineManifest(changedProgram),
    /local code differs/);
});

function sealManifestDigestOnly(manifest) {
  manifest.manifest_digest = digest(Object.fromEntries(Object.entries(manifest)
    .filter(([key]) => key !== 'manifest_digest')));
}

test('one DSH model stream is replaced by a certified tool call with provenance', async () => {
  const { pin, read, manifest, task } = fixture();
  const events = [];
  const intercept = createOnlineInterceptor({ manifest, task, mode: 'execute',
    similarity: async () => [0.97], audit: (row) => events.push(row) });
  intercept.observe('s1', { name: pin, callId: 'model-call',
    arguments: { path: 'source:PAPER_1' } },
  { value: { structuredContent: { source_id: 'source-opaque', version: 'v1' } } });
  let providerCalled = 0;
  const stream = await intercept.intercept('s1', { tools: [offered(read, ['source_id'])] }, () => {
    providerCalled++;
    return (async function* () { yield { type: 'finish', reason: { kind: 'stop' } }; })();
  });
  const chunks = [];
  const assembler = new BlockAssembler();
  for await (const chunk of stream) { chunks.push(chunk); assembler.push(chunk); }
  assert.equal(providerCalled, 0);
  assert.equal(chunks.at(-1).reason.kind, 'tool-calls');
  assert.equal(assembler.blocks()[0].name, read);
  assert.deepEqual(JSON.parse(assembler.blocks()[0].arguments),
    { source_id: 'source-opaque' });
  const callId = assembler.blocks()[0].id;
  intercept.observe('s1', { name: read, callId, arguments: {
    source_id: 'source-opaque' } },
  { value: { structuredContent: { text: 'research evidence', version: 'v1' } } });
  assert.equal(events.at(-1).kind, 'model_request_skipped_verified');
});

test('a verified model-chosen locator can anchor a later certified read', async () => {
  const locate = 'mcp__research__locate_quote';
  const read = 'mcp__research__read_match';
  const manifest = {
    schema_version: 1, source_library_digest: 'a'.repeat(64),
    artifacts: [{ motif_id: 'certified-locate-read', certified_digest: 'b'.repeat(64),
      tools: [locate, read], supporting_task_count: 2,
      validation_task_fingerprint: 'independent-heldout',
      transfer_evidence: [{ from_tool: locate, from_field: 'match_id',
        to_tool: read, to_param: 'match_id' }] }],
    contracts: {
      [locate]: { read_only: true, required_params: ['source_id', 'quote'],
        default_params: {}, output_fields: ['match_id', 'sha256'],
        description: 'Locate a paper quotation' },
      [read]: { read_only: true, required_params: ['match_id'],
        default_params: {}, output_fields: ['sha256'],
        description: 'Read the matched paper page' },
    },
    slot_rules: {}, version_fields: { [locate]: 'sha256', [read]: 'sha256' },
  };
  sealManifest(manifest);
  const task = { schema_version: 1, task_id: 'quote-impact', session_id: 's1',
    intent: 'Check a paper quotation against the current research claim',
    input_version: 'snapshot-1', bindings: {},
    source_versions: { [locate]: 'pdf-hash-1', [read]: 'pdf-hash-1' } };
  const history = [{ name: locate, ok: true,
    arguments: { source_id: 'source-opaque', quote: 'highlighted text' },
    output: { match_id: 'match-opaque', sha256: 'pdf-hash-1' },
    sourceVersion: 'pdf-hash-1', inputVersion: 'snapshot-1' }];
  const base = { manifest, task, history,
    availableTools: new Map([[read, offered(read, ['match_id'])]]),
    similarity: async () => [0.97], minSimilarity: 0.8, minMargin: 0.1 };
  assert.deepEqual((await proposeNext(base)).arguments, { match_id: 'match-opaque' });
  assert.equal(await proposeNext({ ...base, history: [{ ...history[0],
    sourceVersion: 'changed-pdf-hash' }] }), null);
  assert.equal(await proposeNext({ ...base, task: { ...task,
    bindings: { [locate]: { quote: 'a different highlight' } } } }), null);
});

test('independent versioned source handles form one DSH tool batch', async () => {
  const { pin, read, manifest, task } = fixture();
  const list = 'mcp__research__list_approved_sources';
  manifest.contracts[list] = { read_only: true, required_params: [],
    default_params: {}, output_fields: [], description: 'List approved sources' };
  sealManifest(manifest);
  const scoped = { ...task, bindings: {},
    source_versions: { [pin]: ['v1', 'v2'], [read]: ['v1', 'v2'] } };
  assert.deepEqual(parseStructuredTask(scoped, manifest).source_versions[pin], ['v1', 'v2']);
  assert.throws(() => parseStructuredTask({ ...scoped,
    source_versions: { [pin]: ['v1', 'v1'], [read]: 'v1' } }, manifest),
  /invalid source version scope/);
  const events = [];
  const intercept = createOnlineInterceptor({ manifest, task: scoped,
    mode: 'execute', similarity: async (_query, descriptions) =>
      descriptions.map(() => 0.97), audit: (row) => events.push(row) });
  intercept.observe('s1', { name: pin, callId: 'model-pin-1',
    arguments: { path: 'source:PAPER_1' } },
  { value: { structuredContent: { source_id: 'source-one', version: 'v1' } } });
  intercept.observe('s1', { name: list, callId: 'approved-list',
    arguments: {} }, { value: { structuredContent: { ok: true } } });
  intercept.observe('s1', { name: pin, callId: 'model-pin-2',
    arguments: { path: 'source:PAPER_2' } },
  { value: { structuredContent: { source_id: 'source-two', version: 'v2' } } });
  let providerCalls = 0;
  const options = { tools: [offered(read, ['source_id'])] };
  const next = () => { providerCalls++; return (async function* () {})(); };
  const assembler = new BlockAssembler();
  for await (const chunk of await intercept.intercept('s1', options, next)) {
    assembler.push(chunk);
  }
  assert.equal(providerCalls, 0);
  const blocks = assembler.blocks();
  assert.equal(blocks.length, 2);
  assert.deepEqual(blocks.map((block) => JSON.parse(block.arguments).source_id),
    ['source-one', 'source-two']);
  for (const block of blocks.toReversed()) {
    const sourceId = JSON.parse(block.arguments).source_id;
    intercept.observe('s1', { name: read, callId: block.id,
      arguments: { source_id: sourceId } },
    { value: { structuredContent: { text: 'approved text',
      version: sourceId === 'source-one' ? 'v1' : 'v2' } } });
  }
  assert.equal(events.filter((row) => row.kind === 'model_request_skipped_verified').length, 1);
  assert.equal(events.filter((row) => row.kind === 'motif_tool_result_verified').length, 2);
  assert.equal(intercept.state('s1').attempted, 1);
  await intercept.intercept('s1', options, next);
  assert.equal(providerCalls, 1);
});

test('an unapproved or failed interleaved call is a Motif barrier', async () => {
  const { pin, read, manifest, task } = fixture();
  const intercept = createOnlineInterceptor({ manifest, task,
    mode: 'execute', similarity: async () => [0.99] });
  intercept.observe('s1', { name: pin, callId: 'pin-1',
    arguments: { path: 'source:PAPER_1' } },
  { value: { structuredContent: { source_id: 'source-one', version: 'v1' } } });
  intercept.observe('s1', { name: 'mcp__unknown__write', callId: 'unknown',
    arguments: {} }, { value: { structuredContent: { ok: true } } });
  let providerCalls = 0;
  const next = () => { providerCalls++; return (async function* () {})(); };
  await intercept.intercept('s1', { tools: [offered(read, ['source_id'])] }, next);
  assert.equal(providerCalls, 1);
  intercept.observe('s1', { name: pin, callId: 'pin-2',
    arguments: { path: 'source:PAPER_1' } },
  { value: { structuredContent: { source_id: 'source-two', version: 'v1' } } });
  intercept.observe('s1', { name: read, callId: 'bad-result',
    arguments: { source_id: 'source-two' } },
  { isError: true, value: { isError: true } });
  await intercept.intercept('s1', { tools: [offered(read, ['source_id'])] }, next);
  assert.equal(providerCalls, 2);
});

test('verified results can continue to a later dependency layer without a model', async () => {
  const { pin, read, manifest, task } = fixture();
  const inspect = 'mcp__research__inspect_page';
  const artifact = { ...manifest.artifacts[0],
    tools: [pin, read, inspect],
    transfer_evidence: [...manifest.artifacts[0].transfer_evidence,
      { from_tool: read, from_field: 'page_id',
        to_tool: inspect, to_param: 'page_id' }] };
  const extended = { ...manifest, artifacts: [artifact],
    contracts: { ...manifest.contracts,
      [read]: { ...manifest.contracts[read], output_fields: ['text', 'page_id', 'version'] },
      [inspect]: { read_only: true, required_params: ['page_id'],
        default_params: {}, output_fields: ['finding', 'version'],
        description: 'Inspect a pinned paper page' } },
    version_fields: { ...manifest.version_fields, [inspect]: 'version' } };
  sealManifest(extended);
  const scoped = { ...task, source_versions: { ...task.source_versions,
    [inspect]: 'v1' } };
  const intercept = createOnlineInterceptor({ manifest: extended, task: scoped,
    mode: 'execute', similarity: async (_query, descriptions) =>
      descriptions.map(() => 0.98) });
  intercept.observe('s1', { name: pin, callId: 'pin-1',
    arguments: { path: 'source:PAPER_1' } },
  { value: { structuredContent: { source_id: 'source-one', version: 'v1' } } });
  const noProvider = () => { throw new Error('provider should be bypassed'); };
  let first;
  for await (const chunk of await intercept.intercept('s1',
    { tools: [offered(read, ['source_id']), offered(inspect, ['page_id'])] }, noProvider)) {
    if (chunk.type === 'block-end') first = chunk.block;
  }
  assert.equal(first.name, read);
  intercept.observe('s1', { name: read, callId: first.id,
    arguments: { source_id: 'source-one' } },
  { value: { structuredContent: { page_id: 'page-two', version: 'v1' } } });
  let second;
  for await (const chunk of await intercept.intercept('s1',
    { tools: [offered(read, ['source_id']), offered(inspect, ['page_id'])] }, noProvider)) {
    if (chunk.type === 'block-end') second = chunk.block;
  }
  assert.equal(second.name, inspect);
  assert.deepEqual(JSON.parse(second.arguments), { page_id: 'page-two' });
});

test('a dependent chain cannot continue across two individually approved source versions', async () => {
  const { pin, read, manifest, task } = fixture();
  const inspect = 'mcp__research__inspect_page';
  const artifact = { ...manifest.artifacts[0], tools: [pin, read, inspect],
    transfer_evidence: [...manifest.artifacts[0].transfer_evidence,
      { from_tool: read, from_field: 'page_id',
        to_tool: inspect, to_param: 'page_id' }] };
  const extended = { ...manifest, artifacts: [artifact],
    contracts: { ...manifest.contracts,
      [read]: { ...manifest.contracts[read], output_fields: ['page_id', 'version'] },
      [inspect]: { read_only: true, required_params: ['page_id'],
        default_params: {}, output_fields: ['version'],
        description: 'Inspect one approved page' } },
    version_fields: { ...manifest.version_fields, [inspect]: 'version' } };
  sealManifest(extended);
  const scoped = { ...task, source_versions: { [pin]: ['v1', 'v2'],
    [read]: ['v1', 'v2'], [inspect]: ['v1', 'v2'] } };
  const history = [
    { name: pin, callId: 'pin-1', ok: true,
      arguments: { path: 'source:PAPER_1' },
      output: { source_id: 'same-handle', version: 'v1' },
      sourceVersion: 'v1', inputVersion: 'snapshot-1' },
    { name: read, callId: 'read-2', ok: true,
      arguments: { source_id: 'same-handle' },
      output: { page_id: 'page-two', version: 'v2' },
      sourceVersion: 'v2', inputVersion: 'snapshot-1' },
  ];
  const proposals = await proposeReadyBatch({ manifest: extended, task: scoped,
    history, availableTools: new Map([[inspect, offered(inspect, ['page_id'])]]),
    similarity: async (_query, descriptions) => descriptions.map(() => 0.99),
    minSimilarity: 0.8, minMargin: 0.1 });
  assert.deepEqual(proposals, []);
});

test('one observed root with competing certified successors defers to the model', async () => {
  const { pin, read, manifest, task } = fixture();
  const alternate = 'mcp__research__read_alternate';
  const second = { ...manifest.artifacts[0], motif_id: 'certified-alternative',
    certified_digest: 'c'.repeat(64), tools: [pin, alternate],
    transfer_evidence: [{ from_tool: pin, from_field: 'source_id',
      to_tool: alternate, to_param: 'source_id' }] };
  const extended = { ...manifest, artifacts: [...manifest.artifacts, second],
    contracts: { ...manifest.contracts,
      [alternate]: { ...manifest.contracts[read], description: 'Read alternate evidence' } },
    version_fields: { ...manifest.version_fields, [alternate]: 'version' } };
  sealManifest(extended);
  const history = [{ name: pin, callId: 'pin-1', ok: true,
    arguments: { path: 'source:PAPER_1' },
    output: { source_id: 'source-one', version: 'v1' },
    sourceVersion: 'v1', inputVersion: 'snapshot-1' }];
  const proposals = await proposeReadyBatch({ manifest: extended,
    task: { ...task, source_versions: { ...task.source_versions,
      [alternate]: 'v1' } }, history,
    availableTools: new Map([[read, offered(read, ['source_id'])],
      [alternate, offered(alternate, ['source_id'])]]),
    similarity: async (_query, descriptions) => descriptions.map(() => 0.99),
    minSimilarity: 0.8, minMargin: 0.1 });
  assert.deepEqual(proposals, []);
});

test('version drift, missing parameter, no offered tool and shadow mode defer', async () => {
  const { pin, read, manifest, task } = fixture();
  const history = [{ name: pin, ok: true,
    arguments: { path: 'source:PAPER_1' },
    output: { source_id: 'source-opaque', version: 'v2' },
    sourceVersion: 'v2', inputVersion: 'snapshot-1' }];
  const common = { manifest, task, history,
    availableTools: new Map([[read, offered(read, ['source_id'])]]),
    similarity: async () => [0.97], minSimilarity: 0.8, minMargin: 0.1 };
  assert.equal(await proposeNext(common), null);
  history[0].sourceVersion = 'v1';
  assert.equal(await proposeNext({ ...common, availableTools: new Map() }), null);
  assert.equal(await proposeNext({ ...common,
    availableTools: new Map([[read, offered(read, ['another_param'])]]) }), null);
  history[0].output = { version: 'v1' };
  assert.equal(await proposeNext(common), null);
  const intercept = createOnlineInterceptor({ manifest, task,
    similarity: async () => [0.97] });
  intercept.observe('s1', { name: pin, callId: 'c1' },
    { value: { structuredContent: { source_id: 'source-opaque', version: 'v1' } } });
  let called = 0;
  await intercept.intercept('s1', { tools: [offered(read, ['source_id'])] }, () => {
    called++;
    return (async function* () {})();
  });
  assert.equal(called, 1);
});

test('semantic uncertainty and conflicting task binding keep the model in control', async () => {
  const { pin, read, manifest, task } = fixture();
  const history = [{ name: pin, ok: true,
    arguments: { path: 'source:PAPER_1' },
    output: { source_id: 'source-opaque', version: 'v1' },
    sourceVersion: 'v1', inputVersion: 'snapshot-1' }];
  const common = { manifest, task, history,
    availableTools: new Map([[read, offered(read, ['source_id'])]]),
    minSimilarity: 0.8, minMargin: 0.1 };
  assert.equal(await proposeNext({ ...common, similarity: async () => [0.6] }), null);
  const conflicted = { ...task, bindings: { ...task.bindings,
    [read]: { source_id: 'a-different-source' } } };
  assert.equal(await proposeNext({ ...common, task: conflicted,
    similarity: async () => [0.97] }), null);
});

test('a stale result after a bypass is never counted as a verified skip', async () => {
  const { pin, read, manifest, task } = fixture();
  const events = [];
  const intercept = createOnlineInterceptor({ manifest, task, mode: 'execute',
    similarity: async () => [0.99], audit: (row) => events.push(row) });
  intercept.observe('s1', { name: pin, callId: 'c1',
    arguments: { path: 'source:PAPER_1' } },
  { value: { structuredContent: { source_id: 'opaque', version: 'v1' } } });
  const chunks = [];
  for await (const chunk of await intercept.intercept('s1',
    { tools: [offered(read, ['source_id'])] }, () => { throw new Error('provider must be skipped'); })) {
    chunks.push(chunk);
  }
  intercept.observe('s1', { name: read, callId: chunks[1].id,
    arguments: { source_id: 'opaque' } },
  { value: { structuredContent: { text: 'changed', version: 'v2' } } });
  assert.equal(events.at(-1).kind, 'bypass_result_unverified');
  let called = 0;
  await intercept.intercept('s1', { tools: [offered(read, ['source_id'])] }, () => {
    called++;
    return (async function* () {})();
  });
  assert.equal(called, 1);
});
