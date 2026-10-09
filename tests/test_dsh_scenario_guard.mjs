import { test } from 'node:test';
import assert from 'node:assert/strict';
import { apply } from '../src/adapters/dsh_scenario_guard.mjs';

test('scenario tools are restricted and the execution guard rejects other calls', () => {
  const old = process.env.SSS_SCENARIO_TOOLS;
  process.env.SSS_SCENARIO_TOOLS = JSON.stringify(['mcp__demo__pin_note']);
  try {
    let handler, restriction, guard;
    apply({ on(event, fn) { assert.equal(event, 'agent/created'); handler = fn; } });
    handler({ agent: { ctx: { tools: {
      restrict(value) { restriction = value; }, guard(fn) { guard = fn; },
    } } } });
    assert.deepEqual(restriction, { allow: ['mcp__demo__pin_note'] });
    assert.equal(guard({name:'mcp__demo__pin_note'}), undefined);
    assert.match(guard({name:'bash'}), /outside/);
  } finally {
    if (old === undefined) delete process.env.SSS_SCENARIO_TOOLS;
    else process.env.SSS_SCENARIO_TOOLS = old;
  }
});
