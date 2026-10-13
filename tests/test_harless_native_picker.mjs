import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

for (const pptWebUrl of [null, '/ppt']) test(`Native /harless picker keeps PPT in chat; separate delivery entry ${pptWebUrl ?? 'not enabled'}`, async () => {
  const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
  const posts = [];
  const navigations = [];
  let registered;
  let decoration;
  let statusComponent;
  const popup = { binding: { segment: { via: 'enter', token: '/harless' } },
    open(_name, ui) { this.ui = ui; } };
  const value = {
    ppt_web_url: pptWebUrl,
    selection: { scene: 'example', mode: 'shadow', rsi: true }, preview_scene: null,
    preview_scenes: [
      { id: 'ppt', label: 'PPT' },
      { id: 'paper-proofreading', label: 'Paper Proofreading' },
      { id: 'research-data-analysis', label: 'Research Data Analysis' },
      { id: 'new-scene', label: 'New Scene' },
    ],
    scenes: [
      { id: 'ppt', label: 'PPT', available: true },
      { id: 'paper-proofreading', label: 'Paper Proofreading', available: false, unavailable_reason: 'missing_backend' },
      { id: 'research-data-analysis', label: 'Research Data Analysis', available: false, unavailable_reason: 'missing_backend' },
      { id: 'new-scene', label: 'New Scene', available: true },
    ],
  };
  const fetch = async (_url, init) => {
    if (init.method === 'POST') posts.push(JSON.parse(init.body));
    return { ok: true, json: async () => value };
  };
  runInNewContext(source, {
    window: { __ModuleLoader__: { load(spec) { registered = spec; } }, location: { assign(url) { navigations.push(url); } } }, fetch,
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
    ['PPT', 'Paper Proofreading', 'Research Data Analysis', 'New Scene']);
  assert.equal(sceneRows.some(row => row.label === 'Sample'), false);
  await popup.ui.onSelect(sceneRows[1], session);
  assert.deepEqual(posts[0], { action: 'select', session_id: 'session-1', selection: { scene: 'ppt' } });
  assert.deepEqual(navigations, []);
  await decoration.ui.onSelect(rows[1], session);
  const modeRows = await popup.ui.options(session, new AbortController().signal);
  assert.deepEqual(Array.from(modeRows.slice(1), row => row.label), ['Origin', 'Shadow', 'Execute']);
  await popup.ui.onSelect(modeRows.find(row => row.id === 'mode:baseline'), session);
  assert.deepEqual(posts[1], { action: 'select', session_id: 'session-1', selection: { mode: 'baseline' } });
});
