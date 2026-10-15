/** Durable private execution identities, separate from public conversation titles. */
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { z } from 'zod';

export function registerPrivateLanes(ctx: any, output: string, principal: string,
  legacy: (id: string) => boolean = () => false) {
  const path = join(output, 'private-lane-sessions.json');
  const schema = z.object({ version: z.literal(1), principal: z.string(), sessions: z.record(z.string(), z.string()) });
  const state = existsSync(path) ? schema.parse(JSON.parse(readFileSync(path, 'utf8'))) : { version: 1, principal, sessions: {} as Record<string,string> };
  if (state.principal !== principal) throw Error('private_lane_scope_mismatch');
  const isPrivate = (id: string) => Object.hasOwn(state.sessions, id) || legacy(id);
  const reserve = (parent: string) => {
    const id = 'session-' + randomUUID();
    state.sessions[id] = parent;
    const temporary = path + '.' + randomUUID() + '.tmp';
    writeFileSync(temporary, JSON.stringify(state), { mode: 0o600 }); renameSync(temporary, path);
    return id;
  };
  // The marker is available in the very first api-session/added frame. It is
  // also folded on cold replay, so no title matching or async UI lookup races.
  ctx.sessionProjections?.register({ key: 'harlessComparisonLane', stateSchema: z.boolean(),
    init: (header: any) => isPrivate(header.id), apply: (state: boolean) => state,
    wire: { viewSchema: z.boolean(), view: (state: boolean) => state }, stateVersion: 1 });
  for (const method of ['list', 'search']) {
    const original = ctx.sessionController[method]?.bind(ctx.sessionController);
    if (original) ctx.sessionController[method] = async (...args: any[]) => {
      const result = await original(...args);
      return { ...result, items: result.items.filter((row: any) => !isPrivate(row.sessionId)) };
    };
  }
  return { isPrivate, reserve };
}
