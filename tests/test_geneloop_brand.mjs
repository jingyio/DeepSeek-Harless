import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createHash } from 'node:crypto';
import vm from 'node:vm';
import { createGateway } from '../scripts/harless_gateway.mjs';

test('GeneLoop uses public brand slots without replacing provider or conversation content', () => {
  const records = [], head = [], effects = [], oldIcon = { remove() { this.removed = true; } };
  const legacyLink = { remove() { this.removed = true; } };
  const document = { title: '当前会话 · DeepSeek Harness', head: { append: node => head.push(node) },
    querySelectorAll: selector => selector === 'link[rel~="icon"]' ? [oldIcon]
      : selector === 'body > a[href="/paper-revision"]' ? [legacyLink] : [], createElement: tag => ({ tag }) };
  let observe;
  const window = {};
  vm.runInNewContext(readFileSync(new URL('../src/adapters/geneloop_brand.js', import.meta.url), 'utf8'), {
    window, document, MutationObserver: class { constructor(fn) { observe = fn; } observe() {} },
  });
  const ctx = { slots: { inject(_name, fn) { const output = fn(); if (output?.next) [...output]; },
    register(options, component) { records.push({ options, component }); } } };
  const React = { createElement: (type, props, ...children) => ({ type, props, children }),
    useLayoutEffect: effect => effects.push(effect) };
  window.__installGeneLoopBrand(ctx, React);
  window.__installGeneLoopBrand(ctx, React);
  assert.equal(records.length, 6);
  assert.deepEqual(records.map(row => row.options.name), ['sidebar.brand.mark', 'sidebar.brand.name', 'conversation.hero.brand.mark',
    'conversation.hero.agentPreset', 'conversation.session.header.actions', 'settings.onboarding']);
  assert.ok(records.every(row => row.options.priority < 0));
  const mark = records[0].component({ size: 24 });
  assert.equal(mark.props['aria-label'], 'GeneLoop');
  assert.equal(mark.props.style.width, 24); assert.equal(mark.props.style.height, 24);
  assert.equal(mark.props.style.background, undefined, 'transparent mark has no white disc');
  assert.equal(mark.children[0].props.src, '/assets/geneloop-spiral.svg?v=1');
  assert.equal(mark.children[0].props.style.objectFit, 'contain', 'ribbon is not cropped');
  assert.equal(records[1].component().children[0], 'GeneLoop');
  assert.equal(document.title, '当前会话 · GeneLoop');
  document.title = 'DeepSeek Flash 模型测试'; observe();
  assert.equal(document.title, 'DeepSeek Flash 模型测试');
  assert.equal(oldIcon.removed, true);
  assert.equal(head[0].href, '/assets/geneloop-spiral.svg?v=1');
  assert.equal(head[0].type, 'image/svg+xml');
  assert.equal(legacyLink.removed, true);
  assert.equal(head[1].textContent, 'body > a[href="/paper-revision"]{display:none!important}');

  const preset = records.find(row => row.options.name === 'conversation.hero.agentPreset');
  const header = records.find(row => row.options.name === 'conversation.session.header.actions');
  assert.equal(preset.component(), null);
  assert.equal(header.options.id, 'agent-preset'); assert.equal(header.component(), null);
  const onboarding = records.filter(row => row.options.name === 'settings.onboarding');
  assert.equal(onboarding.length, 1);
  assert.equal(onboarding[0].options.id, 'welcome-notice');
  let completed = 0;
  assert.equal(onboarding[0].component({ complete() { completed++; } }), null);
  assert.equal(completed, 0, 'onboarding state is not changed during render');
  effects.forEach(effect => effect());
  assert.equal(completed, 1, 'the coordinator advances without a modal or settings write');
});

test('legacy paper entry cleanup waits for parsed body and does not select conversation links', () => {
  const removed = [], queries = [], events = [], nodes = [];
  const document = { title: 'GeneLoop', readyState: 'loading', head: { append: node => nodes.push(node) },
    createElement: tag => ({ tag }), addEventListener: (...args) => events.push(args),
    querySelectorAll(selector) {
      queries.push(selector);
      return selector === 'body > a[href="/paper-revision"]' ? [{ remove: () => removed.push('legacy') }] : [];
    } };
  vm.runInNewContext(readFileSync(new URL('../src/adapters/geneloop_brand.js', import.meta.url), 'utf8'), {
    window: {}, document, MutationObserver: class { observe() {} },
  });
  assert.deepEqual(removed, []);
  assert.equal(events.length, 1); assert.equal(events[0][0], 'DOMContentLoaded');
  assert.equal(events[0][2].once, true);
  events[0][1]();
  assert.deepEqual(removed, ['legacy']);
  assert.ok(queries.every(selector => ['link[rel~="icon"]', 'body > a[href="/paper-revision"]'].includes(selector)));
});

test('transparent spiral logo is public and static while account data stays protected', async t => {
  const directory = mkdtempSync(join(tmpdir(), 'geneloop-brand-'));
  const accountHtml = new URL('../src/adapters/harless_account.html', import.meta.url);
  const gateway = createGateway({ dataDir: directory, publicOrigin: 'https://app.example.test', accountHtml });
  t.after(() => { gateway.close(); rmSync(directory, { force: true, recursive: true }); });
  gateway.server.listen(0, '127.0.0.1'); await once(gateway.server, 'listening');
  const url = `http://127.0.0.1:${gateway.server.address().port}`;
  const spiral = await fetch(url + '/assets/geneloop-spiral.svg?v=1');
  assert.equal(spiral.status, 200); assert.equal(spiral.headers.get('content-type'), 'image/svg+xml');
  const svg = await spiral.text();
  assert.equal(svg, readFileSync(new URL('../src/adapters/brand/geneloop-spiral.svg', import.meta.url), 'utf8'));
  assert.match(svg, /<linearGradient/); assert.match(svg, /<path/);
  assert.doesNotMatch(svg, /<text|<script|<foreignObject|<image|<rect|(?:href|onload)=/i,
    'the mark has no words, background, executable content or external dependencies');
  assert.equal((await fetch(url + '/assets/geneloop-spiral.svg', { method: 'POST' })).status, 405);
  const svgHead = await fetch(url + '/assets/geneloop-spiral.svg', { method: 'HEAD' });
  assert.equal(svgHead.status, 200); assert.equal(await svgHead.text(), '');
  // The original supplied file remains unchanged for already cached pages.
  const logo = await fetch(url + '/assets/geneloop.jpg?v=1');
  assert.equal(logo.status, 200); assert.equal(logo.headers.get('content-type'), 'image/jpeg');
  const hash = createHash('sha256').update(Buffer.from(await logo.arrayBuffer())).digest('hex');
  assert.equal(hash, '96dd2571f1881eed9c49f2a7e690f20b65f5ee07468e2788e8e9f1731aa97f3b');
  assert.equal((await fetch(url + '/assets/geneloop.jpg', { method: 'POST' })).status, 405);
  const head = await fetch(url + '/assets/geneloop.jpg', { method: 'HEAD' });
  assert.equal(head.status, 200); assert.equal(await head.text(), '');
  const login = await fetch(url + '/login');
  assert.equal(login.status, 200); assert.match(login.headers.get('content-security-policy'), /img-src 'self' data:/);
  const html = await login.text();
  assert.match(html, /\/assets\/geneloop-spiral\.svg\?v=1/);
  assert.doesNotMatch(html, /geneloop\.jpg|216\.21%|background:#fff;flex:none/);
  assert.match(html, /GeneLoop/); assert.doesNotMatch(html, /DeepSeek Harless|deepseek <|HARNESS|我的对话/);
  const protectedPage = await fetch(url + '/', { redirect: 'manual' });
  assert.equal(protectedPage.status, 303); assert.equal(protectedPage.headers.get('location'), '/login');
});
