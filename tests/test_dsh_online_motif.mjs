import assert from 'node:assert/strict';
import test from 'node:test';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { markAgentLoopRequest } from '@deepseek-ai/dsh-llm';
import { apply } from '../src/adapters/dsh_online_motif.mjs';
import { digest } from '../src/adapters/online_motif_frontier.mjs';

test('DSH plugin intercepts an agent loop stream before the provider', async () => {
  const root = mkdtempSync(join(tmpdir(), 'sss-online-motif-'));
  const saved = { ...process.env };
  const priorFetch = globalThis.fetch;
  const pin = 'mcp__test__pin';
  const read = 'mcp__test__read';
  try {
    const manifest = {
      schema_version: 1, source_library_digest: 'a'.repeat(64),
      artifacts: [{ motif_id: 'm1', certified_digest: 'b'.repeat(64),
        tools: [pin, read], supporting_task_count: 3,
        validation_task_fingerprint: 'heldout',
        transfer_evidence: [{ from_tool: pin, from_field: 'id',
          to_tool: read, to_param: 'id' }] }],
      contracts: {
        [pin]: { read_only: true, required_params: ['path'],
          default_params: {}, output_fields: ['id', 'version'],
          description: 'Pin paper' },
        [read]: { read_only: true, required_params: ['id'],
          default_params: {}, output_fields: ['text', 'version'],
          description: 'Read paper' },
      },
      slot_rules: { [pin]: { path: 'paper:[A-Za-z0-9]+' } },
      version_fields: { [pin]: 'version', [read]: 'version' },
    };
    manifest.manifest_digest = digest(manifest);
    const task = { schema_version: 1, task_id: 't1', session_id: 's1',
      intent: 'Read paper', input_version: 'snapshot',
      bindings: { [pin]: { path: 'paper:A1' } },
      source_versions: { [pin]: 'v1', [read]: 'v1' } };
    const manifestPath = join(root, 'manifest.json');
    const taskPath = join(root, 'task.json');
    writeFileSync(manifestPath, JSON.stringify(manifest));
    writeFileSync(taskPath, JSON.stringify(task));
    process.env.SSS_ONLINE_MOTIF_MANIFEST = manifestPath;
    process.env.SSS_ONLINE_MOTIF_TASK = taskPath;
    process.env.SSS_ONLINE_MOTIF_MODE = 'execute';
    process.env.SSS_MOTIF_EMBEDDING_ENDPOINT = 'http://127.0.0.1:9999/v1/embeddings';
    process.env.SSS_MOTIF_EMBEDDING_MODEL = 'local-test';
    process.env.SSS_ONLINE_MOTIF_PROMPT_SHA256 = createHash('sha256')
      .update('Read paper').digest('hex');
    globalThis.fetch = async () => ({ ok: true,
      json: async () => ({ data: [
        { index: 0, embedding: [1, 0] },
        { index: 1, embedding: [1, 0] },
      ] }) });
    const listeners = new Map();
    apply({ on(event, callback) { listeners.set(event, callback); } });
    let resultListener;
    listeners.get('agent/created')({ agent: { session: { id: 's1' },
      ctx: { on(event, callback) {
        assert.equal(event, 'tools/result');
        resultListener = callback;
      } } } });
    resultListener({ name: pin, callId: 'first', arguments: { path: 'paper:A1' } },
      { value: { structuredContent: { id: 'opaque-id', version: 'v1' } } });
    let providerCalls = 0;
    const wrongPrompt = markAgentLoopRequest(Object.freeze({
      sessionId: 's1', messages: [{ role: 'user', source: { kind: 'user' },
        content: [{ type: 'text', text: 'A changed research task' }] }],
      tools: [{ name: read, parameters: { type: 'object',
        required: ['id'], properties: { id: { type: 'string' } } } }] }));
    for await (const _ of listeners.get('llm/stream')(wrongPrompt, () => {
      providerCalls++;
      return (async function* () {})();
    })) { /* The changed prompt is sent to the provider. */ }
    assert.equal(providerCalls, 1);
    const request = markAgentLoopRequest(Object.freeze({
      sessionId: 's1', messages: [{ role: 'user', source: { kind: 'user' },
        content: [{ type: 'text', text: 'Read paper' }] }],
      tools: [{ name: read, parameters: { type: 'object',
        required: ['id'], properties: { id: { type: 'string' } } } }] }));
    const chunks = [];
    for await (const chunk of listeners.get('llm/stream')(request, () => {
      providerCalls++;
      return (async function* () {})();
    })) chunks.push(chunk);
    assert.equal(providerCalls, 1);
    assert.equal(chunks[1].name, read);
    assert.deepEqual(JSON.parse(chunks[1].argumentsDelta), { id: 'opaque-id' });
    assert.equal(chunks.at(-1).reason.kind, 'tool-calls');
  } finally {
    globalThis.fetch = priorFetch;
    process.env = saved;
    rmSync(root, { recursive: true, force: true });
  }
});
