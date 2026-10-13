import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DeliveryAdapter } from '../dist/delivery-adapter.js';

test('空 PPT job 仅允许显式 Web 只读初始化；原 CLI 和输出授权不能绕过来源准入', async () => {
  const root = await mkdtemp(join(tmpdir(), 'ppt-web-session-'));
  const directory = join(root, '.local', 'job'); await mkdir(directory, { recursive: true });
  const path = join(directory, 'job.json');
  const job = { slides: 6, inputs: [], allow_output: false };
  const backend = async () => { throw Error('No tool should run during composition'); };
  try {
    await writeFile(path, JSON.stringify(job));
    await assert.rejects(DeliveryAdapter.create(root, path, backend, []), /固定任务缺少/);
    const adapter = await DeliveryAdapter.create(root, path, backend, [], true);
    assert.match(adapter.inputVersion, /^[a-f0-9]{64}$/);
    await writeFile(path, JSON.stringify({ ...job, allow_output: true }));
    await assert.rejects(DeliveryAdapter.create(root, path, backend, [], true), /固定任务缺少/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
