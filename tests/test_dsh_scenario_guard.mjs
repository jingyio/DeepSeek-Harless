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

test('PTC permits only its native transport plus the same MCP bindings, never a shell', () => {
  const previous=process.env.SSS_SCENARIO_TOOLS, mode=process.env.SSS_SCENARIO_PRESENTATION;
  process.env.SSS_SCENARIO_TOOLS='["mcp__demo__pin_note"]';process.env.SSS_SCENARIO_PRESENTATION='ptc';
  try {
    let handler,guard,presentation='ptc';
    apply({on(_event,fn){handler=fn;}});
    handler({agent:{ctx:{tools:{restrict(){},guard(fn){guard=fn;},modeFor(){return presentation;}}}}});
    assert.equal(guard({name:'run_code'}),undefined);assert.equal(guard({name:'mcp__demo__pin_note'}),undefined);
    assert.match(guard({name:'bash'}),/outside/);assert.match(guard({name:'mcp__other__read'}),/outside/);
    presentation='native';assert.match(guard({name:'run_code'}),/outside/);
  } finally {
    if(previous===undefined)delete process.env.SSS_SCENARIO_TOOLS;else process.env.SSS_SCENARIO_TOOLS=previous;
    if(mode===undefined)delete process.env.SSS_SCENARIO_PRESENTATION;else process.env.SSS_SCENARIO_PRESENTATION=mode;
  }
});
