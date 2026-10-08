#!/usr/bin/env node
// Evaluator-only fixture setup. Agent sessions use the read-only Calendar bridge.
const fs = require('fs');
const path = require('path');
const { calendarClient } = require('./calendar-review.cjs');

const root = path.join(__dirname, '..');
const state = path.join(root, '.local', 'benchmarks', 'mcp-app-internal-v2', 'calendar');
const calendarFile = path.join(root, '.local', 'google-calendar', 'test-calendar.json');
const manifestFile = path.join(state, 'fixture-manifest.json');
const testCalendar = JSON.parse(fs.readFileSync(calendarFile, 'utf8'));
if (testCalendar.summary !== 'SSS MCP Test' || !testCalendar.createdBySSS || !testCalendar.id) {
  throw new Error('Dedicated SSS test calendar is not verified');
}

const timezone = 'Asia/Shanghai';
const fixture = [
  ['a1', 'A: 预约占用一', '2026-10-12T09:30:00+08:00', '2026-10-12T10:15:00+08:00'],
  ['a2', 'A: 预约占用二', '2026-10-12T13:00:00+08:00', '2026-10-12T14:00:00+08:00'],
  ['b1', 'B: 预约占用一', '2026-10-13T14:30:00+08:00', '2026-10-13T15:30:00+08:00'],
  ['b2', 'B: 预约占用二', '2026-10-13T16:15:00+08:00', '2026-10-13T17:00:00+08:00'],
  ['c1', 'C: 预约占用一', '2026-10-14T10:00:00+08:00', '2026-10-14T11:00:00+08:00'],
  ['c2', 'C: 预约占用二', '2026-10-14T14:00:00+08:00', '2026-10-14T15:00:00+08:00'],
].map(([suffix, summary, start, end]) => ({
  id: `sss20260929cal${suffix}`,
  summary: `SSS 测试｜${summary}`,
  description: 'SSS synthetic calendar benchmark fixture. No real meeting or attendee.',
  start: { dateTime: start, timeZone: timezone },
  end: { dateTime: end, timeZone: timezone },
  transparency: 'opaque',
  visibility: 'private',
  reminders: { useDefault: false },
}));
const change = {
  id: 'sss20260929calc3', summary: 'SSS 测试｜C: 后续新增占用',
  description: 'SSS synthetic calendar benchmark change. Invalidates the old C recommendation. No attendee.',
  start: { dateTime: '2026-10-14T11:30:00+08:00', timeZone: timezone },
  end: { dateTime: '2026-10-14T12:30:00+08:00', timeZone: timezone },
  transparency: 'opaque', visibility: 'private', reminders: { useDefault: false },
};

async function main() {
  const mode = process.argv[2] || '--preview';
  if (!['--preview', '--apply', '--apply-change', '--cleanup'].includes(mode)) throw new Error('Use --preview, --apply, --apply-change, or --cleanup');
  const selected = mode === '--apply-change' ? [change] : mode === '--cleanup' ? [...fixture, change] : fixture;
  const publicView = selected.map(({ id, summary, start, end }) => ({ id, summary, start: start.dateTime, end: end.dateTime }));
  if (mode === '--preview') {
    process.stdout.write(JSON.stringify({ calendar: testCalendar.summary, eventCount: fixture.length,
      attendees: 0, invitations: false, events: publicView }, null, 2) + '\n');
    return;
  }
  const calendar = calendarClient();
  const remote = await calendar.calendarList.get({ calendarId: testCalendar.id });
  if (remote.data.summary !== testCalendar.summary || remote.data.accessRole !== 'owner') {
    throw new Error('Remote test calendar name or owner access differs from frozen local record');
  }
  const operations = [];
  if (mode === '--apply-change' && !fs.existsSync(path.join(state, 'agent-c', 'answer.md'))) {
    throw new Error('Freeze the original C Agent attempt before applying the change');
  }
  for (const event of selected) {
    if (mode === '--apply' || mode === '--apply-change') {
      try {
        const response = await calendar.events.insert({ calendarId: testCalendar.id,
          requestBody: event, sendUpdates: 'none' });
        operations.push({ id: event.id, action: 'created', etag: response.data.etag,
          updated: response.data.updated });
      } catch (error) {
        if (error.code !== 409) throw error;
        const response = await calendar.events.get({ calendarId: testCalendar.id, eventId: event.id });
        const found = response.data;
        if (found.summary !== event.summary || found.start?.dateTime !== event.start.dateTime ||
            found.end?.dateTime !== event.end.dateTime || found.attendees?.length) {
          throw new Error(`Existing event ${event.id} differs from fixture; stop without overwriting`);
        }
        operations.push({ id: event.id, action: 'already_present', etag: found.etag,
          updated: found.updated });
      }
    } else {
      try {
        const response = await calendar.events.get({ calendarId: testCalendar.id, eventId: event.id });
        if (response.data.summary !== event.summary || response.data.attendees?.length) {
          throw new Error(`Existing event ${event.id} does not match fixture; refuse deletion`);
        }
        await calendar.events.delete({ calendarId: testCalendar.id, eventId: event.id, sendUpdates: 'none' });
        operations.push({ id: event.id, action: 'deleted' });
      } catch (error) {
        if (error.code === 404) operations.push({ id: event.id, action: 'already_absent' });
        else throw error;
      }
    }
  }
  fs.mkdirSync(state, { recursive: true, mode: 0o700 });
  const recordFile = mode === '--apply-change' ? path.join(state, 'fixture-change-manifest.json') : manifestFile;
  fs.writeFileSync(recordFile, JSON.stringify({ mode, calendarId: testCalendar.id,
    calendarSummary: testCalendar.summary, recordedAt: new Date().toISOString(),
    events: publicView, operations }, null, 2) + '\n', { mode: 0o600 });
  process.stdout.write(JSON.stringify({ mode, calendar: testCalendar.summary,
    created: operations.filter(x => x.action === 'created').length,
    alreadyPresent: operations.filter(x => x.action === 'already_present').length,
    deleted: operations.filter(x => x.action === 'deleted').length,
    eventCount: selected.length, manifest: recordFile }) + '\n');
}
main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
