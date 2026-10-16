import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { bindSceneInputs } from '../src/adapters/harless_task_scope.ts';

test('A full paper source set admits 16 task-owned files while other scenes keep eight', async () => {
  const root = mkdtempSync(join(tmpdir(), 'harless-paper-upload-'));
  const makeWorkspace = name => { const path = join(root, name); mkdirSync(join(path, 'inputs'), { recursive: true }); return path; };
  const data = Array.from({ length: 17 }, (_, index) => Buffer.from(`Section ${index}`));
  const parts = data.map((_, index) => ({ type: 'file', receiptId: `receipt-${index}` }));
  const ctx = {
    fileUploads: { resolve: (_, receiptId) => {
      const index = Number(receiptId.slice('receipt-'.length));
      return { name: `section-${index}.tex`, bytes: data[index].length, index };
    } },
    attachments: { async *readFileStream(ref) { yield data[ref.index]; } },
  };
  try {
    const paper = { id: 'paper-proofreading', adapter: 'workspace' };
    const admitted = await bindSceneInputs(ctx, {}, makeWorkspace('paper'), paper, parts.slice(0, 16), {}, 'Review sources', 'task-1');
    assert.equal(admitted.length, 16);
    const approval = JSON.parse(readFileSync(join(root, 'paper', 'approved-inputs.json'), 'utf8'));
    assert.equal(Object.keys(approval.files).length, 16);
    await assert.rejects(bindSceneInputs(ctx, {}, makeWorkspace('paper-over'), paper, parts, {}, 'Review sources', 'task-2'), /scene_input_limit/);
    await assert.rejects(bindSceneInputs(ctx, {}, makeWorkspace('general'), { id: 'new-scene', adapter: 'workspace' },
      parts.slice(0, 9), {}, 'Read files', 'task-3'), /scene_input_limit/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
