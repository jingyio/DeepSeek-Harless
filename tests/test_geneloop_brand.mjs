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
  const records = [], head = [], oldIcon = { remove() { this.removed = true; } };
  const document = { title: '当前会话 · DeepSeek Harness', head: { append: node => head.push(node) },
    querySelectorAll: () => [oldIcon], createElement: tag => ({ tag }) };
  let observe;
  const window = {};
  vm.runInNewContext(readFileSync(new URL('../src/adapters/geneloop_brand.js', import.meta.url), 'utf8'), {
    window, document, MutationObserver: class { constructor(fn) { observe = fn; } observe() {} },
  });
  const ctx = { slots: { inject(_name, fn) { const output = fn(); if (output?.next) [...output]; },
    register(options, component) { records.push({ options, component }); } } };
  const React = { createElement: (type, props, ...children) => ({ type, props, children }) };
  window.__installGeneLoopBrand(ctx, React);
  window.__installGeneLoopBrand(ctx, React);
  assert.equal(records.length, 3);
  assert.deepEqual(records.map(row => row.options.name), ['sidebar.brand.mark', 'sidebar.brand.name', 'conversation.hero.brand.mark']);
  assert.ok(records.every(row => row.options.priority < 0));
  assert.equal(records[0].component({ size: 24 }).props['aria-label'], 'GeneLoop');
  assert.equal(records[1].component().children[0], 'GeneLoop');
  assert.equal(document.title, '当前会话 · GeneLoop');
  document.title = 'DeepSeek Flash 模型测试'; observe();
  assert.equal(document.title, 'DeepSeek Flash 模型测试');
  assert.equal(oldIcon.removed, true);
  assert.equal(head[0].href, '/assets/geneloop.jpg?v=1');
});

test('login logo is public and byte-identical while account data stays protected', async t => {
  const directory = mkdtempSync(join(tmpdir(), 'geneloop-brand-'));
  const accountHtml = new URL('../src/adapters/harless_account.html', import.meta.url);
  const gateway = createGateway({ dataDir: directory, publicOrigin: 'https://app.example.test', accountHtml });
  t.after(() => { gateway.close(); rmSync(directory, { force: true, recursive: true }); });
  gateway.server.listen(0, '127.0.0.1'); await once(gateway.server, 'listening');
  const url = `http://127.0.0.1:${gateway.server.address().port}`;
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
  assert.match(html, /GeneLoop/); assert.doesNotMatch(html, /DeepSeek Harless|deepseek <|HARNESS|我的对话/);
  const protectedPage = await fetch(url + '/', { redirect: 'manual' });
  assert.equal(protectedPage.status, 303); assert.equal(protectedPage.headers.get('location'), '/login');
});
