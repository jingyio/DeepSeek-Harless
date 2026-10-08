const test = require('node:test');
const assert = require('node:assert/strict');
const { callAvailability, computeSlots, windows, busyIntervals } = require('../scripts/calendar-availability.cjs');

const calendarId = 'sss-test-calendar';
const zone = 'Asia/Shanghai';
const cases = [
  { day: '2026-10-12', minutes: 60, windows: [['10:00', '12:00'], ['14:00', '17:00']],
    busy: [['09:30', '10:15'], ['13:00', '14:00']], expected: ['10:15', '11:15'] },
  { day: '2026-10-13', minutes: 45, windows: [['15:00', '17:30']],
    busy: [['14:30', '15:30'], ['16:15', '17:00']], expected: ['15:30', '16:15'] },
  { day: '2026-10-14', minutes: 90, windows: [['09:00', '13:00'], ['14:00', '17:00']],
    busy: [['10:00', '11:00'], ['14:00', '15:00']], expected: ['11:00', '12:30'] },
  { day: '2026-10-14', minutes: 90, windows: [['09:00', '13:00'], ['14:00', '17:00']],
    busy: [['10:00', '11:00'], ['11:30', '12:30'], ['14:00', '15:00']], expected: ['15:00', '16:30'] },
];

function iso(day, hhmm) { return `${day}T${hhmm}:00+08:00`; }
function args(row) {
  return { calendarId, timeZone: zone, durationMinutes: row.minutes,
    timeWindows: row.windows.map(([a, b]) => ({ start: iso(row.day, a), end: iso(row.day, b) })) };
}
function upstream(row, options = {}) {
  const calls = [];
  return { calls, async callTool(request) {
    calls.push(request);
    if (options.error) return { isError: true, content: [] };
    const target = options.wrongCalendar || calendarId;
    return { content: [{ type: 'text', text: JSON.stringify({ calendars: {
      [target]: { busy: row.busy.map(([a, b]) => ({ start: iso(row.day, a), end: iso(row.day, b) })) },
    } }) }] };
  } };
}

test('finds earliest slot for A, B, original C, and changed C', async () => {
  for (const row of cases) {
    const provider = upstream(row);
    const result = await callAvailability(provider, 'find-available-slots', args(row), calendarId);
    assert.equal(result.status, 'available');
    assert.deepEqual(result.earliest, { start: iso(row.day, row.expected[0]), end: iso(row.day, row.expected[1]) });
    assert.equal(provider.calls.length, 1);
    assert.deepEqual(provider.calls[0].arguments.calendars, [{ id: calendarId }]);
    assert.match(result.sourceSha256, /^[a-f0-9]{64}$/);
  }
});

test('validates feasibility separately from earliestness after a new event', async () => {
  const row = cases[3];
  const provider = upstream(row);
  const check = (a, b) => callAvailability(provider, 'validate-slot',
    { ...args(row), candidateStart: iso(row.day, a), candidateEnd: iso(row.day, b) }, calendarId);
  const stale = await check('11:00', '12:30');
  assert.equal(stale.noConflict, false);
  assert.equal(stale.valid, false);
  assert.equal(stale.isEarliest, false);
  const current = await check('15:00', '16:30');
  assert.equal(current.valid, true);
  assert.equal(current.isEarliest, true);
  const later = await check('15:30', '17:00');
  assert.equal(later.valid, true);
  assert.equal(later.isEarliest, false);
});

test('touching busy endpoints are free, short gaps are rejected', () => {
  const allowed = windows([{ start: iso('2026-10-12', '10:00'), end: iso('2026-10-12', '11:00') }]);
  const busy = busyIntervals([{ start: iso('2026-10-12', '09:00'), end: iso('2026-10-12', '10:00') }]);
  assert.equal(computeSlots(allowed, busy, 60).length, 1);
  assert.equal(computeSlots(allowed, busy, 61).length, 0);
});

test('rejects wrong calendar, offset, and incomplete provider result', async () => {
  const row = cases[0];
  const provider = upstream(row);
  await assert.rejects(callAvailability(provider, 'find-available-slots',
    { ...args(row), calendarId: 'primary' }, calendarId), /Only the SSS test calendar/);
  assert.equal(provider.calls.length, 0);
  await assert.rejects(callAvailability(provider, 'find-available-slots',
    { ...args(row), timeWindows: [{ start: '2026-10-12T10:00:00Z', end: iso(row.day, '12:00') }] },
    calendarId), /offset does not match/);
  assert.equal(provider.calls.length, 0);
  await assert.rejects(callAvailability(upstream(row, { wrongCalendar: 'primary' }),
    'find-available-slots', args(row), calendarId), /does not cover exactly/);
  await assert.rejects(callAvailability(upstream(row, { error: true }),
    'find-available-slots', args(row), calendarId), /query failed/);
});
