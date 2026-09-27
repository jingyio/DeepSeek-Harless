// Local event review queue. No Google API calls are made in this module.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const root = path.join(process.env.SSS_GOOGLE_CALENDAR_STATE || path.join(__dirname, '../.local/google-calendar'), 'outbox');
const emailPattern = /^[^\s@,<>\r\n]+@[^\s@,<>\r\n]+\.[^\s@,<>\r\n]+$/;
const timestampPattern = /^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?(?:Z|[+-]\d\d:\d\d)$/;

function payload(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Event must be an object');
  const summary = input.summary;
  const description = input.description ?? '';
  const calendarId = input.calendarId ?? 'primary';
  const start = input.start;
  const end = input.end;
  const timeZone = input.timeZone;
  const attendees = input.attendees ?? [];
  if (typeof summary !== 'string' || !summary.trim() || summary.length > 200 || /[\r\n\0]/.test(summary)) throw new Error('Invalid event summary');
  if (typeof description !== 'string' || description.length > 10000 || description.includes('\0')) throw new Error('Invalid description');
  if (typeof calendarId !== 'string' || !calendarId || calendarId.length > 254 || /[\r\n\0]/.test(calendarId)) throw new Error('Invalid calendar ID');
  if (typeof start !== 'string' || typeof end !== 'string' || !timestampPattern.test(start) || !timestampPattern.test(end)) throw new Error('Start and end require ISO times with explicit offsets');
  const duration = Date.parse(end) - Date.parse(start);
  if (!Number.isFinite(duration) || duration < 60000 || duration > 12 * 3600000) throw new Error('Event duration must be between 1 minute and 12 hours');
  if (timeZone !== undefined && (typeof timeZone !== 'string' || !/^[A-Za-z_]+(?:\/[A-Za-z_+-]+)+$/.test(timeZone))) throw new Error('Invalid IANA time zone');
  if (!Array.isArray(attendees) || attendees.length > 20 || attendees.some((entry) => typeof entry !== 'string' || entry.length > 254 || !emailPattern.test(entry))) throw new Error('Invalid attendees');
  return { summary, description, calendarId, start, end, attendees, ...(timeZone ? { timeZone } : {}) };
}

function digest(event) { return crypto.createHash('sha256').update(JSON.stringify(event)).digest('hex'); }
function directory() {
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const stat = fs.lstatSync(root);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('Outbox is not a real directory');
  fs.chmodSync(root, 0o700);
  return root;
}
function fileFor(id) {
  if (!/^[a-f0-9]{32}$/.test(id)) throw new Error('Invalid event review ID');
  return path.join(directory(), `${id}.json`);
}
function prepare(input) {
  const event = payload(input);
  const id = crypto.randomBytes(16).toString('hex');
  const record = { version: 1, id, status: 'prepared', createdAt: new Date().toISOString(), event, sha256: digest(event) };
  fs.writeFileSync(fileFor(id), JSON.stringify(record, null, 2), { flag: 'wx', mode: 0o600 });
  return record;
}
function read(id) {
  const file = fileFor(id);
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o077)) throw new Error('Unsafe event review file');
  const record = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (record.version !== 1 || record.id !== id || record.sha256 !== digest(payload(record.event))) throw new Error('Event review has changed or is invalid');
  return record;
}
function write(record) {
  const file = fileFor(record.id);
  const temp = `${file}.${crypto.randomBytes(8).toString('hex')}.tmp`;
  fs.writeFileSync(temp, JSON.stringify(record, null, 2), { flag: 'wx', mode: 0o600 });
  fs.renameSync(temp, file);
}
function list() {
  return fs.readdirSync(directory()).filter((name) => /^[a-f0-9]{32}\.json$/.test(name))
    .map((name) => read(name.slice(0, -5)))
    .map(({ id, status, createdAt, event, sha256 }) => ({ id, status, createdAt, summary: event.summary, start: event.start, calendarId: event.calendarId, sha256 }));
}
module.exports = { payload, digest, prepare, read, write, list, fileFor };
