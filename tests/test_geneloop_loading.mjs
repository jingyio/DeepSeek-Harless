import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../src/adapters/geneloop_brand.js', import.meta.url), 'utf8');
function sourceOf(value) {
  const listeners = new Set();
  return { getSnapshot: () => value, subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    set(next) { value = next; for (const fn of [...listeners]) fn(); }, count: () => listeners.size };
}
function setup() {
  const createElement = tag => ({ tag, hidden: false, children: [], attributes: {},
    append(...nodes) { for (const node of nodes) { if (node.parent) node.parent.children = node.parent.children.filter(value => value !== node); node.parent = this; this.children.push(node); } }, setAttribute(key, value) { this.attributes[key] = value; } });
  const document = { title: 'GeneLoop', readyState: 'complete', head: createElement('head'), documentElement: createElement('html'),
    createElement, querySelectorAll: () => [] };
  const timers = new Map(); let sequence = 0, reloads = 0;
  const window = { location: { reload: () => reloads++ } };
  vm.runInNewContext(source, { window, document, MutationObserver: class { observe() {} },
    setTimeout: (fn, delay) => { const id = ++sequence; timers.set(id, { fn, delay }); return id; },
    clearTimeout: id => timers.delete(id) });
  const [cover, notice] = document.documentElement.children;
  const list = sourceOf({ current: undefined, phase: 'pending' }), sessions = new Map();
  const records = [], effects = [], disposers = [], mirrors = [];
  const original = { options: { id: 'body' }, component: function NativeSession() {}, inject: () => ({}), store: {} };
  const ctx = { get(name) { assert.equal(name, 'sessions'); return { list, binding: id => ({ session: sessions.get(id) }) }; },
    effect(fn) { disposers.push(fn()); }, slots: {
      entries: name => name === 'conversation.session' ? [original] : [],
      inject(name, fn) { assert.equal(name, 'conversation.view'); disposers.push(fn()); },
      register(options, component) { records.push({ options, component }); return () => {}; },
    } };
  const React = { createElement: (type, props, ...children) => ({ type, props, children }), useLayoutEffect: fn => effects.push(fn) };
  const install = () => window.__installGeneLoopLoading(ctx, React, (from, to) => { mirrors.push([from, to]); return () => {}; });
  const session = (id, openState = 'cold') => {
    const state = sourceOf({ openState, running: false, hasMore: true, loadingOlder: false }); sessions.set(id, state); return state;
  };
  const render = (id, state) => {
    const result = records[0].component({ sessionId: id, useSession: selector => selector(state.getSnapshot()), renderSlot: (...args) => args });
    result.props.ref(createElement('section'));
    while (effects.length) effects.shift()(); return result;
  };
  return { window, document, cover, notice, timers, list, records, original, mirrors, disposers, install, session, render, reloads: () => reloads };
}

test('head loader waits for ready list, current history and committed comparison hydration', () => {
  const f = setup(), load = f.window.__geneLoopPageLoad;
  assert.equal(f.cover.hidden, false);
  assert.equal(f.cover.attributes.role, 'status');
  assert.equal(f.cover.children[0].children[0].src, '/assets/geneloop-spiral.svg?v=1');
  const state = f.session('a'); f.install(); f.install();
  assert.equal(f.records.length, 1, 'installer is idempotent');
  f.list.set({ phase: 'ready', current: 'a' });
  const finish = load.hold('a');
  state.set({ openState: 'open', running: false, hasMore: true });
  assert.equal(f.cover.hidden, false, 'open is insufficient before view commit');
  const rendered = f.render('a', state);
  assert.equal(f.cover.hidden, false, 'view stays covered until its comparison GET settles');
  assert.equal(f.cover.parent.attributes['data-loading'],'true','history and composer share the loading boundary');
  finish(); assert.equal(f.cover.hidden, true);
  assert.equal(f.cover.parent.attributes['data-loading'],'false');
  assert.equal(f.timers.size, 0);
  assert.equal(rendered.type, 'div');
  assert.equal(rendered.props.className, 'geneloop-conversation-load-region');
  assert.notEqual(f.cover.parent, f.document.documentElement, 'history loader is inside the chat, never over the sidebar');
  assert.equal(rendered.children[0].type, f.original.component);
  assert.equal(f.records[0].options.inject, f.original.inject);
  assert.equal(f.records[0].options.store, f.original.store);
  assert.equal(rendered.children[0].props.renderSlot('conversation.view', {}, { only: 'chat' })[0], 'geneloop.loading.view');
  assert.deepEqual(f.mirrors, [['conversation.view', 'geneloop.loading.view']]);
  assert.equal(f.records[0].options.children['geneloop.loading.view'].scope, 'session');
});

test('late previous-page completion cannot uncover the next page and streaming never remasks', () => {
  const f = setup(), load = f.window.__geneLoopPageLoad;
  const a = f.session('a', 'open'), b = f.session('b', 'loading'); f.install();
  f.list.set({ phase: 'ready', current: 'a' });
  const previous = load.hold('a'); f.render('a', a);
  f.list.set({ phase: 'ready', current: 'b' });
  previous(); load.commit('a'); assert.equal(f.cover.hidden, false);
  assert.equal(a.count(), 0, 'old history state subscription is disposed');
  b.set({ openState: 'open', running: true, hasMore: true }); f.render('b', b);
  assert.equal(f.cover.hidden, true, 'running tasks do not delay initial history');
  const streaming = load.hold('b');
  b.set({ openState: 'open', running: true, hasMore: true, loadingOlder: true });
  assert.equal(f.cover.hidden, true, 'stream events and manual pagination remain visible');
  streaming(); assert.equal(f.cover.hidden, true);
});

test('blank ready page, failed history and stalled boot have an exit without a reveal-content option', () => {
  const blank = setup(); blank.install(); blank.list.set({ phase: 'ready', current: undefined });
  assert.equal(blank.cover.hidden, true);
  const failed = setup(), state = failed.session('failed', 'loading'); failed.install();
  failed.list.set({ phase: 'ready', current: 'failed' });
  state.set({ openState: 'error' }); assert.equal(failed.cover.hidden, true, 'native error remains reachable');
  assert.equal(failed.cover.children.length, 2, 'only the logo and loading label are shown');
  assert.doesNotMatch(source, /显示已加载内容/);
  const stalled = setup(), timeout = [...stalled.timers.values()][0];
  assert.equal(timeout.delay, 20000); timeout.fn();
  assert.equal(stalled.cover.hidden, true); assert.equal(stalled.notice.hidden, false);
  stalled.notice.children[1].onclick(); assert.equal(stalled.reloads(), 1);
  stalled.notice.children[2].onclick(); assert.equal(stalled.notice.hidden, true);
});

test('loading is accessible without animation and teardown removes public subscriptions', () => {
  const f = setup(), state = f.session('a', 'loading'); f.install(); f.list.set({ phase: 'ready', current: 'a' });
  assert.equal(state.count(), 1); assert.equal(f.list.count(), 1);
  const css = f.document.head.children.map(node => node.textContent || '').join('\n');
  assert.match(css, /prefers-reduced-motion:reduce.*animation:none/);
  assert.match(css, /button:focus-visible/);
  assert.match(css, /data-loading=true.*visibility:hidden;pointer-events:none/);
  assert.match(css, /position:absolute;inset:0;z-index:20/);
  assert.match(css, /loading-mark img\{width:20px;height:30px/);
  assert.equal(f.cover.attributes['aria-live'], 'polite');
  f.disposers.reverse().forEach(dispose => dispose?.());
  assert.equal(state.count(), 0); assert.equal(f.list.count(), 0); assert.equal(f.cover.hidden, true);
});
