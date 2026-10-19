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
function fixture(fetcher, initial = comparison(), { streaming = false, sessions = {}, anchorSeq, traceOnly = false, clipboard, location, chatSnapshot } = {}) {
  let plugin, Component, cursor = 0, states = [], effects = [], effectSlots = [], cleanups = [], tree;
  const timers = new Map(), requests = [], downloaded = [], revoked = [], events = new Map(), listeners = new Map(); let timerId = 0;
  const positioning = [], dismissals = [], clipboardWrites = [], mountedChildren = new Set();
  const MarkdownText = function NativeMarkdown() {};
  const React = {
    createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat() }),
    useState(initial) { const n = cursor++, bucket = states; if (!(n in bucket)) bucket[n] = initial;
      return [bucket[n], value => { bucket[n] = typeof value === 'function' ? value(bucket[n]) : value; }]; },
    useRef(value) { const n = cursor++; if (!(n in states)) states[n] = { current: value }; return states[n]; },
    useEffect(effect, deps) { const n = cursor++; const old = effectSlots[n]; if (!old || deps.some((value, i) => old[i] !== value)) {
      effectSlots[n] = deps; effects.push(() => { cleanups[n]?.(); cleanups[n] = effect(); }); } },
    useLayoutEffect(effect, deps) { this.useEffect(effect, deps); },
  };
  const listener = (name, fn) => {
    if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn);
    events.set(name, event => { for (const callback of [...listeners.get(name) || []]) callback(event); });
  };
  const unlisten = (name, fn) => { listeners.get(name)?.delete(fn); if (!listeners.get(name)?.size) events.delete(name); };
  const document = { hidden: false, addEventListener: listener, removeEventListener: unlisten,
    body: { appendChild() {} }, createElement: () => ({ click() { downloaded.push({ href: this.href, name: this.download }); }, remove() {} }) };
  const window = { crypto: webcrypto, location: { href: 'https://geneloop.example/' }, navigator: { clipboard }, addEventListener: listener, removeEventListener: unlisten,
    __ModuleLoader__: { load(value) { plugin = value; } } };
  const primitives = {
    MarkdownText, Tooltip: function NativeTooltip() {},
    FileTypeIcon: function NativeFileTypeIcon() {},
    fileExtension: name => name.split('.').slice(1).pop()?.toLowerCase() || '',
    fileSizeText: bytes => bytes + ' bytes',
    ...Object.fromEntries(['CopyOutline', 'CheckOutline', 'LikeOutline', 'LikeFill', 'DislikeOutline', 'DislikeFill', 'BranchOutline', 'DatabaseOutline', 'ClockOutline', 'DownloadOutline']
      .map(name => ['Icon' + name + '16', function NativeIcon() {}])),
    writeClipboard: async text => { clipboardWrites.push(text); if (!clipboard?.writeText) return false;
      try { await clipboard.writeText(text); return true; } catch { return false; } },
    useAnchoredPosition: options => { positioning.push(options); return options.open ? { left: 12, top: 24 } : null; },
    useDismissOnOutsidePointer: (rootRef, open, setOpen, panelRef) => {
      dismissals.push({ rootRef, open, panelRef });
      React.useEffect(() => {
        if (!open) return;
        const close = event => { if (!rootRef.current?.contains(event.target) && !panelRef.current?.contains(event.target)) setOpen(false); };
        document.addEventListener('pointerdown', close);
        return () => document.removeEventListener('pointerdown', close);
      }, [rootRef, open, setOpen, panelRef]);
    },
  };
  const ReactDOM = { createPortal: (child, target) => ({ type: 'portal', props: { target }, children: [child] }) };
  const openedPreviews = [];
  const streams = [];
  if (streaming) window.EventSource = class {
    constructor(url, options) { this.url = url; this.options = options; streams.push(this); }
    addEventListener(name, callback) { if (name === 'snapshot') this.snapshot = callback; }
    close() { this.closed = true; }
    emit(value) { this.snapshot({ data: JSON.stringify(value) }); }
  };
  const fetch = async (url, init) => { requests.push({ url, init }); return fetcher ? fetcher(url, init, requests.length) : Response.json(initial); };
  runInNewContext(source, { window, document, fetch, AbortController, Uint8Array,
    URL: class extends URL { static createObjectURL() { return 'blob:verified-file'; } static revokeObjectURL(value) { revoked.push(value); } },
    setTimeout: (fn, delay) => { const id = ++timerId; timers.set(id, { fn, delay }); return id; }, clearTimeout: id => timers.delete(id) });
  const blocks = new Map();
  plugin.factory(name => name === 'react' ? React : name === 'react-dom' ? ReactDOM : name === '@deepseek-ai/dsh-client-ui-primitives' ? primitives : undefined).apply({
    get: name => ({ commandUi: { decorate: () => () => {} }, inputTriggers: { registerSource: () => () => {} }, sessions,
      conversation: { blocks: { storeFor: id => ({ getSnapshot: () => blocks.get(id) }), set: (id, value) => blocks.set(id, value) } },
      sidebarRight: { openResource: address => openedPreviews.push(address) } })[name],
    effect: fn => fn(), uiConversation: { events: { register: () => () => {} } },
    slots: { inject(_name, fn) { fn(); }, register(spec, component) { if (spec.key === 'harless-comparison') Component = component; } },
  });
  const node = { data: initial, anchorSeq, location };
  const render = () => { cursor = 0; tree = Component({ node, traceOnly, ...(chatSnapshot === undefined ? {} : { useChat: select => select(chatSnapshot) }) });
    const pending = effects; effects = []; pending.forEach(fn => fn()); return tree; };
  const all = (predicate, entry = tree) => !entry || typeof entry !== 'object' ? [] :
    [...(predicate(entry) ? [entry] : []), ...(entry.children || []).filter(child => child !== undefined).flatMap(child => all(predicate, child))];
  const content = entry => typeof entry === 'string' ? entry : (entry?.children || []).map(content).join('');
  // Render a hook-bearing public child in its own seat, so opening a metric
  // cannot accidentally write the parent ComparisonNode's hook state.
  const mount = entry => {
    const seat = { cursor: 0, states: [], effects: [], effectSlots: [], cleanups: [], tree: undefined };
    const child = { render() {
      const parent = { cursor, states, effects, effectSlots, cleanups };
      ({ states, effects, effectSlots, cleanups } = seat); cursor = 0;
      try {
        seat.tree = entry.type(entry.props); const pending = effects; effects = []; pending.forEach(fn => fn()); return seat.tree;
      } finally {
        Object.assign(seat, { cursor, states, effects, effectSlots, cleanups });
        ({ cursor, states, effects, effectSlots, cleanups } = parent);
      }
    }, all: predicate => all(predicate, seat.tree), content: () => content(seat.tree),
    dispose() { seat.cleanups.forEach(fn => fn?.()); mountedChildren.delete(child); } };
    mountedChildren.add(child); child.render(); return child;
  };
  render();
  return { render, all, content, requests, timers, downloaded, revoked, events, streams, MarkdownText, primitives, initial,
    mount, positioning, dismissals, clipboardWrites, document, openedPreviews,
    isMarkdown: row => row.type === MarkdownText || row.type?.name === 'BufferedMarkdown',
    setChatSnapshot: value => { chatSnapshot = value; }, setNodeLocation: value => { node.location = value; },
    setNodeData: value => { node.data = value; },
    remount: (value = initial) => {
      cleanups.forEach(fn => fn?.()); states = []; effects = []; effectSlots = []; cleanups = [];
      node.data = value; return render();
    }, blocks,
    dispose: () => { for (const child of mountedChildren) child.dispose(); cleanups.forEach(fn => fn?.()); } };
}

test('cold history renders no output frame until an authoritative snapshot arrives', async () => {
  const initial = comparison(); initial.status = 'running'; initial.scoring_available = false; initial.snapshot_revision = 1;
  for (const lane of Object.values(initial.lanes)) { lane.status = 'queued'; lane.answer = ''; lane.artifacts = []; }
  let finish;
  const f = fixture(() => new Promise(resolve => { finish = resolve; }), initial);
  assert.equal(f.render(), null);
  assert.doesNotMatch(f.content(f.render()), /等待执行|等待当前任务|停止生成/);
  assert.equal(f.blocks.size, 0, 'historical submission data does not block the composer');
  const done = comparison(); done.snapshot_revision = 8; finish(Response.json(done)); await flush(); f.render();
  assert.equal(f.all(row => f.isMarkdown(row)).length, 2);
  assert.equal(f.all(row => row.props.className === 'harless-paired-loading').length, 0);
  assert.equal(f.all(row => row.type === 'button' && f.content(row) === '停止生成').length, 0); f.dispose();
});

test('new Paper Execute results use verified reuse labels while historic Shadow and fallback remain truthful', async () => {
  for(const [mode,fallback] of [['execute',undefined],['shadow',undefined],['baseline','runtime_bundle_certification_invalid']]){
    const value=comparison();value.scene='paper-proofreading';
    Object.assign(value.lanes.motif,{mode,fallback_reason:fallback,
      stats:{upstream_requests:2,verified_skips:mode==='execute'?1:0,shadow_candidates:mode==='shadow'?3:0}});
    const f=fixture(undefined,value);try{
      await flush();const tree=f.render();
      const titles=f.all(row=>row.type==='strong').map(row=>f.content(row));
      assert.ok(titles.includes(mode==='shadow'?'Motif · 影子评估':'Motif'));
      const text=f.content(tree);
      if(mode==='shadow'){
        assert.match(text,/预测候选 3/);assert.doesNotMatch(text,/已验证跳过 3/);
      }else{
        assert.doesNotMatch(text,/影子评估|预测候选/);
        assert.match(text,new RegExp('已验证跳过 '+(mode==='execute'?1:0)));
      }
      if(fallback)assert.match(text,/优化未启用，已回退普通模式/);
    }finally{f.dispose();}
  }
});

test('missing bound sources is explained as ordinary execution, not a task error or optimization success', async () => {
  const value = comparison(); value.lanes.motif.fallback_reason = 'rsi_requires_approved_sources';
  value.lanes.motif.stats.verified_skips = 0;
  const f = fixture(undefined, value); await flush();
  const text = f.content(f.render());
  assert.match(text, /本轮未绑定可复用的资料，按标准流程回答/);
  assert.doesNotMatch(text, /rsi_requires_approved_sources|优化未启用/);
  assert.equal(f.all(row => row.props.role === 'alert').length, 0);
  assert.match(text, /已验证跳过 0/); f.dispose();
});

test('returning to completed comparison reuses verified results while the new GET is pending or older', async () => {
  const initial = comparison(); initial.status = 'running'; initial.scoring_available = false; initial.snapshot_revision = 1;
  for (const lane of Object.values(initial.lanes)) { lane.status = 'queued'; lane.answer = ''; lane.artifacts = []; }
  const done = comparison(); done.snapshot_revision = 8; done.lanes.motif.feedback = 'up';
  let finish, reads = 0;
  const f = fixture(() => ++reads === 1 ? Response.json(done) : new Promise(resolve => { finish = resolve; }), initial, { streaming: true });
  await flush(); f.render(); f.remount(structuredClone(initial));
  assert.equal(f.all(row => f.isMarkdown(row)).length, 2);
  assert.equal(f.all(row => row.props['aria-label'] === '赞 Motif 回复')[0].props['aria-pressed'], true);
  assert.doesNotMatch(f.content(f.render()), /等待执行|等待当前任务|停止生成/);
  assert.equal(f.blocks.get('session-a'), undefined);
  assert.equal(f.streams.length, 1, 'a cached completed task does not reopen a live stream');
  finish(Response.json(initial)); await flush(); f.render();
  assert.equal(f.all(row => f.isMarkdown(row)).length, 2, 'an older read cannot erase cached results'); f.dispose();
});

test('cached results cannot leak into a different conversation during navigation', async () => {
  const f = fixture(); await flush(); f.render();
  const next = comparison(); next.id = 'comparison-b'; next.session_id = 'session-b'; next.status = 'running';
  for (const lane of Object.values(next.lanes)) { lane.status = 'queued'; lane.answer = ''; lane.artifacts = []; }
  f.setNodeData(next); f.render();
  assert.equal(f.all(row => f.isMarkdown(row)).length, 0);
  assert.equal(f.render(), null); f.dispose();
});

test('numeric scoring is absent for running, completed and failed comparisons and never submits on refresh', async () => {
  for (const status of ['running', 'completed', 'failed']) {
    const value = comparison(); value.status = status; value.snapshot_revision = 1;
    value.scores = { baseline: 2, motif: 5 }; // Old research results remain server-owned metadata.
    for (const lane of Object.values(value.lanes)) lane.status = status;
    const f = fixture(undefined, value); await flush(); f.render();
    const absent = () => {
      assert.equal(f.all(row => row.type === 'fieldset' || (row.type === 'input' && row.props.type === 'radio')).length, 0);
      assert.doesNotMatch(f.content(f.render()), /结果评分|两侧完成后评分|正在保存评分/);
    };
    absent(); value.score_revision++; value.scores.baseline = 4;
    f.events.get('focus')(); await flush(); f.render(); absent();
    f.remount(structuredClone(value)); await flush(); f.render(); absent();
    assert.equal(f.requests.filter(row => row.init.method === 'POST').length, 0,
      'historic scores and navigation cannot create a hidden rating write');
    f.dispose();
  }
});

test('a rejected feedback action keeps confirmed votes and leaves the other lane unchanged', async () => {
  const value = comparison(); value.lanes.baseline.feedback = 'up'; value.lanes.motif.feedback = 'down';
  let finish;
  const f = fixture((_url, init) => init.method === 'POST' ? new Promise(resolve => { finish = resolve; }) : Response.json(value), value);
  await flush(); f.render();
  const button = label => f.all(row => row.props['aria-label'] === label)[0];
  const work = button('赞 Baseline 回复').props.onClick(); f.render();
  finish(Response.json({ error: { message: 'save rejected' } }, { status: 500 })); await work; await flush(); f.render();
  assert.equal(button('赞 Baseline 回复').props['aria-pressed'], true);
  assert.equal(button('踩 Motif 回复').props['aria-pressed'], true);
  assert.equal(f.all(row => row.props.className === 'harless-paired-error').length, 1);
  assert.equal(f.requests.filter(row => row.init.method === 'POST').length, 1); f.dispose();
});

test('401 and 403 feedback responses never replay a mutation after access returns', async () => {
  for (const status of [401, 403]) {
    const value = comparison(), writes = []; let finish;
    const f = fixture((_url, init) => {
      if (init.method !== 'POST') return Response.json(value);
      writes.push(JSON.parse(init.body)); return new Promise(resolve => { finish = resolve; });
    }, value);
    await flush(); f.render();
    const button = () => f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0];
    const work = button().props.onClick(); button().props.onClick();
    finish(Response.json({ error: {} }, { status })); await work; await flush(); f.render();
    assert.equal(button().props['aria-pressed'], false);
    assert.equal(writes.length, 1); assert.match(f.content(f.all(row => row.props.className === 'harless-paired-error')[0]), /登录已过期|没有权限/);
    f.remount(comparison()); await flush(); f.render();
    assert.equal(button().props['aria-pressed'], false); assert.equal(writes.length, 1); f.dispose();
  }
});

test('leaving the authenticated page ignores a late feedback response and never replays it', async () => {
  const value = comparison(), writes = []; let finish;
  const f = fixture((_url, init) => {
    if (init.method !== 'POST') return Response.json(value);
    writes.push(JSON.parse(init.body)); return new Promise(resolve => { finish = resolve; });
  }, value);
  await flush(); f.render();
  const button = () => f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0];
  const work = button().props.onClick(); f.render();
  f.events.get('pagehide')();
  const late = comparison(); late.lanes.baseline.feedback = 'up'; late.snapshot_revision = 2;
  finish(Response.json(late)); await work; await flush(); f.render();
  assert.equal(writes.length, 1); assert.equal(button().props['aria-pressed'], false);
  f.remount(comparison()); await flush(); f.render(); assert.equal(button().props['aria-pressed'], false); f.dispose();
});

test('feedback rejected for an obsolete output refreshes the replacement without resubmitting', async () => {
  const value = comparison(); value.snapshot_revision = 2; let finish; const writes = [];
  const f = fixture((_url, init) => {
    if (init.method !== 'POST') return Response.json(value);
    writes.push(JSON.parse(init.body)); return new Promise(resolve => { finish = resolve; });
  }, value);
  await flush(); f.render();
  const button = () => f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0];
  const work = button().props.onClick(); f.render();
  value.lanes.baseline.output_sha256 = 'replacement-hash'; value.lanes.baseline.answer = '已更新的结果';
  value.snapshot_revision++; value.score_revision++; value.scores = {};
  finish(Response.json({ error: {} }, { status: 409 })); await work; await flush(); f.render();
  assert.equal(writes.length, 1); assert.equal(writes[0].action, 'feedback'); assert.equal(writes[0].output_sha256, 'baseline-hash');
  assert.equal(button().props['aria-pressed'], false);
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, '已更新的结果');
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-error')[0]), /结果已更新/); f.dispose();
});

test('a restarted server epoch supersedes a higher old revision and rejects late old-epoch snapshots', async () => {
  const old = comparison(); old.snapshot_epoch = 7; old.snapshot_revision = 120;
  const restarted = comparison(); restarted.snapshot_epoch = 8; restarted.snapshot_revision = 90;
  restarted.lanes.baseline.answer = '服务恢复后的已完成结果'; let current = old;
  const f = fixture(() => Response.json(current), old); await flush(); f.render();
  current = restarted; f.events.get('focus')(); await flush(); f.render();
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, restarted.lanes.baseline.answer);
  current = old; f.events.get('focus')(); await flush(); f.render();
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, restarted.lanes.baseline.answer);
  f.remount(old); assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, restarted.lanes.baseline.answer); f.dispose();
});
test('paired answers delegate Markdown and inline artifact mentions to the native safe renderer', async () => {
  const f = fixture(); await flush(); f.render();
  const markdown = f.all(row => f.isMarkdown(row)); assert.equal(markdown.length, 2);
  assert.match(markdown[0].props.text, /\*\*结果\*\*/);
  assert.equal(markdown[0].props.streaming, false);
  assert.equal(markdown[0].props.fileMentions.resolve('/app/work/outputs/report/research_report.pdf').title, 'research_report.pdf');
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
    const wrapperAttrs = {}, wrapper = { nodeType: 1, nodeName: 'CODE', tagName: 'CODE',
      setAttribute: (key, next) => { wrapperAttrs[key] = next; } };
    const node = { nodeType: 1, nodeName: tag.toUpperCase(), tagName: tag.toUpperCase(), childNodes: [icon, textNode], onClick,
      parentElement: tag === 'button' ? wrapper : undefined,
      closest: selector => selector === 'pre' && pre ? {} : selector === 'code' && tag === 'button' ? wrapper : null,
      getAttribute: key => attrs[key], setAttribute: (key, next) => { attrs[key] = next; } };
    return { node, textNode, icon, attrs, onClick, wrapperAttrs };
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
  for (const row of [absolute, relative, custom, captionWithPath]) {
    assert.equal(row.attrs['data-harless-artifact-link'], '', 'only a verified file target becomes a styled file link');
    assert.equal(row.attrs.title, 'research_report.pdf', 'the public tooltip never exposes the private path');
  }
  assert.equal(absolute.wrapperAttrs['data-harless-artifact-inline'], '', 'the native inline-code wrapper can lose its file-chip frame');
  for (const row of [unknown, code, external]) {
    assert.equal(row.attrs['data-harless-artifact-link'], undefined);
    assert.equal(row.wrapperAttrs['data-harless-artifact-inline'], undefined);
  }
  assert.equal(captionWithPath.textNode.nodeValue, '下载 /app/work/' + artifact.name);
  assert.equal(unknown.textNode.nodeValue, '/app/work/not-approved.pdf');
  assert.equal(code.textNode.nodeValue, '/app/work/' + artifact.name); assert.equal(external.textNode.nodeValue, artifact.name);
  for (const row of rows) { assert.equal(row.node.childNodes[0], row.icon); assert.equal(row.node.onClick, row.onClick); }
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, original, 'do not rewrite inline or fenced source code');
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
  const mention = f.all(row => f.isMarkdown(row))[0].props.fileMentions.resolve('/app/work/' + artifact.name);
  mention.open();
  assert.deepEqual(f.downloaded, [], 'opening a file mention never downloads');
  assert.deepEqual(f.openedPreviews, ['dsh-resource://geneloop-delivery/session-a/comparison-a/baseline/file-one/research_report.pdf']);
  f.dispose();
});

test('delivery card and inline link preview in the native right sidebar while the download control remains independent', async () => {
  const f = fixture(url => url.includes('&file=') ? new Response(fileBytes, { headers: { 'content-type': 'application/pdf' } }) : Response.json(comparison()));
  await flush(); f.render();
  const preview = f.all(row => row.props['aria-label'] === '预览 research_report.pdf' && row.type === 'button');
  assert.equal(preview.length, 2); preview[1].props.onClick();
  assert.equal(f.openedPreviews[0], 'dsh-resource://geneloop-delivery/session-a/comparison-a/motif/file-one/research_report.pdf');
  assert.equal(f.downloaded.length, 0);
  const pane = f.all(row => row.props.className === 'harless-paired-answer')[0];
  let prevented = false;
  pane.props.onClickCapture({ target: { closest: () => ({ getAttribute: () => artifact.name }) }, preventDefault() { prevented = true; }, stopPropagation() {} });
  assert.ok(prevented); assert.match(f.openedPreviews[1], /\/baseline\//); assert.equal(f.downloaded.length, 0);
  const download = f.all(row => row.type === 'a' && row.props['aria-label'] === '下载 research_report.pdf')[0];
  download.props.onClick({ preventDefault() {} }); await waitUntil(() => f.downloaded.length === 1);
  assert.equal(f.openedPreviews.length, 2); assert.equal(f.downloaded[0].name, 'research_report.pdf'); f.dispose();
});
test('network read failure keeps rendered output and backs off; recovery stops polling completed turns', async () => {
  let reads = 0; const value = comparison();
  const f = fixture(() => { if (++reads < 3) throw TypeError('Failed to fetch'); return Response.json(value); });
  await flush(); f.render();
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, value.lanes.baseline.answer);
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
test('feedback with an uncertain network response is reconciled by GET and never auto-posted twice', async () => {
  const value = comparison(); let posts = 0;
  const f = fixture((_url, init) => {
    if (init.method === 'POST') {
      assert.equal(JSON.parse(init.body).action, 'feedback');
      posts++; value.lanes.baseline.feedback = 'up'; value.snapshot_revision = 2; throw TypeError('Failed to fetch');
    }
    return Response.json(value);
  });
  await flush(); f.render();
  await f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props.onClick(); await flush(); f.render();
  assert.equal(posts, 1); assert.equal(f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props['aria-pressed'], true);
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

test('delivery cards keep native file identity and authenticated icon downloads for arbitrary file types', async () => {
  const extensions = ['pdf', 'docx', 'pptx', 'csv', 'json', 'txt', 'png', 'zip', 'unusual'];
  const mimeTypes = { pdf: 'application/pdf', docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation', csv: 'text/csv', json: 'application/json',
    txt: 'text/plain', png: 'image/png', zip: 'application/zip', unusual: 'application/octet-stream' };
  const value = comparison(); value.presentation = 'single'; delete value.lanes.motif;
  const bodies = new Map();
  value.lanes.baseline.artifacts = extensions.map((extension, index) => {
    const bytes = Buffer.from('actual delivered bytes: ' + extension + '!'.repeat(index));
    const id = 'file-' + extension; bodies.set(id, bytes);
    return { id, name: 'outputs/private-task/成品.' + extension, bytes: bytes.length,
      sha256: createHash('sha256').update(bytes).digest('hex') };
  });
  const f = fixture(url => {
    const id = new URL(url, 'https://example.test').searchParams.get('file');
    return id ? new Response(bodies.get(id), { headers: { 'content-type': mimeTypes[id.slice(5)] } }) : Response.json(value);
  }, value);
  await flush(); f.render();
  const cards = f.all(row => row.props.className === 'harless-artifact-card');
  assert.equal(cards.length, extensions.length, 'files are not limited to the PDF renderer');
  for (let index = 0; index < cards.length; index++) {
    const card = cards[index], file = value.lanes.baseline.artifacts[index], name = '成品.' + extensions[index];
    const filename = f.all(row => row.props.className === 'harless-paired-filename', card)[0];
    assert.equal(f.content(filename), name); assert.equal(filename.props.title, name);
    assert.equal(f.all(row => row.type === f.primitives.FileTypeIcon, card)[0].props.path, name);
    const meta = f.content(f.all(row => row.props.className === 'harless-artifact-meta', card)[0]);
    assert.match(meta, new RegExp(extensions[index], 'i'));
    assert.ok(meta.includes(file.bytes + ' bytes'), 'metadata formats the authoritative receipt size');
    const links = f.all(row => row.type === 'a' && row.props.download, card);
    assert.equal(links.length, 1, 'the single download control has the existing guarded route');
    assert.equal(links[0].props['aria-label'], '下载 ' + name);
    assert.equal(links[0].props.download, name);
    assert.equal(links[0].children[0].type, f.primitives.IconDownloadOutline16);
    links[0].props.onClick({ preventDefault() {} }); links[0].props.onClick({ preventDefault() {} });
    await waitUntil(() => f.downloaded.length === index + 1); f.render();
    assert.equal(f.downloaded[index].name, name);
    const requests = f.requests.filter(row => row.url.includes('&file=' + file.id));
    assert.equal(requests.length, 1, 'rapid icon clicks do not duplicate the authenticated fetch');
    assert.equal(requests[0].init.credentials, 'same-origin');
  }
  f.dispose();
});

test('delivery metadata keeps zero-byte files but omits missing or invalid sizes', async () => {
  const value = comparison(); value.presentation = 'single'; delete value.lanes.motif;
  value.lanes.baseline.artifacts = [
    { id: 'empty', name: 'outputs/empty.txt', bytes: 0 },
    { id: 'no-extension', name: 'outputs/LICENSE' },
    { id: 'invalid-size', name: 'outputs/archive.unusual', bytes: -1 },
  ];
  const f = fixture(undefined, value); await flush(); f.render();
  const cards = f.all(row => row.props.className === 'harless-artifact-card');
  assert.equal(cards.length, 3);
  const metadata = cards.map(card => f.content(f.all(row => row.props.className === 'harless-artifact-meta', card)[0]));
  assert.match(metadata[0], /0 bytes/);
  assert.doesNotMatch(metadata.slice(1).join('\n'), /undefined|NaN|null|-1 bytes|0 bytes/);
  assert.ok(f.all(row => row.type === 'a' && row.props.download === 'LICENSE', cards[1]).length,
    'an extensionless delivery still has a download control');
  f.dispose();
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
for (const scene of ['ppt', 'paper-proofreading', 'research-data-analysis']) test(`${scene}: no delivery renders no empty-file notice and cannot invent a download`, async () => {
  const value = comparison(); value.lanes.motif.artifacts = []; value.lanes.motif.delivery_status = 'not_delivered';
  value.scene = scene;
  value.lanes.motif.delivery_message = '本轮未通过交付校验，没有可下载成品。';
  const f = fixture(undefined, value); await flush(); f.render();
  const pane = f.all(row => row.type === 'section' && row.props['aria-label'] === 'Motif')[0];
  assert.match(f.content(pane), /回复完成/); assert.doesNotMatch(f.content(pane), /没有可下载成品/);
  assert.equal(f.all(row => row.type === 'a' && row.props.download, pane).length, 0);
  assert.equal(f.all(row => f.isMarkdown(row), pane)[0].props.fileMentions.resolve(artifact.name), undefined); f.dispose();
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
    assert.doesNotMatch(f.content(pane), /交付校验|另一侧结果已保留|暂无结果文件|暂无回复/);
    assert.equal(f.all(row => f.isMarkdown(row), pane).length, 0);
    assert.equal(f.all(row => row.type === 'a' && row.props.download, pane).length, 0);
  }
  assert.equal(f.timers.size, 0); f.dispose();
});
test('a file-only result leaves the empty answer seat silent while verified cards stay available', async () => {
  const value=comparison();
  for (const lane of Object.values(value.lanes)) lane.answer='';
  const f=fixture(undefined,value);await flush();f.render();
  assert.equal(f.all(row=>row.props.className==='harless-artifact-card').length,2);
  assert.doesNotMatch(f.content(),/本轮未生成文字回复|本轮尚无|本轮没有/);f.dispose();
});
test('overlapping old GET cannot undo saved feedback; followup read still happens', async () => {
  const value = comparison(), old = comparison(); value.snapshot_revision = old.snapshot_revision = 1; let finishRead, reads = 0;
  const f = fixture((_url, init) => {
    if (init.method === 'POST') { value.lanes.baseline.feedback = 'up'; value.snapshot_revision++; return Response.json(value); }
    if (++reads === 2) return new Promise(resolve => { finishRead = () => resolve(Response.json(old)); });
    return Response.json(value);
  });
  await flush(); f.render(); f.events.get('focus')(); await flush();
  await f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props.onClick();
  finishRead(); await flush(); f.render();
  assert.equal(f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props['aria-pressed'], true);
  const timer = [...f.timers.values()][0]; assert.equal(timer.delay, 0); f.timers.clear(); await timer.fn();
  assert.equal(reads, 3); f.dispose();
});
test('duplicate basenames stay inert while exact approved paths remain downloadable', async () => {
  const value = comparison(); value.lanes.baseline.artifacts.push({ ...artifact, id: 'other', name: 'outputs/other/research_report.pdf' });
  const f = fixture(undefined, value); await flush(); f.render();
  const mentions = f.all(row => f.isMarkdown(row))[0].props.fileMentions;
  assert.equal(mentions.resolve('research_report.pdf'), undefined);
  assert.equal(mentions.resolve('/app/work/' + artifact.name).title, 'research_report.pdf'); f.dispose();
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
  current.lanes.baseline.feedback = 'up';
  const f = fixture(() => Response.json(current), initial); await flush(); f.render();
  f.setNodeData(structuredClone(initial)); f.render(); f.render();
  assert.equal(f.all(row => row.type === 'a' && row.props.download).length, 2);
  assert.equal(f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props['aria-pressed'], true);
  assert.equal(f.all(row => f.isMarkdown(row))[1].props.streaming, false);
  assert.equal(f.timers.size, 0); f.dispose();
});
test('GET deadline covers stalled response JSON and frees polling for backoff recovery', async () => {
  const f = fixture((_url, init) => ({ ok: true, status: 200, json: () => waitForAbort(init.signal) }));
  await flush(); const deadline = [...f.timers.values()].find(timer => timer.delay === 30000); assert.ok(deadline);
  deadline.fn(); await flush(); f.render();
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-connection')[0]), /连接超时/);
  assert.equal([...f.timers.values()][0].delay, 3600); f.dispose();
});
test('POST deadline reconciles server-saved feedback using GET without another POST', async () => {
  const value = comparison(); let posts = 0;
  const f = fixture((_url, init) => {
    if (init.method === 'POST') {
      assert.equal(JSON.parse(init.body).action, 'feedback');
      posts++; value.lanes.baseline.feedback = 'up'; value.snapshot_revision = 2;
      return { ok: true, status: 200, json: () => waitForAbort(init.signal) };
    }
    return Response.json(value);
  });
  await flush(); f.render();
  const action = f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props.onClick();
  await flush(); [...f.timers.values()].find(timer => timer.delay === 30000).fn(); await action; await flush(); f.render();
  assert.equal(posts, 1); assert.equal(f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props['aria-pressed'], true);
  assert.match(f.content(f.all(row => row.props.className === 'harless-paired-error')[0]), /连接超时.*请勿重复提交/);
  assert.equal(f.all(row => row.props['aria-label'] === '赞 Baseline 回复')[0].props.disabled, false); f.dispose();
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
  assert.equal(f.all(row=>f.isMarkdown(row)).length,1);
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
  assert.equal(f.all(row=>f.isMarkdown(row))[0].props.text,'正在分析第一');
  assert.equal(f.all(row=>f.isMarkdown(row))[0].props.streaming,true);
  assert.equal(f.all(row=>row.props.className==='geneloop-looping')[0].props.title,'正在读取数据');
  assert.equal(f.all(row=>row.props.className==='harless-activity')[0].props.open,undefined,'tool details remain collapsed');
  partial.lanes.baseline.answer+='组数据';stream.emit(partial);f.render();
  assert.equal(f.all(row=>f.isMarkdown(row))[0].props.text,'正在分析第一组数据');
  stream.emit(comparison());f.render();assert.equal(stream.closed,true);
  assert.equal(f.all(row=>f.isMarkdown(row))[0].props.streaming,false);f.dispose();
});

test('paired lanes own matching bottom GeneLooping indicators and finish independently', async () => {
  const value=comparison();value.status='running';
  for(const row of Object.values(value.lanes))Object.assign(row,{status:'running',answer:'',artifacts:[],delivery_message:'结果文件会在生成并通过交付检查后显示。',progress:{tool:'mcp__files__read_file',subject:'材料.pdf',status:'running'}});
  const f=fixture(undefined,value,{streaming:true});await flush();f.render();
  assert.equal(f.all(row=>row.props.className==='geneloop-looping').length,2);
  assert.equal(f.all(row=>row.type==='footer'||row.type==='fieldset').length,0);
  assert.equal(f.all(row=>row.props.className==='geneloop-process-status').length,0);
  for (const pane of f.all(row=>row.props.className==='harless-paired-pane')) {
    const indicator=f.all(row=>row.props.className==='geneloop-looping',pane)[0];
    assert.equal(f.content(indicator),'GeneLooping…');
    assert.match(indicator.props.title,/正在阅读文档：材料.pdf/);
    assert.ok(pane.children.indexOf(indicator)>pane.children.findIndex(row=>row?.props?.className==='harless-paired-answer'));
  }
  assert.doesNotMatch(f.content(),/正在处理，结果会自动更新|结果文件会在生成/);
  const partial=structuredClone(value);Object.assign(partial.lanes.baseline,{status:'completed',answer:'Baseline 完成'});
  f.streams[0].emit(partial);f.render();
  assert.equal(f.all(row=>row.props.className==='geneloop-looping').length,1);
  assert.equal(f.all(row=>row.props.className==='geneloop-looping')[0].props['aria-label'],'Motif 正在处理');
  f.streams[0].emit(comparison());f.render();assert.equal(f.all(row=>row.props.className==='geneloop-looping').length,0);f.dispose();
});

test('a stale initial GET cannot replace newer streaming text; unmount closes the stream', async () => {
  let resolve;const blocked=new Promise(r=>resolve=r),value=comparison();value.status='running';
  for(const row of Object.values(value.lanes))row.status='running';
  const f=fixture(()=>blocked,value,{streaming:true}),stream=f.streams[0];stream.onopen();
  const partial=structuredClone(value);partial.lanes.baseline.answer='新的流式片段';stream.emit(partial);f.render();
  resolve(Response.json(value));await flush();f.render();
  assert.equal(f.all(row=>f.isMarkdown(row))[0].props.text,'新的流式片段');
  f.dispose();assert.equal(stream.closed,true);assert.equal(f.timers.size,0);
});

test('a streamed result for another conversation is rejected and never shown', async () => {
  const value=comparison();value.status='running';for(const row of Object.values(value.lanes))row.status='running';
  const f=fixture(undefined,value,{streaming:true});await flush();const foreign=structuredClone(value);foreign.session_id='another-user';foreign.lanes.baseline.answer='foreign secret';
  f.streams[0].emit(foreign);await flush();f.render();
  assert.equal(f.streams[0].closed,true);assert.ok(f.all(row=>f.isMarkdown(row)).every(row=>!row.props.text.includes('foreign secret')));f.dispose();
});


test('old stream snapshots cannot replace newer retry output or close the active stream', async () => {
  const value=comparison();value.status='running';value.snapshot_revision=10;
  for(const row of Object.values(value.lanes))row.status='running';
  const f=fixture(undefined,value,{streaming:true});await flush();f.render();const stream=f.streams[0];stream.onopen();
  const next=structuredClone(value);next.snapshot_revision=12;next.lanes.baseline.answer='新尝试的流式回复';next.lanes.baseline.attempt=1;
  stream.emit(next);f.render();
  const stale=structuredClone(value);stale.snapshot_revision=11;stale.status='failed';stale.lanes.baseline.answer='旧尝试失败';
  stream.emit(stale);f.render();
  assert.equal(f.all(row=>f.isMarkdown(row))[0].props.text,'新尝试的流式回复');assert.notEqual(stream.closed,true);
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
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, '真实第一段');
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.streaming, true);
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
  assert.equal(old.closed, true); assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, '第一段，第二段');
  const reconnect = [...f.timers.entries()].find(([, timer]) => timer.delay === 2000);
  f.timers.delete(reconnect[0]); reconnect[1].fn(); assert.equal(f.streams.length, 2);
  const late = structuredClone(current); late.snapshot_revision = 99; late.lanes.baseline.answer = 'retired connection';
  old.emit(late); old.onerror(); f.render();
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, '第一段，第二段');
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
  assert.equal(f.all(row => f.isMarkdown(row))[0].props.text, '第二个会话');
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
  next.lanes.baseline.progress={label:'正在调用数据分析工具',status:'running'};f.streams[0].emit(next);f.render();
  const old=f.all(row=>row.props.className==='harless-stream-messages')[0];assert.ok(old);
  assert.equal(f.all(row=>f.isMarkdown(row),old)[0].props.text,'先读取资料');
  assert.equal(f.all(row=>row.props.className==='harless-paired-answer')[0].children[0].props.text,'已经核验，正在');
  assert.match(f.all(row=>row.props.className==='geneloop-looping')[0].props.title,/分析工具/);
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
  assert.deepEqual(copied,[value.lanes.baseline.answer]);assert.ok(f.all(row=>row.props.kind==='usage' && row.props.label==='用量 1.5K tok').length);
  assert.ok(f.all(row=>row.props.kind==='clock' && row.props.label==='用时 1分04秒').length);
  await f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props.onClick();await flush();f.render();
  assert.equal(f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props['aria-pressed'],true);
  await f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props.onClick();await flush();f.render();
  assert.equal(f.all(row=>row.props['aria-label']==='赞 Baseline 回复')[0].props['aria-pressed'],false);
  assert.equal(f.requests.filter(row=>row.init.method==='POST').length,2);f.dispose();
});

test('comparison actions follow the latest turn of the whole conversation, including later ordinary Chat', async () => {
  const location = { kind: 'turn', turn: { turn: 2, status: 'closed' } };
  const f = fixture(undefined, comparison(), { location, chatSnapshot: { timeline: { turnOrder: [1, 2] } } });
  const panes = () => f.all(row => row.type === 'section' && row.props['data-actions-reveal']);
  assert.deepEqual(panes().map(row => row.props['data-actions-reveal']), ['always', 'always']);
  for (const kind of ['assistant-step', 'harless-comparison']) {
    f.setChatSnapshot({ timeline: { turnOrder: [1, 2, 3] }, nodes: new Map([['later', { kind, location: { kind: 'turn', turn: { turn: 3 } } }]]) });
    f.render(); assert.deepEqual(panes().map(row => row.props['data-actions-reveal']), ['hover', 'hover'], kind);
  }
  f.setChatSnapshot({ timeline: { turnOrder: [1, 2] } }); f.render();
  assert.deepEqual(panes().map(row => row.props['data-actions-reveal']), ['always', 'always']);
  f.setNodeLocation({ kind: 'step', turn: { turn: 1 } }); f.render();
  assert.deepEqual(panes().map(row => row.props['data-actions-reveal']), ['hover', 'hover']); f.dispose();
});

test('unknown comparison or timeline turn keeps actions discoverable and touch and keyboard paths remain visible', () => {
  const f = fixture(undefined, comparison(), { chatSnapshot: { timeline: { turnOrder: [3] } } });
  const reveal = () => f.all(row => row.props['data-actions-reveal']).map(row => row.props['data-actions-reveal']);
  assert.deepEqual(reveal(), ['always', 'always']);
  f.setNodeLocation({ kind: 'turn', turn: { turn: 2 } }); f.setChatSnapshot({ timeline: { turnOrder: [] } }); f.render();
  assert.deepEqual(reveal(), ['always', 'always']);
  f.setChatSnapshot({}); f.render(); assert.deepEqual(reveal(), ['always', 'always']);
  f.setChatSnapshot(undefined); f.render(); assert.deepEqual(reveal(), ['always', 'always']);
  const css = f.all(row => row.type === 'style').map(row => f.content(row)).join('\n');
  assert.match(css, /@media\(hover:hover\)\{[^}]*data-actions-reveal=hover[^}]*opacity:0/);
  assert.match(css, /:focus-within[^}]*opacity:1/);
  assert.match(css, /:has\(\.harless-message-metric\[data-open\]\)/);
  assert.match(css, /@media\(prefers-reduced-motion:reduce\)/); f.dispose();
});

test('lane actions use native glyphs and bottom tooltips, with a one-second copy check and no extra visible label', async () => {
  const copied = [], value = comparison(); value.lanes.baseline.feedback = 'up';
  const f = fixture(undefined, value, { clipboard: { writeText: async text => copied.push(text) } });
  await flush(); f.render();
  const button = label => f.all(row => row.type === 'button' && row.props['aria-label'] === label)[0];
  for (const [label, icon] of [['复制 Baseline 回复', 'IconCopyOutline16'], ['赞 Baseline 回复', 'IconLikeFill16'],
    ['踩 Baseline 回复', 'IconDislikeOutline16'], ['从 Baseline 在新对话中分支', 'IconBranchOutline16']]) {
    assert.equal(button(label).children[0].type, f.primitives[icon]);
    assert.equal(button(label).props.title, undefined, 'native Tooltip replaces browser title tooltips');
  }
  const tips = f.all(row => row.props.className === 'harless-message-actions')
    .flatMap(actions => f.all(row => row.type === f.primitives.Tooltip, actions));
  assert.equal(tips.length, 8); assert.ok(tips.every(row => row.props.side === 'bottom'));
  assert.ok(tips.some(row => row.props.label === '取消标记')); assert.ok(tips.some(row => row.props.label === '有问题的回答'));
  await button('复制 Baseline 回复').props.onClick(); f.render();
  assert.deepEqual(copied, [value.lanes.baseline.answer]); assert.deepEqual(f.clipboardWrites, copied);
  assert.equal(button('复制 Baseline 回复').children[0].type, f.primitives.IconCheckOutline16);
  assert.equal(f.all(row => row.props.role === 'status' && f.content(row) === '已复制')[0].props.className, 'harless-visually-hidden');
  await button('复制 Baseline 回复').props.onClick(); assert.equal(copied.length, 1, 'check feedback prevents accidental duplicate copies');
  const timer = [...f.timers].find(([, value]) => value.delay === 1000); assert.ok(timer);
  f.timers.delete(timer[0]); timer[1].fn(); f.render();
  assert.equal(button('复制 Baseline 回复').children[0].type, f.primitives.IconCopyOutline16);
  assert.equal(f.all(row => row.props.role === 'status' && f.content(row) === '已复制').length, 0); f.dispose();
});

test('copy completion after leaving the comparison cannot change another conversation footer', async () => {
  let finish; const f = fixture(undefined, comparison(), { clipboard: { writeText: () => new Promise(resolve => { finish = resolve; }) } });
  await flush(); f.render(); const work = f.all(row => row.props['aria-label'] === '复制 Baseline 回复')[0].props.onClick();
  const next = comparison(); next.id = 'comparison-b'; next.session_id = 'session-b'; f.setNodeData(next); f.render();
  finish(); await work; f.render();
  assert.equal(f.all(row => row.props['aria-label'] === '复制 Baseline 回复')[0].children[0].type, f.primitives.IconCopyOutline16);
  assert.equal([...f.timers.values()].some(timer => timer.delay === 1000), false); f.dispose();
});

test('lane metrics use exact usage and completion time, compact counts, and only available timing facts', async () => {
  const value = comparison(), baseline = value.lanes.baseline;
  baseline.stats = { prompt_tokens: 1024, completion_tokens: 500, upstream_requests: 2 };
  baseline.duration_ms = 64500; baseline.started_at = new Date(2020, 0, 2, 3, 3, 0).toISOString();
  baseline.finished_at = new Date(2020, 0, 2, 3, 4, 5).toISOString();
  const f = fixture(undefined, value); await flush(); f.render();
  const metric = kind => f.all(row => row.type?.name === 'ReplyMetric' && row.props.kind === kind)[0];
  assert.equal(metric('usage').props.label, '用量 1.5K tok');
  assert.deepEqual(JSON.parse(JSON.stringify(metric('usage').props.rows)), [['总用量', '1,524 tok'], ['输入', '1,024 tok'], ['输出', '500 tok']]);
  assert.equal(metric('clock').props.label, '用时 1分04秒');
  assert.deepEqual(JSON.parse(JSON.stringify(metric('clock').props.rows)), [['本轮总用时', '1分04秒'],
    ['开始时间', '2020年1月2日 03:03'], ['完成时间', '2020年1月2日 03:04']]);
  const stamp = f.all(row => row.type === 'time' && row.props.className === 'harless-message-time')[0];
  assert.equal(stamp.props.dateTime, baseline.finished_at); assert.equal(f.content(stamp), '2020年1月2日 03:04');
  assert.doesNotMatch(JSON.stringify(metric('clock').props), /TTFT|首字|每秒|tok\/s|速度/);
  for (const [total, label] of [[0, '0'], [999, '999'], [12345, '12.3K'], [517000, '517K'], [1200000, '1.2M']]) {
    baseline.usage = { input: total, output: 0, total }; baseline.duration_ms = 900;
    f.events.get('focus')(); await flush(); f.render();
    assert.equal(metric('usage').props.label, '用量 ' + label + ' tok'); assert.equal(metric('clock').props.label, '用时 0秒');
  }
  f.dispose();
});

test('unknown usage and timing are omitted instead of exposing fictional waiting metrics or zeroes', async () => {
  const value = comparison(), f = fixture(undefined, value); await flush(); f.render();
  assert.equal(f.all(row => row.type?.name === 'ReplyMetric').length, 0);
  assert.equal(f.all(row => row.type === 'time' && row.props.className === 'harless-message-time').length, 0);
  value.lanes.baseline.stats = { prompt_tokens: 10 }; value.lanes.motif.duration_ms = 0;
  f.events.get('focus')(); await flush(); f.render();
  assert.equal(f.all(row => row.type?.name === 'ReplyMetric' && row.props.kind === 'usage').length, 0, 'partial input is not a total usage figure');
  const metrics = f.all(row => row.type?.name === 'ReplyMetric'); assert.equal(metrics.length, 1);
  assert.equal(metrics[0].props.label, '用时 0秒', 'a genuine zero duration is retained');
  f.dispose();
});

test('usage and time details use public anchored portals with outside and Escape dismissal', async () => {
  const value = comparison(); value.lanes.baseline.stats = { prompt_tokens: 1024, completion_tokens: 500 };
  value.lanes.baseline.duration_ms = 64500;
  const f = fixture(undefined, value); await flush(); f.render();
  for (const kind of ['usage', 'clock']) {
    const entry = f.all(row => row.type?.name === 'ReplyMetric' && row.props.kind === kind)[0], child = f.mount(entry);
    const trigger = () => child.all(row => row.type === 'button')[0];
    assert.equal(trigger().props['aria-haspopup'], 'dialog'); assert.equal(trigger().props['aria-expanded'], false);
    assert.equal(trigger().children[0].type, f.primitives[kind === 'usage' ? 'IconDatabaseOutline16' : 'IconClockOutline16']);
    let focused = 0; const insideTrigger = {}, insidePanel = {}, anchor = f.positioning.at(-1);
    anchor.anchorRef.current = { contains: target => target === insideTrigger, querySelector: () => ({ focus: () => focused++ }) };
    anchor.panelRef.current = { contains: target => target === insidePanel };
    trigger().props.onClick(); child.render(); assert.equal(trigger().props['aria-expanded'], true);
    const portal = child.all(row => row.type === 'portal')[0], panel = child.all(row => row.props.role === 'dialog')[0];
    assert.equal(portal.props.target, f.document.body); assert.equal(panel.props['aria-label'], entry.props.title);
    assert.deepEqual(panel.props.style, { left: 12, top: 24 });
    assert.equal(f.positioning.at(-1).side, 'top'); assert.equal(f.positioning.at(-1).gap, 8); assert.equal(f.positioning.at(-1).margin, 12);
    assert.equal(f.dismissals.at(-1).panelRef, anchor.panelRef, 'portaled content participates in outside-click boundaries');
    assert.match(child.content(), kind === 'usage' ? /总用量1,524 tok输入1,024 tok输出500 tok/ : /本轮总用时1分04秒/);
    assert.doesNotMatch(child.content(), /TTFT|首字|每秒|tok\/s/);
    f.events.get('pointerdown')({ target: insidePanel }); child.render(); assert.equal(trigger().props['aria-expanded'], true);
    f.events.get('pointerdown')({ target: {} }); child.render(); assert.equal(trigger().props['aria-expanded'], false);
    assert.equal(child.all(row => row.type === 'portal').length, 0);
    trigger().props.onClick(); child.render(); f.events.get('keydown')({ key: 'Escape' }); child.render();
    assert.equal(trigger().props['aria-expanded'], false); assert.equal(focused, 1); child.dispose();
  }
  const css = f.all(row => row.type === 'style').map(row => f.content(row)).join('\n');
  assert.match(css, /max-width:calc\(100vw - 24px\)/); assert.match(css, /max-height:calc\(100dvh - 24px\)/);
  assert.match(css, /overflow:auto/); f.dispose();
});

test('trajectory shows both lanes together and distinguishes verified optimization from shadow candidates', async () => {
  const value=comparison();value.lanes.baseline.trace=[{id:'base',kind:'tool',label:'读取数据',status:'completed'}];
  value.lanes.motif.mode='shadow';value.lanes.motif.trace=[{id:'shadow',kind:'motif',label:'预测候选',status:'completed',optimized:false,verified_skip:false}];
  const f=fixture(undefined,value,{traceOnly:true});await flush();f.render();
  assert.equal(f.all(row=>row.props.className==='harless-trace-column').length,2);
  assert.match(f.content(f.all(row=>row.props.className==='harless-comparison-trace')[0]),/Baseline.*Motif · 影子评估/);
  const rows=index=>{const component=f.all(row=>row.type?.name==='TraceRows')[index];return component.type(component.props);};
  assert.match(f.content(rows(0)),/读取数据/);assert.match(f.content(rows(1)),/预测候选/);
  assert.doesNotMatch(f.content(rows(1)),/已应用优化|已验证跳过/);
  value.lanes.motif.trace=[{id:'verified',kind:'motif',label:'执行已认证节点',status:'completed',optimized:true,verified_skip:true}];
  f.events.get('focus')();await flush();f.render();
  const tree=rows(1);assert.match(f.content(tree),/已验证跳过模型请求/);assert.equal(f.all(row=>row.props['data-optimized']==='true',tree).length,1);f.dispose();
});

test('single-lane tasks are ordinary execution records in the unified trajectory', async()=>{
  const value=comparison();value.presentation='single';delete value.lanes.motif;
  const f=fixture(undefined,value,{traceOnly:true});await flush();f.render();
  assert.equal(f.all(row=>row.props.className==='harless-trace-column').length,1);
  assert.match(f.content(f.all(row=>row.props.className==='harless-comparison-trace')[0]),/执行过程/);assert.doesNotMatch(f.content(f.all(row=>row.props.className==='harless-comparison-trace')[0]),/Baseline|Motif/);f.dispose();
});

test('completed process messages retain verified artifact routing without repeating the unbound final template',async()=>{
  const value=comparison();value.lanes.baseline.answer='结果 {{estimate}}';value.lanes.baseline.answer_display='结果 1.25';
  value.lanes.baseline.messages=[{id:'prior',text:'先查看 `/app/work/outputs/report/research_report.pdf`',status:'completed'},
    {id:'final',text:'结果 {{estimate}}',status:'completed'}];
  const f=fixture(undefined,value);await flush();f.render();
  const process=f.all(row=>row.props.className==='harless-process-message')[0];assert.equal(typeof process.props.ref,'function');
  let prevented=false;process.props.onClickCapture({target:{closest:()=>({getAttribute:()=>'/private/not-approved.pdf'})},
    preventDefault(){prevented=true;},stopPropagation(){}});assert.equal(prevented,true);
  const texts=f.all(row=>f.isMarkdown(row)).map(row=>row.props.text);assert.ok(texts.includes('结果 1.25'));
  assert.equal(texts.some(text=>text.includes('{{estimate}}')),false);assert.equal(f.all(row=>f.isMarkdown(row),process)[0].props.fileMentions.resolve('/app/work/'+artifact.name).title,'research_report.pdf');
  f.dispose();
});

test('approved relative Markdown links retain captions and open preview; examples, images and remote links stay untouched',async()=>{
  const value=comparison();value.lanes.baseline.answer='[阅读报告](research_report.pdf)\n\n`[示例](research_report.pdf)`\n\n```md\n[代码](research_report.pdf)\n```\n\n![图片](research_report.pdf) [网站](https://example.com/research_report.pdf) [未知](missing.pdf)';
  const f=fixture(undefined,value);await flush();f.render();
  const markdown=f.all(row=>f.isMarkdown(row))[0].props.text;
  const href=/\[阅读报告\]\(([^)]+)\)/.exec(markdown)[1];
  assert.match(href,/^https:\/\/geneloop\.example\/#geneloop-preview=/);
  assert.match(decodeURIComponent(href),/session-a\/comparison-a\/baseline\/file-one\/research_report.pdf/);
  assert.ok(markdown.includes('`[示例](research_report.pdf)`'));assert.ok(markdown.includes('```md\n[代码](research_report.pdf)\n```'));
  assert.ok(markdown.includes('![图片](research_report.pdf)'));assert.ok(markdown.includes('[网站](https://example.com/research_report.pdf) [未知](missing.pdf)'));
  let prevented=false;const answer=f.all(row=>row.props.className==='harless-paired-answer')[0];
  answer.props.onClickCapture({target:{closest:()=>({getAttribute:()=>href})},preventDefault(){prevented=true;},stopPropagation(){}});
  assert.equal(prevented,true);assert.equal(f.openedPreviews.length,1);assert.equal(f.downloaded.length,0);f.dispose();
});


test('sandbox output and scratch paths resolve only to approved files, including bare filenames in tables',async()=>{
 const value=comparison();value.lanes.baseline.artifacts=[{...artifact,name:'outputs/code/pelican.html'}, {...artifact,id:'scratch',name:'code/bird.svg'}];
 value.lanes.baseline.answer='| 文件 |\n|---|\n| `pelican.html` |\n| [动画](/work/outputs/pelican.html) |';
 const f=fixture(undefined,value);await flush();f.render();const md=f.all(row=>f.isMarkdown(row))[0];
 const mentions=md.props.fileMentions;
 for(const path of ['pelican.html','/work/outputs/pelican.html','outputs/pelican.html','sandbox:/work/outputs/pelican.html'])assert.equal(mentions.resolve(path).title,'pelican.html');
 assert.equal(mentions.resolve('/work/bird.svg').title,'bird.svg');assert.equal(mentions.resolve('missing.md'),undefined);
 assert.match(md.props.text,/#geneloop-preview=/);
 value.lanes.baseline.artifacts.push({...artifact,id:'duplicate',name:'outputs/other/pelican.html'});
 f.dispose();const ambiguous=fixture(undefined,value);await flush();ambiguous.render();
 assert.equal(ambiguous.all(row=>ambiguous.isMarkdown(row))[0].props.fileMentions.resolve('pelican.html'),undefined);ambiguous.dispose();
});
