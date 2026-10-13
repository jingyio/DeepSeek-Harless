import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { startBroker } from '../scripts/web_budget_broker.mjs';

test('budget broker rejects unconfirmed and conflicting routes and streams a confirmed turn', async () => {
  const received = [];
  const target = createServer(async (req, res) => {
    let body = ''; for await (const chunk of req) body += chunk;
    received.push({ path: req.url, session: req.headers['x-deepseek-harness-session-id'], body });
    res.writeHead(200, { 'Content-Type': 'text/event-stream' });
    res.write('data: first\n\n'); res.end('data: [DONE]\n\n');
  });
  target.listen(0, '127.0.0.1'); await once(target, 'listening');
  const token = 'fixture-control-token-with-enough-length';
  const broker = startBroker({ port: 0, target: `http://127.0.0.1:${target.address().port}/v1`, controlToken: token });
  await once(broker, 'listening');
  const root = `http://127.0.0.1:${broker.address().port}`;
  const session = 'session-11111111-1111-4111-8111-111111111111';
  const route = 'turn-' + 'a'.repeat(32);
  const model = () => fetch(root + '/v1/chat/completions', { method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-DeepSeek-Harness-Session-Id': session },
    body: JSON.stringify({ model: 'deepseek-flash', stream: true }) });
  const control = (path, budgetSession, suppliedToken = token) => fetch(root + path, { method: 'POST',
    headers: { 'X-SSS-Control-Token': suppliedToken, 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: session, budget_session_id: budgetSession }) });
  try {
    assert.equal((await model()).status, 403); assert.equal(received.length, 0);
    assert.equal((await control('/bind', route, 'wrong')).status, 401);
    assert.equal((await control('/bind', route)).status, 200);
    assert.equal((await control('/bind', 'turn-' + 'b'.repeat(32))).status, 409);
    const response = await model();
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'data: first\n\ndata: [DONE]\n\n');
    assert.equal(received.length, 1);
    assert.deepEqual(received[0], { path: '/v1/chat/completions', session: route,
      body: JSON.stringify({ model: 'deepseek-flash', stream: true }) });
    assert.equal((await control('/unbind', 'turn-' + 'b'.repeat(32))).status, 409);
    assert.equal((await control('/unbind', route)).status, 200);
    assert.equal((await model()).status, 403); assert.equal(received.length, 1);
    assert.equal((await fetch(root + '/v1/models')).status, 404);
  } finally {
    broker.closeAllConnections(); target.closeAllConnections();
    await Promise.all([new Promise(resolve => broker.close(resolve)), new Promise(resolve => target.close(resolve))]);
  }
});
