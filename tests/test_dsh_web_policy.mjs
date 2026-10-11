import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { markAgentLoopRequest } from '@deepseek-ai/dsh-llm';

test('Web admission rejects other sessions, changed questions, schema drift and auxiliary requests',
  { skip: !process.features?.typescript }, async () => {
    const { apply } = await import('../src/adapters/dsh_web_policy.ts');
    const directory = mkdtempSync(join(tmpdir(), 'sss-web-policy-'));
    const previous = process.env.SSS_WEB_POLICY;
    const schemas = [{ name: 'mcp__demo__pin_note', description: 'pin',
      parameters: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'] } }];
    const policy = { output: directory, endpoint: 'http://127.0.0.1:1234/v1',
      mode: 'baseline', allowed_tools: schemas.map(row => row.name), max_output_tokens: 1000,
      prompt_sha256: createHash('sha256').update('fixed task').digest('hex') };
    const path = join(directory, 'policy.json'); writeFileSync(path, JSON.stringify(policy));
    process.env.SSS_WEB_POLICY = path;
    const listeners = new Map(); let executionGuard;
    const ctx = { effect() {}, on(name, listener) { listeners.set(name, listener); },
      sessionController: {
        async create() {
          listeners.get('agent/created')({ agent: { session: { id: 'owned' }, ctx: {
            tools: { restrict() {}, guard(value) { executionGuard = value; }, schemas() { return schemas; } }, on() {},
          } } });
          return { sessionId: 'owned' };
        },
        async prompt(_request, signal) { assert.ok(signal instanceof AbortSignal); return { accepted: true }; },
        async inspect() { return { meta: { id: 'owned' }, events: [] }; },
        selectModel() {}, cancel() {},
      } };
    try {
      apply(ctx);
      await ctx.sessionController.create({});
      await assert.rejects(ctx.sessionController.create({}), /One task/);
      assert.throws(() => ctx.sessionController.fork({}), /Fork/);
      assert.throws(() => ctx.sessionController.selectModel({ sessionId: 'owned', provider: 'other' }), /fixed/);
      const request = { sessionId: 'owned', content: [{ type: 'text', text: 'changed task' }] };
      await assert.rejects(ctx.sessionController.prompt(request), /Prompt changed/);
      await assert.rejects(ctx.sessionController.prompt({ ...request, sessionId: 'wrong' }), /Other Web session/);
      await ctx.sessionController.prompt({ ...request, content: [{ type: 'text', text: 'fixed task\n' }] }, new AbortController().signal);
      assert.equal(executionGuard({ name: 'mcp__demo__pin_note' }), undefined);
      assert.match(executionGuard({ name: 'bash' }), /outside/);
      const stream = listeners.get('llm/stream');
      const body = { sessionId: 'owned', provider: 'deepseek-official', model: 'deepseek-flash',
        reasoningEffort: 'off', maxTokens: 1000, tools: schemas,
        messages: [{ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'fixed task' }] }] };
      const next = () => (async function* () { yield { type: 'fixture' }; })();
      assert.throws(() => stream(body, next), /Auxiliary/);
      assert.throws(() => stream(markAgentLoopRequest({ ...body, sessionId: 'wrong' }), next), /Other Web/);
      assert.throws(() => stream(markAgentLoopRequest({ ...body, reasoningEffort: 'high' }), next), /Unapproved/);
      assert.throws(() => stream(markAgentLoopRequest({ ...body, tools: [{ ...schemas[0], description: 'drift' }] }), next), /schema version/);
      assert.throws(() => stream(markAgentLoopRequest({ ...body,
        messages: [...body.messages, { role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: 'new question' }] }] }), next), /envelope/);
      const result = [];
      for await (const item of stream(markAgentLoopRequest(body), next)) result.push(item);
      assert.equal(result.length, 1);
      await assert.rejects(ctx.sessionController.prompt(request), /Prompt changed/);
      assert.ok(JSON.parse(readFileSync(join(directory, 'task-state.json'))).session_id === 'owned');
    } finally {
      if (previous === undefined) delete process.env.SSS_WEB_POLICY;
      else process.env.SSS_WEB_POLICY = previous;
      rmSync(directory, { recursive: true });
    }
});
