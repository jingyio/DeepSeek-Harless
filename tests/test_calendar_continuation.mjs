import assert from 'node:assert/strict';
import test from 'node:test';
import { createCalendarContinuation, validateCalendarArtifact } from
  '../src/motif_core/calendar_continuation.mjs';
import { digest } from '../src/motif_core/online_skill_runtime.mjs';

const find = 'mcp__calendar_fixture__find-available-slots';
const validate = 'mcp__calendar_fixture__validate-slot';
const version = 'a'.repeat(64);
function artifact() {
  const row = {
    status: 'trace_validated_read_only', motif_id: 'calendar_pair_test',
    tools: [find, validate], source_trace_ids: ['B', 'C'],
    validation_trace_id: 'D', heldout_guard_checks: {
      find_before_validate: true, unchanged_task_arguments: true,
      candidate_from_result: true, same_fresh_source: true,
      validated_earliest: true },
    source_guard: 'sourceSha256_equal_after_live_validation',
    argument_carryover: ['calendarId', 'timeZone', 'timeWindows', 'durationMinutes']
      .map((param) => ({ from_param: param, to_param: param })),
    transfer_evidence: [['earliest.start', 'candidateStart'],
      ['earliest.end', 'candidateEnd']].map(([from_field, to_param]) => ({
      from_tool: find, from_field, to_tool: validate, to_param,
      supporting_trace_ids: ['B', 'C'] })),
  };
  return { ...row, certified_digest: digest(row) };
}
const args = { calendarId: 'test-calendar', timeZone: 'Asia/Shanghai',
  timeWindows: [{ start: '2026-10-16T09:00:00+08:00',
    end: '2026-10-16T12:00:00+08:00' }], durationMinutes: 55 };
const output = { earliest: { start: '2026-10-16T11:00:00+08:00',
  end: '2026-10-16T11:55:00+08:00' }, sourceSha256: version };
const offered = { name: validate, parameters: { type: 'object',
  required: [...Object.keys(args), 'candidateStart', 'candidateEnd'],
  properties: Object.fromEntries([...Object.keys(args), 'candidateStart',
    'candidateEnd'].map((key) => [key, { type: 'string' }])) } };
const next = () => 'model-called';

test('certified continuation copies exact model-selected inputs and skips one request', async () => {
  const log = [];
  const motif = createCalendarContinuation({ artifact: artifact(), sessionId: 'S',
    audit: (row) => log.push(row) });
  assert.equal(motif.intercept({ sessionId: 'S', tools: [offered] }, next), 'model-called');
  motif.observe({ name: find, arguments: args, callId: 'F' },
    { content: [{ type: 'text', text: JSON.stringify(output) }] });
  const stream = motif.intercept({ sessionId: 'S', tools: [offered] }, next);
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  const call = chunks.find((chunk) => chunk.type === 'tool-call-delta');
  assert.equal(call.name, validate);
  assert.deepEqual(JSON.parse(call.argumentsDelta), { ...args,
    candidateStart: output.earliest.start, candidateEnd: output.earliest.end });
  motif.observe({ name: validate, arguments: JSON.parse(call.argumentsDelta), id: call.id,
    callId: call.id }, { content: [{ type: 'text', text: JSON.stringify({
      valid: true, isEarliest: true, sourceSha256: version }) }] });
  assert.equal(motif.state.halted, false);
  assert.ok(log.some((row) => row.kind === 'model_request_skipped_verified'));
  assert.equal(motif.intercept({ sessionId: 'S', tools: [offered] }, next), 'model-called');
});

test('source change after live validation hands control back to model', async () => {
  const motif = createCalendarContinuation({ artifact: artifact(), sessionId: 'S' });
  motif.observe({ name: find, arguments: args, callId: 'F' },
    { content: [{ type: 'text', text: JSON.stringify(output) }] });
  const stream = motif.intercept({ sessionId: 'S', tools: [offered] }, next);
  let call;
  for await (const chunk of stream) if (chunk.type === 'tool-call-delta') call = chunk;
  motif.observe({ name: validate, arguments: JSON.parse(call.argumentsDelta),
    callId: call.id }, { content: [{ type: 'text', text: JSON.stringify({
      valid: false, isEarliest: false, sourceSha256: 'b'.repeat(64) }) }] });
  assert.equal(motif.state.halted, true);
  assert.equal(motif.intercept({ sessionId: 'S', tools: [offered] }, next), 'model-called');
});

test('modified certificate and malformed calendar inputs are rejected', () => {
  const changed = artifact();
  changed.argument_carryover.pop();
  assert.throws(() => validateCalendarArtifact(changed));
  const motif = createCalendarContinuation({ artifact: artifact(), sessionId: 'S' });
  motif.observe({ name: find, arguments: { ...args, durationMinutes: '55' },
    callId: 'F' }, { content: [{ type: 'text', text: JSON.stringify(output) }] });
  assert.equal(motif.intercept({ sessionId: 'S', tools: [offered] }, next), 'model-called');
});

test('a failed first lookup blocks reuse even if the Agent retries', () => {
  const motif = createCalendarContinuation({ artifact: artifact(), sessionId: 'S' });
  motif.observe({ name: find, arguments: args, callId: 'failed' },
    { isError: true, content: [{ type: 'text', text: 'calendar unavailable' }] });
  motif.observe({ name: find, arguments: args, callId: 'retried' },
    { content: [{ type: 'text', text: JSON.stringify(output) }] });
  assert.equal(motif.state.halted, true);
  assert.equal(motif.intercept({ sessionId: 'S', tools: [offered] }, next), 'model-called');
});
