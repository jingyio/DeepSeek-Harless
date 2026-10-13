import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

test('Native /harless picker lists only the three English UI scenes and saves choices', async () => {
  const source = readFileSync(new URL('../src/adapters/harless_web_client/client.js', import.meta.url), 'utf8');
  const posts = [];
  let registered;
  let decoration;
  const value = {
    selection: { scene: 'example', mode: 'shadow', rsi: true }, preview_scene: null,
    preview_scenes: [
      { id: 'ppt', label: 'PPT' },
      { id: 'paper-proofreading', label: 'Paper Proofreading' },
      { id: 'research-data-analysis', label: 'Research Data Analysis' },
    ],
    scenes: [{ id: 'example', label: 'Sample', execute_available: false }],
  };
  const fetch = async (_url, init) => {
    if (init.method === 'POST') posts.push(JSON.parse(init.body));
    return { ok: true, json: async () => value };
  };
  runInNewContext(source, {
    window: { __ModuleLoader__: { load(spec) { registered = spec; } } }, fetch,
  });
  assert.equal(registered.id, 'deepseek-harless-web-client');
  registered.factory().apply({
    get: name => name === 'commandUi' ? { decorate(spec) { decoration = spec; return () => {}; } } : undefined,
    effect: install => install(),
  });
  assert.equal(decoration.name, 'harless');
  assert.equal(decoration.ui.kind, 'popupSelect');
  const session = { sessionId: 'session-1' };
  const rows = await decoration.ui.options(session, new AbortController().signal);
  assert.deepEqual(Array.from(rows.slice(0, 3), row => row.label),
    ['PPT', 'Paper Proofreading', 'Research Data Analysis']);
  assert.equal(rows.some(row => row.label === 'Sample'), false);
  assert.equal(rows.some(row => row.label === 'Mode · Shadow'), true);
  await decoration.ui.onSelect(rows[0], session);
  assert.deepEqual(posts[0], { action: 'select_preview_scene', session_id: 'session-1', scene_id: 'ppt' });
  await decoration.ui.onSelect(rows.find(row => row.id === 'mode:baseline'), session);
  assert.deepEqual(posts[1], { action: 'select', session_id: 'session-1', selection: { mode: 'baseline' } });
});
