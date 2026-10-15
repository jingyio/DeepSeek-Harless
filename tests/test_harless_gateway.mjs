import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import net from 'node:net';
import { once } from 'node:events';
import { createHash, createHmac } from 'node:crypto';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, realpathSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createGateway, createOwnerClaim, createInvites } from '../scripts/harless_gateway.mjs';
import { memberSceneDeployment } from '../scripts/harless_member_scenes.mjs';

test('Scene deployment mounts code read-only and keeps user data and credentials out', t => {
  const root=realpathSync(mkdtempSync(join(tmpdir(),'harless-scene-deploy-')));
  t.after(()=>rmSync(root,{recursive:true,force:true}));
  for(const name of ['src','scripts','scenarios','python/bin'])mkdirSync(join(root,name),{recursive:true});
  const python=join(root,'python/bin/python');writeFileSync(python,'test dependency file');
  writeFileSync(join(root,'python/pyvenv.cfg'),'diagnostic installation marker');
  const scene={id:'new-scene',preset:'sss-task',label:'New Scene',adapter:'workspace',
    allowed_tools:['mcp__workspace__list_files'],environment_references:{},
    mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{serverName:'workspace',transport:'stdio',command:python,
      cwd:root,args:[join(root,'scenarios/general/server.py'),'__HARLESS_SESSION_WORKSPACE__/inputs']}}]};
  const policy={scenes:[scene],resources:{owner_private:{text:'Never inherit this'}}};
  const deployment={projectRoot:root,pythonExecutable:python,pythonRoots:[join(root,'python')]};
  const result=memberSceneDeployment(policy,deployment);
  assert.equal(result.output,'/app/.local/web');
  assert.deepEqual(result.allowed_tools,scene.allowed_tools);
  assert.equal(result.scenes[0].mcp_rows[0].config.args[0],'/app/scenarios/general/server.py');
  assert.equal(result.scenes[0].mcp_rows[0].config.args[1],'__HARLESS_SESSION_WORKSPACE__/inputs');
  assert.ok(result.mounts.every(row=>row.source!==root && !row.source.includes('/.local/')));
  assert.equal(policy.scenes[0].mcp_rows[0].config.cwd,root);
  assert.equal(result.scenes[0].resources,undefined);
  assert.equal(memberSceneDeployment(policy,undefined),null);
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[{...scene,environment_references:{key:'owner-secret'}}]},deployment),/credentials/);
  const withSecret=structuredClone(scene);withSecret.mcp_rows[0].config.env={API_KEY:'never-deploy'};
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[withSecret]},deployment),/authority/);
  assert.throws(()=>memberSceneDeployment(policy,{...deployment,pythonRoots:[root]}),/installation/);
  const unsafe=structuredClone(scene);unsafe.mcp_rows[0].config.args[0]='/owner/private/tool.py';
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[unsafe]},deployment),/approved scene code/);
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[{...scene,manifest:join(root,'private-manifest.json')}]},deployment),/sanitized/);
  const library=join(root,'library');mkdirSync(library);writeFileSync(join(library,'agent-events.jsonl'),'private raw trace');
  assert.throws(()=>memberSceneDeployment(policy,{...deployment,libraryRoot:library}),/private evidence/);
  const files={id:'files',preset:'sss-scene-files',label:'Files',adapter:'files',
    allowed_tools:['mcp__file_management__read_task'],environment_references:{},
    mcp_rows:[{name:'@deepseek-ai/dsh-mcp-client',config:{serverName:'file_management',transport:'stdio',
      command:python,cwd:root,args:[join(root,'scenarios/file-management/plan_tools.py')],env:{
        FM_WEB_WORKSPACE:'__HARLESS_SESSION_WORKSPACE__',
        FM_TASK_FILE:'__HARLESS_SESSION_WORKSPACE__/file-task.json',
        FM_OUTPUT:'__HARLESS_SESSION_WORKSPACE__/file-results'}}}]};
  const withFiles=memberSceneDeployment({...policy,scenes:[scene,files]},deployment);
  assert.equal(withFiles.scenes[1].mcp_rows[0].config.args[0],'/app/scenarios/file-management/plan_tools.py');
  assert.equal(withFiles.scenes[1].mcp_rows[0].config.env.FM_TASK_FILE,
    '__HARLESS_SESSION_WORKSPACE__/file-task.json');
  assert.deepEqual(withFiles.allowed_tools,[...scene.allowed_tools,...files.allowed_tools]);
  const unsafeFiles=structuredClone(files);
  unsafeFiles.mcp_rows[0].config.env.FM_OUTPUT='/owner/private';
  assert.throws(()=>memberSceneDeployment({...policy,scenes:[unsafeFiles]},deployment),/server-bound task workspace/);
});

const listen = server => new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
const close = server => new Promise(resolve => server.close(resolve));
const origin = 'https://app.example.test';

test('gateway shutdown closes an idle browser connection and finishes promptly', async t => {
  const dir = mkdtempSync(join(tmpdir(), 'harless-gateway-close-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const gateway = createGateway({dataDir:dir,publicOrigin:origin});
  const port = await listen(gateway.server), socket = net.connect(port,'127.0.0.1');
  t.after(() => socket.destroy()); await once(socket,'connect');
  const stopped=once(gateway.server,'close'), disconnected=once(socket,'close');
  gateway.close();gateway.close();
  await Promise.race([Promise.all([stopped,disconnected]),new Promise((_,reject)=>{
    const timer=setTimeout(()=>reject(Error('gateway shutdown remained blocked by browser socket')),1000);timer.unref();
  })]);
});
async function fixture(t, handleUpstream) {
  const dir = mkdtempSync(join(tmpdir(), 'harless-gateway-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const seen = [];
  const upstream = http.createServer((req, res) => {
    seen.push({ path: req.url, cookie: req.headers.cookie, host: req.headers.host, origin: req.headers.origin });
    if (req.url.startsWith('/?token=')) {
      res.writeHead(303, { location: '/', 'set-cookie': 'dsh-auth-test=secret-internal; HttpOnly; Path=/' });
      res.end(); return;
    }
    if (handleUpstream?.(req, res)) return;
    res.writeHead(200, { 'content-type': 'application/json', 'set-cookie': 'dsh-auth-test=never-public' });
    res.end(JSON.stringify({ path: req.url }));
  });
  const ownerPort = await listen(upstream);
  t.after(() => close(upstream));
  const tokenFile = join(dir, 'owner-token');
  writeFileSync(tokenFile, 'https://app.example.test/?token=' + 'A'.repeat(43));
  const html = join(dir, 'account.html'); writeFileSync(html, '<!doctype html><title>account</title>');
  const config = { dataDir: join(dir, 'db'), membersDir: join(dir, 'members'),
    publicOrigin: origin, ownerPort, ownerTokenFile: tokenFile, accountHtml: html,
    apiKey: 'test', dummyPasswordHash: 'scrypt-v1$test$' + '0'.repeat(128) };
  let gateway = createGateway(config);
  let port = await listen(gateway.server);
  t.after(() => close(gateway.server));
  const base = () => `http://127.0.0.1:${port}`;
  const request = (path, { method = 'GET', body, cookie, requestOrigin = origin } = {}) => fetch(base() + path, {
    method, redirect: 'manual', headers: {
      ...(cookie ? { cookie } : {}), ...(body ? { 'content-type': 'application/json', origin: requestOrigin } : {}),
    }, body: body ? JSON.stringify(body) : undefined,
  });
  return { dir, seen, config, request, upstream, base, get gateway() { return gateway; },
    async restart() { await close(gateway.server); gateway = createGateway(config); port = await listen(gateway.server); } };
}

test('disconnecting an HTTP event stream releases its backend subscription without ending sibling streams', { timeout: 5000 }, async t => {
  const active = new Map(), stopped = [];
  let f;
  t.after(() => { for (const response of active.values()) response.destroy(); f?.gateway.close(); });
  f = await fixture(t, (req, res) => {
    if (!req.url.startsWith('/api/harless/events/')) return false;
    active.set(req.url, res);
    res.once('close', () => { active.delete(req.url); stopped.push(req.url); });
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store' });
    res.write('event: ready\ndata: {}\n\n');
    return true;
  });
  const code = createOwnerClaim(f.gateway);
  const claimed = await f.request('/api/account/claim', { method: 'POST', body: {
    claimCode: code, username: 'owner', displayName: 'Owner', password: 'long-enough-test-password',
  } });
  assert.equal(claimed.status, 200);
  const cookie = claimed.headers.get('set-cookie').split(';')[0];
  const openStream = path => new Promise((resolve, reject) => {
    const request = http.get(f.base() + path, { headers: { cookie }, agent: false }, response => {
      response.once('error', () => {}); // Expected on deliberate downstream cancellation.
      response.once('data', chunk => resolve({ request, response, first: chunk.toString() }));
    });
    request.once('error', reject);
  });
  const [left, right] = await Promise.all([openStream('/api/harless/events/left'), openStream('/api/harless/events/right')]);
  assert.match(left.first, /event: ready/); assert.match(right.first, /event: ready/);
  assert.equal(active.size, 2, 'GET body completion must not cancel a live event stream');
  const leftClosed = once(active.get('/api/harless/events/left'), 'close', { signal: AbortSignal.timeout(2000) });
  left.response.destroy(); left.request.destroy(); await leftClosed;
  assert.deepEqual(stopped, ['/api/harless/events/left']);
  assert.equal(active.size, 1);
  const nextChunk = once(right.response, 'data', { signal: AbortSignal.timeout(2000) });
  active.get('/api/harless/events/right').write('event: progress\ndata: {"step":2}\n\n');
  assert.match((await nextChunk)[0].toString(), /"step":2/);
  const json = await f.request('/api/harless/tasks', { cookie });
  assert.equal(json.status, 200); assert.deepEqual(await json.json(), { path: '/api/harless/tasks' });
  const rightClosed = once(active.get('/api/harless/events/right'), 'close', { signal: AbortSignal.timeout(2000) });
  right.response.destroy(); right.request.destroy(); await rightClosed;
  assert.equal(active.size, 0);
});

test('browser disconnect before response headers cancels the pending upstream HTTP request', { timeout: 5000 }, async t => {
  let received;
  const arrived = new Promise(resolve => { received = resolve; });
  let f, backend, downstream;
  t.after(() => { downstream?.destroy(); backend?.res.destroy(); f?.gateway.close(); });
  f = await fixture(t, (req, res) => {
    if (req.url !== '/api/harless/slow-stream') return false;
    received({ req, res }); return true;
  });
  const code = createOwnerClaim(f.gateway);
  const claimed = await f.request('/api/account/claim', { method: 'POST', body: {
    claimCode: code, username: 'owner', displayName: 'Owner', password: 'long-enough-test-password',
  } });
  const cookie = claimed.headers.get('set-cookie').split(';')[0];
  downstream = http.get(f.base() + '/api/harless/slow-stream', { headers: { cookie }, agent: false });
  downstream.on('error', () => {});
  backend = await arrived;
  const closed = once(backend.res, 'close', { signal: AbortSignal.timeout(2000) });
  downstream.destroy(); await closed;
  assert.equal(backend.res.destroyed, true);
});

test('gateway shutdown closes both sides of an upgraded browser connection',async t=>{
 const f=await fixture(t);let backendSocket;
 f.upstream.on('upgrade',(_req,socket)=>{backendSocket=socket;socket.resume();socket.once('end',()=>socket.end());socket.write('HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n');});
 const code=createOwnerClaim(f.gateway);
 const response=await f.request('/api/account/claim',{method:'POST',body:{claimCode:code,username:'owner',displayName:'Owner',password:'long-enough-test-password'}});
 assert.equal(response.status,200);const cookie=response.headers.get('set-cookie').split(';')[0];
 const socket=net.connect(new URL(f.base()).port,'127.0.0.1');
 try {
  await once(socket,'connect',{signal:AbortSignal.timeout(2000)});
  socket.write('GET /api/$stream HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nCookie: '+cookie+'\r\n\r\n');
  const [reply]=await once(socket,'data',{signal:AbortSignal.timeout(2000)});assert.match(reply.toString(),/101 Switching/);assert.ok(backendSocket);
  const stopped=once(f.gateway.server,'close'),downstream=once(socket,'close'),upstream=once(backendSocket,'close');
  f.gateway.close();
  await Promise.race([Promise.all([stopped,downstream,upstream]),new Promise((_,reject)=>{const timer=setTimeout(()=>reject(Error('upgraded connection prevented gateway shutdown')),1000);timer.unref();})]);
 } finally {socket.destroy();backendSocket?.destroy();f.gateway.close();}
});

test('owner claim, login, profile, password, logout and persistence', async t => {
  const f = await fixture(t);
  const claim = createOwnerClaim(f.gateway);
  const initial = await f.request('/');
  assert.equal(initial.status, 303); assert.equal(initial.headers.get('location'), '/login');
  const badOrigin = await f.request('/api/account/claim', { method: 'POST', requestOrigin: 'https://evil.test',
    body: { claimCode: claim, username: 'owner', displayName: 'Owner', password: 'StrongPass123!' } });
  assert.equal(badOrigin.status, 403);
  const claimed = await f.request('/api/account/claim', { method: 'POST',
    body: { claimCode: claim, username: 'owner', displayName: 'Owner', password: 'StrongPass123!' } });
  assert.equal(claimed.status, 200);
  const firstCookie = claimed.headers.get('set-cookie').split(';')[0];
  assert.equal((await claimed.json()).user.role, 'owner');
  const invalidInvite = await f.request('/api/account/invites', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'incorrect-pass', count: 1 } });
  assert.equal(invalidInvite.status, 403);
  const generated = await f.request('/api/account/invites', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'StrongPass123!', count: 1 } });
  assert.equal(generated.status, 200);
  const inviteCode = (await generated.json()).codes[0];
  assert.ok(inviteCode.length >= 20);
  assert.ok(!readFileSync(join(f.config.dataDir, 'accounts.json'), 'utf8').includes(inviteCode));
  assert.equal((await f.request('/api/account/me', { cookie: firstCookie }).then(r => r.json())).user.username, 'owner');
  assert.equal((await f.request('/?token=' + 'A'.repeat(43), { cookie: firstCookie })).status, 400);
  const root = await f.request('/api/harless/tasks', { cookie: firstCookie });
  assert.equal(root.status, 200); assert.equal(root.headers.get('set-cookie'), null);
  assert.equal(f.seen.at(-1).cookie, 'dsh-auth-test=secret-internal');
  assert.equal(f.seen.at(-1).host, `127.0.0.1:${f.config.ownerPort}`);
  writeFileSync(join(f.dir, 'owner-token'), 'https://app.example.test/?token=' + 'B'.repeat(43));
  assert.equal((await f.request('/api/harless/tasks', { cookie: firstCookie })).status, 200);
  assert.ok(f.seen.some(row => row.path === '/?token=' + 'B'.repeat(43)));
  const profile = await f.request('/api/account/profile', { method: 'POST', cookie: firstCookie,
    body: { username: 'owner2', displayName: '研究负责人' } });
  assert.equal(profile.status, 200); assert.equal((await profile.json()).user.displayName, '研究负责人');
  const wrong = await f.request('/api/account/password', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'wrong-password', newPassword: 'LongerPass123!' } });
  assert.equal(wrong.status, 403);
  const changed = await f.request('/api/account/password', { method: 'POST', cookie: firstCookie,
    body: { currentPassword: 'StrongPass123!', newPassword: 'LongerPass123!' } });
  assert.equal(changed.status, 200);
  assert.equal((await f.request('/api/account/me', { cookie: firstCookie }).then(r => r.json())).user, null);
  await f.restart();
  const login = await f.request('/api/account/login', { method: 'POST',
    body: { username: 'owner2', password: 'LongerPass123!' } });
  assert.equal(login.status, 200);
  const secondCookie = login.headers.get('set-cookie').split(';')[0];
  assert.equal((await f.request('/api/account/logout', { method: 'POST', cookie: secondCookie, body: {} })).status, 200);
  assert.equal((await f.request('/api/account/me', { cookie: secondCookie }).then(r => r.json())).user, null);
  assert.equal((await f.request('/api/account/claim', { method: 'POST',
    body: { claimCode: claim, username: 'again', displayName: 'Again', password: 'StrongPass123!' } })).status, 400);
});

test('invite registration is single-use and account metadata is independent', async t => {
  const f = await fixture(t);
  const [invite] = createInvites(f.gateway, 1);
  const registered = await f.request('/api/account/register', { method: 'POST',
    body: { inviteCode: invite, username: 'alice', displayName: 'Alice', password: 'AlicePass123!' } });
  assert.equal(registered.status, 200);
  const cookie = registered.headers.get('set-cookie').split(';')[0];
  const user = (await registered.json()).user;
  assert.equal(user.role, 'member'); assert.notEqual(user.id, 'owner');
  const memberInvite = await f.request('/api/account/invites', { method: 'POST', cookie,
    body: { currentPassword: 'AlicePass123!', count: 1 } });
  assert.equal(memberInvite.status, 403);
  const duplicate = await f.request('/api/account/register', { method: 'POST',
    body: { inviteCode: invite, username: 'bob', displayName: 'Bob', password: 'BobStrong123!' } });
  assert.equal(duplicate.status, 400);
  const me = await f.request('/api/account/me', { cookie });
  assert.equal((await me.json()).user.username, 'alice');
  const db = JSON.parse(readFileSync(join(f.config.dataDir, 'accounts.json'), 'utf8'));
  assert.ok(!JSON.stringify(db).includes('AlicePass123!'));
  assert.ok(!JSON.stringify(db).includes(invite));
  assert.ok(db.users[0].passwordHash.startsWith('scrypt-v1$'));
});

test('two invited users register and remain authenticated concurrently', async t => {
  const f = await fixture(t);
  const [aliceCode, bobCode] = createInvites(f.gateway, 2);
  const [alice, bob] = await Promise.all([
    f.request('/api/account/register', { method: 'POST', body: {
      inviteCode: aliceCode, username: 'alice', displayName: 'Alice', password: 'AlicePass123!' } }),
    f.request('/api/account/register', { method: 'POST', body: {
      inviteCode: bobCode, username: 'bob', displayName: 'Bob', password: 'BobStrong123!' } }),
  ]);
  assert.equal(alice.status, 200); assert.equal(bob.status, 200);
  const aliceCookie = alice.headers.get('set-cookie').split(';')[0];
  const bobCookie = bob.headers.get('set-cookie').split(';')[0];
  assert.notEqual(aliceCookie, bobCookie);
  const [aliceMe, bobMe] = await Promise.all([
    f.request('/api/account/me', { cookie: aliceCookie }).then(r => r.json()),
    f.request('/api/account/me', { cookie: bobCookie }).then(r => r.json()),
  ]);
  assert.equal(aliceMe.user.username, 'alice'); assert.equal(bobMe.user.username, 'bob');
  assert.notEqual(aliceMe.user.id, bobMe.user.id);
  await f.restart();
  assert.equal((await f.request('/api/account/me', { cookie: aliceCookie }).then(r => r.json())).user.username, 'alice');
  assert.equal((await f.request('/api/account/me', { cookie: bobCookie }).then(r => r.json())).user.username, 'bob');
});

test('stale member plugin paths fail during gateway startup', async t => {
  const f = await fixture(t);
  assert.throws(() => createGateway({ ...f.config, sourceDir: join(f.dir, 'new-checkout', 'src'),
    memberPatch: [{ insert: [{ name: 'file:///old-checkout/src/adapters/dsh_web_tasks.ts' }] }] }),
  /Plugin is outside source directory/);
});

test('scoped budget rejects cross-account control and model traffic', async t => {
  const dir = mkdtempSync(join(tmpdir(), 'harless-scoped-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const upstream = [];
  const mock = http.createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk);
    upstream.push({ path: req.url, authorization: req.headers.authorization,
      control: req.headers['x-sss-control-token'], body: Buffer.concat(chunks).toString() });
    res.writeHead(200, { 'content-type': 'application/json' }); res.end('{}');
  });
  const upstreamPort = await listen(mock); t.after(() => close(mock));
  const html = join(dir, 'account.html'); writeFileSync(html, '<title>test</title>');
  const config = { dataDir: join(dir, 'accounts'), membersDir: join(dir, 'members'),
    publicOrigin: origin, accountHtml: html, adminToken: 'test-admin-secret', apiKey: 'real-model-key',
    scopedBudgetPort: 1, upstreamControlPort: upstreamPort, upstreamBrokerPort: upstreamPort,
    memberPolicy: { control_token: 'real-control-secret', budget_usd: .5 } };
  const gateway = createGateway(config);
  const port = await listen(gateway.server), scopePort = await listen(gateway.scopedBudget);
  t.after(() => close(gateway.server)); t.after(() => close(gateway.scopedBudget));
  const [codeA, codeB] = createInvites(gateway, 2);
  async function register(code, username) {
    const response = await fetch(`http://127.0.0.1:${port}/api/account/register`, {
      method: 'POST', headers: { origin, 'content-type': 'application/json' },
      body: JSON.stringify({ inviteCode: code, username, displayName: username, password: 'LongTestPassword123!' }),
    });
    assert.equal(response.status, 200); return (await response.json()).user;
  }
  const alice = await register(codeA, 'alice'), bob = await register(codeB, 'bob');
  const prefix = user => createHash('sha256').update(user.id).digest('hex').slice(0, 8);
  const delegated = (user, kind) => createHmac('sha256', config.adminToken)
    .update(kind + ':' + user.id).digest('base64url');
  const task = prefix(alice) + 'a'.repeat(24), budget = 'turn-' + task;
  const session = 'session-12345678-1234-1234-1234-123456789abc';
  const scoped = (path, body, token, model = false) => fetch(`http://127.0.0.1:${scopePort}${path}`, {
    method: 'POST', headers: { 'content-type': 'application/json',
      ...(model ? { authorization: `Bearer ${token}`, 'x-deepseek-harness-session-id': session }
        : { 'x-sss-control-token': token }) }, body: JSON.stringify(body),
  });
  assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd: .5 },
    delegated(bob, 'control'))).status, 403);
  assert.equal((await scoped('/tasks/register', { task_id: task, session_id: budget, budget_usd: .5 },
    delegated(alice, 'control'))).status, 200);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(alice, 'model'), true)).status, 403);
  assert.equal((await scoped('/bind', { session_id: session, budget_session_id: budget },
    delegated(bob, 'control'))).status, 403);
  assert.equal((await scoped('/bind', { session_id: session, budget_session_id: budget },
    delegated(alice, 'control'))).status, 200);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(bob, 'model'), true)).status, 403);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(alice, 'model'), true)).status, 200);
  assert.equal(upstream.at(-1).authorization, 'Bearer real-model-key');
  assert.equal((await fetch(`http://127.0.0.1:${scopePort}/tasks/stats?session_id=${budget}`, {
    headers: { 'x-sss-control-token': delegated(bob, 'control') },
  })).status, 403);
  assert.equal((await scoped('/unbind', { session_id: session, budget_session_id: budget },
    delegated(alice, 'control'))).status, 200);
  assert.equal((await scoped('/v1/chat/completions', { model: 'test' }, delegated(alice, 'model'), true)).status, 403);
});
