const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const state = fs.mkdtempSync(path.join(os.tmpdir(), 'sss-calendar-test-'));
process.env.SSS_GOOGLE_CALENDAR_STATE = state;
const outbox = require('../scripts/calendar-outbox.cjs');
const review = require('../scripts/calendar-review.cjs');
const web = require('../scripts/calendar-review-web.cjs');
const event = { calendarId: 'test@example.com', summary: 'SSS test', start: '2026-09-28T10:00:00+08:00',
  end: '2026-09-28T10:30:00+08:00', timeZone: 'Asia/Shanghai', attendees: [] };

test('event must have bounded valid time and safe attendees', () => {
  assert.throws(() => outbox.payload({ ...event, end: event.start }), /duration/);
  assert.throws(() => outbox.payload({ ...event, attendees: ['bad\n@example.com'] }), /attendees/);
  assert.throws(() => outbox.payload({ ...event, start: '2026-09-28T10:00:00' }), /offsets/);
});

test('prepared event is only local until reviewed and cannot be created twice', async () => {
  const record = outbox.prepare(event);
  assert.equal(outbox.read(record.id).status, 'prepared');
  let calls = 0;
  const calendar = { events: { insert: async (request) => {
    calls++;
    assert.equal(request.calendarId, 'test@example.com');
    assert.equal(request.requestBody.id, record.id);
    assert.equal(request.sendUpdates, 'none');
    return { data: { id: record.id, htmlLink: 'https://calendar.google.com/test' } };
  } } };
  await review.createReviewed(record.id, calendar);
  assert.equal(calls, 1);
  assert.equal(outbox.read(record.id).status, 'created');
  await assert.rejects(review.createReviewed(record.id, calendar), /cannot create it again/);
  assert.equal(calls, 1);
});

test('uncertain result cannot be retried and review page escapes user content', async () => {
  const record = outbox.prepare({ ...event, summary: '<script>alert(1)</script>' });
  const html = web.reviewPage(record, '/create');
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<script>'));
  await assert.rejects(review.createReviewed(record.id, { events: { insert: async () => { throw new Error('timeout'); } } }), /uncertain/);
  assert.equal(outbox.read(record.id).status, 'uncertain');
  await assert.rejects(review.createReviewed(record.id, { events: { insert: async () => {} } }), /cannot create it again/);
});

test('browser review keeps same-origin form submission and rejects cross-origin requests', async () => {
  const record = outbox.prepare(event);
  const { server, url } = await web.start(record.id, { quiet: true, open: false });
  try {
    const page = await fetch(`${url}/missing`);
    assert.equal(page.headers.get('referrer-policy'), 'same-origin');
    const blocked = await fetch(`${url}/create`, { method: 'POST', headers: { Origin: 'https://malicious.example', 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'confirmation=TEST' });
    assert.equal(blocked.status, 403);
    const checked = await fetch(`${url}/create`, { method: 'POST', headers: { Origin: new URL(url).origin, 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'confirmation=TEST' });
    assert.equal(checked.status, 400);
    assert.equal(outbox.read(record.id).status, 'prepared');
  } finally {
    server.close();
  }
});

test.after(() => fs.rmSync(state, { recursive: true, force: true }));
