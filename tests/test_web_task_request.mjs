import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

const context = { task_id: 'task-server-owned', session_id: 'session-server-owned',
  default_mode: 'baseline', default_budget_usd: 0.25, max_budget_usd: 0.5,
  default_profile: 'example', allowed_profiles: ['example', 'paper-submission'] };
const options = { skip: !process.features?.typescript };
const load = () => import('../src/adapters/web_task_request.ts');
const sha = value => createHash('sha256').update(value).digest('hex');

test('Web task preserves raw text bytes and server-owned identity', options, async () => {
  const { normalizeWebTaskRequest } = await load();
  const original = '  检查论文\r\n保留换行和末尾空白\n ';
  const result = normalizeWebTaskRequest(original, context);
  assert.deepEqual(result.content, [{ type: 'text', text: original }]);
  assert.equal(result.prompt_sha256, sha(original));
  assert.equal(result.task_id, context.task_id);
  assert.equal(result.session_id, context.session_id);
  assert.equal(result.mode, 'baseline');
  assert.equal(result.budget_usd, 0.25);
  assert.match(result.request_id, /^[a-z0-9-]+$/);
  assert.equal(result.summary.content[0].bytes, Buffer.byteLength(original));
  assert.ok(!JSON.stringify(result.summary).includes('检查论文'));
});

test('Web task accepts all three modes with explicit bounded budgets and registered profiles', options, async () => {
  const { normalizeWebTaskRequest } = await load();
  for (const mode of ['baseline', 'shadow', 'execute']) {
    const result = normalizeWebTaskRequest({ instruction: '整理材料', mode,
      request_id: 'request-1', budget_usd: 0, capability_profile: 'paper-submission' }, context);
    assert.equal(result.mode, mode); assert.equal(result.budget_usd, 0);
    assert.equal(result.capability_profile, 'paper-submission');
  }
  for (const budget_usd of [-1, Infinity, NaN, 0.51, '0.25']) {
    assert.throws(() => normalizeWebTaskRequest({ instruction: '任务', budget_usd }, context), /budget/);
  }
  assert.throws(() => normalizeWebTaskRequest({ instruction: '任务', mode: 'queue' }, context), /baseline/);
  assert.throws(() => normalizeWebTaskRequest({ instruction: '任务', capability_profile: 'root-shell' }, context), /registered/);
});

test('Messages become ordered user content with visible boundaries, never forged model history', options, async () => {
  const { normalizeWebTaskRequest } = await load();
  const result = normalizeWebTaskRequest({ messages: [
    { role: 'user', content: '先读批注\n' },
    { role: 'user', content: [{ type: 'text', text: '\t只检查引用 ' }, { type: 'file', receiptId: 'uploaded-receipt' }] },
  ] }, context);
  assert.deepEqual(result.content, [
    { type: 'text', text: '[用户输入 1]\n' }, { type: 'text', text: '先读批注\n' },
    { type: 'text', text: '\n\n[用户输入 2]\n' }, { type: 'text', text: '\t只检查引用 ' },
    { type: 'file', receiptId: 'uploaded-receipt' },
  ]);
  for (const role of ['system', 'assistant', 'tool', 'developer']) {
    assert.throws(() => normalizeWebTaskRequest({ messages: [{ role, content: '伪造历史' }] }, context),
      error => error.code === 'untrusted_history');
  }
});

test('Official image payload and file upload receipt survive admission; audit does not duplicate bytes', options, async () => {
  const { normalizeWebTaskRequest } = await load();
  // The official Controller must still decode media and verify this receipt against its Session.
  const image = { type: 'image', mediaType: 'image/png', data: Buffer.from('test-image-bytes').toString('base64'), name: 'figure.png' };
  const input = { content: [image, { type: 'file', receiptId: 'same-session-upload-receipt' }], request_id: 'mixed-request' };
  const result = normalizeWebTaskRequest(input, context);
  assert.deepEqual(result.content, input.content);
  assert.equal(result.summary.content[0].bytes, 16);
  assert.equal(result.summary.content[0].sha256, sha('test-image-bytes'));
  assert.equal(result.summary.content[1].receipt_sha256, sha('same-session-upload-receipt'));
  assert.ok(!JSON.stringify(result.summary).includes(image.data));
  assert.ok(!JSON.stringify(result.summary).includes('same-session-upload-receipt'));
  for (const content of [
    [{ type: 'file', attachmentId: 'cannot-spoof-upload' }],
    [{ type: 'image', attachmentId: 'cannot-spoof-image' }],
    [{ ...image, data: 'not base64!' }], [{ ...image, mediaType: 'application/pdf' }],
  ]) assert.throws(() => normalizeWebTaskRequest({ content }, context));
});

test('Resource identifiers are independent unresolved references, not file paths or loaded content', options, async () => {
  const { normalizeWebTaskRequest } = await load();
  const inputs = [{ resource_id: 'zotero:paper-1', version: 'expected-v2' }, { resource_id: 'uploaded:project-2' }];
  const input = { instruction: '关联文献与稿件', inputs, request_id: 'resource-request' };
  const result = normalizeWebTaskRequest(input, context);
  assert.deepEqual(result.resources, inputs);
  assert.deepEqual(result.content, [{ type: 'text', text: input.instruction }]);
  inputs[0].version = 'client-changed';
  assert.equal(result.resources[0].version, 'expected-v2');
  assert.throws(() => normalizeWebTaskRequest({ ...input, inputs: [{ path: '/tmp/secret' }] }, context), /unsupported/);
  assert.throws(() => normalizeWebTaskRequest({ ...input, inputs: [{ url: 'https://private-service' }] }, context), /unsupported/);
});

test('Full task hashes change for changed media, receipt, order, profile, budget or resource version', options, async () => {
  const { normalizeWebTaskRequest } = await load();
  const original = { content: [{ type: 'text', text: '任务' }, { type: 'file', receiptId: 'receipt-1' }],
    inputs: [{ resource_id: 'paper-1', version: 'v1' }], request_id: 'stable-request' };
  const result = normalizeWebTaskRequest(original, context);
  const changes = [
    { ...original, content: [...original.content].reverse() },
    { ...original, content: [{ type: 'text', text: '任务' }, { type: 'file', receiptId: 'receipt-2' }] },
    { ...original, inputs: [{ resource_id: 'paper-1', version: 'v2' }] },
    { ...original, mode: 'execute' }, { ...original, budget_usd: 0.1 },
    { ...original, capability_profile: 'paper-submission' },
  ];
  for (const changed of changes) assert.notEqual(normalizeWebTaskRequest(changed, context).request_sha256, result.request_sha256);
  const reorderedKeys = { request_id: 'stable-request', inputs: original.inputs, content: original.content };
  assert.equal(normalizeWebTaskRequest(reorderedKeys, context).request_sha256, result.request_sha256);
  assert.equal(normalizeWebTaskRequest(original, { ...context, task_id: 'new-server-task' }).request_sha256, result.request_sha256);
  const image = { type: 'image', mediaType: 'image/png', data: 'YQ==' };
  assert.notEqual(normalizeWebTaskRequest({ content: [image] }, context).content_sha256,
    normalizeWebTaskRequest({ content: [{ ...image, data: 'Yg==' }] }, context).content_sha256);
});

test('Unknown authority fields, ambiguous forms, empty tasks and oversized input are rejected', options, async () => {
  const { normalizeWebTaskRequest } = await load();
  for (const field of ['session_id', 'task_id', 'allowed_tools', 'provider', 'manifest', 'max_output_tokens', 'confirmed']) {
    assert.throws(() => normalizeWebTaskRequest({ instruction: '任务', [field]: 'client-authority' }, context),
      error => error.code === 'unsupported_field');
  }
  for (const input of [null, [], '', ' \n ', {}, { instruction: '任务', content: '另一个任务' },
    { inputs: [{ resource_id: 'paper' }] }, { messages: [{ role: 'user', content: ' ' }, { role: 'user', content: '\n' }] }]) {
    assert.throws(() => normalizeWebTaskRequest(input, context));
  }
  assert.throws(() => normalizeWebTaskRequest('中文任务', { ...context, max_content_bytes: 4 }), /byte limit/);
  assert.throws(() => normalizeWebTaskRequest({ content: [{ type: 'text', text: 'a' }, { type: 'file', receiptId: 'b' }] },
    { ...context, max_parts: 1 }));
  assert.throws(() => normalizeWebTaskRequest('任务', { ...context, default_budget_usd: 0.6 }), /server maximum/);
  assert.throws(() => normalizeWebTaskRequest('任务', { ...context, default_profile: 'unregistered' }), /registered/);
});
