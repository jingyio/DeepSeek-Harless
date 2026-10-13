import test from 'node:test';
import assert from 'node:assert/strict';
import { apply } from '../src/adapters/dsh_codex_login.ts';

function harness() {
  const routes = new Map();
  let stored = false, busy = false, interaction;
  const ctx = {
    effect: (register) => register(),
    credentials: {
      readRecord: async () => stored ? { kind: 'grant', payload: { secret: 'never-return' } } : undefined,
      deleteRecord: async () => { stored = false; },
    },
    authorization: {
      describe: () => ({ inFlight: busy }),
      begin: ({ interaction: selected }) => { busy = true; interaction = selected; return new Promise(() => {}); },
      cancel: () => { busy = false; },
    },
    connection: { fetch: { register: ({ path, fetch }) => { routes.set(path, fetch); return () => {}; } },
      requestRejection: () => 401 },
    webServer: { register: () => () => {}, tapIndex: () => () => {} },
  };
  apply(ctx);
  const fetch = routes.get('/api/harless/codex-login');
  const request = (action, contentType = 'application/json') => new Request('http://localhost/api/harless/codex-login', {
    method: 'POST', headers: { 'Content-Type': contentType }, body: JSON.stringify({ action }),
  });
  return { fetch, request, get interaction() { return interaction; }, setStored: (value) => { stored = value; },
    setBusy: (value) => { busy = value; } };
}

test('private Codex control exposes only status and a device-code notice', async () => {
  const h = harness();
  const initial = await (await h.fetch(new Request('http://localhost/api/harless/codex-login'))).json();
  assert.deepEqual([initial.signed_in, initial.available, initial.in_flight], [false, true, false]);
  const started = await h.fetch(h.request('login'));
  assert.equal(started.status, 202);
  const method = await h.interaction.prompt({ kind: 'select', options: [{ id: 'browser' }, { id: 'device_code' }] });
  assert.equal(method, 'device_code');
  h.interaction.notify({ message: 'Enter code', url: 'https://auth.openai.com/codex/device', code: 'ABCD' });
  const pending = await (await h.fetch(new Request('http://localhost/api/harless/codex-login'))).json();
  assert.equal(pending.notice.code, 'ABCD');
  assert.equal(pending.status, 'pending');
  assert.equal((await h.fetch(h.request('logout'))).status, 409);
  await h.fetch(h.request('cancel'));
  h.setStored(true);
  const signedIn = await (await h.fetch(new Request('http://localhost/api/harless/codex-login'))).json();
  assert.equal(signedIn.signed_in, true);
  assert.equal(JSON.stringify(signedIn).includes('never-return'), false);
  assert.equal((await h.fetch(h.request('logout'))).status, 200);
  assert.equal((await (await h.fetch(new Request('http://localhost/api/harless/codex-login'))).json()).signed_in, false);
});

test('Codex login rejects unexpected prompts and non-JSON writes', async () => {
  const h = harness();
  assert.equal((await h.fetch(h.request('login', 'text/plain'))).status, 415);
  await h.fetch(h.request('login'));
  await assert.rejects(() => h.interaction.prompt({ kind: 'secret' }), /unsupported prompt/);
});
