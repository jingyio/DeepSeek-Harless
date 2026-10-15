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
function fixture(fetcher, initial = comparison(), { streaming = false, sessions = {}, anchorSeq } = {}) {
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
  const window = { crypto: webcrypto, addEventListener: listener, removeEventListener: unlisten,
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
  const render = () => { cursor = 0; tree = Component({ node }); const pending = effects; effects = []; pending.forEach(fn => fn()); return tree; };
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
  const pane = f.all(row => row.type === 'section' && row.props['aria-label'] === 'Motif · DSH')[0];
  assert.match(f.content(pane), /回复完成/); assert.match(f.content(pane), /没有可下载成品/);
  assert.equal(f.all(row => row.type === 'a' && row.props.download, pane).length, 0);
  assert.equal(f.all(row => row.type === f.MarkdownText, pane)[0].props.fileMentions.resolve(artifact.name), undefined); f.dispose();
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
  assert.match(f.content(f.all(row=>row.props.className==='harless-activity')[0]),/正在读取数据/);
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


test('completed paired and single turns branch at their own anchor without local title overrides', async () => {
  for (const single of [false, true]) {
    const value = comparison(); if (single) { value.presentation = 'single'; delete value.lanes.motif; }
    const calls = [], opened = []; let finish;
    const f = fixture(undefined, value, { anchorSeq: 17, sessions: {
      fork: options => { calls.push(options); return new Promise(resolve => { finish = resolve; }); },
      open: id => opened.push(id),
    } });
    await flush(); f.render();
    const button = f.all(row => row.props['aria-label'] === '在新对话中分支')[0]; assert.ok(button);
    const operation = button.props.onClick(); button.props.onClick();
    assert.equal(calls.length, 1); assert.equal(calls[0].sessionId, 'session-a');
    assert.equal(calls[0].atSeq, 17); assert.equal(calls[0].increaseTitle, false);
    finish('branch-1'); await operation; assert.deepEqual(opened, ['branch-1']); f.dispose();
  }
});
