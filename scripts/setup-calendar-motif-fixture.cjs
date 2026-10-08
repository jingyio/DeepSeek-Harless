#!/usr/bin/env node
// Evaluator-only, idempotent synthetic Calendar fixture for Motif continuation tests.
const fs = require('fs');
const path = require('path');
const { calendarClient } = require('./calendar-review.cjs');

const root = path.join(__dirname, '..');
const state = path.join(root, '.local/benchmarks/mcp-app-internal-v2/calendar/motif-continuation-v1');
const record = JSON.parse(fs.readFileSync(path.join(root, '.local/google-calendar/test-calendar.json'), 'utf8'));
if (record.summary !== 'SSS MCP Test' || record.createdBySSS !== true || !record.id) {
  throw new Error('Dedicated SSS test calendar record is missing');
}
const zone = 'Asia/Shanghai';
function event(suffix, summary, start, end) {
  return { id: `sss20260929cal${suffix}`, summary: `SSS 测试｜${summary}`,
    description: 'SSS synthetic Motif scheduling evaluation. No real meeting or attendee.',
    start: { dateTime: `2026-10-${start}+08:00`, timeZone: zone },
    end: { dateTime: `2026-10-${end}+08:00`, timeZone: zone },
    transparency: 'opaque', visibility: 'private', reminders: { useDefault: false } };
}
const base = [
  event('d1', 'D: 占用一', '15T09:40:00', '15T10:30:00'),
  event('d2', 'D: 占用二', '15T11:20:00', '15T12:00:00'),
  event('e1', 'E: 占用一', '16T09:00:00', '16T09:30:00'),
  event('e2', 'E: 占用二', '16T10:20:00', '16T11:00:00'),
];
const change = event('e3', 'E: 新增占用', '16T11:10:00', '16T11:40:00');
const tasks = [
  { case: 'D', date: '2026-10-15', durationMinutes: 50,
    windows: [['09:00', '12:00'], ['14:00', '16:00']], expected: ['10:30', '11:20'] },
  { case: 'E', date: '2026-10-16', durationMinutes: 55,
    windows: [['09:00', '12:00'], ['14:00', '16:00']], expected: ['11:00', '11:55'],
    afterChangeExpected: ['14:00', '14:55'] },
];
function view(item) {
  return { id: item.id, summary: item.summary, start: item.start.dateTime,
    end: item.end.dateTime, attendees: [] };
}
async function main() {
  const mode = process.argv[2] || '--preview';
  if (!['--preview', '--apply', '--apply-change'].includes(mode)) {
    throw new Error('Use --preview, --apply, or --apply-change');
  }
  const selected = mode === '--apply-change' ? [change] : base;
  if (mode === '--preview') {
    process.stdout.write(JSON.stringify({ calendar: record.summary, writes: base.map(view),
      laterChange: view(change), tasks, invitations: false }, null, 2) + '\n');
    return;
  }
  if (mode === '--apply-change' && !fs.existsSync(path.join(state, 'agent-e/answer.md'))) {
    throw new Error('Freeze the original E answer before adding the change');
  }
  const client = calendarClient();
  const remote = await client.calendarList.get({ calendarId: record.id });
  if (remote.data.summary !== record.summary || remote.data.accessRole !== 'owner') {
    throw new Error('Remote test calendar identity or owner role changed');
  }
  const operations = [];
  for (const item of selected) {
    try {
      const created = await client.events.insert({ calendarId: record.id,
        requestBody: item, sendUpdates: 'none' });
      operations.push({ id: item.id, action: 'created', updated: created.data.updated });
    } catch (error) {
      if (error.code !== 409) throw error;
      const found = (await client.events.get({ calendarId: record.id, eventId: item.id })).data;
      if (found.summary !== item.summary || found.start?.dateTime !== item.start.dateTime ||
          found.end?.dateTime !== item.end.dateTime || found.attendees?.length) {
        throw new Error(`Existing test event ${item.id} differs; refusing overwrite`);
      }
      operations.push({ id: item.id, action: 'already_present', updated: found.updated });
    }
  }
  fs.mkdirSync(state, { recursive: true, mode: 0o700 });
  const target = path.join(state, mode === '--apply' ? 'fixture-manifest.json' : 'change-manifest.json');
  fs.writeFileSync(target, JSON.stringify({ mode, calendarId: record.id,
    calendarSummary: record.summary, events: selected.map(view), operations,
    recordedAt: new Date().toISOString() }, null, 2) + '\n', { mode: 0o600 });
  process.stdout.write(JSON.stringify({ mode, created: operations.filter(x => x.action === 'created').length,
    alreadyPresent: operations.filter(x => x.action === 'already_present').length,
    eventCount: selected.length, manifest: target }) + '\n');
}
main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
