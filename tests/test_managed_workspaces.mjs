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

test('workspace public baseline, updates and rename never expose host deployment paths', options, async()=>{
 const {protectWorkspaceProjection}=await import('../src/adapters/harless_managed_workspaces.ts');
 const workspace={workspaceId:'owned-workspace',path:'/home/private/deployment/project',title:'论文',sessionIds:['chat'],createdAt:'now'};
 const controller={async *follow(){yield {type:'baseline',value:{items:[workspace],archivedSessionIds:[]}};yield{type:'upsert',workspace};},
  async rename(){return{workspace};},async insertSessionBefore(){return{workspace};}};
 protectWorkspaceProjection(controller);
 const frames=[];for await(const frame of controller.follow(new AbortController().signal))frames.push(frame);
 assert.equal(frames[0].value.items[0].path,'/workspaces/owned-workspace');
 assert.doesNotMatch(JSON.stringify(frames),/home|private|deployment/);
 assert.equal((await controller.rename({})).workspace.path,'/workspaces/owned-workspace');
 assert.equal(workspace.path,'/home/private/deployment/project','authoritative registry is not mutated');
});

test('workspace browser preserves store receivers and top-level New chat targets the clicked workspace', async()=>{
 const slots=[], window={}, created=[];
 const document={createElement:()=>({remove(){}}),head:{append(){}}};
 vm.runInNewContext(readFileSync(new URL('../src/adapters/geneloop_workspaces.js',import.meta.url),'utf8'),{window,document});
 class Store {
  constructor(value){this.value=value;this.listeners=new Set();}
  getSnapshot(){return this.value;}
  subscribe(fn){this.listeners.add(fn);return()=>this.listeners.delete(fn);}
 }
 const workspaces={list:new Store({items:[{workspaceId:'a',title:'课题 A',path:'/private/a',sessionIds:[]},{workspaceId:'b',title:'课题 B',path:'/private/b',sessionIds:[]}],archivedSessionIds:[]})};
 const sessions={list:new Store({current:null,ids:[],byId:{}}),async create(request){created.push(request);return 'new-'+created.length;},open(){}};
 const navigation={startSession(){throw Error('old behavior');}},services={workspaces,sessions,uiWorkspace:navigation};
 const ctx={get:name=>services[name],effect:fn=>fn(),slots:{inject(_name,fn){const v=fn();if(v?.next)[...v];},register(options,component){slots.push({options,component});}}};
 const React={createElement:(type,props,...children)=>({type,props,children}),useState:initial=>[initial,()=>{}],useRef:initial=>({current:initial}),useEffect(){},
  useSyncExternalStore(subscribe,snapshot){const stop=subscribe(()=>{});stop();return snapshot();}};
 window.__installGeneLoopWorkspaces(ctx,React,{Modal:'modal'});
 const Browser=slots.find(row=>row.options.name==='sidebar.workspaces').component;
 const tree=Browser({wide:true}),nodes=[];
 const visit=node=>{if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(visit);return;}nodes.push(node);node.children?.forEach(visit);};visit(tree);
 assert.doesNotMatch(JSON.stringify(tree),/\/private\//);
 const workspaceNames=nodes.filter(node=>node.props?.className==='geneloop-workspace-name');
 assert.ok(workspaceNames.every(node=>!('title' in node.props)), 'workspace names have no hover tooltip');
 workspaceNames.find(node=>node.children[1].children.includes('课题 B')).props.onClick();
 navigation.startSession(); await new Promise(resolve=>setImmediate(resolve));
 assert.equal(created.length,1); assert.equal(created[0].workspaceId,'b');
 navigation.startSession(); await new Promise(resolve=>setImmediate(resolve));
 assert.equal(created.length,2,'New chat creates a fresh chat instead of reopening a blank one');
 assert.equal(created[1].workspaceId,'b');
});

test('workspace pins persist per account and cannot address another account or resurrect a deleted group', options, async t => {
  const { createManagedWorkspaceService } = await import('../src/adapters/harless_managed_workspaces.ts');
  const root = temporary(t), one = registry(), two = registry();
  const a = createManagedWorkspaceService(root, 'account-a', one), b = createManagedWorkspaceService(root, 'account-b', two);
  const left = (await a.create({ name: '同名课题', request_id: randomUUID() })).workspace;
  const right = (await b.create({ name: '同名课题', request_id: randomUUID() })).workspace;
  await Promise.all([a.pin({ workspace_id: left.workspaceId, pinned: true }), b.pin({ workspace_id: right.workspaceId, pinned: true })]);
  assert.deepEqual(a.preferences().pinned_workspace_ids, [left.workspaceId]);
  assert.deepEqual(b.preferences().pinned_workspace_ids, [right.workspaceId]);
  assert.deepEqual(createManagedWorkspaceService(root, 'account-a', one).preferences(), a.preferences());
  await assert.rejects(a.pin({ workspace_id: right.workspaceId, pinned: true }), error => error.status === 404);
  await assert.rejects(a.pin({ workspace_id: left.workspaceId, pinned: 'true' }));
  await assert.rejects(a.pin({ workspace_id: left.workspaceId, pinned: true, path: right.path }));
  await a.pin({ workspace_id: left.workspaceId, pinned: false });
  assert.deepEqual(a.preferences().pinned_workspace_ids, []);
  await a.pin({ workspace_id: left.workspaceId, pinned: true });
  one.items.splice(0, 1);
  assert.deepEqual(a.preferences().pinned_workspace_ids, []);
  await assert.rejects(a.pin({ workspace_id: left.workspaceId, pinned: true }), error => error.status === 404);
  assert.doesNotMatch(JSON.stringify(b.preferences()), /path|managed-workspaces/);
});

test('pin endpoint enforces normal authentication and returns only owned opaque IDs', options, async t => {
  const { registerManagedWorkspaceRoutes } = await import('../src/adapters/harless_managed_workspaces.ts');
  const routes = new Map(), records = registry(), ctx = { workspaceRegistry: records, effect: fn => fn(), connection: {
    requestRejection: req => req.headers.get('authorization') === 'fixture' ? undefined : 401,
    fetch: { register: route => { routes.set(route.path, route); return () => {}; } },
  } };
  const service = registerManagedWorkspaceRoutes(ctx, { output: temporary(t), principal: 'member' });
  const item = (await service.create({ name: '项目', request_id: randomUUID() })).workspace;
  const route = routes.get('/api/harless/workspaces/preferences');
  const send = (data, auth = true) => route.fetch(new Request('http://localhost/api/harless/workspaces/preferences', {
    method: data ? 'POST' : 'GET', headers: { 'content-type': 'application/json', ...(auth ? { authorization: 'fixture' } : {}) },
    ...(data ? { body: JSON.stringify(data) } : {}),
  }));
  assert.equal((await send(undefined, false)).status, 401);
  assert.equal((await send({ workspace_id: item.workspaceId, pinned: true }, false)).status, 401);
  const pinned = await send({ workspace_id: item.workspaceId, pinned: true });
  assert.equal(pinned.headers.get('cache-control'), 'no-store');
  assert.deepEqual(await pinned.json(), { pinned_workspace_ids: [item.workspaceId] });
  assert.deepEqual(await (await send()).json(), { pinned_workspace_ids: [item.workspaceId] });
  assert.equal((await send({ workspace_id: randomUUID(), pinned: true })).status, 404);
});

function interactiveWorkspaceBrowser() {
  const slots = [], values = [], headerValues = [], calls = [], streams = [], cleanups = [], styles = [], inputs = new Map();
  const window = { innerWidth: 1200, innerHeight: 800, EventSource: class {
    constructor(url) { this.url = url; streams.push(this); } close() { this.closed = true; }
  } };
  const document = { createElement: () => ({ remove() {} }), head: { append: style => styles.push(style) } };
  class Store { constructor(value) { this.value = value; this.listeners = new Set(); } getSnapshot() { return this.value; }
    subscribe(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); } emit() { for (const fn of this.listeners) fn(); } }
  const workspaces = { list: new Store({ items: [{ workspaceId: 'a', title: '论文', path: '/private/a', sessionIds: ['one'] },
    { workspaceId: 'b', title: '实验', path: '/private/b', sessionIds: [] }], archivedSessionIds: [] }),
    async delete(id) { calls.push(['delete', id]); this.list.value = { ...this.list.value, items: this.list.value.items.filter(item => item.workspaceId !== id) }; },
    async rename(id, title) { calls.push(['rename', id, title]); },
  };
  const sessions = { list: new Store({ current: 'one', ids: ['one'], byId: { one: { id: 'one', title: '已有聊天' } } }),
    open(id) { calls.push(['open', id]); }, async create(options) { calls.push(['create', options]); return 'new'; },
    scope(id) { return { id }; },
    clear() { calls.push(['clear']); this.list.value = { ...this.list.value, current: undefined }; this.list.emit(); },
    async refresh() { calls.push(['refresh']); } };
  const navigation = { startSession() {}, async forkSession(id) { calls.push(['fork', id]); }, async archiveSession(id) { calls.push(['archive', id]); } };
  const layout = { selectPanel(id) { calls.push(['panel', id]); } };
  const services = { workspaces, sessions, uiWorkspace: navigation, layout, conversation: { input: { for(scope) {
    return { state: { getSnapshot: () => inputs.get(scope.id) || { draft: '', attachmentIds: [], phase: 'plain' } } };
  } } } };
  let index = 0, pinned = [], hookValues = values, deleted = [], purged = [], restored = [], trashFailure = null, delayTrash = null;
  const settingsValues = new Map();
  const React = { createElement: (type, props, ...children) => ({ type, props, children }),
    useState(initial) { const i = index++, target = hookValues; if (!(i in target)) target[i] = typeof initial === 'function' ? initial() : initial;
      return [target[i], update => { target[i] = typeof update === 'function' ? update(target[i]) : update; }]; },
    useRef(initial) { const i = index++; if (!(i in hookValues)) hookValues[i] = { current: initial }; return hookValues[i]; }, useEffect() {},
    useSyncExternalStore(_subscribe, snapshot) { return snapshot(); },
  };
  const ctx = { get: name => services[name], effect: fn => { const cleanup = fn(); if (typeof cleanup === 'function') cleanups.push(cleanup); }, slots: { inject(_name, fn) { const result = fn(); if (result?.next) [...result]; },
    register(options, component) { slots.push({ options, component }); } } };
  const fetch = async (url, options) => {
    if (url === '/api/harless/session-trash') {
      if (options?.method === 'POST') {
        const input = JSON.parse(options.body); calls.push(['trash', input]);
        if (delayTrash) await delayTrash;
        if (trashFailure) return { ok: false, status: 409, json: async () => ({ error: { code: trashFailure } }) };
        if (input.action === 'delete') deleted = [...new Set([...deleted, input.session_id])];
        else if (input.action === 'clear') { purged = [...deleted]; deleted = []; }
        else { deleted = deleted.filter(id => id !== input.session_id); restored.push(input.session_id); }
      }
      return { ok: true, json: async () => ({ revision: JSON.stringify(deleted), restored_archive_ids: restored, deleted_session_ids: [...deleted, ...purged], sessions: deleted.map(id => ({ session_id: id, title: sessions.list.value.byId[id]?.title || '新会话', workspace_id: 'a' })) }) };
    }
    if (options?.method === 'POST') { const input = JSON.parse(options.body); calls.push(['pin', input]); pinned = input.pinned ? [...pinned, input.workspace_id] : pinned.filter(id => id !== input.workspace_id); }
    return { ok: true, json: async () => ({ pinned_workspace_ids: pinned }) };
  };
  vm.runInNewContext(readFileSync(new URL('../src/adapters/geneloop_workspaces.js', import.meta.url), 'utf8'), { window, document, fetch });
  window.__installGeneLoopWorkspaces(ctx, React, { Modal: 'modal' });
  const Browser = slots.find(row => row.options.name === 'sidebar.workspaces').component;
  const Home = slots.find(row => row.options.name === 'main' && row.options.key === 'geneloop-workspace').component;
  const Header = slots.find(row => row.options.id === 'geneloop-chat-management').component;
  const render = () => { index = 0; hookValues = values; return Browser({ wide: true }); };
  const header = () => { index = 0; hookValues = headerValues; return Header(); };
  const nodes = tree => { const result = []; const visit = node => { if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit); result.push(node); node.children?.forEach(visit); }; visit(tree); return result; };
  const click = button => button.props.onClick({ stopPropagation() {}, currentTarget: { getBoundingClientRect: () => ({ right: 260, bottom: 180 }), focus() {} } });
  const settings = id => { if (!settingsValues.has(id)) settingsValues.set(id, []); index = 0; hookValues = settingsValues.get(id);
    return slots.find(row => row.options.name === 'settings.section' && row.options.id === id).component({ close: () => calls.push(['close-settings']) }); };
  return { render, header, home: () => Home(), nodes, click, calls, workspaces, sessions, navigation, streams, inputs, styles,
    settings, slots,
    dispose: () => cleanups.reverse().forEach(fn => fn()),
    remount: () => { values.length = 0; return render(); }, setDeleted: ids => { deleted = ids; },
    failTrash: code => { trashFailure = code; }, delayTrash: promise => { delayTrash = promise; } };
}

test('workspace browser restores folder controls and an accessible menu with durable pinning', async () => {
  const ui = interactiveWorkspaceBrowser(); let tree = ui.render(), nodes = ui.nodes(tree);
  const primary = nodes.find(node => node.props?.className === 'geneloop-workspace-name');
  assert.equal(primary.children[0].type, 'svg', 'folder outline remains visible next to every workspace');
  assert.equal(primary.props['aria-expanded'], true);
  assert.ok(!nodes.some(node => ['geneloop-workspace-toggle','geneloop-workspace-chevron'].includes(node.props?.className)));
  assert.equal(nodes.some(node => node.props?.type === 'search'), false, 'search is a compact optional control');
  assert.ok(nodes.filter(node => node.props?.className === 'geneloop-workspace-name').every(node => !node.props.title));
  ui.click(nodes.find(node => node.props?.['aria-label'] === '工作区操作 实验'));
  nodes = ui.nodes(ui.render());
  assert.ok(nodes.some(node => node.props?.role === 'menuitem' && node.children.includes('工作区设置')));
  ui.click(nodes.find(node => node.props?.role === 'menuitem' && node.children.includes('置顶工作区')));
  await new Promise(resolve => setImmediate(resolve));
  nodes = ui.nodes(ui.render());
  assert.equal(nodes.find(node => node.props?.className === 'geneloop-workspace-name').children[1].children[0], '实验');
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.find(row => row[0] === 'pin'))), ['pin', { workspace_id: 'b', pinned: true }]);
  assert.doesNotMatch(JSON.stringify(ui.render()), /\/private\//);
});

test('private execution lanes never appear in grouped, ungrouped, archived or overview chat lists', () => {
  const ui = interactiveWorkspaceBrowser();
  const state = ui.sessions.list.value;
  for (const id of ['private-grouped', 'private-ungrouped', 'private-archived']) {
    state.ids.push(id); state.byId[id] = { id, title: id, projectionValues: { harlessComparisonLane: true } };
  }
  ui.workspaces.list.value.items[0].sessionIds.push('private-grouped');
  ui.workspaces.list.value.archivedSessionIds.push('private-archived');
  const publicNames = tree => ui.nodes(tree).filter(node => node.type === 'button').flatMap(node => node.children.filter(child => typeof child === 'string'));
  assert.ok(publicNames(ui.render()).includes('已有聊天'));
  assert.ok(publicNames(ui.render()).every(value => !value.includes('private-')));
  const overview = JSON.stringify(ui.home());
  assert.doesNotMatch(overview, /private-grouped/);
  assert.match(overview, /1 个/);
});

test('workspace region inset covers direct and display-contents slot wrappers without depending on native class hashes', () => {
  const ui = interactiveWorkspaceBrowser();
  const css = ui.styles.map(style => style.textContent).join('\n');
  const rule = [...css.matchAll(/([^{}]+)\{([^{}]+)\}/g)].find(([, , declaration]) => declaration.includes('margin-right:0'));
  assert.ok(rule, 'override the native negative right margin, not padding inside the workspace list');
  assert.deepEqual(rule[1].split(','), ['div:has(>.geneloop-workspaces)', 'div:has(>div>.geneloop-workspaces)'],
    'cover both public slot host shapes, including the measured display:contents wrapper');
  assert.match(rule[2], /min-width:0/);
  assert.match(rule[2], /box-sizing:border-box/);
  assert.match(css, /grid-template-columns:minmax\(0,1fr\) 28px 28px/);
});

test('deleting a named workspace requires consequence review and keeps its chats visible ungrouped', async () => {
  const ui = interactiveWorkspaceBrowser();
  ui.click(ui.nodes(ui.render()).find(node => node.props?.['aria-label'] === '工作区操作 论文'));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.role === 'menuitem' && node.children.includes('删除工作区')));
  assert.deepEqual(ui.calls, [], 'opening confirmation cannot mutate the workspace');
  const nodes = ui.nodes(ui.render()), modal = nodes.find(node => node.type === 'modal' && node.props.title === '删除工作区');
  assert.equal(modal.props.open, true);
  assert.match(JSON.stringify(modal), /删除工作区“论文”/);
  assert.match(JSON.stringify(modal), /已有对话将移至.*未分组.*对话记录和文件都会保留/);
  const confirmation = ui.nodes(modal).find(node => node.type === 'button' && node.children.includes('删除工作区'));
  ui.click(confirmation); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(ui.calls, [['delete', 'a']]);
  assert.equal(ui.sessions.list.value.byId.one.title, '已有聊天');
  assert.match(JSON.stringify(ui.render()), /未分组/);
  ui.navigation.startSession(); await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.find(row => row[0] === 'create'))), ['create', {}]);
});

test('chat overflow menu invokes the shared fork and archive navigation capabilities', async () => {
  const ui = interactiveWorkspaceBrowser();
  ui.click(ui.nodes(ui.render()).find(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.role === 'menuitem' && node.children.includes('在新对话中分支')));
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(ui.calls, [['fork', 'one']]);
  ui.click(ui.nodes(ui.render()).find(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.role === 'menuitem' && node.children.includes('归档对话')));
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(ui.calls[1], ['archive', 'one']);
});

test('workspace landing uses a public panel, preserves the current chat, and starts new chats in the selected group', async () => {
  const ui = interactiveWorkspaceBrowser();
  const workspace = ui.nodes(ui.render()).find(node => node.props?.className === 'geneloop-workspace-name' && node.children[1].children.includes('实验'));
  assert.equal(workspace.props['aria-expanded'], false);
  ui.click(workspace);
  assert.equal(ui.nodes(ui.render()).find(node => node.props?.className === 'geneloop-workspace-name' && node.children[1].children.includes('实验')).props['aria-expanded'], true);
  assert.deepEqual(ui.calls, [['panel', 'geneloop-workspace']]);
  assert.equal(ui.sessions.list.value.current, 'one', 'opening a workspace overview does not replace an existing chat or draft');
  assert.match(JSON.stringify(ui.home()), /实验工作区/);
  assert.match(JSON.stringify(ui.home()), /这个工作区还没有对话/);
  assert.doesNotMatch(JSON.stringify(ui.home()), /\/private\//);
  ui.click(ui.nodes(ui.home()).find(node => node.props?.className === 'geneloop-workspace-start'));
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls.find(row => row[0] === 'create'))), ['create', { workspaceId: 'b' }]);
  assert.deepEqual(ui.calls.at(-1), ['panel', null]);
  ui.click(ui.nodes(ui.home()).find(node => node.props?.className === 'geneloop-workspace-home-menu'));
  const settings = ui.nodes(ui.render()).find(node => node.props?.role === 'menuitem' && node.children.includes('工作区设置'));
  assert.ok(settings, 'overview header uses the same workspace management menu');
  ui.click(settings);
  const modal = ui.nodes(ui.render()).find(node => node.type === 'modal' && node.props.title === '工作区设置');
  assert.equal(modal.props.open, true);
  assert.equal(ui.nodes(modal).find(node => node.type === 'input').props.value, '实验');
});

test('workspace clicks toggle without selected/current updates or sidebar remount reopening the group', () => {
  const ui = interactiveWorkspaceBrowser();
  const group = name => ui.nodes(ui.render()).find(node => node.props?.className === 'geneloop-workspace-name' && node.children[1].children.includes(name));
  assert.equal(group('论文').props['aria-expanded'], true);
  ui.click(group('论文'));
  assert.equal(group('论文').props['aria-expanded'], false);
  ui.sessions.list.emit();
  assert.equal(group('论文').props['aria-expanded'], false, 'same-current stream updates do not undo explicit collapse');
  ui.remount();
  assert.equal(group('论文').props['aria-expanded'], false, 'sidebar remount preserves explicit collapsed state');
  ui.click(group('论文'));
  assert.equal(group('论文').props['aria-expanded'], true);
  ui.click(group('实验'));
  assert.equal(group('实验').props['aria-expanded'], true);
  ui.click(group('实验'));
  assert.equal(group('实验').props['aria-expanded'], false, 'selected group also collapses');
  ui.sessions.list.emit();
  assert.equal(group('实验').props['aria-expanded'], false);
  assert.ok(!ui.calls.some(row => row[0] === 'create' || row[0] === 'open'), 'collapse never creates or changes the current chat');
});

test('an explicitly named blank conversation keeps its visible name in the sidebar and workspace overview', () => {
  const ui=interactiveWorkspaceBrowser();
  ui.sessions.list.value.byId.one={id:'one',blank:true,title:'空会话手动名称'};
  let nodes=ui.nodes(ui.render());
  assert.ok(nodes.some(row=>row.props?.className==='geneloop-chat-name'&&row.children.includes('空会话手动名称')));
  ui.click(nodes.find(row=>row.props?.className==='geneloop-workspace-name'));
  assert.ok(ui.nodes(ui.home()).some(row=>row.type==='span'&&row.children.includes('空会话手动名称')));
  ui.dispose();
});

test('archive and trash belong to native settings while workspace and first chat retain a visible gap', () => {
  const ui = interactiveWorkspaceBrowser(); ui.workspaces.list.value.archivedSessionIds = ['one'];
  const sidebar = ui.nodes(ui.render());
  assert.ok(!sidebar.some(node => node.type === 'button' && node.children.some(child => ['已归档对话', '最近删除'].includes(child))));
  for (const [id, label] of [['geneloop-archived', '已归档对话'], ['geneloop-trash', '最近删除']]) {
    const entry = ui.slots.find(row => row.options.name === 'settings.section' && row.options.id === id);
    assert.equal(entry.options.label(), label); assert.equal(ui.settings(id).type, 'section');
  }
  const archived = ui.settings('geneloop-archived'), open = ui.nodes(archived).find(node => node.type === 'button');
  ui.click(open); assert.ok(ui.calls.some(row => row[0] === 'open' && row[1] === 'one'));
  assert.ok(ui.calls.some(row => row[0] === 'close-settings'));
  assert.match(ui.styles.map(style => style.textContent).join(''), /\.geneloop-workspace-row\+\.geneloop-chat-row\{margin-top:3px\}/);
  ui.dispose();
});

test('archived restore returns to its original workspace and clear requires an explicit reviewed confirmation', async () => {
  const ui = interactiveWorkspaceBrowser(), settle = () => new Promise(resolve => setImmediate(resolve));
  await settle(); ui.workspaces.list.value.archivedSessionIds = ['one'];
  const button = (page, label) => ui.nodes(page).find(node => node.type === 'button' && node.props?.['aria-label'] === label);
  ui.click(button(ui.settings('geneloop-archived'), '恢复对话 已有聊天')); await settle();
  assert.ok(!button(ui.settings('geneloop-archived'), '恢复对话 已有聊天'));
  assert.ok(ui.workspaces.list.value.items[0].sessionIds.includes('one'));
  assert.ok(button(ui.render(), '会话操作 已有聊天'));
  ui.click(button(ui.render(), '会话操作 已有聊天'));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.role === 'menuitem' && node.children.includes('移入回收站'))); await settle();
  const clear = () => button(ui.settings('geneloop-trash'), '清空最近删除');
  ui.click(clear());
  assert.ok(ui.nodes(ui.settings('geneloop-trash')).some(node => node.props?.['aria-label'] === '核对清空对话'));
  assert.ok(!ui.calls.some(row => row[0] === 'trash' && row[1].action === 'clear'));
  ui.click(ui.nodes(ui.settings('geneloop-trash')).find(node => node.type === 'button' && node.children.includes('取消')));
  assert.ok(!ui.nodes(ui.settings('geneloop-trash')).some(node => node.props?.['aria-label'] === '核对清空对话'));
  ui.click(clear());
  ui.click(ui.nodes(ui.settings('geneloop-trash')).find(node => node.type === 'button' && node.children.includes('永久清空 1 个对话'))); await settle();
  assert.ok(clear().props.disabled);
  assert.ok(!button(ui.render(), '会话操作 已有聊天'));
  const request = ui.calls.find(row => row[0] === 'trash' && row[1].action === 'clear')[1];
  assert.equal(request.revision, '["one"]'); ui.dispose();
});

test('mobile settings uses its public seat to give content full width without changing desktop or unrelated dialogs', () => {
  const ui = interactiveWorkspaceBrowser();
  const css = ui.styles.map(style => style.textContent).join('');
  const scope = '[role="dialog"][aria-modal="true"]:has([data-slot="geneloop.settings.section"])';
  const mobile = css.slice(css.indexOf('@media(max-width:640px){'), css.indexOf('\n    }', css.indexOf('@media(max-width:640px){')));
  assert.ok(mobile.startsWith('@media(max-width:640px){'));
  assert.ok(mobile.includes(scope + '{box-sizing:border-box;width:calc(100vw - 24px)'));
  assert.match(mobile, /height:min\(800px,calc\(100dvh - 24px\)\);flex-direction:column/);
  assert.ok(mobile.includes(scope + '>nav{width:100%;min-width:0'));
  assert.match(mobile, />nav>div:last-child\{[^}]*flex-direction:row[^}]*overflow-x:auto/);
  assert.match(mobile, />nav>div:last-child>button\{flex:0 0 auto;height:44px;white-space:nowrap/);
  assert.match(mobile, />nav\+div\{min-width:0;min-height:0;flex:1\}/);
  assert.match(mobile, />nav>div:first-child\{padding:0 160px 0 0/);
  assert.match(mobile, />nav\+div>div:first-child button\{white-space:nowrap\}/);
  assert.match(mobile, />nav\+div>div:first-child\{position:absolute;top:8px;right:8px/);
  assert.ok(mobile.split('\n').slice(1).filter(line => line.trim()).every(line => line.trim().startsWith(scope)), 'every responsive rule stays in the owned settings shell');
  assert.doesNotMatch(mobile, /VOzbGW|\!important/);
  ui.dispose();
});

test('moving current chat to trash clears selection without creating another chat and supports durable restoration', async () => {
  const ui = interactiveWorkspaceBrowser();
  await new Promise(resolve => setImmediate(resolve));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.role === 'menuitem' && node.children.includes('移入回收站')));
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(JSON.parse(JSON.stringify(ui.calls[0])), ['trash', { action: 'delete', session_id: 'one' }]);
  assert.ok(ui.calls.some(row => row[0] === 'clear'));
  assert.ok(ui.calls.some(row => row[0] === 'panel' && row[1] === null));
  assert.ok(!ui.calls.some(row => ['create', 'archive'].includes(row[0])));
  assert.ok(!ui.nodes(ui.render()).some(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  assert.ok(!ui.nodes(ui.home()).some(node => node.type === 'button' && node.children.some(child => child?.type === 'span' && child.children.includes('已有聊天'))));
  assert.ok(!ui.nodes(ui.render()).some(node => node.type === 'button' && node.children.includes('最近删除')));
  const dialog = ui.settings('geneloop-trash');
  assert.equal(dialog.type, 'section'); assert.equal(dialog.props['aria-label'], '最近删除');
  const restore = ui.nodes(dialog).find(node => node.props?.['aria-label'] === '恢复对话 已有聊天');
  ui.click(restore); await new Promise(resolve => setImmediate(resolve));
  assert.ok(ui.calls.some(row => row[0] === 'trash' && row[1].action === 'restore' && row[1].session_id === 'one'));
  assert.ok(ui.nodes(ui.render()).some(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  assert.equal(ui.sessions.list.value.current, undefined, 'restoration does not unexpectedly open or create a chat');
});

test('header provides deletion when sidebar is collapsed and active-task refusal leaves current chat intact', async () => {
  const ui = interactiveWorkspaceBrowser();
  await new Promise(resolve => setImmediate(resolve));
  ui.failTrash('session_busy');
  const button = ui.nodes(ui.header()).find(node => node.props?.['aria-label'] === '将当前对话移入回收站');
  assert.equal(button.children[0].type, 'svg', 'direct recycle-bin icon does not duplicate native export ellipsis');
  ui.click(button);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.sessions.list.value.current, 'one');
  assert.ok(!ui.calls.some(row => ['clear', 'create', 'archive'].includes(row[0])));
  const error = ui.nodes(ui.header()).find(node => node.type === 'modal' && node.props.title === '操作未完成');
  assert.equal(error.props.open, true);
  assert.match(JSON.stringify(error), /停止生成或等待完成/);
});

test('completing a delayed deletion cannot clear a different conversation opened meanwhile', async () => {
  const ui = interactiveWorkspaceBrowser();
  await new Promise(resolve => setImmediate(resolve));
  let finish; ui.delayTrash(new Promise(resolve => { finish = resolve; }));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  ui.click(ui.nodes(ui.render()).find(node => node.props?.role === 'menuitem' && node.children.includes('移入回收站')));
  ui.sessions.list.value = { ...ui.sessions.list.value, current: 'two', ids: ['one', 'two'], byId: { ...ui.sessions.list.value.byId, two: { id: 'two', title: '另一对话' } } };
  ui.sessions.list.emit(); finish();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.sessions.list.value.current, 'two');
  assert.ok(!ui.calls.some(row => ['clear', 'create'].includes(row[0])));
});

test('account trash stream clears deleted selection and refreshes restored membership without permanent removal events', async () => {
  const ui = interactiveWorkspaceBrowser();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.streams.length, 1);
  const stream = ui.streams[0]; assert.equal(stream.url, '/api/harless/session-trash?stream=1');
  ui.setDeleted(['one']); stream.onmessage({ data: '{"changed":true}' });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.sessions.list.value.current, undefined);
  assert.ok(!ui.nodes(ui.render()).some(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  ui.setDeleted([]); stream.onmessage({ data: '{"changed":true}' });
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(ui.nodes(ui.render()).some(node => node.props?.['aria-label'] === '会话操作 已有聊天'));
  assert.equal(ui.calls.filter(row => row[0] === 'refresh').length, 2);
  assert.ok(!ui.calls.some(row => ['open', 'create'].includes(row[0])));
  ui.dispose(); assert.equal(stream.closed, true, 'plugin unmount releases account notification stream');
});

test('workspace new chat reuses an empty blank by membership without depending on redacted host paths', async () => {
  const ui = interactiveWorkspaceBrowser();
  ui.sessions.list.value.byId.one.blank = true;
  ui.sessions.list.value.byId.one.cwd = '/server/session/work';
  ui.workspaces.list.value.items[0].path = '';
  ui.navigation.startSession('a'); await new Promise(resolve => setImmediate(resolve));
  assert.ok(!ui.calls.some(row => row[0] === 'create'));
  assert.ok(ui.calls.some(row => row[0] === 'open' && row[1] === 'one'));
  ui.inputs.set('one', { draft: '尚未发送的问题', attachmentIds: ['csv', 'json'], phase: 'plain' });
  assert.equal(await ui.navigation.connectWorkspace('a'), 'one', 'workspace selection during upload preserves current draft and attachment owner');
  assert.ok(!ui.calls.some(row => row[0] === 'create'));
  ui.navigation.startSession('a'); await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.calls.filter(row => row[0] === 'create').length, 1, 'explicit new chat never reuses an occupied composer');
  assert.deepEqual(ui.inputs.get('one').attachmentIds, ['csv', 'json']);
  assert.equal(ui.inputs.get('one').draft, '尚未发送的问题');
});

test('new chat cannot reuse an inactive blank whose draft may belong to another window', async () => {
  const ui = interactiveWorkspaceBrowser();
  ui.sessions.list.value.current = undefined;
  ui.sessions.list.value.byId.one.blank = true;
  ui.navigation.startSession('a'); await new Promise(resolve => setImmediate(resolve));
  assert.equal(ui.calls.filter(row => row[0] === 'create').length, 1);
  assert.ok(!ui.calls.some(row => row[0] === 'open' && row[1] === 'one'));
  ui.dispose();
});

test('removed and restored native membership refresh trash without exposing archived deleted chats or reopening a frozen selection', async () => {
  const ui = interactiveWorkspaceBrowser();
  await new Promise(resolve => setImmediate(resolve));
  ui.workspaces.list.value.archivedSessionIds = ['one'];
  ui.setDeleted(['one']);
  ui.sessions.list.value = { ...ui.sessions.list.value, current: undefined, ids: [] };
  ui.sessions.list.emit();
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(ui.calls.some(row => row[0] === 'clear'), 'removed-current masked gap must clear the durable native selection too');
  const archive = ui.settings('geneloop-archived');
  assert.ok(!ui.nodes(archive).some(node => node.type === 'span' && node.children.includes('已有聊天')));
  ui.setDeleted([]); ui.sessions.list.value.ids = ['one']; ui.sessions.list.emit();
  await new Promise(resolve => setImmediate(resolve));
  const restoredArchive = ui.settings('geneloop-archived');
  assert.ok(ui.nodes(restoredArchive).some(node => node.type === 'span' && node.children.includes('已有聊天')));
  assert.equal(ui.sessions.list.value.current, undefined);
});

test('workspace browser installation retries delayed service readiness without duplicating directory flows or native replacement', async () => {
  const slots = [], styles = [], services = {}, callbacks = [], window = {};
  const document = { createElement: () => ({ remove() {} }), head: { append: value => styles.push(value) } };
  const ctx = { get: name => services[name], inject: (_names, ready) => callbacks.push(ready), effect: fn => fn(),
    slots: { inject(_name, fn) { const value = fn(); if (value?.next) [...value]; }, register(options, component) { slots.push({ options, component }); } } };
  const React = { createElement: (type, props, ...children) => ({ type, props, children }) };
  vm.runInNewContext(readFileSync(new URL('../src/adapters/geneloop_workspaces.js', import.meta.url), 'utf8'), {
    window, document, fetch: async () => ({ ok: true, json: async () => ({ sessions: [], deleted_session_ids: [] }) }),
  });
  window.__installGeneLoopWorkspaces(ctx, React, { Modal: 'modal' });
  assert.equal(slots.length, 2); assert.equal(callbacks.length, 1);
  const store = value => ({ getSnapshot: () => value, subscribe: () => () => {} });
  services.workspaces = { list: store({ items: [], archivedSessionIds: [] }) };
  services.sessions = { list: store({ current: undefined, ids: [], byId: {} }) };
  services.uiWorkspace = { startSession() {} };
  callbacks[0](); window.__installGeneLoopWorkspaces(ctx, React, { Modal: 'modal' });
  assert.equal(slots.filter(row => row.options.name === 'sidebar.workspaces').length, 1);
  assert.equal(slots.filter(row => row.options.name.endsWith('.directoryFlow')).length, 2);
  assert.equal(styles.length, 1);
  assert.ok(slots.find(row => row.options.name === 'sidebar.workspaces').options.priority < 0, 'public single slot elects our browser before native default');
  await new Promise(resolve => setImmediate(resolve));
});
