import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
const start = source.indexOf('      // Adapt public seats/stores only:');
const end = source.indexOf('      // The pinned native tab roster', start);
const code = source.slice(start, end);
const flash = { provider: 'deepseek-official', model: 'flash', reasoningEffort: 'off' };
const pro = { provider: 'deepseek-official', model: 'pro', reasoningEffort: 'off' };
function store(value) {
  const listeners = new Set();
  return { getSnapshot: () => value, set(next) { value = next; for (const fn of listeners) fn(); },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); } };
}
const flush = async () => { for (let i = 0; i < 12; i++) await new Promise(resolve => setImmediate(resolve)); };
function fixture() {
  const original = new Map(), wrappers = new Map(), effects = [], queues = new Map(), scopes = new Map(), native = new Map(), faces = new Map();
  const requests = [], prompts = [], notices = [], menus = new Map(), launches = [], mirrors = [];
  for (const id of ['alice', 'bob']) {
    scopes.set(id, { effect(install) { effects.push(install()); } });
    queues.set(id, []);
    native.set(id, { available: true, directory: store({ current: flash, status: 'ready', error: null, groups: [], routable: true }), load() {},
      select(selection) {
        requests.push({ id, selection });
        this.directory.set({ ...this.directory.getSnapshot(), status: 'selecting' });
        return new Promise(resolve => queues.get(id).push(accepted => {
          this.directory.set({ ...this.directory.getSnapshot(), current: accepted ? selection : this.directory.getSnapshot().current,
            status: accepted ? 'ready' : 'error', error: accepted ? null : '当前选项不可用。' });
          resolve(accepted);
        }));
      } });
    faces.set(id, { prompt(...args) { prompts.push({ id, args, current: native.get(id).directory.getSnapshot().current }); return Promise.resolve({ ok: true }); } });
    menus.set(id, store({ open: false, groups: [], highlight: null }));
  }
  const keyboard = { snapshot: { draft: '保留这段草稿', draftRev: 3 }, dismissPopup() {} };
  const launcher = store('harless-scenes');
  original.set('conversation.composer.bar', { options: {}, children: { 'conversation.input.model': { kind: 'single', scope: 'session' } },
    inject: () => ({ command: () => {}, keyboard, hooks: { menuLauncher: launcher } }), component() {} });
  original.set('conversation.input.model', { options: {}, inject: id => native.get(id), component() {} });
  const ctx = { slots: { entries: name => [original.get(name)].filter(Boolean), subscribe: () => () => {},
    inject(_name, install) { effects.push(install()); }, register(spec, component) { wrappers.set(spec.name, { ...spec, component }); return () => {}; } } };
  runInNewContext(code, { ctx, React: {}, h: () => {}, Promise,
    mirrorPublicSlot(a, b) { mirrors.push([a, b]); return () => {}; },
    sessions: { scope: id => { const scope = scopes.get(id); scope.id = id; return scope; }, binding: id => ({ session: faces.get(id) }) },
    triggers: { sessionOf: scope => ({ menu: menus.get(scope.id), toggleSource: (...args) => launches.push(args) }) },
    conversation: { input: { for: scope => ({ notify: (level, text) => notices.push({ id: scope.id, level, text }) }) } },
  });
  return { requests, prompts, notices, menus, launches, mirrors, wrappers, native, faces,
    model: id => wrappers.get('conversation.input.model').inject(id),
    composer: id => wrappers.get('conversation.composer.bar').inject(id),
    settle: (id, accepted = true) => queues.get(id).shift()(accepted),
    dispose: () => effects.reverse().forEach(fn => fn?.()) };
}
test('model and reasoning update immediately, queue behind the current write, and ignore intermediate projections', async () => {
  const f = fixture(), model = f.model('alice');
  await model.select(pro);
  assert.equal(model.directory.getSnapshot().current.model, 'pro');
  assert.equal(model.directory.getSnapshot().status, 'ready');
  await model.select({ ...flash, reasoningEffort: 'high' });
  assert.equal(model.directory.getSnapshot().current.reasoningEffort, 'high');
  assert.equal(f.requests.length, 1);
  f.settle('alice'); await flush();
  assert.equal(f.requests.length, 2);
  assert.equal(model.directory.getSnapshot().current.model, 'flash');
  assert.equal(model.directory.getSnapshot().current.reasoningEffort, 'high');
  f.settle('alice'); await flush();
  assert.equal(model.directory.getSnapshot().current.reasoningEffort, 'high');
  assert.equal(model.directory.getSnapshot().status, 'ready');
});
test('a send waits for its selected model, and subsequent choices cannot overtake that send', async () => {
  const f = fixture(), model = f.model('alice');
  await model.select(pro);
  const sent = f.faces.get('alice').prompt([{ type: 'text', text: 'hello' }], 'queue', undefined, 'request-1');
  await model.select(flash);
  assert.equal(f.prompts.length, 0);
  f.settle('alice'); await sent; await flush();
  assert.equal(f.prompts.length, 1);
  assert.equal(f.prompts[0].current.model, 'pro');
  assert.equal(f.prompts[0].args[3], 'request-1');
  assert.equal(f.requests.length, 2);
  f.settle('alice'); await flush();
});
test('rejected selection rolls back, warns, and a waiting send is never sent using a different model', async () => {
  const f = fixture(), model = f.model('alice');
  await model.select(pro);
  const sent = f.faces.get('alice').prompt([], 'queue').catch(error => error);
  f.settle('alice', false); await flush();
  assert.match((await sent).message, /消息尚未发送/);
  assert.equal(f.prompts.length, 0);
  assert.equal(model.directory.getSnapshot().current.model, 'flash');
  assert.match(f.notices[0].text, /已恢复之前/);
  await f.faces.get('alice').prompt([], 'queue');
  assert.equal(f.prompts[0].current.model, 'flash');
});
test('navigation keeps the same queue, different sessions remain independent, cancellation and teardown stop queued sends', async () => {
  const f = fixture(), a = f.model('alice'), b = f.model('bob');
  await a.select(pro); await b.select({ ...flash, reasoningEffort: 'high' });
  assert.equal(f.model('alice'), a);
  assert.equal(f.requests.length, 2);
  const aborted = f.faces.get('alice').prompt([], 'queue', { aborted: true }).catch(error => error);
  f.settle('bob'); f.settle('alice'); await flush();
  assert.match((await aborted).message, /取消/);
  assert.equal(f.prompts.length, 0);
  await a.select(flash); const pending = f.faces.get('alice').prompt([], 'queue').catch(error => error);
  f.dispose(); f.settle('alice'); await flush();
  assert.match((await pending).message, /会话已关闭/);
  assert.equal(f.prompts.length, 0);
});
test('web command filtering keeps scene and file sources, preserves keyboard highlight identity and uses the scene launcher', () => {
  const f = fixture(), props = f.composer('alice'), menu = f.menus.get('alice');
  const keep = { name: 'custom' };
  menu.set({ open: true, groups: [
    { source: 'command', status: 'ready', items: ['export', 'feedback', 'harless', 'permission', 'model'].map(name => ({ name })).concat(keep) },
    { source: 'harless-scenes', status: 'ready', items: [{ name: 'data' }, { name: 'ppt' }] },
  ], highlight: { source: 'command', index: 5 } });
  assert.deepEqual(Array.from(menu.getSnapshot().groups[0].items, x => x.name), ['custom']);
  assert.equal(menu.getSnapshot().highlight.index, 0);
  assert.equal(menu.getSnapshot().groups[1].items.length, 2);
  assert.equal(props.command, undefined);
  props.toggleCommandMenu({ start: 0, end: 0 });
  assert.equal(f.launches[0][0], 'harless-scenes');
  assert.equal(f.launches[0][1].position, 'leading');
  assert.equal(f.launches[0][1].span.start, 0);
  assert.equal(f.launches[0][1].span.end, 0);
  assert.equal(props.keyboard.snapshot.draft, '保留这段草稿');
  assert.equal(props.hooks.menuLauncher.getSnapshot(), 'command');
  props.keyboard.snapshot = { draft: '/data 保留这段草稿', draftRev: 4 };
  props.toggleCommandMenu({ start: 14, end: 14 });
  assert.equal(f.launches[1][1].span.end, 5);
  assert.ok(f.mirrors.some(([name]) => name === 'conversation.input.model'));
});
