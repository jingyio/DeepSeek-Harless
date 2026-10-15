/** Account-local conversation branching through public seeded-session APIs. */
import { randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { fallbackSessionTitle, normalizeSessionTitle, truncateTitleUtf8 } from '@deepseek-ai/dsh-session-title';

type Event = { type: string; seq: number; time?: number; data: any; [key: string]: any };
export type BranchSeed = {
  sessionId: string; sourceSessionId: string; title: string; seed: Event[];
  inheritedEventCount: number; sourceMeta: any; sourceAtSeq: number;
};
type BranchHost = {
  ensureOwned(id: string): Promise<void>;
  inspect(id: string): Promise<{ meta: any; events: Event[] }>;
  listTitles?(): Promise<string[]> | string[];
  /** Resolve app-owned comparison metadata to detached history, never task/rating references. */
  projectEvents?(sourceId: string, events: Event[]): Promise<Event[]> | Event[];
  /** Compose a FRESH session-local preset/workspace; never reuse the source's bound preset. */
  createSeeded(value: BranchSeed): Promise<void>;
};

export class SessionBranchError extends Error {
  code: string; status: number;
  constructor(code: string, message: string, status = 409) { super(message); this.code = code; this.status = status; }
}

/** Native fork anchors refer to an event inside a completed turn, not a message index. */
export function completedBranchPrefix(events: Event[], atSeq?: number): Event[] {
  if (atSeq !== undefined && (!Number.isSafeInteger(atSeq) || atSeq < 0))
    throw new SessionBranchError('invalid_branch_anchor', '分支位置无效，请刷新后重试。', 400);
  if (!Array.isArray(events) || events.some((event, index) => event.seq !== index))
    throw new SessionBranchError('invalid_branch_history', '无法读取完整的对话记录。');
  const lastSeq = events.at(-1)?.seq ?? -1;
  const boundary = atSeq === undefined || atSeq > lastSeq
    ? events.findLast(event => event.type === 'turn/end')
    : events.find(event => event.type === 'turn/end' && event.seq >= atSeq);
  if (!boundary) throw new SessionBranchError('branch_turn_incomplete', '请等待所选回复完成后再创建分支。');
  // Exclude all later events, including subsequent uploads and turn metadata.
  return structuredClone(events.slice(0, boundary.seq + 1));
}

export function branchTitleRoot(title: unknown): string {
  const value = typeof title === 'string' && title.trim() ? title.trim() : '新会话';
  return value.replace(/\s*(?:（\d+）|\(\d+\))$/u, '').trim() || '新会话';
}

/** Native titles live in session/title events; metadata alone is not authoritative. */
export function sessionBranchTitle(meta: any, events: Event[]): string {
  const logged = events.findLast(event => event.type === 'session/title' && typeof event.data?.title === 'string' && event.data.title.trim());
  const explicit = logged?.data.title ?? meta?.title;
  if (typeof explicit === 'string' && explicit.trim()) return normalizeSessionTitle(explicit, 80) || '新会话';
  for (const event of events) if (event.type === 'user/message' && event.data?.source?.kind === 'user') {
    const text = (event.data.content ?? []).filter((part: any) => part.type === 'text').map((part: any) => part.text).join('\n');
    // Match the installed native title service's deterministic fallback config.
    const title = fallbackSessionTitle(text, 5, 40);
    if (title) return title;
  }
  return '新会话';
}

/** One runtime serves one account; persist reservations so restarts cannot reuse a number. */
export function createSessionBranchService(output: string, principal: string, host: BranchHost) {
  const path = join(output, 'conversation-branches.json');
  const state: { version: 1; principal: string; counters: Record<string, number>; children: Record<string, any> } = {
    version: 1, principal, counters: {}, children: {},
  };
  try {
    const saved = JSON.parse(readFileSync(path, 'utf8'));
    if (saved.version !== 1 || saved.principal !== principal || !saved.counters || !saved.children ||
        Object.values(saved.counters).some(value => !Number.isSafeInteger(value) || Number(value) < 0))
      throw new SessionBranchError('branch_state_invalid', '分支状态无法校验，请联系管理员。');
    Object.assign(state, saved);
  } catch (error) { if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error; }
  const save = () => {
    mkdirSync(output, { recursive: true, mode: 0o700 });
    writeFileSync(path + '.tmp', JSON.stringify(state), { mode: 0o600 });
    renameSync(path + '.tmp', path);
  };
  let pending: Promise<unknown> = Promise.resolve();
  return {
    fork(request: { sessionId: string; atSeq?: number }): Promise<{ sessionId: string }> {
      const result = pending.then(async () => {
        // Ownership precedes reading history, filesystem writes, and number allocation.
        await host.ensureOwned(request.sessionId);
        const source = await host.inspect(request.sessionId);
        const prefix = completedBranchPrefix(source.events, request.atSeq);
        const sourceAtSeq = prefix.at(-1)!.seq;
        const projected = host.projectEvents ? await host.projectEvents(request.sessionId, prefix) : prefix;
        const seed = structuredClone(projected);
        // Live comparison task IDs would grant edits to the original ratings/results.
        // The projection is history only. A branch's next send gets fresh tasks/budgets.
        for (const event of seed) if (event.type === 'user/message') delete event.data.harless_comparison;
        if (seed.some((event, index) => event.seq !== index))
          throw new SessionBranchError('invalid_branch_projection', '分支记录无法校验，请刷新后重试。');
        const root = branchTitleRoot(sessionBranchTitle(source.meta, source.events));
        let number = Object.hasOwn(state.counters, root) ? state.counters[root] : 0;
        const existingTitles = await host.listTitles?.() ?? [];
        for (const title of existingTitles) {
          if (branchTitleRoot(title) !== root) continue;
          const match = /(?:（(\d+)）|\((\d+)\))$/u.exec(title);
          const used = Number(match?.[1] ?? match?.[2] ?? 0);
          if (Number.isSafeInteger(used)) number = Math.max(number, used);
        }
        if (number >= Number.MAX_SAFE_INTEGER) throw new SessionBranchError('branch_number_exhausted', '此对话的分支数量已达到上限。');
        const sessionId = 'session-' + randomUUID();
        let title: string;
        do {
          const suffix = '（' + (++number) + '）';
          title = truncateTitleUtf8(root, 80 - Buffer.byteLength(suffix)) + suffix;
        } while (existingTitles.includes(title));
        Object.defineProperty(state.counters, root, { value: number, configurable: true, writable: true, enumerable: true });
        state.children[sessionId] = { source: request.sessionId, at_seq: sourceAtSeq, title, status: 'reserved' };
        save();
        await host.createSeeded({ sessionId, sourceSessionId: request.sessionId, title, seed,
          inheritedEventCount: seed.length, sourceMeta: structuredClone(source.meta), sourceAtSeq });
        state.children[sessionId].status = 'created'; save();
        return { sessionId };
      });
      pending = result.catch(() => undefined);
      return result;
    },
  };
}
