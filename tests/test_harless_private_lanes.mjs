import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
const options = { skip: !process.features?.typescript };

test('private lane identity exists before the first list frame and survives restart without title matching', options, async () => {
  const { registerPrivateLanes } = await import('../src/adapters/harless_private_lanes.ts');
  const directory = mkdtempSync(join(tmpdir(), 'private-lanes-'));
  try {
    let projection;
    const rows = [{ sessionId: 'parent', title: 'Baseline DSH' }, { sessionId: 'old-child', title: 'Renamed' }];
    const makeContext = () => ({ sessionProjections: { register(value) { projection = value; } }, sessionController: {
      async list() { return { items: rows }; }, async search() { return { items: rows, hasMore: false }; },
    } });
    const ctx = makeContext(), lanes = registerPrivateLanes(ctx, directory, 'alice', id => id === 'old-child');
    const id = lanes.reserve('parent');
    assert.equal(projection.init({ id }), true, 'the native added frame already carries the marker');
    assert.equal(projection.init({ id: 'parent' }), false);
    assert.equal(projection.init({ id: 'old-child' }), true, 'historical comparison relationships remain private');
    rows.push({ sessionId: id, title: '新会话' });
    assert.deepEqual((await ctx.sessionController.list()).items.map(row => row.sessionId), ['parent']);
    assert.deepEqual((await ctx.sessionController.search()).items.map(row => row.sessionId), ['parent']);
    const restored = registerPrivateLanes(makeContext(), directory, 'alice');
    assert.equal(restored.isPrivate(id), true);
    assert.throws(() => registerPrivateLanes(makeContext(), directory, 'bob'), /scope_mismatch/);
  } finally { rmSync(directory, { recursive: true, force: true }); }
});
