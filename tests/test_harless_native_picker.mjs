import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

test('Native /harless picker opens Scenes and Mode submenus and saves choices', async () => {
  const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
  const posts = [];
  let registered;
  let decoration;
  let statusComponent;
  const popup = { binding: { segment: { via: 'enter', token: '/harless' } },
    open(_name, ui) { this.ui = ui; } };
  const value = {
    selection: { scene: 'example', mode: 'shadow', rsi: true }, preview_scene: null,
    preview_scenes: [
      { id: 'ppt', label: 'PPT' },
      { id: 'paper-proofreading', label: 'Paper Proofreading' },
      { id: 'research-data-analysis', label: 'Research Data Analysis' },
      { id: 'files', label: 'Files' },
      { id: 'new-scene', label: 'New Scene' },
    ],
    scenes: [
      { id: 'ppt', label: 'PPT', available: true },
      { id: 'paper-proofreading', label: 'Paper Proofreading', available: false, unavailable_reason: 'missing_backend' },
      { id: 'research-data-analysis', label: 'Research Data Analysis', available: false, unavailable_reason: 'missing_backend' },
      { id: 'files', label: 'Files', available: true },
      { id: 'new-scene', label: 'New Scene', available: true },
    ],
  };
  const fetch = async (_url, init) => {
    if (init.method === 'POST') posts.push(JSON.parse(init.body));
    return { ok: true, json: async () => value };
  };
  runInNewContext(source, {
    window: { __ModuleLoader__: { load(spec) { registered = spec; } } }, fetch,
  });
  assert.equal(registered.id, 'deepseek-harless-web-client');
  registered.factory(name => name === 'react' ? { createElement() {}, useState() {}, useEffect() {} } : undefined).apply({
    get: name => name === 'commandUi' ? {
      decorate(spec) { decoration = spec; return () => {}; }, popupFor() { return popup; },
    } : name === 'sessions' ? { scope: () => ({}) } : undefined,
    effect: install => install(),
    slots: { inject(_name, install) { install(); }, register(_spec, component) { statusComponent = component; } },
  });
  assert.equal(typeof statusComponent, 'function');
  assert.equal(decoration.name, 'harless');
  assert.equal(decoration.ui.kind, 'popupSelect');
  const session = { sessionId: 'session-1' };
  const rows = await decoration.ui.options(session, new AbortController().signal);
  assert.deepEqual(Array.from(rows, row => row.label), ['Scenes', 'Mode', 'RSI']);
  await decoration.ui.onSelect(rows[0], session);
  const sceneRows = await popup.ui.options(session, new AbortController().signal);
  assert.deepEqual(Array.from(sceneRows.slice(1), row => row.label),
    ['PPT', 'Paper Proofreading', 'Research Data Analysis', 'Files', 'New Scene']);
  assert.equal(sceneRows.some(row => row.label === 'Sample'), false);
  await popup.ui.onSelect(sceneRows[1], session);
  assert.deepEqual(posts[0], { action: 'select', session_id: 'session-1', selection: { scene: 'ppt' } });
  await decoration.ui.onSelect(rows[1], session);
  const modeRows = await popup.ui.options(session, new AbortController().signal);
  assert.deepEqual(Array.from(modeRows.slice(1), row => row.label), ['Origin', 'Shadow', 'Execute']);
  await popup.ui.onSelect(modeRows.find(row => row.id === 'mode:baseline'), session);
  assert.deepEqual(posts[1], { action: 'select', session_id: 'session-1', selection: { mode: 'baseline' } });
  value.selection.scene='ppt';value.scene_options={};
  value.scene_option_fields=[{key:'allow_output',label:'输出权限',default:false,
    values:[{value:false,label:'只读检查'},{value:true,label:'允许生成 PPT 新副本'}]}];
  const pptRows=await decoration.ui.options(session,new AbortController().signal);
  await decoration.ui.onSelect(pptRows.find(row=>row.id==='page:options'),session);
  const outputRows=await popup.ui.options(session,new AbortController().signal);
  await popup.ui.onSelect(outputRows.find(row=>row.id==='option:allow_output=true'),session);
  assert.deepEqual(posts[2],{action:'set_scene_options',session_id:'session-1',options:{allow_output:true}});
  value.selection.scene='files';value.scene_options={};
  value.scene_option_fields=[{key:'allow_output',label:'整理权限',default:false,
    values:[{value:false,label:'只读盘点与检索'},{value:true,label:'允许整理任务副本'}]}];
  const filesRows=await decoration.ui.options(session,new AbortController().signal);
  assert.equal(filesRows.find(row=>row.id==='page:options').label,'任务选项');
  await decoration.ui.onSelect(filesRows.find(row=>row.id==='page:options'),session);
  const filePermissionRows=await popup.ui.options(session,new AbortController().signal);
  await popup.ui.onSelect(filePermissionRows.find(row=>row.id==='option:allow_output=true'),session);
  assert.deepEqual(posts[3],{action:'set_scene_options',session_id:'session-1',options:{allow_output:true}});
});
