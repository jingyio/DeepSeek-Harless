const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const state = fs.mkdtempSync(path.join(os.tmpdir(), 'sss-gmail-test-'));
process.env.GMAIL_MCP_STATE_DIR = state;
const outbox = require('../scripts/gmail-outbox.cjs');
const review = require('../scripts/gmail-review.cjs');
const reviewWeb = require('../scripts/gmail-review-web.cjs');

test.after(() => fs.rmSync(state, { recursive: true, force: true }));

test('prepare and review data are exact and private', () => {
  const email = { to: ['colleague@example.org'], subject: '研究进展：新结果', body: '你好，\n这是结果。' };
  const record = outbox.prepare(email);
  assert.equal(record.status, 'prepared');
  assert.equal(outbox.read(record.id).email.body, email.body);
  assert.equal(fs.statSync(outbox.fileFor(record.id)).mode & 0o077, 0);
  assert.equal(outbox.list().find((item) => item.id === record.id).subject, email.subject);
  const raw = Buffer.from(review.rawMessage(record.email), 'base64url').toString('utf8');
  assert.match(raw, /^To: colleague@example.org\r\n/);
  assert.match(raw, /Subject: =\?UTF-8\?B\?/);
  assert.equal(Buffer.from(raw.split('\r\n\r\n')[1].trim(), 'base64').toString('utf8'), email.body);
});

test('header injection and malformed addresses are rejected', () => {
  assert.throws(() => outbox.prepare({ to: ['a@example.org\r\nBcc: victim@example.org'], subject: 'x', body: 'y' }));
  assert.throws(() => outbox.prepare({ to: ['a@example.org'], subject: 'x\nBcc: victim@example.org', body: 'y' }));
  assert.throws(() => outbox.prepare({ to: [], subject: 'x', body: 'y' }));
  assert.throws(() => outbox.prepare({ to: ['a@example.org'], subject: 'x', body: 'y', replyToMessageId: 'x\r\nBcc: x' }));
});

test('reply headers are bound to a selected Gmail message', () => {
  const source = { threadId: 'thread123', payload: { headers: [
    { name: 'Message-ID', value: '<original@example.org>' },
    { name: 'References', value: '<older@example.org>' },
    { name: 'From', value: 'Colleague <colleague@example.org>' },
    { name: 'Subject', value: 'Question' },
  ] } };
  const context = review.replyContext(source);
  review.validateReply({ to: ['colleague@example.org'], cc: [], bcc: [], subject: 'Re: Question' }, context);
  assert.throws(() => review.validateReply({ to: ['other@example.org'], cc: [], bcc: [], subject: 'Re: Question' }, context));
  assert.throws(() => review.validateReply({ to: ['colleague@example.org'], cc: [], bcc: [], subject: 'Different topic' }, context));
  const raw = Buffer.from(review.rawMessage({ to: ['colleague@example.org'], cc: [], bcc: [], subject: 'Re: Question', body: 'Answer' }, 'me@example.org', context), 'base64url').toString('utf8');
  assert.match(raw, /In-Reply-To: <original@example.org>/);
  assert.match(raw, /References: <older@example.org> <original@example.org>/);
  assert.match(raw, /^From: me@example.org/m);
  assert.throws(() => review.replyContext({ threadId: 'x', payload: { headers: [{ name: 'Message-ID', value: 'bad\r\nBcc: x' }] } }));
});

test('changed prepared content is detected', () => {
  const record = outbox.prepare({ to: ['a@example.org'], subject: 'x', body: 'y' });
  const file = outbox.fileFor(record.id);
  const changed = JSON.parse(fs.readFileSync(file, 'utf8'));
  changed.email.body = 'tampered';
  fs.writeFileSync(file, JSON.stringify(changed), { mode: 0o600 });
  assert.throws(() => outbox.read(record.id), /changed/);
});

test('noninteractive send fails before reaching Gmail', () => {
  const record = outbox.prepare({ to: ['a@example.org'], subject: 'x', body: 'y' });
  const oauth = { installed: { client_id: 'test', client_secret: 'test' } };
  const sendToken = { scopes: ['gmail.send'], tokens: { access_token: 'fake', scope: 'https://www.googleapis.com/auth/gmail.send' } };
  fs.writeFileSync(path.join(state, 'oauth-client.json'), JSON.stringify(oauth), { mode: 0o600 });
  fs.writeFileSync(path.join(state, 'send-tokens.json'), JSON.stringify(sendToken), { mode: 0o600 });
  const result = spawnSync(process.execPath, [path.join(__dirname, '../scripts/gmail-review.cjs'), record.id], {
    env: { ...process.env, GMAIL_MCP_STATE_DIR: state }, input: `SEND ${record.id}\n`, encoding: 'utf8', timeout: 5000,
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /interactive terminal/);
  assert.equal(outbox.read(record.id).status, 'prepared');
});

test('browser review escapes mail content and rejects cross-origin submission', async () => {
  const record = outbox.prepare({ to: ['a@example.org'], subject: '<script>alert(1)</script>', body: '<img src=x>' });
  const html = reviewWeb.reviewPage({ record, senderAddress: 'me@example.org' }, '/send');
  assert.ok(!html.includes('<script>alert(1)</script>'));
  assert.ok(html.includes('&lt;img src=x&gt;'));
  const { server, url } = await reviewWeb.start(record.id, { quiet: true, open: false });
  try {
    const page = await fetch(`${url}/missing`);
    assert.equal(page.headers.get('referrer-policy'), 'same-origin');
    const blocked = await fetch(`${url}/send`, { method: 'POST', headers: { Origin: 'https://malicious.example', 'Content-Type': 'application/x-www-form-urlencoded' }, body: `confirmation=SEND+${record.id}` });
    assert.equal(blocked.status, 403);
    const checked = await fetch(`${url}/send`, { method: 'POST', headers: { Origin: new URL(url).origin, 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'confirmation=TEST' });
    assert.equal(checked.status, 400);
    assert.equal(outbox.read(record.id).status, 'prepared');
  } finally {
    server.close();
  }
});
