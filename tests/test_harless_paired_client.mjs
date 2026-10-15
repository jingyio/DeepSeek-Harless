/** No-model browser-component diagnostics; real server/browser acceptance is separate. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { createHash, webcrypto } from 'node:crypto';

const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
const fileBytes = Buffer.from('%PDF-1.7\nfixture');
const artifact = { id: 'file-one', name: 'outputs/report/research_report.pdf', bytes: fileBytes.length,
  sha256: createHash('sha256').update(fileBytes).digest('hex') };
const comparison = () => ({ id: 'comparison-a', session_id: 'session-a', status: 'completed', score_revision: 1,
  scores: { baseline: null, motif: null }, scoring_available: true,
  lanes: Object.fromEntries(['baseline', 'motif'].map(lane => [lane, { status: 'completed', mode: lane === 'baseline' ? 'baseline' : 'execute',
    answer: '**结果**\n\n| 项目 | 值 |\n|---|---|\n| n | 12 |\n\n`/app/work/outputs/report/research_report.pdf`',
    artifacts: [{ ...artifact }], output_sha256: lane + '-hash', stats: { upstream_requests: 2 }, delivery_status: 'available' }])) });
const tick = () => new Promise(resolve => setImmediate(resolve));
async function flush() { for (let i = 0; i < 12; i++) await tick(); }
async function waitUntil(predicate) {
  const deadline = Date.now() + 5000;
  while (!predicate()) {
    assert.ok(Date.now() < deadline, 'async download did not settle within 5 seconds');
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}
function fixture(fetcher, initial = comparison(), { streaming = false, sessions = {}, anchorSeq, traceOnly = false, clipboard } = {}) {
  let plugin, Component, cursor = 0, states = [], effects = [], effectSlots = [], cleanups = [], tree;
  const timers = new Map(), requests = [], downloaded = [], revoked = [], events = new Map(); let timerId = 0;
  const MarkdownText = function NativeMarkdown() {};
  const React = {
    createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat() }),
    useState(initial) { const n = cursor++; if (!(n in states)) states[n] = initial; return [states[n], value => { states[n] = typeof value === 'function' ? value(states[n]) : value; }]; },
    useRef(value) { const n = cursor++; if (!(n in states)) states[n] = { current: value }; return states[n]; },
    useEffect(effect, deps) { const n = cursor++; const old = effectSlots[n]; if (!old || deps.some((value, i) => old[i] !== value)) {
      effectSlots[n] = deps; effects.push(() => { cleanups[n]?.(); cleanups[n] = effect(); }); } },
  };
  const listener = (name, fn) => events.set(name, fn), unlisten = name => events.delete(name);
  const document = { hidden: false, addEventListener: listener, removeEventListener: unlisten,
    body: { appendChild() {} }, createElement: () => ({ click() { downloaded.push({ href: this.href, name: this.download }); }, remove() {} }) };
  const window = { crypto: webcrypto, navigator: { clipboard }, addEventListener: listener, removeEventListener: unlisten,
    __ModuleLoader__: { load(value) { plugin = value; } } };
  const streams = [];
  if (streaming) window.EventSource = class {
    constructor(url, options) { this.url = url; this.options = options; streams.push(this); }
    addEventListener(name, callback) { if (name === 'snapshot') this.snapshot = callback; }
    close() { this.closed = true; }
    emit(value) { this.snapshot({ data: JSON.stringify(value) }); }
  };
  const fetch = async (url, init) => { requests.push({ url, init }); return fetcher ? fetcher(url, init, requests.length) : Response.json(initial); };
  runInNewContext(source, { window, document, fetch, AbortController, Uint8Array,
    URL: { createObjectURL: () => 'blob:verified-file', revokeObjectURL: value => revoked.push(value) },
    setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout: id => timers.delete(id) });
  const blocks = new Map();
  plugin.factory(name => name === 'react' ? React : name === '@deepseek-ai/dsh-client-ui-primitives' ? { MarkdownText } : undefined).apply({
    get: name => ({ commandUi: { decorate: () => () => {} }, inputTriggers: { registerSource: () => () => {} }, sessions,
      conversation: { blocks: { storeFor: id => ({ getSnapshot: () => blocks.get(id) }), set: (id, value) => blocks.set(id, value) } } })[name],
    effect: fn => fn(), uiConversation: { events: { register: () => () => {} } },
    slots: { inject(_name, fn) { fn(); }, register(spec, component) { if (spec.key === 'harless-comparison') Component = component; } },
  });
  const node = { data: initial, anchorSeq };
  const render = () => { cursor = 0; tree = Component({ node, traceOnly }); const pending = effects; effects = []; pending.forEach(fn => fn()); return tree; };
  const all = (predicate, entry = tree) => !entry || typeof entry !== 'object' ? [] :
    [...(predicate(entry) ? [entry] : []), ...(entry.children || []).filter(child => child !== undefined).flatMap(child => all(predicate, child))];
  const content = entry => typeof entry === 'string' ? entry : (entry?.children || []).map(content).join('');
  render();
  return { render, all, content, requests, timers, downloaded, revoked, events, streams, MarkdownText, initial,
    setNodeData: value => { node.data = value; },
    dispose: () => cleanups.forEach(fn => fn?.()) };
}
test('paired answers delegate Markdown and inline artifact mentions to the native safe renderer', async () => {
  const f = fixture(); await flush(); f.render();
  const markdown = f.all(row => row.type === f.MarkdownText); assert.equal(markdown.length, 2);
  assert.match(markdown[0].props.text, /\*\*结果\*\*/);
  assert.equal(markdown[0].props.streaming, false);
  assert.equal(markdown[0].props.fileMentions.resolve('/app/work/outputs/report/research_report.pdf').title, artifact.name);
  assert.equal(markdown[0].props.fileMentions.resolve('/etc/passwd'), undefined);
  const css = f.content(f.all(row => row.type === 'style')[0]);
  assert.doesNotMatch(css, /max-height:70vh|white-space:pre-wrap/);
  assert.match(css, /@container\(max-width:650px\)/);
  assert.equal(f.timers.size, 0, 'completed turns do not poll forever'); f.dispose();
});
test('verified native file labels show the filename without altering Markdown, targets, icons, or custom captions', async () => {
  const value = comparison(), original = value.lanes.baseline.answer;
  const f = fixture(undefined, value); await flush(); f.render();
  const answer = f.all(row => row.props.className === 'harless-paired-answer')[0];
  function rendered(text, { tag = 'button', href, title = artifact.name, pre = false } = {}) {
    const textNode = { nodeType: 3, nodeValue: text }, icon = { nodeType: 1, nodeName: 'svg', childNodes: [] };
    const attrs = { href, title, 'aria-label': '下载 research_report.pdf' }, onClick = () => {};
    const node = { nodeType: 1, nodeName: tag.toUpperCase(), childNodes: [icon, textNode], onClick,
      closest: selector => selector === 'pre' && pre ? {} : null,
      getAttribute: key => attrs[key], setAttribute: (key, next) => { attrs[key] = next; } };
    return { node, textNode, icon, attrs, onClick };
  }
  const absolute = rendered('/app/.local/web/sessions/session-a/work/' + artifact.name);
  const relative = rendered(artifact.name, { tag: 'a', href: 'sandbox:/app/work/' + artifact.name });
  const custom = rendered('下载最终报告', { tag: 'a', href: '/app/work/' + artifact.name });
  const captionWithPath = rendered('下载 /app/work/' + artifact.name, { tag: 'a', href: '/app/work/' + artifact.name });
  const unknown = rendered('/app/work/not-approved.pdf', { title: 'not-approved.pdf' });
  const code = rendered('/app/work/' + artifact.name, { pre: true });
  const external = rendered(artifact.name, { tag: 'a', href: 'https://example.com/' + artifact.name });
  const rows = [absolute, relative, custom, captionWithPath, unknown, code, external];
  answer.props.ref({ querySelectorAll: selector => { assert.equal(selector, 'code > button, a'); return rows.map(row => row.node); } });
  assert.equal(absolute.textNode.nodeValue, 'research_report.pdf'); assert.equal(absolute.attrs.title, 'research_report.pdf');
  assert.equal(relative.textNode.nodeValue, 'research_report.pdf'); assert.equal(relative.attrs.href, 'sandbox:/app/work/' + artifact.name);
  assert.equal(custom.textNode.nodeValue, '下载最终报告'); assert.equal(custom.attrs.href, '/app/work/' + artifact.name);
  assert.equal(captionWithPath.textNode.nodeValue, '下载 /app/work/' + artifact.name);
  assert.equal(unknown.textNode.nodeValue, '/app/work/not-approved.pdf');
  assert.equal(code.textNode.nodeValue, '/app/work/' + artifact.name); assert.equal(external.textNode.nodeValue, artifact.name);
  for (const row of rows) { assert.equal(row.node.childNodes[0], row.icon); assert.equal(row.node.onClick, row.onClick); }
  assert.equal(f.all(row => row.type === f.MarkdownText)[0].props.text, original, 'do not rewrite inline or fenced source code');
  assert.equal(value.lanes.baseline.answer, original);
  f.dispose();
});
test('artifact label adaptation follows stream completion and remains effective after terminal refresh', async () => {
  const running = comparison(); running.status = 'running'; running.snapshot_revision = 0;
  running.lanes.baseline.status = 'running'; running.lanes.baseline.artifacts = [];
  let current = running;
  const f = fixture(url => url.includes('&file=') ? new Response(fileBytes, { headers: { 'content-type': 'application/pdf' } }) : Response.json(current), running, { streaming: true });
  await flush(); f.render();
  const textNode = { nodeType: 3, nodeValue: '/app/.local/web/sessions/session-a/work/' + artifact.name };
  const attrs = { title: artifact.name }, icon = { nodeType: 1, nodeName: 'svg', childNodes: [] };
  const button = { nodeType: 1, nodeName: 'BUTTON', childNodes: [icon, textNode], closest: () => null,
    getAttribute: key => attrs[key], setAttribute: (key, next) => { attrs[key] = next; } };
  const root = { querySelectorAll: () => [button] };
  f.all(row => row.props.className === 'harless-paired-answer')[0].props.ref(root);
  assert.match(textNode.nodeValue, /^\/app\//, 'an unverified streaming path is unchanged');
  current = comparison(); current.snapshot_revision = 1;
  current.lanes.baseline.artifacts.push({ ...artifact, id: 'another-file', name: 'outputs/another/research_report.pdf' });
  f.streams[0].emit(current); f.render();
  f.all(row => row.props.className === 'harless-paired-answer')[0].props.ref(root);
  assert.equal(textNode.nodeValue, 'research_report.pdf'); assert.equal(attrs.title, 'research_report.pdf');
  textNode.nodeValue = '/app/.local/web/sessions/refreshed/work/' + artifact.name;
  current.snapshot_revision = 2; f.events.get('focus')(); await flush(); f.render();
  f.all(row => row.props.className === 'harless-paired-answer')[0].props.ref(root);
  assert.equal(textNode.nodeValue, 'research_report.pdf', 'native text refresh is compacted even when the title was already normalized');
  assert.equal(button.childNodes[0], icon);
  const mention = f.all(row => row.type === f.MarkdownText)[0].props.fileMentions.resolve('/app/work/' + artifact.name);
  mention.open(); await waitUntil(() => f.downloaded.length > 0);
  assert.deepEqual(f.downloaded, [{ href: 'blob:verified-file', name: 'research_report.pdf' }]);
  assert.ok(f.requests.some(row => row.url.endsWith('&lane=baseline&file=file-one') && row.init.credentials === 'same-origin'));
  f.dispose();
});
test('network read failure keeps rendered output and backs off; recovery stops polling completed turns', async () => {
  let reads = 0; const value = comparison();
  const f = fixture(() => { if (++reads < 3) throw TypeError('Failed to fetch'); return Response.json(value); });
  await flush(); f.render();
  assert.equal(f.all(row => row.type === f.MarkdownText)[0].props.text, value.lanes.baseline.answer);
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-connection')[0]), /自动重连/);
  let timer = [...f.timers.values()][0]; assert.equal(timer.delay, 3600); f.timers.clear(); await timer.fn();
  timer = [...f.timers.values()][0]; assert.equal(timer.delay, 7200); f.timers.clear(); await timer.fn(); f.render();
  assert.equal(f.all(row => row.props.className === 'harless-paired-connection').length, 0);
  assert.equal(f.timers.size, 0); assert.ok(f.requests.every(row => row.init.method === 'GET')); f.dispose();
});
test('authentication loss is actionable and does not keep hitting protected endpoints', async () => {
  const f = fixture(() => Response.json({ error: { message: 'unauthorized' } }, { status: 401 }));
  await flush(); f.render();
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-connection')[0]), /登录已过期/);
  assert.equal(f.all(row => row.type === 'a' && row.props.href === '/login').length, 1);
  assert.equal(f.timers.size, 0); f.dispose();
});
test('rating with an uncertain network response is reconciled by GET and never auto-posted twice', async () => {
  const value = comparison(); let posts = 0;
  const f = fixture((_url, init) => {
    if (init.method === 'POST') { posts++; value.scores.baseline = 4; value.score_revision++; throw TypeError('Failed to fetch'); }
    return Response.json(value);
  });
  await flush(); f.render();
  const choice = f.all(row => row.type === 'input' && row.props.name.endsWith('-baseline') && row.props.value === 4)[0];
  await choice.props.onChange(); await flush(); f.render();
  assert.equal(posts, 1); assert.equal(f.all(row => row.type === 'input' && row.props.name.endsWith('-baseline') && row.props.value === 4)[0].props.checked, true);
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-error')[0]), /请勿重复提交/); f.dispose();
});
test('artifact download validates authenticated bytes then triggers an explicit local download', async () => {
  const value = comparison();
  const f = fixture(url => url.includes('&file=') ? new Response(fileBytes, { headers: { 'content-type': 'application/pdf' } }) : Response.json(value));
  await flush(); f.render();
  const link = f.all(row => row.type === 'a' && row.props.download)[0]; link.props.onClick({ preventDefault() {} });
  await waitUntil(() => f.downloaded.length > 0);
  f.render(); assert.deepEqual(f.downloaded, [{ href: 'blob:verified-file', name: 'research_report.pdf' }]);
  assert.match(f.content(f.all(row => row.type === 'small' && row.props.role === 'status')[0]), /浏览器下载/);
  const request = f.requests.find(row => row.url.includes('&file=')); assert.equal(request.init.credentials, 'same-origin'); f.dispose();
});
test('HTML gateway errors or changed file bytes never become successful downloads', async () => {
  for (const response of [new Response('<html>login</html>', { headers: { 'content-type': 'text/html' } }),
    new Response(Buffer.from('%PDF-1.7\nchanged'), { headers: { 'content-type': 'application/pdf' } }),
    Response.json({ error: {} }, { status: 404 })]) {
    const value = comparison(); const f = fixture(url => url.includes('&file=') ? response : Response.json(value));
    await flush(); f.render(); f.all(row => row.type === 'a' && row.props.download)[0].props.onClick({ preventDefault() {} });
    await waitUntil(() => { f.render(); return f.all(row => row.type === 'small' && row.props.role === 'alert').length > 0; });
    assert.equal(f.downloaded.length, 0);
    assert.equal(f.all(row => row.type === 'small' && row.props.role === 'alert').length, 1); f.dispose();
  }
});
test('unknown local markdown links are blocked instead of opening meaningless /app URLs', async () => {
  const f = fixture(); await flush(); f.render(); let prevented = false;
  const answer = f.all(row => row.props.className === 'harless-paired-answer')[0];
  answer.props.onClickCapture({ target: { closest: () => ({ getAttribute: () => '/app/private/draft.pdf' }) },
    preventDefault() { prevented = true; }, stopPropagation() {} });
  f.render(); assert.equal(prevented, true); assert.equal(f.downloaded.length, 0);
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-error')[0]), /尚未登记/); f.dispose();
});
test('completed model text without delivery is visibly distinguished and cannot invent a download', async () => {
  const value = comparison(); value.lanes.motif.artifacts = []; value.lanes.motif.delivery_status = 'not_delivered';
  value.lanes.motif.delivery_message = '本轮未通过交付校验，没有可下载成品。';
  const f = fixture(undefined, value); await flush(); f.render();
  const pane = f.all(row => row.type === 'section' && row.props['aria-label'] === 'Motif')[0];
  assert.match(f.content(pane), /回复完成/); assert.match(f.content(pane), /没有可下载成品/);
  assert.equal(f.all(row => row.type === 'a' && row.props.download, pane).length, 0);
  assert.equal(f.all(row => row.type === f.MarkdownText, pane)[0].props.fileMentions.resolve(artifact.name), undefined); f.dispose();
});
test('an admission failure displays not started with corrective guidance instead of a delivery failure', async () => {
  const value = comparison(); value.status = 'failed'; value.scoring_available = false;
  for (const lane of Object.values(value.lanes)) Object.assign(lane, { status: 'failed', answer: '', artifacts: [], stats: {},
    failure_stage: 'preparation', failure: '请将 TXT/MD 另存为 UTF-8 编码后重新上传。',
    delivery_status: 'not_started', delivery_message: '本轮尚未开始执行，暂无结果文件。' });
  const f = fixture(undefined, value); await flush(); f.render();
  const panes = f.all(row => row.props.className === 'harless-paired-pane'); assert.equal(panes.length, 2);
  for (const pane of panes) {
    assert.match(f.content(pane), /任务未启动/); assert.match(f.content(pane), /UTF-8/);
    assert.doesNotMatch(f.content(pane), /交付校验|另一侧结果已保留/);
    assert.equal(f.all(row => row.type === f.MarkdownText, pane).length, 0);
    assert.equal(f.all(row => row.type === 'a' && row.props.download, pane).length, 0);
  }
  assert.equal(f.timers.size, 0); f.dispose();
});
test('overlapping old GET cannot undo a saved score; followup read still happens', async () => {
  const value = comparison(), old = comparison(); let finishRead, reads = 0;
  const f = fixture((_url, init) => {
    if (init.method === 'POST') { value.scores.baseline = 5; value.score_revision++; return Response.json(value); }
    if (++reads === 2) return new Promise(resolve => { finishRead = () => resolve(Response.json(old)); });
    return Response.json(value);
  });
  await flush(); f.render(); f.events.get('focus')(); await flush();
  await f.all(row => row.type === 'input' && row.props.name.endsWith('-baseline') && row.props.value === 5)[0].props.onChange();
  finishRead(); await flush(); f.render();
  assert.equal(f.all(row => row.type === 'input' && row.props.name.endsWith('-baseline') && row.props.value === 5)[0].props.checked, true);
  const timer = [...f.timers.values()][0]; assert.equal(timer.delay, 0); f.timers.clear(); await timer.fn();
  assert.equal(reads, 3); f.dispose();
});
test('duplicate basenames stay inert while exact approved paths remain downloadable', async () => {
  const value = comparison(); value.lanes.baseline.artifacts.push({ ...artifact, id: 'other', name: 'outputs/other/research_report.pdf' });
  const f = fixture(undefined, value); await flush(); f.render();
  const mentions = f.all(row => row.type === f.MarkdownText)[0].props.fileMentions;
  assert.equal(mentions.resolve('research_report.pdf'), undefined);
  assert.equal(mentions.resolve('/app/work/' + artifact.name).title, artifact.name); f.dispose();
});
test('explicit retry of a settled failed lane restarts polling and stops after the replacement settles', async () => {
  const value = comparison(); value.status = 'failed'; value.lanes.motif.status = 'failed'; value.scoring_available = false;
  const f = fixture((_url, init) => {
    if (init.method === 'POST') { value.status = 'running'; value.lanes.motif.status = 'running'; }
    return Response.json(value);
  }, value);
  await flush(); f.render(); assert.equal(f.timers.size, 0);
  await f.all(row => row.type === 'button' && f.content(row) === '重试此侧')[0].props.onClick(); await flush(); f.render();
  const timer = [...f.timers.values()][0]; assert.equal(timer.delay, 1800);
  value.status = 'completed'; value.lanes.motif.status = 'completed'; f.timers.clear(); await timer.fn(); f.render();
  assert.equal(f.timers.size, 0); assert.equal(f.requests.filter(row => row.init.method === 'POST').length, 1); f.dispose();
});
const waitForAbort = signal => new Promise((_resolve, reject) => {
  if (signal.aborted) reject(signal.reason);
  else signal.addEventListener('abort', () => reject(signal.reason), { once: true });
});
test('reassembled start-event objects cannot roll newer completed results back to a stale snapshot', async () => {
  const initial = comparison(), current = comparison(); initial.status = 'running';
  initial.lanes.motif.status = 'running'; initial.lanes.baseline.artifacts = []; initial.scoring_available = false;
  current.scores.baseline = 5;
  const f = fixture(() => Response.json(current), initial); await flush(); f.render();
  f.setNodeData(structuredClone(initial)); f.render(); f.render();
  assert.equal(f.all(row => row.type === 'a' && row.props.download).length, 2);
  assert.equal(f.all(row => row.type === 'input' && row.props.name.endsWith('-baseline') && row.props.value === 5)[0].props.checked, true);
  assert.equal(f.all(row => row.type === f.MarkdownText)[1].props.streaming, false);
  assert.equal(f.timers.size, 0); f.dispose();
});
test('GET deadline covers stalled response JSON and frees polling for backoff recovery', async () => {
  const f = fixture((_url, init) => ({ ok: true, status: 200, json: () => waitForAbort(init.signal) }));
  await flush(); const deadline = [...f.timers.values()].find(timer => timer.delay === 30000); assert.ok(deadline);
  deadline.fn(); await flush(); f.render();
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-connection')[0]), /连接超时/);
  assert.equal([...f.timers.values()][0].delay, 3600); f.dispose();
});
test('POST deadline reconciles a server-saved rating using GET without another POST', async () => {
  const value = comparison(); let posts = 0;
  const f = fixture((_url, init) => {
    if (init.method === 'POST') {
      posts++; value.scores.baseline = 5; value.score_revision++;
      return { ok: true, status: 200, json: () => waitForAbort(init.signal) };
    }
    return Response.json(value);
  });
  await flush(); f.render();
  const action = f.all(row => row.type === 'input' && row.props.name.endsWith('-baseline') && row.props.value === 5)[0].props.onChange();
  await flush(); [...f.timers.values()].find(timer => timer.delay === 30000).fn(); await action; await flush(); f.render();
  assert.equal(posts, 1); assert.equal(f.all(row => row.type === 'input' && row.props.name.endsWith('-baseline') && row.props.value === 5)[0].props.checked, true);
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-error')[0]), /连接超时.*请勿重复提交/);
  assert.equal(f.all(row => row.type === 'fieldset')[0].props.disabled, false); f.dispose();
});
test('download body timeout gives a retryable error and releases duplicate-download guard', async () => {
  const value = comparison(); let downloads = 0;
  const f = fixture((url, init) => {
    if (!url.includes('&file=')) return Response.json(value);
    if (++downloads === 1) return { ok: true, status: 200, headers: new Headers({ 'content-type': 'application/pdf' }), blob: () => waitForAbort(init.signal) };
    return new Response(fileBytes, { headers: { 'content-type': 'application/pdf' } });
  });
  await flush(); f.render(); f.all(row => row.type === 'a' && row.props.download)[0].props.onClick({ preventDefault() {} });
  await flush(); [...f.timers.values()].find(timer => timer.delay === 60000).fn(); await flush(); f.render();
  assert.equal(f.downloaded.length, 0); assert.match(f.content(f.all(row => row.type === 'small' && row.props.role === 'alert')[0]), /连接超时/);
  f.all(row => row.type === 'a' && row.props.download)[0].props.onClick({ preventDefault() {} });
  await waitUntil(() => f.downloaded.length === 1); assert.equal(downloads, 2); f.dispose();
});
test('unmount aborts a stalled request silently and leaves no retry timer', async () => {
  const f = fixture((_url, init) => ({ ok: true, status: 200, json: () => waitForAbort(init.signal) }));
  await flush(); f.dispose(); await flush(); f.render();
  assert.equal(f.timers.size, 0); assert.equal(f.all(row => row.props.className === 'harless-paired-connection').length, 0);
  assert.equal(f.requests.length, 1);
});


test('single conversation continuation renders one streamed answer without comparison labels or rating', async () => {
  const value=comparison();value.presentation='single';delete value.lanes.motif;value.scoring_available=false;
  const f=fixture(undefined,value);await flush();f.render();
  assert.equal(f.all(row=>row.type===f.MarkdownText).length,1);
  assert.equal(f.all(row=>row.type==='fieldset').length,0);
  assert.equal(f.all(row=>row.type==='strong'&&f.content(row).includes('Baseline')).length,0);
  assert.equal(f.all(row=>row.props.className==='harless-paired-error').length,0);f.dispose();
});

test('live stream renders incremental text and real activity before terminal completion', async () => {
  const value=comparison();value.status='running';value.scoring_available=false;
  for(const row of Object.values(value.lanes)){row.status='running';row.answer='';row.artifacts=[];}
  const f=fixture(undefined,value,{streaming:true});await flush();f.render();
  const stream=f.streams[0];assert.match(stream.url,/stream=1/);assert.equal(stream.options.withCredentials,true);stream.onopen();
  const partial=structuredClone(value);partial.lanes.baseline.answer='正在分析第一';
  partial.lanes.baseline.progress={label:'正在读取数据',status:'running'};
  partial.lanes.baseline.activity=[{label:'读取数据',status:'running'}];stream.emit(partial);f.render();
  assert.equal(f.all(row=>row.type===f.MarkdownText)[0].props.text,'正在分析第一');
  assert.equal(f.all(row=>row.type===f.MarkdownText)[0].props.streaming,true);
  assert.match(f.content(f.all(row=>row.props.className==='harless-live-status')[0]),/正在读取数据/);
  assert.equal(f.all(row=>row.props.className==='harless-activity')[0].props.open,undefined,'tool details remain collapsed');
  partial.lanes.baseline.answer+='组数据';stream.emit(partial);f.render();
  assert.equal(f.all(row=>row.type===f.MarkdownText)[0].props.text,'正在分析第一组数据');
  stream.emit(comparison());f.render();assert.equal(stream.closed,true);
  assert.equal(f.all(row=>row.type===f.MarkdownText)[0].props.streaming,false);f.dispose();
});

test('a stale initial GET cannot replace newer streaming text; unmount closes the stream', async () => {
  let resolve;const blocked=new Promise(r=>resolve=r),value=comparison();value.status='running';
  for(const row of Object.values(value.lanes))row.status='running';
  const f=fixture(()=>blocked,value,{streaming:true}),stream=f.streams[0];stream.onopen();
  const partial=structuredClone(value);partial.lanes.baseline.answer='新的流式片段';stream.emit(partial);f.render();
  resolve(Response.json(value));await flush();f.render();
  assert.equal(f.all(row=>row.type===f.MarkdownText)[0].props.text,'新的流式片段');
  f.dispose();assert.equal(stream.closed,true);assert.equal(f.timers.size,0);
});

test('a streamed result for another conversation is rejected and never shown', async () => {
  const value=comparison();value.status='running';for(const row of Object.values(value.lanes))row.status='running';
  const f=fixture(undefined,value,{streaming:true});await flush();const foreign=structuredClone(value);foreign.session_id='another-user';foreign.lanes.baseline.answer='foreign secret';
  f.streams[0].emit(foreign);await flush();f.render();
  assert.equal(f.streams[0].closed,true);assert.ok(f.all(row=>row.type===f.MarkdownText).every(row=>!row.props.text.includes('foreign secret')));f.dispose();
});


test('old stream snapshots cannot replace newer retry output or close the active stream', async () => {
  const value=comparison();value.status='running';value.snapshot_revision=10;
  for(const row of Object.values(value.lanes))row.status='running';
  const f=fixture(undefined,value,{streaming:true});await flush();f.render();const stream=f.streams[0];stream.onopen();
  const next=structuredClone(value);next.snapshot_revision=12;next.lanes.baseline.answer='新尝试的流式回复';next.lanes.baseline.attempt=1;
  stream.emit(next);f.render();
  const stale=structuredClone(value);stale.snapshot_revision=11;stale.status='failed';stale.lanes.baseline.answer='旧尝试失败';
  stream.emit(stale);f.render();
  assert.equal(f.all(row=>row.type===f.MarkdownText)[0].props.text,'新尝试的流式回复');assert.notEqual(stream.closed,true);
  f.dispose();
});

test('an open but buffered stream keeps polling real incremental output before completion', async () => {
  const initial = comparison(); initial.status = 'running'; initial.snapshot_revision = 1;
  for (const lane of Object.values(initial.lanes)) { lane.status = 'queued'; lane.answer = ''; }
  let finishRead, current = structuredClone(initial);
  const f = fixture((_url, _init, n) => n === 1 ? new Promise(resolve => { finishRead = resolve; }) : Response.json(current), initial, { streaming: true });
  f.streams[0].onopen();
  finishRead(Response.json(initial)); await flush(); f.render();
  const poll = [...f.timers.entries()].find(([, timer]) => timer.delay === 1800);
  assert.ok(poll, 'onopen alone must not suppress the GET recovery path');
  current.snapshot_revision = 2; current.lanes.baseline.status = 'running'; current.lanes.baseline.answer = '真实第一段';
  f.timers.delete(poll[0]); await poll[1].fn(); await flush(); f.render();
  assert.equal(f.all(row => row.type === f.MarkdownText)[0].props.text, '真实第一段');
  assert.equal(f.all(row => row.type === f.MarkdownText)[0].props.streaming, true);
  assert.ok(f.requests.every(row => row.init.method === 'GET'));
  f.dispose(); assert.equal(f.timers.size, 0);
});

test('stream liveness has a read-only watchdog and ignores callbacks from a retired connection', async () => {
  let current = comparison(); current.status = 'running'; current.snapshot_revision = 10;
  for (const lane of Object.values(current.lanes)) { lane.status = 'running'; lane.answer = ''; }
  const f = fixture(() => Response.json(current), current, { streaming: true }); await flush(); f.render();
  const old = f.streams[0]; old.onopen();
  const partial = structuredClone(current); partial.snapshot_revision = 11; partial.lanes.baseline.answer = '第一段';
  old.emit(partial); f.render();
  // A native projection may rebuild the same persisted start node at any time.
  f.setNodeData(structuredClone(current)); f.render(); assert.equal(f.streams.length, 1);
  f.events.get('focus')(); await flush(); f.render();
  assert.ok([...f.timers.values()].some(timer => timer.delay === 5000));
  current = structuredClone(partial); current.snapshot_revision = 12; current.lanes.baseline.answer += '，第二段';
  const watchdog = [...f.timers.entries()].find(([, timer]) => timer.delay === 10000);
  f.timers.delete(watchdog[0]); watchdog[1].fn(); await flush(); f.render();
  assert.equal(old.closed, true); assert.equal(f.all(row => row.type === f.MarkdownText)[0].props.text, '第一段，第二段');
  const reconnect = [...f.timers.entries()].find(([, timer]) => timer.delay === 2000);
  f.timers.delete(reconnect[0]); reconnect[1].fn(); assert.equal(f.streams.length, 2);
  const late = structuredClone(current); late.snapshot_revision = 99; late.lanes.baseline.answer = 'retired connection';
  old.emit(late); old.onerror(); f.render();
  assert.equal(f.all(row => row.type === f.MarkdownText)[0].props.text, '第一段，第二段');
  const done = comparison(); done.snapshot_revision = 13; current = done;
  f.streams[1].emit(done); f.render();
  assert.equal(f.streams[1].closed, true); assert.ok(f.requests.every(row => row.init.method === 'GET'));
  f.dispose(); assert.equal(f.timers.size, 0);
});

test('loss of access closes an existing stream and its recovery timers', async () => {
  const current = comparison(); current.status = 'running'; current.snapshot_revision = 1;
  let denied = false;
  const f = fixture(() => denied ? Response.json({ error: {} }, { status: 404 }) : Response.json(current), current, { streaming: true });
  await flush(); f.render(); f.streams[0].onopen(); f.streams[0].emit(current); f.render();
  denied = true; f.events.get('focus')(); await flush(); f.render();
  assert.equal(f.streams[0].closed, true); assert.equal(f.timers.size, 0);
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-connection')[0]), /不存在/);
  f.dispose();
});

test('switching conversations closes the old stream before accepting the new session snapshot', async () => {
  let current = comparison(); current.status = 'running'; current.snapshot_revision = 10;
  const f = fixture(() => Response.json(current), current, { streaming: true }); await flush(); f.render();
  const old = f.streams[0]; old.onopen(); old.emit(current); f.render();
  current = comparison(); current.id = 'comparison-b'; current.session_id = 'session-b'; current.status = 'running'; current.snapshot_revision = 1;
  current.lanes.baseline.answer = '第二个会话';
  f.setNodeData(current); f.render(); assert.equal(old.closed, true);
  const late = comparison(); late.snapshot_revision = 999; late.lanes.baseline.answer = '旧会话迟到内容';
  old.emit(late); await flush(); f.render();
  assert.equal(f.all(row => row.type === f.MarkdownText)[0].props.text, '第二个会话');
  assert.match(f.streams[1].url, /session-b/); f.dispose(); assert.equal(f.timers.size, 0);
});


test('completed paired and single turns branch from a selected lane and immutable output once', async () => {
  for (const single of [false, true]) {
    const value = comparison(); if (single) { value.presentation = 'single'; delete value.lanes.motif; }
    const calls = [], opened = []; let finish;
    const f = fixture((_url, init) => {
      if(init.method !== 'POST') return Response.json(value);
      calls.push(JSON.parse(init.body)); return new Promise(resolve => { finish = () => resolve(Response.json({sessionId:'branch-1'})); });
    }, value, { anchorSeq: 17, sessions: { open: id => opened.push(id) } });
    await flush(); f.render();
    const button = f.all(row => row.props['aria-label'] === '从 Baseline 在新对话中分支')[0]; assert.ok(button);
    assert.equal(f.all(row => row.type==='button' && f.content(row)==='在新对话中分支').length,0,'no duplicate large text button');
    const operation = button.props.onClick(); button.props.onClick();
    assert.equal(calls.length, 1); assert.equal(calls[0].session_id, 'session-a');
    assert.equal(calls[0].id,'comparison-a');assert.equal(calls[0].lane,'baseline');assert.equal(calls[0].output_sha256,'baseline-hash');
    assert.equal(calls[0].action,'fork');assert.equal(calls[0].title,undefined);
    finish(); await operation; assert.deepEqual(opened, ['branch-1']); f.dispose();
  }
});

test('successive real assistant messages stay visible during tools and collapse only after the final answer', async () => {
  const value=comparison();value.status='running';value.snapshot_revision=1;
  const row=value.lanes.baseline;row.status='running';row.answer='先读取资料';row.messages=[{id:'first',text:'先读取资料',status:'completed'}];
  const f=fixture(undefined,value,{streaming:true});await flush();f.render();
  const next=structuredClone(value);next.snapshot_revision=2;next.lanes.baseline.answer='已经核验，正在';
  next.lanes.baseline.messages.push({id:'second',text:'已经核验，正在',status:'streaming'});
  next.lanes.baseline.progress={label:'正在调用数据分析工具'};f.streams[0].emit(next);f.render();
  const old=f.all(row=>row.props.className==='harless-stream-messages')[0];assert.ok(old);
  assert.equal(f.all(row=>row.type===f.MarkdownText,old)[0].props.text,'先读取资料');
  assert.equal(f.all(row=>row.props.className==='harless-paired-answer')[0].children[0].props.text,'已经核验，正在');
  assert.match(f.content(f.all(row=>row.props.className==='harless-live-status')[0]),/分析工具/);
  next.status='completed';next.snapshot_revision=3;next.lanes.baseline.status='completed';next.lanes.baseline.answer='完整结论';
  next.lanes.baseline.messages.push({id:'final',text:'完整结论',status:'completed'});f.streams[0].emit(next);f.render();
  assert.equal(f.all(row=>row.props.className==='harless-stream-messages').length,0);
  assert.equal(f.all(row=>row.props.className==='harless-paired-answer')[0].children[0].props.text,'完整结论');
  assert.equal(f.all(row=>row.props.className==='harless-activity')[0].props.open,undefined);f.dispose();
});

test('lane footer copies full Markdown, reports actual usage and duration, and persists reversible feedback', async () => {
  const value=comparison(),copied=[];value.lanes.baseline.stats={upstream_requests:2,prompt_tokens:1024,completion_tokens:500};
  value.lanes.baseline.duration_ms=64500;
  const f=fixture((_url,init)=>{
    if(init.method==='POST'){const body=JSON.parse(init.body);assert.equal(body.action,'feedback');assert.equal(body.output_sha256,'baseline-hash');value.lanes[body.lane].feedback=body.vote;}
    return Response.json(value);
  },value,{clipboard:{writeText:async text=>copied.push(text)}});await flush();f.render();
  await f.all(row=>row.props['aria-label']==='复制 Baseline 回复')[0].props.onClick();f.render();
  assert.deepEqual(copied,[value.lanes.baseline.answer]);assert.ok(f.all(row=>row.props['aria-label']==='用量 1.5k tok').length);
  assert.ok(f.all(row=>row.props['aria-label']==='耗时 1 分 4 秒').length);
  await f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props.onClick();await flush();f.render();
  assert.equal(f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props['aria-pressed'],true);
  await f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props.onClick();await flush();f.render();
  assert.equal(f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props['aria-pressed'],false);
  assert.equal(f.requests.filter(row=>row.init.method==='POST').length,2);f.dispose();
});

test('trajectory tabs use each lane actual events and distinguish verified optimization from shadow candidates', async () => {
  const value=comparison();value.lanes.baseline.trace=[{id:'base',kind:'tool',label:'读取数据',status:'completed'}];
  value.lanes.motif.mode='shadow';value.lanes.motif.trace=[{id:'shadow',kind:'motif',label:'预测候选',status:'completed',optimized:false,verified_skip:false}];
  const f=fixture(undefined,value,{traceOnly:true});await flush();f.render();
  const tabs=f.all(row=>row.props.role==='tab');assert.equal(f.content(tabs[1]),'Motif · 影子评估');
  assert.equal(tabs[0].props.tabIndex,0);assert.equal(tabs[1].props.tabIndex,-1);
  const rows=()=>{const component=f.all(row=>typeof row.type==='function'&&row.type.name==='TraceRows')[0];return component.type(component.props);};
  assert.match(f.content(rows()),/读取数据/);
  f.all(row=>row.props.role==='tablist')[0].props.onKeyDown({key:'ArrowRight',preventDefault(){}});f.render();
  assert.equal(f.all(row=>row.props.role==='tab')[1].props['aria-selected'],true);
  assert.match(f.content(rows()),/预测候选/);assert.doesNotMatch(f.content(rows()),/已应用优化|已验证跳过/);
  value.lanes.motif.trace=[{id:'verified',kind:'motif',label:'执行已认证节点',status:'completed',optimized:true,verified_skip:true}];
  f.events.get('focus')();await flush();f.render();
  const tree=rows();assert.match(f.content(tree),/已验证跳过模型请求/);assert.equal(f.all(row=>row.props['data-optimized']==='true',tree).length,1);
  f.dispose();
});

test('completed process messages retain verified artifact routing without repeating the unbound final template',async()=>{
  const value=comparison();value.lanes.baseline.answer='结果 {{estimate}}';value.lanes.baseline.answer_display='结果 1.25';
  value.lanes.baseline.messages=[{id:'prior',text:'先查看 `/app/work/outputs/report/research_report.pdf`',status:'completed'},
    {id:'final',text:'结果 {{estimate}}',status:'completed'}];
  const f=fixture(undefined,value);await flush();f.render();
  const process=f.all(row=>row.props.className==='harless-process-message')[0];assert.equal(typeof process.props.ref,'function');
  let prevented=false;process.props.onClickCapture({target:{closest:()=>({getAttribute:()=>'/private/not-approved.pdf'})},
    preventDefault(){prevented=true;},stopPropagation(){}});assert.equal(prevented,true);
  const texts=f.all(row=>row.type===f.MarkdownText).map(row=>row.props.text);assert.ok(texts.includes('结果 1.25'));
  assert.equal(texts.some(text=>text.includes('{{estimate}}')),false);assert.equal(f.all(row=>row.type===f.MarkdownText,process)[0].props.fileMentions.resolve('/app/work/'+artifact.name).title,artifact.name);
  f.dispose();
});
