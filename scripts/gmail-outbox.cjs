// Local review queue. This module has no Gmail API or send capability.
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const root = path.join(process.env.GMAIL_MCP_STATE_DIR || path.join(__dirname, '../.local/google-gmail'), 'outbox');
const emailPattern = /^[A-Z0-9.!#$%&'*+\/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9.-]*[A-Z0-9])?\.[A-Z]{2,}$/i;

function addresses(value, label, required = false) {
  const entries = typeof value === 'string' ? [value] : (value ?? []);
  if (!Array.isArray(entries) || entries.length > 20 || (required && entries.length === 0)) {
    throw new Error(`${label} must contain 1–20 email addresses`);
  }
  return entries.map((entry) => {
    if (typeof entry !== 'string' || entry.length > 254 || !emailPattern.test(entry) || /[\r\n\0,<>]/.test(entry)) {
      throw new Error(`Invalid ${label} address`);
    }
    return entry;
  });
}

function payload(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Email must be an object');
  const to = addresses(input.to, 'to', true);
  const cc = addresses(input.cc, 'cc');
  const bcc = addresses(input.bcc, 'bcc');
  const subject = input.subject;
  const body = input.body;
  const replyToMessageId = input.replyToMessageId;
  if (typeof subject !== 'string' || !subject.trim() || subject.length > 200 || /[\r\n\0]/.test(subject)) {
    throw new Error('Subject must be a nonempty single line under 200 characters');
  }
  if (typeof body !== 'string' || !body.trim() || body.length > 100000 || body.includes('\0')) {
    throw new Error('Body must contain 1–100000 characters');
  }
  if (replyToMessageId !== undefined && (typeof replyToMessageId !== 'string' || !/^[A-Za-z0-9_-]{8,128}$/.test(replyToMessageId))) {
    throw new Error('Invalid Gmail message ID for reply');
  }
  return { to, cc, bcc, subject, body, ...(replyToMessageId ? { replyToMessageId } : {}) };
}

function digest(email) { return crypto.createHash('sha256').update(JSON.stringify(email)).digest('hex'); }

function directory() {
  fs.mkdirSync(root, { recursive: true, mode: 0o700 });
  const stat = fs.lstatSync(root);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error('Outbox is not a real directory');
  fs.chmodSync(root, 0o700);
  return root;
}

function fileFor(id) {
  if (!/^[a-f0-9]{32}$/.test(id)) throw new Error('Invalid draft ID');
  return path.join(directory(), `${id}.json`);
}

function prepare(input) {
  const email = payload(input);
  const id = crypto.randomBytes(16).toString('hex');
  const record = { version: 1, id, status: 'prepared', createdAt: new Date().toISOString(), email, sha256: digest(email) };
  fs.writeFileSync(fileFor(id), JSON.stringify(record, null, 2), { flag: 'wx', mode: 0o600 });
  return record;
}

function read(id) {
  const file = fileFor(id);
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o077)) throw new Error('Unsafe draft file');
  const record = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (record.version !== 1 || record.id !== id || record.sha256 !== digest(payload(record.email))) {
    throw new Error('Draft has changed or is invalid');
  }
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
    .map(({ id, status, createdAt, email, sha256 }) => ({ id, status, createdAt, to: email.to, subject: email.subject, sha256 }));
}

module.exports = { prepare, read, write, list, payload, digest, fileFor };
