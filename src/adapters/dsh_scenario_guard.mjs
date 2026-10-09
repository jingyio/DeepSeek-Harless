/** Scenario capability boundary; arbitrary MCP extensions share this host plugin. */
export const name = 'sss-scenario-guard';
export const inject = ['tools', 'agents'];

export function apply(ctx) {
  const names = JSON.parse(process.env.SSS_SCENARIO_TOOLS ?? '[]');
  if (!Array.isArray(names) || !names.length ||
      names.some(name => typeof name !== 'string' || !/^mcp__[a-zA-Z0-9_]+$/.test(name)) ||
      new Set(names).size !== names.length) throw new TypeError('Invalid scenario tool allowlist');
  const allowed = new Set(names);
  ctx.on('agent/created', ({ agent }) => {
    agent.ctx.tools.restrict({ allow: names });
    agent.ctx.tools.guard(call => allowed.has(call.name) ? undefined : 'Tool is outside this scenario');
  });
}
