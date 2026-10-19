import test from 'node:test';
import assert from 'node:assert/strict';
import {createStatusCache} from '../src/adapters/harless_status_cache.ts';

test('overlapping UI polls share one scan, scoped by configuration and refreshed after expiry', async () => {
  let clock = 0;
  const calls = [], releases = [];
  const status = createStatusCache(key => {
    calls.push(key);
    return new Promise(resolve => releases.push(resolve));
  }, 4000, () => clock);
  const pending = Array.from({length: 20}, () => status('original-profile'));
  const other = status('another-profile');
  await Promise.resolve();
  assert.deepEqual(calls, ['original-profile', 'another-profile']);
  clock = 10000; // a slow scan is still shared, even beyond the cache TTL
  const late = status('original-profile');
  releases[0]({generation: 1}); releases[1]({generation: 9});
  assert.deepEqual(await Promise.all([...pending, late]), Array(21).fill({generation: 1}));
  assert.deepEqual(await other, {generation: 9});
  clock = 13999;
  assert.deepEqual(await status('original-profile'), {generation: 1});
  assert.equal(calls.length, 2);
  clock = 14000;
  const refreshed = status('original-profile');
  await Promise.resolve();
  assert.equal(calls.length, 3);
  releases[2]({generation: 2});
  assert.deepEqual(await refreshed, {generation: 2});
});

test('failed status scans reject all waiters and permit a fresh read', async () => {
  let calls = 0;
  const status = createStatusCache(async () => {
    if (++calls === 1) throw Error('scan unavailable');
    return {generation: 2};
  });
  const rejected = await Promise.allSettled([status('profile'), status('profile')]);
  assert.ok(rejected.every(r => r.status === 'rejected' && r.reason.message === 'scan unavailable'));
  assert.equal(calls, 1);
  assert.deepEqual(await status('profile'), {generation: 2});
});
