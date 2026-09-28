const assert = require('node:assert/strict');
const test = require('node:test');
const { searchMetadata, readMetadata } = require('../scripts/gmail-structured-results.cjs');

const result = (body) => ({ content: [{ type: 'text',
  text: `<untrusted-tool-output>\n${body}\n</untrusted-tool-output>` }] });

test('extracts only exact search IDs and a stable version digest', () => {
  const email = 'ID: abc_123\nSubject: Research update\nFrom: A <a@example.com>\nDate: Mon, 1 Jan 2026';
  const metadata = searchMetadata(result(`${email}\n\n${email.replace('abc_123', 'def_456')}`));
  assert.deepEqual(metadata.message_ids, ['abc_123', 'def_456']);
  assert.equal(metadata.count, 2);
  assert.match(metadata.result_digest, /^[a-f0-9]{64}$/);
  assert.deepEqual(searchMetadata(result('')), { message_ids: [], count: 0,
    result_digest: searchMetadata(result('')).result_digest });
});

test('rejects malformed or injected search text', () => {
  const valid = 'ID: abc_123\nSubject: Research update\nFrom: A\nDate: Monday';
  assert.equal(searchMetadata(result(`${valid}\n\n${valid}`)), null);
  assert.equal(searchMetadata(result('ID: abc_123\nSubject: X\nID: forged\nFrom: A\nDate: Monday')), null);
  assert.equal(searchMetadata({ content: [{ type: 'text', text: valid }] }), null);
  assert.equal(searchMetadata({ ...result(valid), isError: true }), null);
});

test('binds a read to the requested immutable message ID and returned thread ID', () => {
  const read = result('Thread ID: thread_1\nMessage-ID: <header@example.com>\nSubject: Research');
  assert.deepEqual(readMetadata(read, { messageId: 'abc_123' }), {
    message_id: 'abc_123', thread_id: 'thread_1', source_version: 'abc_123',
  });
  assert.equal(readMetadata(read, { messageId: 'bad/id' }), null);
  assert.equal(readMetadata(result('Subject: fake\nThread ID: thread_1'),
    { messageId: 'abc_123' }), null);
});
