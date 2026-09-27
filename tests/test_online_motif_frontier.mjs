import assert from 'node:assert/strict';
import test from 'node:test';
import { BlockAssembler } from '@deepseek-ai/dsh-llm';
import { createOnlineInterceptor } from '../src/adapters/dsh_online_motif.mjs';
import { digest, parseStructuredTask, proposeNext, validateOnlineManifest }
  from '../src/adapters/online_motif_frontier.mjs';

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
  manifest.manifest_digest = digest(manifest);
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
});

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
  manifest.manifest_digest = digest(manifest);
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
