/** Deterministic public-slot component diagnostics; no model or browser calls. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
const node = (kind, seq, data, closed = true) => ({ key: kind + seq, kind, anchorSeq: seq,
  location: { kind: 'step', turn: { turn: 1, status: closed ? 'closed' : 'running' } }, visibility: 'visible', data });
const assistant = (seq, text, closed = true, blocks = []) => node('assistant-step', seq, {
  turn: 1, step: seq, status: closed ? 'settled' : 'running', blocks: [{ kind: 'text', text }, ...blocks], finalNode: { seq },
}, closed);
const tool = (seq, done = true) => node('tool-call', seq, { root: { ...(done ? { kind: 'tool-result', call: { name: 'mcp__dsh-workspace__list_files', argsRaw: '{}' } }
  : { name: 'mcp__dsh-workspace__list_files', argsRaw: '{}' }), callId: 'call-' + seq,
  content: [{ type: 'text', text: 'report.csv · @deepseek-ai/dsh-workspace · DSH' }], subCalls: [], isError: false } }, done);

function fixture(initial, { compactAnswerStep, turnStatus, deliveryResponse } = {}) {
  let plugin, rows = initial, sessionId = 'session-a', tree, activePath = '', cursor = 0;
  const states = new Map(), entries = [], effects = [];
  const React = {
    createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }),
    useState(value) { const key = activePath + ':' + cursor++; if (!states.has(key)) states.set(key, value);
      return [states.get(key), next => states.set(key, typeof next === 'function' ? next(states.get(key)) : next)]; },
    useId() { return 'process-' + activePath.replace(/\W/g, '-'); },
    useEffect(fn,deps) { if (!deliveryResponse) return; const key=activePath+':effect:'+cursor++;
      if(JSON.stringify(states.get(key))!==JSON.stringify(deps)){states.set(key,deps);effects.push(fn);} }, useRef: value => ({ current: value }),
  };
  const MarkdownText = props => React.createElement('native-markdown', props);
  const NativeAssistant = props => React.createElement('native-assistant', props);
  entries.push({ options: { key: 'assistant-step' }, component: NativeAssistant });
  runInNewContext(source, { window: { location: { href:'http://localhost/' }, __ModuleLoader__: { load(value) { plugin = value; } } }, document: {},
    AbortController, URL, setTimeout, clearTimeout, fetch: async (url,init) => { if (!deliveryResponse) throw Error('rendering must not request a model');assert.match(url,/^\/api\/harless\/deliveries\?/);assert.equal(init.credentials,'same-origin');return Response.json(deliveryResponse); } });
  plugin.factory(name => name === 'react' ? React : { MarkdownText }).apply({
    get: name => ({ commandUi: { decorate: () => () => {} }, inputTriggers: { registerSource: () => () => {} }, sessions: {}, conversation: {}, sidebarRight: { openResource: address => states.set('opened',address) } })[name],
    effect: fn => { effects.push(fn); return fn(); }, uiConversation: { events: { register: () => () => {} } },
    slots: { inject(_name, fn) { fn(); }, register(options, component) { entries.push({ options, component }); }, entries: () => entries },
  });
  const materialize = (entry, path) => {
    if (!entry || typeof entry !== 'object') return entry;
    if (typeof entry.type === 'function') {
      activePath = path + '/' + entry.type.name + ':' + (entry.props.key || ''); cursor = 0;
      return materialize(entry.type(entry.props), activePath);
    }
    return { ...entry, children: entry.children.filter(child => child !== undefined).map((child, i) => materialize(child, path + '/' + i)) };
  };
  const render = () => {
    tree = rows.map(row => {
      const registered = entries.find(entry => entry.options.key === row.kind && entry.options.priority === -100);
      if (!registered) return { type: row.kind, props: {}, children: [] };
      const owner = { sessionId, node: row, t: key => key, openFile() {}, renderMessageImages() {}, fileMentions() {},
        useTurnData: () => ({ closing: rows.filter(row => row.kind === 'assistant-step').at(-1)?.data }),
        useChat: select => select({ order: rows.map(row => row.key), nodes: { get: key => rows.find(row => row.key === key) },
          ...(turnStatus ? { timeline: { turns: new Map([[1, { status: turnStatus }]]) } } : {}) }),
        turnProcess: { foldable: compactAnswerStep !== undefined, open: false, spec: { answerStep: compactAnswerStep } },
      };
      const result = materialize(React.createElement(registered.component, owner), row.key);
      // The shipped Compact seat suppresses earlier rows outside our renderer.
      const boundary = rows.find(row => row.kind === 'assistant-step' && row.data.step === compactAnswerStep)?.anchorSeq;
      return boundary !== undefined && row.anchorSeq < boundary ? null : result;
    });
    return tree;
  };
  const all = (predicate, entry = tree) => Array.isArray(entry) ? entry.flatMap(child => all(predicate, child))
    : !entry || typeof entry !== 'object' ? [] : [...(predicate(entry) ? [entry] : []), ...entry.children.flatMap(child => all(predicate, child))];
  const text = (entry = tree) => Array.isArray(entry) ? entry.map(text).join('') : typeof entry === 'string' ? entry
    : entry?.type === 'style' ? '' : entry?.type === 'native-assistant' ? entry.props.node.data.blocks.map(block => block.text || '').join('') : (entry?.children || []).map(text).join('');
  render();
  return { all, text, render, entries, async flushDelivery(){ for(const effect of effects.splice(0))effect();for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));render(); }, opened:()=>states.get('opened'), setRows(value) { rows = value; }, setSession(value) { sessionId = value; },
    toggle() { all(entry => entry.type === 'button' && entry.props.className === 'geneloop-process-toggle')[0].props.onClick(); render(); } };
}

test('completed chat defaults to the final answer with accessible reversible process disclosure', () => {
  const rows = [node('system-prompt', 0, { text: 'private system prompt' }),
    node('context', 1, { content: [{ type: 'text', text: 'attachment context' }], provenance: { plugin: '@deepseek-ai/dsh-attachment' } }),
    assistant(2, '先读取资料'), tool(3), assistant(4, '最终结果')];
  const f = fixture(rows);
  assert.equal(f.all(entry => entry.type === 'native-assistant').length, 1);
  assert.match(f.text(), /最终结果/); assert.doesNotMatch(f.text(), /先读取资料|attachment context|private system prompt/);
  let button = f.all(entry => entry.type === 'button')[0];
  assert.equal(button.props.type, 'button'); assert.equal(button.props['aria-expanded'], false);
  assert.ok(f.all(entry => entry.props.id === button.props['aria-controls'])[0].props.hidden);
  f.toggle();
  assert.match(f.text(), /先读取资料/); assert.match(f.text(), /attachment context/); assert.match(f.text(), /report.csv/);
  assert.doesNotMatch(f.text(), /DSH|dsh-|@deepseek-ai|private system prompt/);
  assert.equal(f.all(entry => entry.type === 'button')[0].props['aria-expanded'], true);
  assert.equal(f.all(entry => entry.type === 'native-assistant').length, 2);
  f.toggle(); assert.doesNotMatch(f.text(), /先读取资料|attachment context/); assert.match(f.text(), /最终结果/);
  assert.ok(!f.entries.some(entry => ['turn-tail', 'user', 'steering', 'turn-error', 'turn-max-tokens'].includes(entry.options.key)), 'native final actions and error messages remain installed');
});

test('real streamed deltas stay visible while tools and previous steps remain collapsed', () => {
  const first = assistant(1, '正在检查', false), runningTool = tool(2, false);
  const f = fixture([first, runningTool]);
  assert.match(f.text(), /正在调用工具：list_files/); assert.doesNotMatch(f.text(), /report.csv/);
  let answer = assistant(3, '新', false);
  f.setRows([first, runningTool, answer]); f.render();
  assert.equal(f.all(entry => entry.type === 'native-assistant').length, 1);
  assert.equal(f.all(entry => entry.type === 'native-assistant')[0].props.node.data.status, 'running');
  assert.match(f.text(), /新/); assert.doesNotMatch(f.text(), /正在检查/);
  answer = assistant(3, '新的增量文字', false);
  f.setRows([first, tool(2), answer]); f.render();
  assert.match(f.text(), /新的增量文字/); assert.match(f.text(), /正在回复/);
  answer = assistant(3, '完整结果', true);
  f.setRows([first, tool(2), answer]); f.render();
  assert.match(f.text(), /完整结果/); assert.equal(f.all(entry => entry.props.role === 'status').length, 0);
});

test('reasoning is collapsed independently of streaming text and retains native images and file interfaces', () => {
  const image = { kind: 'image', attachment: { id: 'image-ref' } };
  const answer = assistant(2, '可以下载报告', false, [{ kind: 'reasoning', text: '推理细节' }, image]);
  const f = fixture([answer]);
  const native = f.all(entry => entry.type === 'native-assistant')[0];
  assert.deepEqual(native.props.node.data.blocks.map(block => block.kind), ['text', 'image']);
  assert.equal(native.props.node.data.blocks[1], image); assert.equal(typeof native.props.fileMentions, 'function');
  assert.equal(typeof native.props.renderMessageImages, 'function'); assert.equal(typeof native.props.useTurnData, 'function');
  assert.doesNotMatch(f.text(), /推理细节/); f.toggle(); assert.match(f.text(), /推理细节/);
});

test('live status follows actual reasoning and document tools without revealing host paths', () => {
  const thinking=assistant(1,'',false,[{kind:'reasoning',text:'private thought'}]);
  const f=fixture([thinking]);assert.match(f.text(),/正在思考/);assert.doesNotMatch(f.text(),/private thought/);
  const reading=tool(2,false);reading.data.root.name='mcp__files__read_file';reading.data.root.argsRaw=JSON.stringify({name:'实验资料.pdf'});
  f.setRows([thinking,reading]);f.render();assert.match(f.text(),/正在阅读文档：实验资料.pdf/);
  reading.data.root.argsRaw=JSON.stringify({path:'/home/private/server.pdf'});f.render();assert.doesNotMatch(f.text(),/home|private|server.pdf/);
  reading.data.root.name='web_search';f.render();assert.match(f.text(),/正在搜索资料/);
  reading.data.root.name='exec_command';f.render();assert.match(f.text(),/正在执行命令/);
});

test('new sessions do not inherit expansion, and absent assistant still presents running tools', () => {
  const f = fixture([node('context', 1, { content: [{ type: 'text', text: '资料' }] }, false), tool(2, false)]);
  assert.match(f.text(), /正在调用工具：list_files/); assert.doesNotMatch(f.text(), /report.csv/);
  f.toggle(); assert.match(f.text(), /report.csv/);
  f.setSession('session-b'); f.render(); assert.doesNotMatch(f.text(), /report.csv/);
  assert.equal(f.all(entry => entry.type === 'button')[0].props['aria-expanded'], false);
});

test('interrupted and incomplete history keep the last content-bearing reply outside the process', () => {
  const interrupted = assistant(2, '已生成的部分回答'); interrupted.data.status = 'interrupted';
  const f = fixture([tool(1), interrupted, assistant(3, ''), node('turn-error', 4, { message: '连接中断' })]);
  assert.match(f.text(), /已生成的部分回答/); assert.doesNotMatch(f.text(), /report.csv/);
  assert.equal(f.all(entry => entry.type === 'native-assistant')[0].props.node.data.status, 'interrupted');
  assert.equal(f.all(entry => entry.type === 'turn-error').length, 1);
});

test('native Compact cannot hide the product answer when an extension block follows prose', () => {
  const final = assistant(4, '', true, [{ kind: 'extension', block: { type: 'custom-result' } }]);
  const f = fixture([assistant(1, '早期回复'), tool(2), assistant(3, '保留这条最终文字'), final], { compactAnswerStep: 4 });
  assert.match(f.text(), /保留这条最终文字/); assert.doesNotMatch(f.text(), /早期回复|report.csv/);
  assert.equal(f.all(entry => entry.type === 'button').length, 1);
  f.toggle(); assert.match(f.text(), /早期回复|report.csv/);
  assert.equal(f.all(entry => entry.type === 'native-assistant' && entry.props.node.data.blocks.some(block => block.text === '保留这条最终文字')).length, 1);
});

test('timeline closure is shared even while earlier node locations still describe an open turn', () => {
  const f = fixture([assistant(1, '旧回答', false), tool(2), assistant(3, '最后回答', false), assistant(4, '', false)], { turnStatus: 'closed' });
  assert.match(f.text(), /最后回答/); assert.equal(f.all(entry => entry.type === 'native-assistant').length, 1);
  assert.equal(f.all(entry => entry.props.role === 'status').length, 0);
});


test('ordinary Chat installs approved command file mentions, previews and independent downloads after completion',async()=>{
 const deliveryResponse={session_id:'session-a',id:'native-task-a',turn:1,presentation:'single',lanes:{baseline:{artifacts:[{id:'file-one',name:'outputs/code/pelican.html',bytes:17}]}}};
 const f=fixture([tool(2),assistant(3,'动画：`pelican.html`')],{deliveryResponse});
 await f.flushDelivery();
 const native=f.all(row=>row.type==='native-assistant')[0],mentions=native.props.fileMentions();
 assert.equal(mentions.resolve('pelican.html').title,'pelican.html');assert.equal(mentions.resolve('/etc/passwd'),undefined);
 mentions.resolve('/work/outputs/pelican.html').open();assert.match(f.opened(),/^dsh-resource:\/\/geneloop-delivery\/session-a\/native-task-a\/baseline\/file-one\/pelican.html$/);
 const preview=f.all(row=>row.type==='button'&&row.children.includes('预览 pelican.html'))[0];assert.ok(preview);preview.props.onClick();
 const download=f.all(row=>row.type==='a'&&row.props.download==='pelican.html')[0];assert.match(download.props.href,/^\/api\/harless\/deliveries\?/);assert.match(download.props.href,/file=file-one/);
});
