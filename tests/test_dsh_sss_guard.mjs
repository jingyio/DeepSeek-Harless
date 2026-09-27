import assert from 'node:assert/strict';
import test from 'node:test';
import { apply, createProvenanceTracker, SSS_TOOLS } from '../src/adapters/dsh_sss_guard.mjs';

test('the dedicated DSH agent sees only SSS tools and cannot dispatch others', () => {
  let created;
  const restrictions = [];
  let gate;
  let resultObserver;
  apply({ on(event, callback) {
    assert.equal(event, 'agent/created');
    created = callback;
  }});
  created({ agent: { session: { id: 'test-session' }, ctx: {
    on(event, callback) {
      assert.equal(event, 'tools/result');
      resultObserver = callback;
    },
    tools: {
    restrict(filter) { restrictions.push(filter); },
    guard(callback) { gate = callback; },
  }}}});
  assert.deepEqual(restrictions, [{ allow: SSS_TOOLS }]);
  assert.equal(gate({ name: 'mcp__sss_runtime__collect_sources' }), undefined);
  assert.equal(gate({ name: 'mcp__sss_runtime__read_page' }), undefined);
  assert.equal(gate({ name: 'mcp__sss_runtime__refresh_sources' }), undefined);
  assert.equal(gate({ name: 'mcp__sss_runtime__open_point' }), undefined);
  assert.equal(gate({ name: 'mcp__sss_runtime__resolve_point' }), undefined);
  assert.match(gate({ name: 'bash' }), /Motif runtime only/);
  assert.match(gate({ name: 'mcp__google_gmail__send_email' }), /Motif runtime only/);
  assert.equal(typeof resultObserver, 'function');
});

test('native provenance records only a host-issued SSS handle', () => {
  let latest;
  const track = createProvenanceTracker((sidecar) => {
    latest = structuredClone(sidecar);
  });
  track({ name: 'mcp__sss_runtime__collect_sources', callId: 'c1', arguments: {} },
    { isError: false, value: { structuredContent: { run_id: 'opaque-run' } } });
  track({ name: 'mcp__sss_runtime__read_page', callId: 'c2',
    arguments: { run_id: 'opaque-run', source: 'a.md', page: 1 } },
    { isError: false, value: {} });
  assert.deepEqual(latest, { c2: { run_id: {
    from_call_id: 'c1', from_field: 'run_id',
  } } });
  track({ name: 'mcp__sss_runtime__read_page', callId: 'c3',
    arguments: { run_id: 'unseen-run' } }, { isError: false, value: {} });
  assert.equal(latest.c3, undefined);
  track({ name: 'mcp__sss_runtime__refresh_sources', callId: 'c4',
    arguments: { run_id: 'opaque-run' } },
    { isError: false, value: { content: [{ type: 'text', text: '{"run_id":"next-run"}' }] } });
  track({ name: 'mcp__sss_runtime__open_point', callId: 'c5',
    arguments: { run_id: 'next-run' } },
    { isError: false, value: { structuredContent: {
      run_id: 'next-run', frontier_id: 'frontier-one',
      point_id: 'P1', question: 'Which result holds?',
      allowed_sources: ['a.md'], handoff_signature: 'signed-frontier',
    } } });
  assert.deepEqual(latest.c5.run_id, {
    from_call_id: 'c4', from_field: 'run_id',
  });
  track({ name: 'mcp__sss_runtime__resolve_point', callId: 'c6',
    arguments: { run_id: 'next-run', frontier_id: 'frontier-one',
      point_id: 'P1', question: 'Which result holds?',
      source_allowlist: ['a.md'], handoff_signature: 'signed-frontier' } },
    { isError: false, value: {} });
  for (const [param, field] of Object.entries({
    frontier_id: 'frontier_id', point_id: 'point_id', question: 'question',
    source_allowlist: 'allowed_sources', handoff_signature: 'handoff_signature',
  })) {
    assert.deepEqual(latest.c6[param], {
      from_call_id: 'c5', from_field: field,
    });
  }
  track({ name: 'mcp__sss_runtime__resolve_point', callId: 'c7',
    arguments: { run_id: 'next-run', frontier_id: 'invented',
      point_id: 'P1', question: 'different question',
      source_allowlist: ['other.md'], handoff_signature: 'forged' } },
    { isError: false, value: {} });
  assert.equal(latest.c7.frontier_id, undefined);
  assert.equal(latest.c7.question, undefined);
  assert.equal(latest.c7.source_allowlist, undefined);
  assert.equal(latest.c7.handoff_signature, undefined);
});
