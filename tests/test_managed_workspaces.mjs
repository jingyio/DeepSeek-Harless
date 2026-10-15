import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, realpathSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { randomUUID } from 'node:crypto';
import vm from 'node:vm';
const options = { skip: !process.features?.typescript };
function registry() {
  const items = [];
  return { items, list: () => items, async create(path, title) {
    let item = items.find(row => row.path === path);
    if (!item) { item = { id: randomUUID(), path, title, sessionIds: [], createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }; items.push(item); }
    return item;
  } };
}
function temporary(t) {
  const path = realpathSync(mkdtempSync(join(tmpdir(), 'geneloop-workspaces-')));
  t.after(() => { assert.ok(resolve(path).startsWith(resolve(tmpdir()) + sep) || resolve(path).startsWith(realpathSync(tmpdir()) + sep)); rmSync(path, { recursive: true, force: true }); });
  return path;
}
test('two accounts can create the same display name concurrently without sharing paths or files', options, async t => {
  const { createManagedWorkspaceService } = await import('../src/adapters/harless_managed_workspaces.ts');
  const directory = temporary(t), a = registry(), b = registry();
  const owner = createManagedWorkspaceService(directory, 'owner', a), member = createManagedWorkspaceService(directory, 'member', b);
  const id = randomUUID(), request = { name: '科研汇报', request_id: id };
  const [one, two, repeated] = await Promise.all([owner.create(request), member.create(request), owner.create(request)]);
  assert.equal(one.workspace.workspaceId, repeated.workspace.workspaceId);
  assert.notEqual(one.workspace.path, two.workspace.path);
  assert.equal(a.items.length, 1); assert.equal(b.items.length, 1);
  assert.ok(one.workspace.path.startsWith(owner.root + sep));
  writeFileSync(join(one.workspace.path, 'source.txt'), 'owner-only');
  assert.throws(() => member.adopt(one.workspace.path), /独立目录/);
  assert.throws(() => readFileSync(join(two.workspace.path, 'source.txt')), /ENOENT/);
  const restored = createManagedWorkspaceService(directory, 'owner', a);
  assert.equal((await restored.create(request)).workspace.workspaceId, one.workspace.workspaceId);
});
test('workspace names and retry IDs reject path injection, conflicts and changed requests', options, async t => {
  const { createManagedWorkspaceService } = await import('../src/adapters/harless_managed_workspaces.ts');
  const service = createManagedWorkspaceService(temporary(t), 'owner', registry());
  for (const name of ['', ' ', '../other', 'a/b', 'a\\b', 'C:project', 'bad\nname', '..', 'x'.repeat(65)])
    await assert.rejects(service.create({ name, request_id: randomUUID() }));
  await assert.rejects(service.create({ name: '研究', request_id: randomUUID(), path: '/home/foreign' }));
  await assert.rejects(service.create({ name: '研究', request_id: '__proto__' }));
  const id = randomUUID(); await service.create({ name: '项目 A', request_id: id });
  await assert.rejects(service.create({ name: '项目 B', request_id: id }), /另一个名称/);
  await assert.rejects(service.create({ name: '项目 A', request_id: randomUUID() }), /同名/);
});
test('old registered workspace and its files survive while unregistered host directories cannot be adopted', options, async t => {
  const { createManagedWorkspaceService } = await import('../src/adapters/harless_managed_workspaces.ts');
  const root = temporary(t), legacy = join(root, 'legacy'), unrelated = join(root, 'other-project');
  mkdirSync(legacy); mkdirSync(unrelated); writeFileSync(join(legacy, 'paper.txt'), 'unchanged');
  const records = registry(); const original = await records.create(legacy, '已有课题');
  const service = createManagedWorkspaceService(join(root, 'private-output'), 'owner', records);
  assert.equal(service.adopt(legacy).workspace.workspaceId, original.id);
  assert.throws(() => service.adopt(unrelated), /独立目录/);
  assert.equal(readFileSync(join(legacy, 'paper.txt'), 'utf8'), 'unchanged');
  const first = await service.create({ name: '可移除分组', request_id: randomUUID() });
  records.items.splice(records.items.findIndex(row => row.id === first.workspace.workspaceId), 1);
  const fresh = await service.create({ name: '可移除分组', request_id: randomUUID() });
  assert.notEqual(fresh.workspace.path, first.workspace.path);
});
test('symlink replacement cannot redirect managed creation into another account', options, async t => {
  const { createManagedWorkspaceService } = await import('../src/adapters/harless_managed_workspaces.ts');
  const base = temporary(t), records = registry(), service = createManagedWorkspaceService(base, 'owner', records);
  const request = { name: '项目', request_id: randomUUID() }, created = await service.create(request);
  const other = join(base, 'foreign'); mkdirSync(other);
  rmSync(created.workspace.path, { recursive: true });
  try { symlinkSync(other, created.workspace.path, process.platform === 'win32' ? 'junction' : 'dir'); }
  catch (error) { if (['EPERM', 'EACCES'].includes(error.code)) { t.skip('symlink permission unavailable'); return; } throw error; }
  await assert.rejects(service.create(request), /独立目录/);
  assert.throws(() => service.adopt(created.workspace.path), /独立目录/);
});
test('workspace API enforces login, returns native adoption and blocks host browsing for every account', options, async t => {
  const { registerManagedWorkspaceRoutes } = await import('../src/adapters/harless_managed_workspaces.ts');
  const routes = new Map(), ctx = { workspaceRegistry: registry(), effect: fn => fn(), connection: {
    requestRejection: req => req.headers.get('authorization') === 'fixture' ? undefined : 401,
    fetch: { register: route => { assert.equal(routes.has(route.path), false); routes.set(route.path, route); return () => {}; } },
  } };
  registerManagedWorkspaceRoutes(ctx, { output: temporary(t), principal: 'owner' });
  const send = (path, data, authenticated = true) => routes.get(path).fetch(new Request('http://localhost' + path,
    { method: 'POST', headers: { 'content-type': 'application/json', ...(authenticated ? { authorization: 'fixture' } : {}) }, body: JSON.stringify(data) }));
  assert.equal((await send('/api/harless/workspaces', { name: '新课题', request_id: randomUUID() }, false)).status, 401);
  const created = await (await send('/api/harless/workspaces', { name: '新课题', request_id: randomUUID() })).json();
  const rpc = (method, args) => send('/api/' + method, { type: 'client-request', rpcId: 'workspace-check', method, payload: { args } });
  const adoption = await (await rpc('workspace/create', { request: { path: created.workspace.path } })).json();
  assert.equal(adoption.result.ok, true); assert.equal(adoption.result.value.workspace.workspaceId, created.workspace.workspaceId);
  for (const method of ['directoryPicker/list', 'directoryPicker/createDirectory', 'directoryPicker/pick', 'workspace/create']) {
    const blocked = await (await rpc(method, { request: { path: '/home/other-account' } })).json();
    assert.equal(blocked.result.ok, false); assert.equal(blocked.result.error.code, 'gateway/forbidden');
    assert.doesNotMatch(JSON.stringify(blocked), /\/home\/other-account/);
  }
  assert.equal((await send('/api/workspace/create', {}, false)).status, 401);
});
test('workspace UI replaces both native directory flows and never installs server browsing controls', () => {
  const slots = [], styles = [], effects = [], window = {};
  const document = { createElement: () => ({ remove() {} }), head: { append: node => styles.push(node) } };
  vm.runInNewContext(readFileSync(new URL('../src/adapters/geneloop_workspaces.js', import.meta.url), 'utf8'), { window, document });
  const ctx = { effect: fn => effects.push(fn()), slots: { inject(_name, fn) { const result = fn(); if (result?.next) [...result]; }, register(options, component) { slots.push({ options, component }); } } };
  const React = { createElement: (type, props, ...children) => ({ type, props, children }), useState: initial => [initial, () => {}],
    useRef: initial => ({ current: initial }), useEffect() {}, useId: () => 'workspace-name' };
  const primitives = { Modal: 'native-modal' };
  window.__installGeneLoopWorkspaces(ctx, React, primitives); window.__installGeneLoopWorkspaces(ctx, React, primitives);
  assert.deepEqual(slots.map(row => row.options.name), ['conversation.hero.workspace.directoryFlow', 'sidebar.workspaces.directoryFlow']);
  assert.ok(slots.every(row => row.options.priority < 0)); assert.equal(styles.length, 1);
  const props = { open: true, busy: false, onPicked: () => {}, onCancel: () => {} };
  // Native slot inject factories receive no owner props. They are merged in by
  // the renderer later; exercising this order catches a crashed replacement.
  for (const slot of slots) {
    const injected = slot.options.inject?.() ?? {};
    const tree = slot.component({ ...injected, ...props });
    assert.equal(tree.type, 'native-modal'); assert.equal(tree.props.open, true);
    assert.match(JSON.stringify(tree), /工作区名称/);
    assert.doesNotMatch(JSON.stringify(tree), /服务器目录|目录选择/);
    assert.equal(slot.component({ ...injected, ...props, open: false }).props.open, false);
  }
  const source = readFileSync(new URL('../src/adapters/geneloop_workspaces.js', import.meta.url), 'utf8');
  assert.doesNotMatch(source, /listDirectory|createDirectory|directoryPicker\/|\/api\/workspace\/create/);
  assert.match(source, /工作区名称/); assert.match(source, /nativeEvent\.isComposing/);
});
