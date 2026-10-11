// Deterministic, read-only scheduling decisions over live Google free/busy data.
const crypto = require('crypto');

const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})$/;
const MINUTE = 60_000;
const MAX_SPAN = 14 * 24 * 60 * MINUTE;
const nameFind = 'find-available-slots';
const nameValidate = 'validate-slot';
const timeWindow = {
  type: 'object', additionalProperties: false, required: ['start', 'end'],
  properties: {
    start: { type: 'string', description: 'ISO timestamp with explicit UTC offset' },
    end: { type: 'string', description: 'ISO timestamp with explicit UTC offset' },
  },
};
const common = {
  calendarId: { type: 'string', description: 'Exact Calendar ID returned by list-calendars' },
  timeZone: { type: 'string', description: 'IANA time zone, e.g. Asia/Shanghai' },
  timeWindows: { type: 'array', minItems: 1, maxItems: 8, items: timeWindow,
    description: 'Allowed scheduling windows; each start/end needs an explicit UTC offset' },
  durationMinutes: { type: 'integer', minimum: 1, maximum: 480,
    description: 'Required continuous duration in whole minutes' },
};
const availabilityTools = [
  { name: nameFind,
    description: 'Compute the earliest continuous free slots from fresh Google Calendar free/busy. Use this for interval arithmetic; returns exact feasible times and source query hash. No event is created.',
    inputSchema: { type: 'object', additionalProperties: false,
      required: ['calendarId', 'timeZone', 'timeWindows', 'durationMinutes'],
      properties: { ...common, maxCandidates: { type: 'integer', minimum: 1, maximum: 5,
        description: 'One earliest slot per distinct free interval; defaults to 1' } } } },
  { name: nameValidate,
    description: 'Requery live Google Calendar free/busy and check that one proposed continuous slot is inside an allowed window, has the requested duration, and has no conflict. No event is created.',
    inputSchema: { type: 'object', additionalProperties: false,
      required: ['calendarId', 'timeZone', 'timeWindows', 'durationMinutes', 'candidateStart', 'candidateEnd'],
      properties: { ...common,
        candidateStart: { type: 'string', description: 'Proposed ISO start with explicit UTC offset' },
        candidateEnd: { type: 'string', description: 'Proposed ISO end with explicit UTC offset' } } } },
];

function instant(value, label) {
  if (typeof value !== 'string' || !INSTANT.test(value)) throw new Error(`${label} needs an ISO timestamp with UTC offset`);
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) throw new Error(`${label} is not a valid timestamp`);
  return ms;
}

function timeZone(value) {
  if (typeof value !== 'string' || value.length > 100) throw new Error('timeZone must be an IANA zone');
  try { new Intl.DateTimeFormat('en', { timeZone: value }); }
  catch { throw new Error('timeZone must be an IANA zone'); }
  return value;
}

function checkedInstant(value, label, zone) {
  const ms = instant(value, label);
  const supplied = value.endsWith('Z') ? 0 :
    (value.at(-6) === '-' ? -1 : 1) *
    (Number(value.slice(-5, -3)) * 60 + Number(value.slice(-2))) * MINUTE;
  const rendered = zoned(ms, zone);
  const actualOffset = rendered.endsWith('Z') ? 0 :
    (rendered.at(-6) === '-' ? -1 : 1) *
    (Number(rendered.slice(-5, -3)) * 60 + Number(rendered.slice(-2))) * MINUTE;
  if (Math.abs(supplied) > 14 * 60 * MINUTE || supplied !== actualOffset) {
    throw new Error(`${label} offset does not match ${zone}`);
  }
  return ms;
}

function zoned(ms, zone) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    timeZoneName: 'longOffset',
  }).formatToParts(new Date(ms));
  const p = Object.fromEntries(parts.map(x => [x.type, x.value]));
  const offset = p.timeZoneName === 'GMT' ? 'Z' : p.timeZoneName.replace('GMT', '');
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}${offset}`;
}

function windows(input, zone = null) {
  if (!Array.isArray(input) || input.length < 1 || input.length > 8) throw new Error('timeWindows needs 1–8 windows');
  const parsed = input.map((w, i) => {
    if (!w || typeof w !== 'object') throw new Error(`timeWindows[${i}] is invalid`);
    const parse = zone ? (value, label) => checkedInstant(value, label, zone) : instant;
    const start = parse(w.start, `timeWindows[${i}].start`);
    const end = parse(w.end, `timeWindows[${i}].end`);
    if (start >= end) throw new Error(`timeWindows[${i}] must end after it starts`);
    return { start, end };
  }).sort((a, b) => a.start - b.start);
  if (Math.max(...parsed.map(w => w.end)) - parsed[0].start > MAX_SPAN) {
    throw new Error('timeWindows span exceeds 14 days');
  }
  const merged = [];
  for (const window of parsed) {
    if (merged.length && window.start < merged.at(-1).end) merged.at(-1).end = Math.max(merged.at(-1).end, window.end);
    else merged.push({ ...window });
  }
  return merged;
}

function busyIntervals(raw) {
  if (!Array.isArray(raw)) throw new Error('Provider free/busy response is missing busy intervals');
  const parsed = raw.map((b, i) => {
    const start = instant(b.start, `busy[${i}].start`);
    const end = instant(b.end, `busy[${i}].end`);
    if (start >= end) throw new Error(`busy[${i}] has invalid duration`);
    return { start, end };
  }).sort((a, b) => a.start - b.start);
  const merged = [];
  for (const item of parsed) {
    if (merged.length && item.start <= merged.at(-1).end) merged.at(-1).end = Math.max(merged.at(-1).end, item.end);
    else merged.push({ ...item });
  }
  return merged;
}

function freeIntervals(allowed, busy) {
  const free = [];
  for (const window of allowed) {
    let cursor = window.start;
    for (const block of busy) {
      if (block.end <= cursor || block.start >= window.end) continue;
      if (block.start > cursor) free.push({ start: cursor, end: Math.min(block.start, window.end) });
      cursor = Math.max(cursor, Math.min(block.end, window.end));
      if (cursor >= window.end) break;
    }
    if (cursor < window.end) free.push({ start: cursor, end: window.end });
  }
  return free;
}

function computeSlots(allowed, busy, durationMinutes, maxCandidates = 1) {
  if (!Number.isInteger(durationMinutes) || durationMinutes < 1 || durationMinutes > 480) {
    throw new Error('durationMinutes must be an integer from 1 to 480');
  }
  if (!Number.isInteger(maxCandidates) || maxCandidates < 1 || maxCandidates > 5) {
    throw new Error('maxCandidates must be an integer from 1 to 5');
  }
  return freeIntervals(allowed, busy).filter(gap => gap.end - gap.start >= durationMinutes * MINUTE)
    .slice(0, maxCandidates).map(gap => ({ start: gap.start, end: gap.start + durationMinutes * MINUTE }));
}

function checkSlot(allowed, busy, durationMinutes, start, end) {
  return {
    correctDuration: end - start === durationMinutes * MINUTE,
    insideWindow: allowed.some(w => w.start <= start && end <= w.end),
    noConflict: busy.every(b => !(b.start < end && b.end > start)),
  };
}

async function callAvailability(upstream, name, args, scopedCalendarId = null) {
  if (![nameFind, nameValidate].includes(name)) throw new Error('Unknown availability tool');
  if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error('Tool arguments must be an object');
  const calendarId = args.calendarId;
  if (typeof calendarId !== 'string' || !calendarId || calendarId.length > 254) throw new Error('Exact calendarId is required');
  if (scopedCalendarId && calendarId !== scopedCalendarId) throw new Error('Only the SSS test calendar may be queried');
  const zone = timeZone(args.timeZone);
  const allowed = windows(args.timeWindows, zone);
  const duration = args.durationMinutes;
  if (!Number.isInteger(duration) || duration < 1 || duration > 480) throw new Error('durationMinutes must be an integer from 1 to 480');
  const min = allowed[0].start;
  const max = allowed.at(-1).end;
  const result = await upstream.callTool({ name: 'get-freebusy', arguments: {
    calendars: [{ id: calendarId }], timeMin: zoned(min, zone),
    timeMax: zoned(max, zone), timeZone: zone,
  } });
  if (result.isError) throw new Error('Google Calendar free/busy query failed');
  const texts = result.content.filter(x => x.type === 'text');
  if (texts.length !== 1) throw new Error('Google Calendar free/busy returned an unexpected result');
  const data = JSON.parse(texts[0].text);
  const keys = Object.keys(data.calendars || {});
  if (keys.length !== 1 || keys[0] !== calendarId || data.calendars[calendarId]?.errors?.length) {
    throw new Error('Google Calendar free/busy result does not cover exactly the requested calendar');
  }
  const busy = busyIntervals(data.calendars[calendarId].busy);
  const evidence = {
    calendarId, timeZone: zone, checkedAt: new Date().toISOString(),
    sourceSha256: crypto.createHash('sha256').update(texts[0].text).digest('hex'),
    busy: busy.filter(b => allowed.some(w => b.start < w.end && b.end > w.start))
      .map(b => ({ start: zoned(b.start, zone), end: zoned(b.end, zone) })),
  };
  if (name === nameFind) {
    const slots = computeSlots(allowed, busy, duration, args.maxCandidates ?? 1);
    return { ...evidence, durationMinutes: duration,
      slots: slots.map(s => ({ start: zoned(s.start, zone), end: zoned(s.end, zone) })),
      earliest: slots[0] ? { start: zoned(slots[0].start, zone), end: zoned(slots[0].end, zone) } : null,
      status: slots.length ? 'available' : 'no_slot' };
  }
  const start = checkedInstant(args.candidateStart, 'candidateStart', zone);
  const end = checkedInstant(args.candidateEnd, 'candidateEnd', zone);
  const checks = checkSlot(allowed, busy, duration, start, end);
  const first = computeSlots(allowed, busy, duration)[0];
  return { ...evidence, candidate: { start: zoned(start, zone), end: zoned(end, zone) },
    durationMinutes: duration, ...checks, earliest: first ?
      { start: zoned(first.start, zone), end: zoned(first.end, zone) } : null,
    isEarliest: Boolean(first && start === first.start && end === first.end),
    valid: Object.values(checks).every(Boolean) };
}

module.exports = { availabilityTools, callAvailability, instant, windows, busyIntervals,
  freeIntervals, computeSlots, checkSlot, zoned };
