import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
function fixture({ locked = false, beforePost, beforeGet } = {}) {
  const scenes = [{ id: 'ppt', label: 'PPT', available: true },
    { id: 'paper-proofreading', label: 'Paper', available: false, unavailable_reason: 'missing_backend' },
    { id: 'research-data-analysis', label: 'Data', available: false },
    { id: 'new-scene', label: 'Chat', available: true }];
  const values = new Map(), inputs = new Map(), posts = [], opened = [], rebinds = [];
  let registered, decoration, trigger, statusComponent;
  function makeInput(id, draft = '/p 请生成报告') {
    values.set(id, { selection: { scene: 'new-scene', mode: 'baseline', rsi: true }, scenes, scene_locked: locked });
    let state = { draft, draftRev: 1, phase: 'plain', attachmentIds: [] };
    const input = { inserts: [], notices: [], state: { getSnapshot: () => state },
      setDraft(draft) { state = { ...state, draft, draftRev: state.draftRev + 1 }; },
      insertReference(ref, span) {
        if (span.draftRev !== state.draftRev) return false;
        this.inserts.push(ref); this.setDraft(state.draft.slice(0, span.start) + ref.clipboardText + state.draft.slice(span.end)); return true;
      },
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
    let value = values.get(id);
    if (!body && beforeGet) { const snapshot = structuredClone(value); await beforeGet(); return { ok:true,json:async()=>snapshot }; }
    if (body?.action === 'select' && locked && body.selection.scene !== value.selection.scene)
      return { ok: false, json: async () => ({ error: { code: 'scene_requires_new_session', message: '新建会话' } }) };
    if (body?.action === 'new_session') { makeInput('fresh', ''); value = values.get('fresh'); value.session_id = 'fresh'; }
    if (body) value.selection = { ...value.selection, ...body.selection };
    if (body?.action === 'set_scene_options') value.scene_options = body.options;
    return { ok: true, json: async () => structuredClone(value) };
  };
  runInNewContext(source, { window: { __ModuleLoader__: { load(spec) { registered = spec; } } }, fetch, AbortController });
  const sessions = { scope: id => inputs.has(id) ? { id } : undefined, refresh: async () => {}, open: id => opened.push(id) };
  registered.factory(name => name === 'react' ? {} : undefined).apply({
    get: name => ({ commandUi: { decorate(spec) { decoration = spec; return () => {}; }, popupFor: () => ({ dismiss() {} }) },
      inputTriggers: { registerSource(spec) { trigger = spec; return () => {}; } }, sessions,
      conversation: { input: { for: scope => inputs.get(scope.id) }, rebindDraftFiles: (id, ids) => rebinds.push({ id, ids }) } })[name],
    effect: install => install(), slots: { inject(_name, install) { install(); }, register(_spec, component) { statusComponent = component; } },
  });
  const pick = async (id, scene = 'ppt', tokenLength = 2) => {
    const input = inputs.get(id), rev = input.state.getSnapshot().draftRev;
    trigger.onPick({ session: { sessionId: id }, candidate: { value: scene }, span: { start: 0, end: tokenLength, draftRev: rev } });
    for (let i = 0; i < 15; i++) await new Promise(resolve => setImmediate(resolve));
  };
  return { decoration, trigger, inputs, posts, opened, values, pick, statusComponent, rebinds };
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
