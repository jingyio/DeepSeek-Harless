import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, symlink, realpath } from 'node:fs/promises';
import { createHash } from 'node:crypto';
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

test('Web任务可跨代码发布保留，但来源不能越过当前任务或跟随越界链接', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'ppt-persistent-web-'));
  const root = join(directory, 'release'), account = join(directory, 'account-data');
  const workspace = join(account, 'sessions', 'one'), other = join(account, 'sessions', 'other');
  await mkdir(join(root, '.local'), { recursive: true });
  await mkdir(workspace, { recursive: true }); await mkdir(other, { recursive: true });
  const input = join(workspace, 'source.pdf'), jobPath = join(workspace, 'job.json');
  const bytes = Buffer.from('approved source fixture'), hash = createHash('sha256').update(bytes).digest('hex');
  const job = path => ({ slides: 6, allow_output: false, inputs: [{ path, version_sha256: hash }] });
  const backend = async () => { throw Error('No model or tools needed'); };
  try {
    await writeFile(input, bytes); await writeFile(jobPath, JSON.stringify(job(input)));
    await assert.rejects(DeliveryAdapter.create(root, jobPath, backend, [], true), { code: 'path_scope_rejected' });
    await assert.rejects(DeliveryAdapter.create(root, jobPath, backend, [], false, account), { code: 'path_scope_rejected' });
    const adapter = await DeliveryAdapter.create(root, jobPath, backend, [], true, account);
    assert.equal(adapter.privateRoot, await realpath(workspace)); await adapter.guard();
    const foreign = join(other, 'source.pdf'); await writeFile(foreign, bytes);
    await writeFile(jobPath, JSON.stringify(job(foreign)));
    await assert.rejects(DeliveryAdapter.create(root, jobPath, backend, [], true, account), { code: 'path_scope_rejected' });
    if (process.platform !== 'win32') {
      const link = join(workspace, 'escape.pdf'); await symlink(foreign, link);
      await writeFile(jobPath, JSON.stringify(job(link)));
      await assert.rejects(DeliveryAdapter.create(root, jobPath, backend, [], true, account), { code: 'path_scope_rejected' });
    }
    await writeFile(jobPath, JSON.stringify(job(input)));
    await assert.rejects(DeliveryAdapter.create(root, jobPath, backend, [foreign], true, account), { code: 'dependency_scope_rejected' });
  } finally { await rm(directory, { recursive: true, force: true }); }
});
