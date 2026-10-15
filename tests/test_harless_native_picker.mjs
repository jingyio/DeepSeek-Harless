import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
const controllerSource = readFileSync(new URL('../node_modules/@deepseek-ai/dsh-client-ui-input-trigger/lib/client.js', import.meta.url), 'utf8');
function nativeController(trigger, input, sessionId = 'alice') {
  let registered;
  const events = [];
  runInNewContext(controllerSource, { window: { __ModuleLoader__: { load(spec) { registered = spec; } } }, AbortController, console });
  const { InputTriggerController } = registered.factory(name => name === '@deepseek-ai/cordis' ? { Service: class {} }
    : name === '@deepseek-ai/dsh-client-store' ? { createSnapshotStore(initial) {
      let value = initial; const listeners = new Set();
      return { getSnapshot: () => value, set(next) { value = next; for (const fn of listeners) fn(); },
        subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); } };
    } } : {});
  const controller = new InputTriggerController({ sessionId, roster: { all: () => [trigger], sources: char => char === '/' ? [trigger] : [] },
    actx: { bail(_scope, event, args) { events.push({ event, args }); return event === 'slash/input-insert-reference' ? input.insertReference(args.reference, args.span) : undefined; } } });
  return { controller, events, track() { const state = input.state.getSnapshot(); controller.track(state.draft, state.draft.length, { tier: 'plain' }, state.draftRev); } };
}
async function flush() { for (let i = 0; i < 20; i++) await new Promise(resolve => setImmediate(resolve)); }
function fixture({ locked = false, beforePost, beforeGet, onOpen, allAvailable = false } = {}) {
  const scenes = [{ id: 'ppt', label: 'PPT', available: true },
    { id: 'paper-proofreading', label: 'Paper', available: false, unavailable_reason: 'missing_backend' },
    { id: 'research-data-analysis', label: 'Data', available: false },
    { id: 'new-scene', label: 'Chat', available: true }];
  if (allAvailable) for (const scene of scenes) scene.available = true;
  const values = new Map(), inputs = new Map(), faces = new Map(), retirements = new Map(), posts = [], opened = [], rebinds = [], reads = [], submissions = [], blocks = new Map(), statusUpdates = [];
  let registered, decoration, trigger, statusComponent, freshCount = 0;
  function makeInput(id, draft = '/p 请生成报告') {
    values.set(id, { selection: { scene: 'new-scene', mode: 'baseline', rsi: true }, scenes, scene_locked: locked });
    let state = { draft, draftRev: 1, phase: 'plain', attachmentIds: [] }; const listeners = new Set();
    const update = next => { state = next; for (const listener of listeners) listener(); };
    const input = { inserts: [], notices: [], state: { getSnapshot: () => state, subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); } },
      setPhase(phase) { update({ ...state, phase }); },
      setDraft(draft) { update({ ...state, draft, draftRev: state.draftRev + 1 }); },
      insertReference(ref, span) {
        if (this.failInsert || span.draftRev !== state.draftRev || state.phase !== 'plain') return false;
        const suffix = state.draft.slice(span.end), separator = suffix.startsWith(' ') ? '' : ' ';
        this.inserts.push(ref); this.setDraft(state.draft.slice(0, span.start) + ref.clipboardText + separator + suffix); return true;
      },
      submit() { submissions.push({ id, ...structuredClone(state) }); },
      notify(level, text) { this.notices.push({ level, text }); },
      addAttachments(ids) { state = { ...state, attachmentIds: ids }; return true; },
      removeAttachment(id) { state = { ...state, attachmentIds: state.attachmentIds.filter(row => row !== id) }; },
    };
    inputs.set(id, input); return input;
  }
  makeInput('alice'); makeInput('bob');
  for (const id of inputs.keys()) faces.set(id, { beginSubmission(value) { retirements.set(id, value.onRetire); return { requestId: 'request-' + id }; } });
  const fetch = async (url, init) => {
    const body = init.method === 'POST' ? JSON.parse(init.body) : undefined;
    if (body) { posts.push(body); await beforePost?.(body, inputs); }
    const id = body?.session_id || body?.inherit_session || new URL(url, 'http://fixture').searchParams.get('session_id');
    if (!body) { reads.push(id); if (reads.length > 20) throw Error('Unbounded settings GET loop'); }
    let value = values.get(id);
    if (!body && beforeGet) { const snapshot = structuredClone(value); await beforeGet(); return { ok:true,json:async()=>snapshot }; }
    if (body?.action === 'new_session') {
      const freshId = ++freshCount === 1 ? 'fresh' : 'fresh' + freshCount;
      makeInput(freshId, ''); value = values.get(freshId); value.session_id = freshId;
    }
    if (body) value.selection = { ...value.selection, ...body.selection };
    if (body?.action === 'set_scene_options') value.scene_options = body.options;
    return { ok: true, json: async () => structuredClone(value) };
  };
  runInNewContext(source, { window: { __ModuleLoader__: { load(spec) { registered = spec; } } }, fetch, AbortController, setTimeout, clearTimeout });
  let current = 'alice'; const sessionListeners = new Set();
  const setCurrent = id => { current = id; for (const fn of sessionListeners) fn(); };
  const sessions = { scope: id => inputs.has(id) ? { id } : undefined, binding: id => ({ session: faces.get(id) }), refresh: async () => {}, open(id) { opened.push(id); setCurrent(id); onOpen?.(id, inputs); },
    list: { getSnapshot: () => ({ current }), subscribe(fn) { sessionListeners.add(fn); return () => sessionListeners.delete(fn); } } };
  registered.factory(name => name === 'react' ? {
    useState: initial => [initial, value => statusUpdates.push(value)], useEffect: effect => effect(),
    createElement: (type, props, ...children) => ({ type, props, children }),
  } : undefined).apply({
    get: name => ({ commandUi: { decorate(spec) { decoration = spec; return () => {}; }, popupFor: () => ({ dismiss() {} }) },
      inputTriggers: { registerSource(spec) { trigger = spec; return () => {}; } }, sessions,
      conversation: { input: { for: scope => inputs.get(scope.id) }, rebindDraftFiles: (id, ids) => rebinds.push({ id, ids }),
        blocks: { storeFor: id => ({ getSnapshot: () => blocks.get(id) }), set: (id, value) => value ? blocks.set(id, value) : blocks.delete(id) } } })[name],
    uiConversation: { events: { register() { return () => {}; } } },
    effect: install => install(), slots: { inject(_name, install) { install(); }, register(spec, component) { if(spec.name==='conversation.input.left')statusComponent = component; } },
  });
  const pick = async (id, scene = 'ppt', tokenLength = 2) => {
    const input = inputs.get(id), rev = input.state.getSnapshot().draftRev;
    trigger.onPick({ session: { sessionId: id }, candidate: { value: scene }, span: { start: 0, end: tokenLength, draftRev: rev } });
    for (let i = 0; i < 15; i++) await new Promise(resolve => setImmediate(resolve));
  };
  return { decoration, trigger, inputs, posts, opened, values, pick, statusComponent, rebinds, reads, submissions, blocks, setCurrent,
    statusUpdates, faces, retirements, observeStatus: (sessionId = 'alice') => statusComponent({ sessionId, openSession: id => sessions.open(id) }) };
}
test('Scene slash source filters each prefix and uses native reference chips', async () => {
  const f = fixture(), session = { sessionId: 'alice' };
  for (const [query, names] of [['', ['ppt','paper','data','chat']], ['p', ['ppt','paper']], ['pp', ['ppt']], ['ppt', ['ppt']], ['pptx', []]]) {
    const rows = await f.trigger.candidates(session, { query, position: 'leading', signal: new AbortController().signal });
    assert.deepEqual(Array.from(rows, row => row.name), names);
  }
  assert.equal((await f.trigger.candidates(session, { query:'p', position:'inline' })).length, 0);
  await f.pick('alice');
  const input = f.inputs.get('alice');
  assert.equal(input.state.getSnapshot().draft, '/ppt 请生成报告');
  assert.equal(input.inserts[0].label, '/ppt'); assert.equal(input.inserts[0].source, 'harless-scenes');
  assert.equal(await f.trigger.codec.serialize('ppt'), '/ppt');
  assert.equal(f.values.get('alice').selection.scene, 'ppt');
  assert.equal(f.values.get('bob').selection.scene, 'new-scene');
  assert.equal(typeof f.statusComponent, 'function');
});
test('Choosing PPT from /harless retains a visible token and preserves other draft text', async () => {
  const f = fixture(), session = { sessionId: 'alice' };
  f.inputs.get('alice').setDraft('/harless 请生成报告');
  const rows = await f.decoration.ui.options(session, new AbortController().signal);
  assert.deepEqual(Array.from(rows.slice(0,4), row => row.label), ['/ppt','/paper','/data','/chat']);
  await f.decoration.ui.onSelect(rows[0], session);
  assert.equal(f.inputs.get('alice').state.getSnapshot().draft, '/ppt 请生成报告');
  assert.equal(f.inputs.get('alice').inserts.length, 1);
  await f.decoration.ui.onSelect(rows.find(row => row.id === 'mode:shadow'), session);
  assert.equal(f.values.get('alice').selection.mode, 'shadow');
});
test('Flat native task options preserve other options and refuse frozen or unoffered choices', async () => {
  const f=fixture(),session={sessionId:'alice'},current=f.values.get('alice');
  current.selection.scene='ppt';current.scene_options={slides:6,template:'academic'};
  current.scene_option_fields=[{key:'slides',label:'页数',default:6,values:[{value:6,label:'6 页'},{value:12,label:'12 页'}]}];
  const before=f.inputs.get('alice').state.getSnapshot().draft;
  const rows=await f.decoration.ui.options(session,new AbortController().signal);
  const choice=rows.find(row=>row.id==='option:slides=12');assert.ok(choice);
  await f.decoration.ui.onSelect(choice,session);
  assert.equal(current.scene_options.slides,12);assert.equal(current.scene_options.template,'academic');
  assert.equal(f.inputs.get('alice').state.getSnapshot().draft,before);
  const count=f.posts.length;
  await assert.rejects(f.decoration.ui.onSelect({id:'option:slides=999'},session),/未知/);
  current.scene_locked=true;
  assert.ok(!(await f.decoration.ui.options(session,new AbortController().signal)).some(row=>row.id.startsWith('option:')));
  await assert.rejects(f.decoration.ui.onSelect(choice,session),/已固定/);
  assert.equal(f.posts.length,count);
});
test('Changing a started scene keeps the visible session, draft and attachments', async () => {
  const f = fixture({ locked:true, allAvailable:true }), old = f.inputs.get('alice'); old.addAttachments(['receipt']);
  f.values.get('alice').selection.scene='research-data-analysis';
  await f.pick('alice');
  assert.equal(f.values.get('alice').selection.scene,'ppt');
  assert.equal(old.state.getSnapshot().draft,'/ppt 请生成报告');
  assert.deepEqual(old.state.getSnapshot().attachmentIds,['receipt']);
  assert.deepEqual(f.opened,[]);assert.deepEqual(f.rebinds,[]);
  assert.ok(f.posts.every(row=>row.action==='select'&&row.session_id==='alice'));
});

test('A draft edited during a scene request is preserved without applying a stale insertion', async () => {
  const f = fixture({ beforePost: async (_body, inputs) => inputs.get('alice').setDraft('新写的文字') });
  await f.pick('alice');
  assert.equal(f.inputs.get('alice').state.getSnapshot().draft, '新写的文字');
  assert.equal(f.inputs.get('alice').inserts.length, 0);
});
test('Unavailable scenes fail before changing the saved selection or editor', async () => {
  const f = fixture(); await f.pick('alice', 'paper-proofreading');
  assert.equal(f.posts.length, 0); assert.equal(f.inputs.get('alice').inserts.length, 0);
  assert.match(f.inputs.get('alice').notices[0].text, /暂不可用/);
});

test('A late settings read cannot overwrite the scene published after selection', async () => {
  let release, reads=0, notifications=0;
  const waiting=new Promise(resolve=>{release=resolve;});
  const f=fixture({beforeGet:async()=>{if(++reads===1) await waiting;}});
  const session={sessionId:'alice'};
  f.trigger.subscribeLexicon(session,()=>notifications++);
  const stale=f.trigger.candidates(session,{query:'p',position:'leading'});
  await f.pick('alice');const before=notifications;release();await stale;
  assert.equal(notifications,before);assert.equal(f.values.get('alice').selection.scene,'ppt');
});

test('Real native controller warms once and never loops settings GETs through lexicon invalidation', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice'); input.setDraft('/');
  const n = nativeController(f.trigger, input); n.track(); await flush();
  assert.ok(f.reads.length <= 2, `unexpected settings loop: ${f.reads.length}`);
  const count = f.reads.length;
  for (const [query, names] of [['p', ['ppt', 'paper']], ['d', ['data']], ['da', ['data']], ['dat', ['data']], ['data', ['data']], ['datax', []], ['pp', ['ppt']], ['', ['ppt','paper','data','chat']]]) {
    input.setDraft('/' + query); n.track(); await flush();
    const group = n.controller.menu.getSnapshot().groups.find(row => row.source === 'harless-scenes');
    assert.deepEqual(Array.from(group?.items || [], row => row.name), names);
  }
  assert.equal(f.reads.length, count, 'per-character candidates use the hot scene catalog');
  assert.deepEqual(Array.from(n.controller.lexicon.getSnapshot().get('/')), ['ppt','paper','data','chat']);
  // A settings refresh / scene selection does not re-publish an unchanged roll.
  let changes = 0; const off = n.controller.lexicon.subscribe(() => changes++);
  await f.decoration.ui.options({ sessionId: 'alice' }, new AbortController().signal);
  await flush(); assert.equal(changes, 0); off(); n.controller.dispose();
});

test('Real native controller space and menu picks insert the same addressed scene reference', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice');
  const n = nativeController(f.trigger, input); await flush();
  input.setDraft('/data'); n.track(); await flush();
  assert.equal(n.controller.onSpace(), true);
  assert.equal(n.events[0].event, 'slash/input-insert-reference');
  assert.equal(input.inserts[0].label, '/data');
  assert.equal(input.inserts[0].source, 'harless-scenes');
  assert.equal(input.state.getSnapshot().draft, '/data ');
  input.setDraft('/d'); n.track(); await flush(); n.controller.pick('harless-scenes', 0); await flush();
  assert.equal(input.state.getSnapshot().draft, '/data ');
  assert.equal(f.values.get('alice').selection.scene, 'research-data-analysis');
  assert.equal(f.values.get('bob').selection.scene, 'new-scene');
  n.controller.dispose();
});

test('A stale PPT candidate cannot apply to a current /d span or a changed revision', async () => {
  const f = fixture({ allAvailable: true }), session = { sessionId: 'alice' }, input = f.inputs.get('alice');
  await f.trigger.candidates(session, { query: 'p', position: 'leading' });
  input.setDraft('/d'); await f.pick('alice', 'ppt');
  assert.equal(f.posts.length, 0); assert.equal(input.inserts.length, 0); assert.equal(input.state.getSnapshot().draft, '/d');
  assert.match(input.notices.at(-1).text, /候选已更新/);
  const rev = input.state.getSnapshot().draftRev; input.setDraft('/p');
  f.trigger.onPick({ session, candidate: { value: 'ppt' }, span: { start: 0, end: 2, draftRev: rev } });
  await flush(); assert.equal(f.posts.length, 0); assert.match(input.notices.at(-1).text, /输入已改变/);
});

test('Real native enter adjudication routes typed complete scenes before allowing the default send', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice');
  const n = nativeController(f.trigger, input); await flush();
  for (const [line, scene] of [['/ppt 做科研汇报', 'ppt'], ['/data分析数据', 'research-data-analysis'], ['/paper 校对论文', 'paper-proofreading']]) {
    input.setDraft(line); input.setPhase('adjudicating');
    assert.equal(await n.controller.adjudicate(line, new AbortController().signal, { attachments: 0 }), undefined);
    assert.equal(f.values.get('alice').selection.scene, scene);
    assert.equal(input.state.getSnapshot().draft, line, 'default native send retains the original request');
    input.setDraft(''); // Native commit clears while leaving adjudication, not a user deletion.
    input.setPhase('plain');
  }
  const count = f.posts.length;
  for (const line of ['/p 做报告', '/pptx 做报告', '/ppt/file.pdf', '/ppt.md', '/feedback hi']) {
    input.setDraft(line);
    assert.equal(await n.controller.adjudicate(line, new AbortController().signal, { attachments: 0 }), undefined);
  }
  assert.equal(f.posts.length, count, 'a partial token, path, or other command must not select a scene');
  assert.equal(f.values.get('bob').selection.scene, 'new-scene'); n.controller.dispose();
});

test('Typed selection failure blocks default submit and retains the addressed draft and attachments', async () => {
  const f = fixture(), input = f.inputs.get('alice'); input.setDraft('/data 分析'); input.addAttachments(['csv']);
  const n = nativeController(f.trigger, input); await flush(); input.setPhase('adjudicating');
  await assert.rejects(n.controller.adjudicate('/data 分析', new AbortController().signal, { attachments: 1 }), /暂不可用/);
  assert.equal(f.posts.length, 0); assert.equal(input.state.getSnapshot().draft, '/data 分析');
  assert.deepEqual(input.state.getSnapshot().attachmentIds, ['csv']); n.controller.dispose();
});

test('A typed PPT prefix followed immediately by Chinese overrides a previous Data selection on Enter', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice');
  f.values.get('alice').selection.scene = 'research-data-analysis';
  const n = nativeController(f.trigger, input); await flush();
  input.setDraft('/ppt中文报告'); n.track(); await flush();
  assert.equal(n.controller.onSpace(), false, 'space after request text must not pick a former candidate');
  assert.equal(input.inserts.length, 0); assert.equal(f.posts.length, 0);
  input.setDraft('/ppt中文报告 '); input.setPhase('adjudicating');
  assert.equal(await n.controller.adjudicate('/ppt中文报告', new AbortController().signal, { attachments: 0 }), undefined);
  assert.equal(f.values.get('alice').selection.scene, 'ppt');
  assert.equal(input.state.getSnapshot().draft, '/ppt中文报告 ');
  assert.equal(f.posts.length, 1); assert.equal(f.posts[0].selection.scene, 'ppt');
  n.controller.dispose();
});

test('Typed Enter on a started scene routes the existing conversation before native submit', async () => {
  const f=fixture({locked:true}),input=f.inputs.get('alice');input.setDraft('/ppt 做科研汇报');input.addAttachments(['paper']);
  const n=nativeController(f.trigger,input);await flush();input.setPhase('adjudicating');
  assert.equal(await n.controller.adjudicate('/ppt 做科研汇报',new AbortController().signal,{attachments:1}),undefined);
  assert.equal(f.values.get('alice').selection.scene,'ppt');
  assert.equal(input.state.getSnapshot().draft,'/ppt 做科研汇报');
  assert.deepEqual(input.state.getSnapshot().attachmentIds,['paper']);
  assert.deepEqual(f.opened,[]);assert.equal(f.submissions.length,0,'native input owns the one submit');n.controller.dispose();
});

test('A manual scene pick preserves attachments edited while the server prepares the scene', async () => {
  const f=fixture({locked:true,allAvailable:true,beforePost:async(body,inputs)=>{
    if(body.action==='select'){const input=inputs.get('alice');input.removeAttachment('old');input.addAttachments(['new']);}
  }}),input=f.inputs.get('alice');
  await f.trigger.candidates({sessionId:'alice'},{query:'p',position:'leading'});
  input.setDraft('/p 计划');input.addAttachments(['old']);await f.pick('alice');
  assert.equal(f.values.get('alice').selection.scene,'ppt');assert.deepEqual(input.state.getSnapshot().attachmentIds,['new']);
  assert.equal(input.notices.length,0);assert.equal(f.submissions.length,0);assert.equal(f.opened.length,0);
});

test('A failed native reference insertion leaves the started conversation unsent', async () => {
  const f=fixture({locked:true,allAvailable:true}),input=f.inputs.get('alice');
  await f.trigger.candidates({sessionId:'alice'},{query:'p',position:'leading'});
  input.setDraft('/p 保留草稿');input.addAttachments(['paper']);input.failInsert=true;await f.pick('alice');
  assert.equal(f.posts.length,0);assert.equal(f.submissions.length,0);assert.equal(f.opened.length,0);
  assert.equal(input.state.getSnapshot().draft,'/p 保留草稿');assert.deepEqual(input.state.getSnapshot().attachmentIds,['paper']);
  assert.match(input.notices.at(-1).text,/输入已改变/);
});

test('Scene selection never creates a target that could overwrite another conversation draft', async () => {
  const f=fixture({locked:true,allAvailable:true}),input=f.inputs.get('alice'),other=f.inputs.get('bob');
  other.setDraft('另一份草稿');other.addAttachments(['other-file']);await f.pick('alice');
  assert.equal(f.inputs.size,2);assert.equal(f.opened.length,0);assert.equal(f.submissions.length,0);
  assert.equal(other.state.getSnapshot().draft,'另一份草稿');assert.deepEqual(other.state.getSnapshot().attachmentIds,['other-file']);
});

test('Aborted typed selection never creates or submits a session and keeps the original draft', async () => {
  const f=fixture({locked:true}),input=f.inputs.get('alice');input.setDraft('/ppt 保留');
  const n=nativeController(f.trigger,input);await flush();const abort=new AbortController();abort.abort();input.setPhase('adjudicating');
  await assert.rejects(n.controller.adjudicate('/ppt 保留',abort.signal,{attachments:0}));
  assert.equal(f.posts.length,0);assert.equal(f.submissions.length,0);assert.equal(input.state.getSnapshot().draft,'/ppt 保留');n.controller.dispose();
});

test('Leaving a session during a failed scene pick aborts the request and suppresses its old toast', async () => {
  let resume, reached; const waiting = new Promise(resolve => { resume = resolve; }); const posted = new Promise(resolve => { reached = resolve; });
  const f = fixture({ beforePost: async () => { reached(); await waiting; throw Error('PPT mount failed'); } });
  const pick = f.pick('alice'); await posted; f.setCurrent('bob'); resume(); await pick;
  assert.equal(f.inputs.get('alice').inserts.length, 0); assert.equal(f.inputs.get('alice').notices.length, 0);
  assert.equal(f.inputs.get('bob').notices.length, 0); assert.equal(f.inputs.get('bob').state.getSnapshot().draft, '/p 请生成报告');
  assert.equal(f.opened.length, 0);
});

test('Leaving during typed select cancels adjudication without sending in either session', async () => {
  let resume, reached; const waiting = new Promise(resolve => { resume = resolve; }); const posted = new Promise(resolve => { reached = resolve; });
  const f = fixture({ beforePost: async () => { reached(); await waiting; throw Error('PPT mount failed'); } }), input = f.inputs.get('alice');
  const n = nativeController(f.trigger, input); await flush(); input.setDraft('/ppt 论文报告'); input.setPhase('adjudicating');
  const attempt = n.controller.adjudicate('/ppt 论文报告', new AbortController().signal, { attachments: 0 });
  await posted; f.setCurrent('bob'); resume(); assert.equal(await attempt, 'handled');
  input.setPhase('plain'); await flush(); assert.equal(f.submissions.length, 0);
  assert.equal(input.state.getSnapshot().draft, '/ppt 论文报告'); assert.equal(input.notices.length, 0); n.controller.dispose();
});

test('Choosing a scene shows its native chip before a delayed backend responds', async()=>{
  let release; const gate=new Promise(resolve=>release=resolve);
  const f=fixture({allAvailable:true,beforePost:()=>gate}), input=f.inputs.get('alice'), session={sessionId:'alice'};
  await f.trigger.candidates(session,{query:'d',position:'leading'}); input.setDraft('/d');
  f.trigger.onPick({session,candidate:{value:'research-data-analysis'},span:{start:0,end:2,draftRev:input.state.getSnapshot().draftRev}});
  assert.equal(input.inserts.at(-1).label,'/data');
  assert.equal(input.state.getSnapshot().draft,'/data ');
  assert.equal(f.values.get('alice').selection.scene,'new-scene');
  release(); await flush(); assert.equal(f.values.get('alice').selection.scene,'research-data-analysis');
});

test('A rejected optimistic pick restores unchanged text and keeps attachments', async()=>{
  const f=fixture({allAvailable:true,beforePost:()=>{throw Error('fixture unavailable');}}), input=f.inputs.get('alice'), session={sessionId:'alice'};
  await f.trigger.candidates(session,{query:'d',position:'leading'}); input.setDraft('/d 计划');input.addAttachments(['data']);
  await f.pick('alice','research-data-analysis');
  assert.equal(input.state.getSnapshot().draft,'/d 计划'); assert.deepEqual(input.state.getSnapshot().attachmentIds,['data']);
  assert.match(input.notices.at(-1).text,/fixture unavailable/);
});

test('Typing after an immediate scene chip is normal and never sends or loses those edits', async()=>{
 let release;const gate=new Promise(resolve=>release=resolve);
 const f=fixture({allAvailable:true,beforePost:()=>gate}),input=f.inputs.get('alice'),session={sessionId:'alice'};
 await f.trigger.candidates(session,{query:'d',position:'leading'});input.setDraft('/d');
 f.trigger.onPick({session,candidate:{value:'research-data-analysis'},span:{start:0,end:2,draftRev:input.state.getSnapshot().draftRev}});
 input.setDraft('/data 请帮我规划分析');input.addAttachments(['latest']);release();await flush();
 assert.equal(input.state.getSnapshot().draft,'/data 请帮我规划分析');assert.deepEqual(input.state.getSnapshot().attachmentIds,['latest']);
 assert.equal(input.notices.length,0);assert.equal(f.submissions.length,0);
 assert.equal(f.values.get('alice').selection.scene,'research-data-analysis');
});

test('Deleting a selected scene token resets only its session and preserves remaining text and files', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice'), session = { sessionId: 'alice' };
  await f.trigger.candidates(session, { query: 'd', position: 'leading' }); input.setDraft('/d 分析计划');
  await f.pick('alice', 'research-data-analysis'); input.addAttachments(['csv']);
  input.setDraft('分析计划');
  assert.match(f.blocks.get('alice').reason, /普通对话/);
  await flush();
  assert.equal(f.values.get('alice').selection.scene, 'new-scene');
  assert.equal(input.state.getSnapshot().draft, '分析计划'); assert.deepEqual(input.state.getSnapshot().attachmentIds, ['csv']);
  assert.equal(f.blocks.has('alice'), false); assert.equal(f.submissions.length, 0);
  assert.equal(f.posts.filter(row => row.selection?.scene === 'new-scene').length, 1);
  assert.equal(f.posts.some(row => row.session_id === 'bob'), false);
});

test('Backspacing a manually typed complete token to a partial prefix clears the old scene', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice'), session = { sessionId: 'alice' };
  f.values.get('alice').selection.scene = 'research-data-analysis';
  await f.trigger.candidates(session, { query: 'd', position: 'leading' });
  input.setDraft('/data'); input.setDraft('/dat'); await flush();
  assert.equal(f.values.get('alice').selection.scene, 'new-scene');
  assert.equal(input.state.getSnapshot().draft, '/dat');
  const count = f.posts.length;
  input.setDraft('/da'); input.setDraft('/d'); input.setDraft(''); await flush();
  assert.equal(f.posts.length, count, 'partial prefixes must not repeatedly rebind a scene');
});

test('Deleting an optimistic chip waits for its mount and then clears it, never restoring a late result', async () => {
  let release, reached; const gate = new Promise(resolve => release = resolve), posted = new Promise(resolve => reached = resolve);
  const f = fixture({ allAvailable: true, beforePost: async body => {
    if (body.selection?.scene === 'research-data-analysis') { reached(); await gate; }
  } }), input = f.inputs.get('alice'), session = { sessionId: 'alice' };
  await f.trigger.candidates(session, { query: 'd', position: 'leading' }); input.setDraft('/d');
  const pick = f.pick('alice', 'research-data-analysis'); await posted;
  f.observeStatus(); await flush();
  input.setDraft('普通问题'); assert.match(f.blocks.get('alice').reason, /普通对话/);
  assert.equal(f.statusUpdates.at(-1).selection.scene, 'new-scene', 'the visible mode changes before the old mount finishes');
  const cancelledAt = f.statusUpdates.length;
  release(); await pick; await flush();
  assert.deepEqual(f.posts.map(row => row.selection.scene), ['research-data-analysis', 'new-scene']);
  assert.equal(f.values.get('alice').selection.scene, 'new-scene');
  assert.equal(input.state.getSnapshot().draft, '普通问题'); assert.equal(input.inserts.length, 1);
  assert.equal(input.notices.length, 0); assert.equal(f.blocks.has('alice'), false);
  assert.ok(f.statusUpdates.slice(cancelledAt).every(value => value.selection.scene === 'new-scene'), 'late scene reads and mount results cannot restore the cancelled badge');
});

test('Only accepted submission resets the next input to Chat without changing the running scene', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice'), session = { sessionId: 'alice' };
  f.values.get('alice').selection.scene = 'research-data-analysis'; input.setDraft('');
  f.trigger.warm(session); await flush();
  assert.equal(f.posts.length, 0, 'loading an empty composer is not a cancellation');
  input.setDraft('/data 第一轮'); input.setPhase('adjudicating');
  await f.trigger.matchEnter(session, '/data 第一轮', new AbortController().signal);
  let forwarded = 0;
  f.faces.get('alice').beginSubmission({ onRetire: () => forwarded++ });
  input.setDraft(''); input.setPhase('plain'); await flush();
  f.observeStatus(); await flush();
  f.retirements.get('alice')({ reason: 'observed', attachments: [] });
  assert.equal(forwarded, 1);
  assert.equal(f.statusUpdates.at(-1).selection.scene, 'new-scene');
  assert.equal(f.statusUpdates.at(-1).paired_comparison, false);
  f.setCurrent('bob'); f.setCurrent('alice'); input.setDraft('继续上一轮'); await flush();
  // The server, tested separately, consumes its selection at admission. The
  // client must never mount a new preset into an already running task.
  assert.equal(f.values.get('alice').selection.scene, 'research-data-analysis'); assert.equal(f.posts.length, 0);
});

test('Failed admission retains the scene and forwards native attachment recovery', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice');
  await f.pick('alice'); f.observeStatus(); await flush();
  const count = f.posts.length; let reason;
  f.faces.get('alice').beginSubmission({ onRetire: value => { reason = value.reason; } });
  input.setDraft(''); await flush();
  f.retirements.get('alice')({ reason: 'failed' });
  input.setDraft('/ppt 请生成报告'); await flush();
  assert.equal(reason, 'failed'); assert.equal(f.posts.length, count);
  assert.equal(f.statusUpdates.at(-1).selection.scene, 'ppt');
});

test('A late accepted submission cannot erase a scene selected for a newer draft', async () => {
  const f = fixture({ allAvailable: true }), input = f.inputs.get('alice');
  await f.pick('alice'); f.observeStatus(); await flush();
  f.faces.get('alice').beginSubmission({});
  input.setDraft('/data 下一轮'); await f.pick('alice', 'research-data-analysis', 5);
  f.retirements.get('alice')({ reason: 'observed', attachments: [] });
  assert.equal(f.statusUpdates.at(-1).selection.scene, 'research-data-analysis');
  assert.match(input.state.getSnapshot().draft, /^\/data/);
});

test('Deleting a started scene token resets its current conversation without moving input or files', async () => {
  const f=fixture({locked:true,allAvailable:true}),input=f.inputs.get('alice'),session={sessionId:'alice'};
  f.values.get('alice').selection.scene='research-data-analysis';await f.trigger.candidates(session,{query:'d',position:'leading'});
  input.setDraft('/data 另一个问题');input.addAttachments(['draft-file']);input.setDraft('另一个问题');await flush();
  assert.equal(f.values.get('alice').selection.scene,'new-scene');assert.equal(input.state.getSnapshot().draft,'另一个问题');
  assert.deepEqual(input.state.getSnapshot().attachmentIds,['draft-file']);assert.equal(f.opened.length,0);assert.equal(f.rebinds.length,0);
  assert.equal(f.blocks.has('alice'),false);assert.equal(f.submissions.length,0);
});

test('A started scene reset in the background updates only its addressed chat without navigation', async () => {
  let release,reached;const gate=new Promise(resolve=>release=resolve),posted=new Promise(resolve=>reached=resolve);
  const f=fixture({locked:true,allAvailable:true,beforePost:async body=>{if(body.selection?.scene==='new-scene'){reached();await gate;}}});
  const input=f.inputs.get('alice');f.values.get('alice').selection.scene='ppt';
  await f.trigger.candidates({sessionId:'alice'},{query:'p',position:'leading'});input.setDraft('/ppt 草稿');input.addAttachments(['paper']);input.setDraft('草稿');await posted;
  f.setCurrent('bob');release();await flush();
  assert.equal(f.opened.length,0);assert.equal(f.blocks.has('alice'),false);assert.equal(input.state.getSnapshot().draft,'草稿');
  assert.equal(f.values.get('alice').selection.scene,'new-scene');assert.equal(f.inputs.get('bob').state.getSnapshot().draft,'/p 请生成报告');
  assert.deepEqual(input.state.getSnapshot().attachmentIds,['paper']);assert.equal(f.inputs.size,2);
});

test('A new pick made during a pending reset wins after the serialized reset completes', async () => {
  let release, reached; const gate = new Promise(resolve => release = resolve), resetting = new Promise(resolve => reached = resolve);
  const f = fixture({ allAvailable: true, beforePost: async body => {
    if (body.selection?.scene === 'new-scene') { reached(); await gate; }
  } }), input = f.inputs.get('alice'), session = { sessionId: 'alice' };
  await f.trigger.candidates(session, { query: 'd', position: 'leading' }); input.setDraft('/d');
  await f.pick('alice', 'research-data-analysis'); input.setDraft(''); await resetting;
  input.setDraft('/p 新计划'); const nextPick = f.pick('alice', 'ppt');
  assert.equal(input.inserts.at(-1).label, '/ppt');
  input.setDraft('/ppt 新计划，继续补充说明'); input.addAttachments(['new-file']);
  release(); await nextPick; await flush();
  assert.deepEqual(f.posts.map(row => row.selection.scene), ['research-data-analysis', 'new-scene', 'ppt']);
  assert.equal(f.values.get('alice').selection.scene, 'ppt'); assert.equal(input.state.getSnapshot().draft, '/ppt 新计划，继续补充说明');
  assert.deepEqual(input.state.getSnapshot().attachmentIds, ['new-file']);
  assert.equal(input.notices.length, 0); assert.equal(f.blocks.has('alice'), false);
});

test('A late cold settings read cannot revive a manually typed scene deleted before its catalog loaded', async () => {
  let release; const gate = new Promise(resolve => release = resolve);
  const f = fixture({ allAvailable: true, beforeGet: () => gate }), input = f.inputs.get('alice'), session = { sessionId: 'alice' };
  f.values.get('alice').selection.scene = 'research-data-analysis';
  const waiting = f.trigger.candidates(session, { query: '', position: 'leading' });
  input.setDraft('/data'); input.setDraft(''); await flush();
  assert.equal(f.values.get('alice').selection.scene, 'new-scene');
  release(); await waiting; await flush();
  assert.equal(f.values.get('alice').selection.scene, 'new-scene');
  assert.equal(f.posts.length, 1); assert.equal(f.blocks.has('alice'), false);
});

test('A backend scene-switch failure retains the original draft and cannot create a surprise conversation', async () => {
  const f=fixture({locked:true,allAvailable:true,beforePost:()=>{const error=Error('请等待当前请求完成');error.code='scene_requires_new_session';throw error;}});
  const input=f.inputs.get('alice');input.setDraft('/p 原草稿');input.addAttachments(['original']);await f.pick('alice');
  assert.equal(f.inputs.size,2);assert.equal(f.opened.length,0);assert.equal(f.submissions.length,0);
  assert.equal(input.state.getSnapshot().draft,'/p 原草稿');assert.deepEqual(input.state.getSnapshot().attachmentIds,['original']);
  assert.equal(f.posts.some(row=>row.action==='new_session'),false);
});
