/** Public settings-slot/component diagnostics; no server mutations or model calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/adapters/harless_account_link.js', import.meta.url), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
async function flush() { for (let i = 0; i < 5; i++) await tick(); }
const user = { username: 'researcher', displayName: '研究员', role: 'member', createdAt: 0 };
const catalog = { default: { provider: 'deepseek', model: 'flash', reasoning_effort: 'off' }, models: [
  { provider: 'deepseek', model: 'flash', label: 'DeepSeek Flash', available: true, reasoning_modes: [
    { id: 'off', label: 'Off', available: true }, { id: 'high', label: 'On', available: true }] },
  { provider: 'deepseek', model: 'pro', label: 'DeepSeek Pro', available: true, reasoning_modes: [
    { id: 'off', label: 'Off', available: true }, { id: 'high', label: 'On', available: false, unavailable_reason: '超过当前任务预算' }] },
] };

function fixture(fetcher, { lateShell = false } = {}) {
  const entries = new Map(), declared = new Set(['sidebar.settings', 'settings.section', 'settings.general.item']);
  const listeners = new Map(), cleanups = [], requests = [], navigations = [], mounted = new Set();
  let seat, cursor = 0;
  const React = {
    createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }),
    useState(initial) { const n = cursor++, target = seat; if (!(n in target.states)) target.states[n] = initial;
      return [target.states[n], value => { target.states[n] = typeof value === 'function' ? value(target.states[n]) : value; }]; },
    useRef(initial) { const n = cursor++; if (!(n in seat.states)) seat.states[n] = { current: initial }; return seat.states[n]; },
    useEffect(fn, deps) { const n = cursor++, target = seat, previous = target.deps[n];
      if (!previous || deps.some((value, i) => value !== previous[i])) { target.deps[n] = deps;
        target.effects.push(() => { target.cleanups[n]?.(); target.cleanups[n] = fn(); }); } },
  };
  const native = function NativeSettingsRoot() {}, originalRows = [
    { id: 'general', label: '通用设置', order: 0 }, { id: 'models', label: '模型', order: 10 }, { id: 'models', label: '模型', order: 10 },
  ];
  const rowsSource = { getSnapshot() { return this.rows; }, rows: originalRows, subscribe(fn) { assert.equal(this, rowsSource); return () => {}; } };
  const nativeHook = { getSnapshot: () => 'native' }, nativeStore = { name: 'native-settings' };
  const original = { component: native, options: {}, locale: 'settings', store: nativeStore,
    children: { 'settings.section': { kind: 'list', scope: 'root' } },
    inject: () => ({ reconnect: 'native-reconnect', hooks: { sections: rowsSource, connectionState: nativeHook } }) };
  entries.set('sidebar.settings', lateShell ? [] : [original]);
  entries.set('settings.section', [{ component: function NativeGeneral() {}, options: { id: 'general', order: 0 },
    children: { 'settings.general.item': { kind: 'list', scope: 'root' } } },
  { component: function NativeModels() {}, options: { id: 'models', order: 10 } }]);
  entries.set('settings.general.item', [{ component: function NativeLanguageRow() {}, options: { id: 'locale', order: 0 }, inject: () => ({ locale: 'zh' }) }]);
  const notify = name => { for (const listener of [...listeners.get(name) || []]) listener(); };
  const slots = {
    entries: name => entries.get(name) || [],
    subscribe(name, fn) { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn); return () => listeners.get(name).delete(fn); },
    inject(_name, fn) { const result = fn(); if (result?.next) [...result]; else if (typeof result === 'function') cleanups.push(result); },
    register(spec, component) {
      assert.ok(declared.has(spec.name), spec.name + ' must be declared');
      for (const name of Object.keys(spec.children || {})) { assert.ok(!declared.has(name), name + ' cannot have two declaration owners'); declared.add(name); }
      const entry = { component, options: Object.fromEntries(['id', 'key', 'priority', 'order', 'label'].filter(key => key in spec).map(key => [key, spec[key]])),
        children: spec.children, inject: spec.inject, locale: spec.locale, store: spec.store };
      entries.set(spec.name, [...slots.entries(spec.name), entry].sort((a, b) => (a.options.priority || 0) - (b.options.priority || 0)));
      notify(spec.name);
      return () => { entries.set(spec.name, slots.entries(spec.name).filter(item => item !== entry)); for (const name of Object.keys(spec.children || {})) declared.delete(name); };
    },
  };
  const ctx = { slots, effect(fn) { const cleanup = fn(); if (typeof cleanup === 'function') cleanups.push(cleanup); } };
  const window = { location: { replace: url => navigations.push(url) } };
  const fetch = async (url, options) => {
    requests.push({ url, options });
    return fetcher ? fetcher(url, options) : Response.json(url === '/api/account/me' ? { user } : catalog);
  };
  runInNewContext(source, { window, fetch, AbortController });
  window.__installGeneLoopAccountSettings(ctx, React); window.__installGeneLoopAccountSettings(ctx, React);
  const all = (predicate, tree) => !tree || typeof tree !== 'object' ? [] : [
    ...(predicate(tree) ? [tree] : []), ...(tree.children || []).flatMap(child => all(predicate, child)),
  ];
  const text = tree => typeof tree === 'string' ? tree : (tree?.children || []).map(text).join('');
  const mount = id => {
    const entry = slots.entries('settings.section').find(row => row.options.id === id), state = { states: [], deps: [], effects: [], cleanups: [], tree: null };
    const instance = { render() { seat = state; cursor = 0; state.tree = entry.component({ close() {} });
      const pending = state.effects.splice(0); pending.forEach(fn => fn()); return state.tree; },
    all: predicate => all(predicate, state.tree), text: () => text(state.tree),
    dispose() { state.cleanups.forEach(fn => fn?.()); mounted.delete(instance); } };
    mounted.add(instance); instance.render(); return instance;
  };
  return { slots, entries, declared, original, nativeHook, nativeStore, rowsSource, native, mount, requests, navigations, all, text, notify,
    addShell() { entries.set('sidebar.settings', [original]); notify('sidebar.settings'); },
    dispose() { for (const child of mounted) child.dispose(); cleanups.reverse().forEach(fn => fn()); } };
}

test('settings installation keeps native shell and child ownership, deduplicates models, and retains late nested entries', () => {
  const f = fixture();
  assert.equal(f.slots.entries('settings.section').filter(row => row.options.id === 'geneloop-account').length, 1);
  const shell = f.slots.entries('sidebar.settings')[0]; assert.equal(shell.options.priority, -100);
  assert.equal(shell.locale, 'settings'); assert.equal(shell.store, f.nativeStore);
  const injected = shell.inject(), sections = injected.hooks.sections;
  assert.equal(injected.reconnect, 'native-reconnect'); assert.equal(injected.hooks.connectionState, f.nativeHook);
  assert.equal(sections.getSnapshot().length, 2); assert.equal(sections.getSnapshot(), sections.getSnapshot());
  sections.subscribe(() => {})();
  const routed = [], rendered = shell.component({ renderSlot: (...args) => routed.push(args) });
  assert.equal(rendered.type, f.native); rendered.props.renderSlot('settings.section', { close: 'close' }, { only: 'models' });
  assert.equal(routed[0][0], 'geneloop.settings.section'); assert.equal(routed[0][2].only, 'models');
  const general = f.slots.entries('geneloop.settings.section').find(row => row.options.id === 'general');
  const alias = Object.keys(general.children)[0]; assert.ok(alias.endsWith('settings.general.item'));
  assert.equal(f.slots.entries(alias)[0].options.id, 'locale');
  f.entries.get('settings.general.item').push({ component() {}, options: { id: 'appearance' } }); f.notify('settings.general.item');
  assert.equal(f.slots.entries(alias).length, 2);
  assert.equal(f.original.children['settings.section'].kind, 'list');
  f.dispose(); assert.equal(f.slots.entries('sidebar.settings').length, 1); assert.equal(f.declared.has('geneloop.settings.section'), false);
});

test('settings wrapper waits for native shell registration without creating duplicate declarations', () => {
  const f = fixture(undefined, { lateShell: true }); assert.equal(f.slots.entries('sidebar.settings').length, 0);
  f.addShell(); assert.equal(f.slots.entries('sidebar.settings').length, 2);
  f.notify('sidebar.settings'); assert.equal(f.slots.entries('sidebar.settings').length, 2); f.dispose();
});

test('account settings renders in the content seat, loads authenticated profile, and hides owner-only actions', async () => {
  const f = fixture(), page = f.mount('geneloop-account');
  assert.match(page.text(), /正在加载账户/); await flush(); page.render();
  assert.match(page.text(), /账户与安全.*个人资料.*密码与安全.*成员账号/);
  assert.doesNotMatch(page.text(), /邀请同学|邀请码/); assert.deepEqual(f.navigations, []);
  assert.equal(page.all(row => row.type === 'input' && row.props.name === 'username')[0].props.value, user.username);
  assert.equal(f.requests[0].url, '/api/account/me'); assert.equal(f.requests[0].options.credentials, 'same-origin');
  assert.equal(f.requests[0].options.cache, 'no-store'); f.dispose();
});

test('profile updates save through existing API and double submit cannot create two writes', async () => {
  let finish;
  const f = fixture((url, options) => url.endsWith('/profile') ? new Promise(resolve => { finish = () => resolve(Response.json({ user: { ...user, ...JSON.parse(options.body) } })); }) : Response.json({ user }));
  const page = f.mount('geneloop-account'); await flush(); page.render();
  page.all(row => row.type === 'input' && row.props.name === 'displayName')[0].props.onChange({ target: { value: '新名字' } }); page.render();
  const form = page.all(row => row.type === 'form')[0], work = form.props.onSubmit({ preventDefault() {} }); form.props.onSubmit({ preventDefault() {} }); page.render();
  assert.equal(f.requests.filter(row => row.options.method === 'POST').length, 1);
  assert.ok(page.all(row => row.type === 'input').every(row => row.props.disabled));
  finish(); await work; page.render(); assert.match(page.text(), /资料已保存/); assert.deepEqual(f.navigations, []);
  assert.equal(page.all(row => row.type === 'input' && row.props.name === 'displayName')[0].props.value, '新名字'); f.dispose();
});

test('password mismatch does not submit and an explicit successful change returns to login', async () => {
  const f = fixture(url => Response.json(url.endsWith('/me') ? { user } : { ok: true })), page = f.mount('geneloop-account'); await flush(); page.render();
  const update = (name, value) => { page.all(row => row.type === 'input' && row.props.name === name)[0].props.onChange({ target: { value } }); page.render(); };
  update('newPassword', 'new-password'); update('repeatPassword', 'not-matching');
  page.all(row => row.type === 'form')[1].props.onSubmit({ preventDefault() {} }); page.render();
  assert.match(page.text(), /两次输入的新密码不一致/); assert.equal(f.requests.length, 1);
  update('repeatPassword', 'new-password'); update('currentPassword', 'old-password');
  page.all(row => row.type === 'form')[1].props.onSubmit({ preventDefault() {} }); await flush();
  assert.deepEqual(f.navigations, ['/login?changed=1']); assert.equal(f.requests[1].url, '/api/account/password'); f.dispose();
});

test('owner invitation requires current password and keeps the returned single-use code only in this page', async () => {
  const f = fixture(url => Response.json(url.endsWith('/me') ? { user: { ...user, role: 'owner' } } : { codes: ['fixture-invite'] }));
  const page = f.mount('geneloop-account'); await flush(); page.render(); assert.match(page.text(), /邀请同学/);
  const form = page.all(row => row.type === 'form')[2];
  f.all(row => row.type === 'input', form)[0].props.onChange({ target: { value: 'current-password' } }); page.render();
  page.all(row => row.type === 'form')[2].props.onSubmit({ preventDefault() {} }); await flush(); page.render();
  assert.equal(f.requests[1].url, '/api/account/invites'); assert.deepEqual(JSON.parse(f.requests[1].options.body), { currentPassword: 'current-password', count: 1 });
  assert.equal(page.all(row => row.type === 'output')[0].children[0], 'fixture-invite');
  assert.deepEqual(f.navigations, []); f.dispose();
});

test('account authentication failures stay recoverable in settings and do not redirect without user action', async () => {
  const f = fixture(() => Response.json({}, { status: 401 })), page = f.mount('geneloop-account'); await flush(); page.render();
  assert.match(page.text(), /登录已过期/); assert.equal(page.all(row => row.type === 'a')[0].props.href, '/login');
  assert.ok(page.all(row => row.type === 'button' && row.children.includes('重试')).length); assert.deepEqual(f.navigations, []); f.dispose();
});

test('model settings read the safe catalog and distinguish actual reasoning availability without exposing provider editing', async () => {
  const f = fixture(), page = f.mount('models'); assert.match(page.text(), /正在加载模型/); await flush(); page.render();
  assert.match(page.text(), /DeepSeek Flash默认模型推理 Off · 可用推理 On · 可用/);
  assert.match(page.text(), /DeepSeek Pro可用推理 Off · 可用推理 On · 超过当前任务预算/);
  assert.doesNotMatch(page.text(), /settings are unavailable|API.?key|endpoint|密钥/);
  assert.equal(page.all(row => row.type === 'input').length, 0); assert.equal(f.requests[0].url, '/api/harless/models');
  assert.equal(f.requests[0].options.method, 'GET'); f.dispose();
});

test('model catalog errors can be retried and late unmounted responses do not keep pages alive', async () => {
  let reads = 0, resolve;
  const f = fixture(() => ++reads === 1 ? Response.json({}, { status: 503 }) : new Promise(finish => { resolve = finish; }));
  const page = f.mount('models'); await flush(); page.render(); assert.match(page.text(), /操作未完成/);
  page.all(row => row.type === 'button')[0].props.onClick(); page.render(); assert.equal(reads, 2);
  page.dispose(); assert.equal(f.requests[1].options.signal.aborted, true); resolve(Response.json(catalog)); await flush(); f.dispose();
});
