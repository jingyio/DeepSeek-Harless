import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { createOnlineInterceptor } from '../src/adapters/dsh_online_motif.mjs';
import { validateOnlineManifest, parseStructuredTask } from '../src/motif_core/online_skill_runtime.mjs';

const bundle = new URL('../examples/motif-library/research-portfolio-v1/', import.meta.url);
const json = (name) => JSON.parse(readFileSync(new URL(name, bundle), 'utf8'));
const manifest = json('online-manifest.json');
const events = readFileSync(new URL('evidence/l_state_update/events.jsonl', bundle), 'utf8')
  .trim().split('\n').map(JSON.parse);
const pin = 'mcp__research_portfolio_fixture__pin_resource';
const read = 'mcp__research_portfolio_fixture__read_pinned';
const index = events.findIndex((row) => row.type === 'tool/call' && row.data.name === pin);
const exec = { name: pin, callId: 'current-pin', arguments: JSON.parse(events[index].data.arguments) };
const output = JSON.parse(events[index + 1].data.message.content[0].content[0].text);
const options = { tools: Object.entries(manifest.contracts).map(([name, contract]) => ({
  name, parameters: { type: 'object', required: contract.required_params,
    properties: Object.fromEntries(contract.required_params.map((param) => [param, { type: 'string' }])) },
})) };

function runtime(overrides = {}) {
  const task = json('task.json');
  task.source_versions[pin] = output.version_sha256;
  task.source_versions[read] = output.version_sha256;
  const audit = [];
  const interceptor = createOnlineInterceptor({ manifest, task, mode: 'execute',
    similarity: async (_query, descriptions) => descriptions.map(() => 1),
    audit: (row) => audit.push(row), ...overrides });
  interceptor.observe(task.session_id, exec, { value: { structuredContent: output } });
  return { interceptor, task, audit };
}

async function collect(interceptor, session, offered = options) {
  let fallback = 0;
  const stream = await interceptor.intercept(session, offered, () => {
    fallback++;
    return (async function* () {})();
  });
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return { chunks, fallback };
}

test('distributed historical manifest and task load in the authoritative online subset', () => {
  validateOnlineManifest(manifest);
  parseStructuredTask(json('task.json'), manifest);
  assert.equal(manifest.artifacts.length, 4);
  const changed = structuredClone(manifest);
  changed.artifacts[0].transfer_evidence[0].from_field = 'forged';
  assert.throws(() => validateOnlineManifest(changed), /invalid or changed/);
});

test('historical operator binds a fresh handle and verifies actual tool completion', async () => {
  const { interceptor, task, audit } = runtime();
  const { chunks, fallback } = await collect(interceptor, task.session_id);
  assert.equal(fallback, 0);
  const call = chunks.find((chunk) => chunk.type === 'tool-call-delta');
  assert.equal(call.name, read);
  assert.deepEqual(JSON.parse(call.argumentsDelta), { source_id: output.source_id });
  // Until the real tool result arrives, the bypass is only an attempt.
  assert.equal(audit.some((row) => row.kind === 'model_request_skipped_verified'), false);
  interceptor.observe(task.session_id,
    { name: call.name, callId: call.id, arguments: JSON.parse(call.argumentsDelta) },
    { value: { structuredContent: { version_sha256: output.version_sha256, text: 'fresh' } } });
  assert.equal(audit.filter((row) => row.kind === 'model_request_skipped_verified').length, 1);
  assert.equal((await collect(interceptor, task.session_id)).fallback, 1);
});

test('wrong session and changed tool schema return to the semantic path', async () => {
  const { interceptor, task } = runtime();
  assert.equal((await collect(interceptor, 'other-session')).fallback, 1);
  const changed = structuredClone(options);
  changed.tools.find((row) => row.name === read).parameters.required.push('unapproved_parameter');
  assert.equal((await collect(interceptor, task.session_id, changed)).fallback, 1);
});

test('unexpected result version halts reuse instead of counting a successful bypass', async () => {
  const { interceptor, task, audit } = runtime();
  const { chunks } = await collect(interceptor, task.session_id);
  const call = chunks.find((chunk) => chunk.type === 'tool-call-delta');
  interceptor.observe(task.session_id,
    { name: call.name, callId: call.id, arguments: JSON.parse(call.argumentsDelta) },
    { value: { structuredContent: { version_sha256: '0'.repeat(64), text: 'changed' } } });
  assert.equal(audit.some((row) => row.kind === 'model_request_skipped_verified'), false);
  assert.equal(interceptor.state(task.session_id).halted, true);
  assert.equal((await collect(interceptor, task.session_id)).fallback, 1);
});

test('failed MCP result halts reuse and remains a failed attempt', async () => {
  const { interceptor, task, audit } = runtime();
  const { chunks } = await collect(interceptor, task.session_id);
  const call = chunks.find((chunk) => chunk.type === 'tool-call-delta');
  interceptor.observe(task.session_id,
    { name: call.name, callId: call.id, arguments: JSON.parse(call.argumentsDelta) },
    { value: { isError: true, content: [{ type: 'text', text: 'source changed; pin again' }] } });
  assert.equal(audit.some((row) => row.kind === 'model_request_skipped_verified'), false);
  assert.equal(interceptor.state(task.session_id).halted, true);
  assert.equal((await collect(interceptor, task.session_id)).fallback, 1);
});
