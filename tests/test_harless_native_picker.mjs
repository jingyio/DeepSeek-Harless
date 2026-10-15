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
  const values = new Map(), inputs = new Map(), posts = [], opened = [], rebinds = [], reads = [], submissions = [];
  let registered, decoration, trigger, statusComponent;
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
  const fetch = async (url, init) => {
    const body = init.method === 'POST' ? JSON.parse(init.body) : undefined;
    if (body) { posts.push(body); await beforePost?.(body, inputs); }
    const id = body?.session_id || body?.inherit_session || new URL(url, 'http://fixture').searchParams.get('session_id');
    if (!body) { reads.push(id); if (reads.length > 20) throw Error('Unbounded settings GET loop'); }
    let value = values.get(id);
    if (!body && beforeGet) { const snapshot = structuredClone(value); await beforeGet(); return { ok:true,json:async()=>snapshot }; }
    if (body?.action === 'select' && locked && body.selection.scene !== value.selection.scene)
      return { ok: false, json: async () => ({ error: { code: 'scene_requires_new_session', message: '新建会话' } }) };
    if (body?.action === 'new_session') { makeInput('fresh', ''); value = values.get('fresh'); value.session_id = 'fresh'; }
    if (body) value.selection = { ...value.selection, ...body.selection };
    if (body?.action === 'set_scene_options') value.scene_options = body.options;
    return { ok: true, json: async () => structuredClone(value) };
  };
  runInNewContext(source, { window: { __ModuleLoader__: { load(spec) { registered = spec; } } }, fetch, AbortController, setTimeout, clearTimeout });
  let current = 'alice'; const sessionListeners = new Set();
  const setCurrent = id => { current = id; for (const fn of sessionListeners) fn(); };
  const sessions = { scope: id => inputs.has(id) ? { id } : undefined, refresh: async () => {}, open(id) { opened.push(id); setCurrent(id); onOpen?.(id, inputs); },
    list: { getSnapshot: () => ({ current }), subscribe(fn) { sessionListeners.add(fn); return () => sessionListeners.delete(fn); } } };
  registered.factory(name => name === 'react' ? {} : undefined).apply({
    get: name => ({ commandUi: { decorate(spec) { decoration = spec; return () => {}; }, popupFor: () => ({ dismiss() {} }) },
      inputTriggers: { registerSource(spec) { trigger = spec; return () => {}; } }, sessions,
      conversation: { input: { for: scope => inputs.get(scope.id) }, rebindDraftFiles: (id, ids) => rebinds.push({ id, ids }) } })[name],
    uiConversation: { events: { register() { return () => {}; } } },
    effect: install => install(), slots: { inject(_name, install) { install(); }, register(spec, component) { if(spec.name==='conversation.input.left')statusComponent = component; } },
  });
  const pick = async (id, scene = 'ppt', tokenLength = 2) => {
    const input = inputs.get(id), rev = input.state.getSnapshot().draftRev;
    trigger.onPick({ session: { sessionId: id }, candidate: { value: scene }, span: { start: 0, end: tokenLength, draftRev: rev } });
    for (let i = 0; i < 15; i++) await new Promise(resolve => setImmediate(resolve));
  };
  return { decoration, trigger, inputs, posts, opened, values, pick, statusComponent, rebinds, reads, submissions, setCurrent };
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
test('Changing a locked scene creates a separate session and hands off the draft and attachments', async () => {
  const f = fixture({ locked:true }), old = f.inputs.get('alice'); old.addAttachments(['receipt']);
  await f.pick('alice');
  assert.equal(f.values.get('alice').selection.scene, 'new-scene');
  assert.equal(f.inputs.get('fresh').state.getSnapshot().draft, '/ppt 请生成报告');
  assert.deepEqual(f.opened, ['fresh']); assert.equal(old.state.getSnapshot().draft, '');
  assert.equal(f.rebinds[0].id, 'fresh'); assert.equal(old.state.getSnapshot().attachmentIds.length, 0);
  assert.equal(f.posts.filter(row => row.action === 'new_session').length, 1);
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

test('Typed Enter on a locked scene hands off its native draft and attachments, then submits once', async () => {
  const f = fixture({ locked: true }), input = f.inputs.get('alice'); input.setDraft('/ppt 做科研汇报'); input.addAttachments(['paper']);
  const n = nativeController(f.trigger, input); await flush(); input.setPhase('adjudicating');
  assert.equal(await n.controller.adjudicate('/ppt 做科研汇报', new AbortController().signal, { attachments: 1 }), 'handled');
  assert.equal(f.opened.length, 0); assert.equal(f.submissions.length, 0, 'must wait until the original input is unfrozen');
  input.setPhase('plain'); await flush();
  assert.deepEqual(f.opened, ['fresh']); assert.equal(f.submissions.length, 1); assert.equal(f.submissions[0].id, 'fresh');
  assert.equal(f.submissions[0].draft, '/ppt 做科研汇报'); assert.deepEqual(f.submissions[0].attachmentIds, ['paper']);
  assert.equal(input.state.getSnapshot().draft, ''); assert.deepEqual(input.state.getSnapshot().attachmentIds, []);
  assert.equal(f.values.get('alice').selection.scene, 'new-scene'); n.controller.dispose();
});

test('Attachment changes without a draft revision during handoff preserve the edited draft and never submit removed files', async () => {
  let revision;
  const f = fixture({ locked: true, beforePost: async (body, inputs) => {
    if (body.action !== 'new_session') return;
    const input = inputs.get('alice'); revision = input.state.getSnapshot().draftRev;
    input.removeAttachment('old-paper'); input.addAttachments(['new-paper']);
    assert.equal(input.state.getSnapshot().draftRev, revision, 'native attachment changes do not advance draftRev');
  } }), input = f.inputs.get('alice'); input.setDraft('/ppt 我的报告'); input.addAttachments(['old-paper']);
  const n = nativeController(f.trigger, input); await flush(); input.setPhase('adjudicating');
  assert.equal(await n.controller.adjudicate('/ppt 我的报告', new AbortController().signal, { attachments: 1 }), 'handled');
  input.setPhase('plain'); await flush();
  assert.equal(f.submissions.length, 0); assert.equal(f.opened.length, 0); assert.equal(f.rebinds.length, 0);
  assert.equal(input.state.getSnapshot().draft, '/ppt 我的报告'); assert.equal(input.state.getSnapshot().draftRev, revision);
  assert.deepEqual(input.state.getSnapshot().attachmentIds, ['new-paper']);
  assert.deepEqual(f.inputs.get('fresh').state.getSnapshot().attachmentIds, []);
  assert.match(input.notices.at(-1).text, /附件已改变/); n.controller.dispose();
});

test('A failed native reference insertion cannot turn a retained draft into an automatic submission', async () => {
  let selects = 0;
  const f = fixture({ locked: true, beforePost: async body => {
    if (body.action === 'select' && ++selects === 2) {
      // A concurrently completed selection now allows the same-session route.
      f.values.get('alice').selection.scene = 'ppt'; f.inputs.get('alice').failInsert = true;
    }
  } }), input = f.inputs.get('alice'); input.setDraft('/ppt 保留草稿'); input.addAttachments(['paper']);
  const n = nativeController(f.trigger, input); await flush(); input.setPhase('adjudicating');
  assert.equal(await n.controller.adjudicate('/ppt 保留草稿', new AbortController().signal, { attachments: 1 }), 'handled');
  input.setPhase('plain'); await flush();
  assert.equal(selects, 2); assert.equal(f.submissions.length, 0); assert.equal(input.inserts.length, 0);
  assert.equal(input.state.getSnapshot().draft, '/ppt 保留草稿'); assert.deepEqual(input.state.getSnapshot().attachmentIds, ['paper']);
  assert.match(input.notices.at(-1).text, /请确认后重新发送/); n.controller.dispose();
});

test('A new attachment added to the target before auto-submit keeps the target draft unsent', async () => {
  const f = fixture({ locked: true, onOpen: (id, inputs) => queueMicrotask(() => inputs.get(id).addAttachments(['paper', 'added-after-handoff'])) });
  const input = f.inputs.get('alice'); input.setDraft('/ppt 论文报告'); input.addAttachments(['paper']);
  const n = nativeController(f.trigger, input); await flush(); input.setPhase('adjudicating');
  assert.equal(await n.controller.adjudicate('/ppt 论文报告', new AbortController().signal, { attachments: 1 }), 'handled');
  input.setPhase('plain'); await flush();
  assert.deepEqual(f.opened, ['fresh']); assert.equal(f.submissions.length, 0);
  assert.equal(f.inputs.get('fresh').state.getSnapshot().draft, '/ppt 论文报告');
  assert.deepEqual(f.inputs.get('fresh').state.getSnapshot().attachmentIds, ['paper', 'added-after-handoff']); n.controller.dispose();
});

test('Aborted typed handoff never creates or submits a new session and keeps the old draft', async () => {
  const f = fixture({ locked: true }), input = f.inputs.get('alice'); input.setDraft('/ppt 保留');
  const n = nativeController(f.trigger, input); await flush(); const abort = new AbortController(); input.setPhase('adjudicating');
  assert.equal(await n.controller.adjudicate('/ppt 保留', abort.signal, { attachments: 0 }), 'handled');
  abort.abort(); input.setPhase('plain'); await flush();
  assert.equal(f.posts.some(row => row.action === 'new_session'), false); assert.equal(f.submissions.length, 0);
  assert.equal(input.state.getSnapshot().draft, '/ppt 保留'); n.controller.dispose();
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
