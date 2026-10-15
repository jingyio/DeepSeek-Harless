/** Account-local, reversible conversation deletion. No history or files are removed. */
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { ApiSessionNotFound } from '@deepseek-ai/dsh-api-session-controller';
import { z } from 'zod';

const idSchema = z.string().min(1).max(200).regex(/^[A-Za-z0-9_-]+$/);
const entrySchema = z.object({ session_id: idSchema, title: z.string(), deleted_at: z.string(),
  workspace_id: z.string().optional(), private_session_ids: z.array(idSchema) });
type Entry = z.infer<typeof entrySchema>;
export class SessionTrashError extends Error {
  code: string; status: number;
  constructor(code: string, message: string, status = 400) { super(message); this.code = code; this.status = status; }
}
type Host = {
  owns(id: string): Promise<void>;
  isPrivate(id: string): boolean;
  privateChildren(id: string): string[];
  busy(ids: string[]): boolean;
  describe(id: string): Promise<{ title: string; workspace_id?: string }>;
  changed?(id: string, deleted: boolean): Promise<void> | void;
};
export function createSessionTrash(path: string, principal: string, host: Host) {
  const schema = z.object({ version: z.literal(1), principal: z.string(), entries: z.array(entrySchema) });
  const state = existsSync(path) ? schema.parse(JSON.parse(readFileSync(path, 'utf8'))) : { version: 1 as const, principal, entries: [] as Entry[] };
  if (state.principal !== principal) throw Error('session_trash_scope_mismatch');
  const listeners = new Set<() => void>();
  const isDeleted = (id: string) => state.entries.some(row => row.session_id === id || row.private_session_ids.includes(id));
  const assertVisible = (id: string) => {
    if (isDeleted(id)) throw new SessionTrashError('session_deleted', '这个对话已删除，可在“最近删除”中恢复。', 404);
  };
  const persist = (entries: Entry[]) => {
    const temporary = path + '.' + randomUUID() + '.tmp';
    writeFileSync(temporary, JSON.stringify({ ...state, entries }), { mode: 0o600 });
    renameSync(temporary, path); state.entries = entries;
    for (const listener of listeners) { try { listener(); } catch { /* A stale subscriber cannot undo durable deletion. */ } }
  };
  const notify = async (id: string, deleted: boolean) => {
    try { await host.changed?.(id, deleted); } catch { /* Lists recover from the persisted tombstone on refresh. */ }
  };
  return {
    isDeleted, assertVisible,
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    list() { return { sessions: state.entries.map(({ private_session_ids, ...row }) => ({ ...row }))
        .sort((a, b) => b.deleted_at.localeCompare(a.deleted_at)),
      deleted_session_ids: [...new Set(state.entries.flatMap(row => [row.session_id, ...row.private_session_ids]))] }; },
    async mutate(action: unknown, value: unknown) {
      if (!['delete', 'restore'].includes(String(action)) || !idSchema.safeParse(value).success)
        throw new SessionTrashError('invalid_trash_request', '请选择要删除或恢复的对话。');
      const id = value as string, previous = state.entries.find(row => row.session_id === id);
      // Owned tombstones are the restore authority, including after a restart.
      // Foreign IDs and private lane IDs never reveal an existence distinction.
      if (!previous) await host.owns(id);
      if (host.isPrivate(id)) throw new SessionTrashError('session_not_found', '找不到这个对话。', 404);
      if (action === 'restore') {
        if (previous) { persist(state.entries.filter(row => row !== previous)); await notify(id, false); }
        return { session_id: id, deleted: false };
      }
      if (previous) return { session_id: id, deleted: true, deleted_at: previous.deleted_at };
      const children = [...new Set(host.privateChildren(id))].filter(child => child !== id);
      if (host.busy([id, ...children])) throw new SessionTrashError('session_busy', '对话正在执行，请先停止或等待回复完成，再删除。', 409);
      const description = await host.describe(id);
      // The caller serializes admission and deletion. Recheck after cold I/O.
      if (host.busy([id, ...children])) throw new SessionTrashError('session_busy', '对话正在执行，请先停止或等待回复完成，再删除。', 409);
      const row = entrySchema.parse({ session_id: id, title: description.title, deleted_at: new Date().toISOString(),
        ...(description.workspace_id ? { workspace_id: description.workspace_id } : {}), private_session_ids: children });
      persist([...state.entries, row]); await notify(id, true);
      return { session_id: id, deleted: true, deleted_at: row.deleted_at };
    },
  };
}
type Trash = ReturnType<typeof createSessionTrash>;
function sessionRequestIds(value: any): string[] {
  if (typeof value === 'string') return [value];
  if (value?.address?.kind === 'subagent') return [value.address.parentSessionId, value.address.childSessionId];
  return [value?.address?.sessionId ?? value?.sessionId].filter(id => typeof id === 'string');
}
async function waitUntilVisible(ids: string[], trash: Trash, signal?: AbortSignal): Promise<boolean> {
  if (signal?.aborted) return false;
  if (!ids.some(trash.isDeleted)) return true;
  return new Promise(resolve => {
    let stop = () => {};
    const update = () => {
      if (!signal?.aborted && ids.some(trash.isDeleted)) return;
      stop(); signal?.removeEventListener('abort', update); resolve(!signal?.aborted);
    };
    stop = trash.subscribe(update); signal?.addEventListener('abort', update, { once: true }); update();
  });
}
function replaceMethod(target: any, method: string, replacement: any, undo: (() => void)[]) {
  const original = target[method]; target[method] = replacement;
  undo.push(() => { if (target[method] === replacement) target[method] = original; });
}

/** Native search builds its authorized-ID set from this public query seam.
 * Filter before it counts the first 20 hits, so deleted/private matches cannot
 * starve older visible matches. Keep native cursor, cancellation and work caps.
 */
export function protectDeletedSessionQuery(provider: any, trash: Trash, isPrivate: (id: string) => boolean = () => false) {
  const undo: (() => void)[] = [];
  const list = provider.listSessions.bind(provider);
  replaceMethod(provider, 'listSessions', async (...args: any[]) => {
    const records = await list(...args);
    return records.filter((record: any) => !trash.isDeleted(record.header.id) && !isPrivate(record.header.id));
  }, undo);
  return () => { for (const dispose of undo.reverse()) dispose(); };
}

/** Wrap public APIs, including cold reads and subscriptions opened before deletion. */
export function protectDeletedSessions(controller: any, trash: Trash) {
  const undo: (() => void)[] = [];
  const check = (id: unknown) => {
    if (typeof id === 'string' && trash.isDeleted(id)) throw new ApiSessionNotFound('这个对话已删除，可在“最近删除”中恢复。');
  };
  for (const method of ['inspect', 'resolveAgent', 'create', 'selectModel', 'rename', 'fork', 'prompt', 'attachment', 'updateQueue', 'cancel', 'page']) {
    const original = controller[method]?.bind(controller); if (!original) continue;
    replaceMethod(controller, method, (...args: any[]) => { for (const id of sessionRequestIds(args[0])) check(id); return original(...args); }, undo);
  }
  for (const method of ['list', 'search']) {
    const original = controller[method]?.bind(controller); if (!original) continue;
    replaceMethod(controller, method, async (...args: any[]) => {
      const result = await original(...args);
      return { ...result, items: result.items.filter((row: any) => !trash.isDeleted(row.sessionId)) };
    }, undo);
  }
  const follow = controller.follow?.bind(controller);
  if (follow) replaceMethod(controller, 'follow', async function* (request: any, signal?: AbortSignal) {
    const ids = sessionRequestIds(request); for (const id of ids) check(id);
    // A native Client Session retains its watched binding across close/open.
    // Keep this subscription alive while hidden; ending it would leave the
    // restored same-ID conversation unable to receive future event frames.
    for await (const frame of follow(request, signal)) {
      for (;;) {
        if (!await waitUntilVisible(ids, trash, signal)) return;
        // Deletion can race the microtask used to resume a pending frame.
        if (ids.some(trash.isDeleted)) continue;
        yield frame; break;
      }
    }
  }, undo);
  const control = controller.control?.bind(controller);
  if (control) replaceMethod(controller, 'control', async function* (...args: any[]) {
    const visible = (map: Record<string, unknown>) => Object.fromEntries(Object.entries(map).filter(([id]) => !trash.isDeleted(id)));
    for await (const frame of control(...args)) {
      if (frame.type === 'baseline') yield { ...frame, value: { ...frame.value,
        queues: visible(frame.value.queues), jobs: visible(frame.value.jobs), projections: visible(frame.value.projections) } };
      else if (!trash.isDeleted(frame.sessionId)) yield frame;
    }
  }, undo);
  return () => { for (const dispose of undo.reverse()) dispose(); };
}

export function protectDeletedSessionFiles(files: any, uploads: any, trash: Trash) {
  const undo: (() => void)[] = [];
  const check = (id: string) => { if (trash.isDeleted(id)) throw new ApiSessionNotFound('这个对话已删除，请先恢复。'); };
  for (const method of ['read', 'readBytes', 'readAll', 'readRelated', 'stat', 'list']) {
    const original = files?.[method]?.bind(files); if (!original) continue;
    replaceMethod(files, method, (...args: any[]) => { check(args[0]?.sessionId); return original(...args); }, undo);
  }
  const changes = files?.changes?.bind(files);
  if (changes) replaceMethod(files, 'changes', async function* (scope: any, signal?: AbortSignal) {
    check(scope.sessionId); const lifetime = new AbortController();
    const stop = trash.subscribe(() => { if (trash.isDeleted(scope.sessionId)) lifetime.abort(); });
    try {
      for await (const frame of changes(scope, signal ? AbortSignal.any([signal, lifetime.signal]) : lifetime.signal)) {
        if (lifetime.signal.aborted) return; check(scope.sessionId); yield frame;
      }
    } catch (error) { if (!lifetime.signal.aborted) throw error; } finally { stop(); }
  }, undo);
  for (const method of ['upload', 'uploadStream']) {
    const original = uploads?.[method]?.bind(uploads); if (!original) continue;
    replaceMethod(uploads, method, (...args: any[]) => { check(method === 'upload' ? args[0]?.session?.id : args[0]?.sessionId); return original(...args); }, undo);
  }
  return () => { for (const dispose of undo.reverse()) dispose(); };
}

export function registerSessionTrashRoute(ctx: any, trash: Trash, serialize: <T>(operation: () => Promise<T>) => Promise<T>) {
  ctx.effect(() => ctx.connection.fetch.register({ path: '/api/harless/session-trash', methods: ['GET', 'POST'], requestBody: 'buffered',
    async fetch(request: Request) {
      const rejected = ctx.connection.requestRejection(request);
      if (rejected) return new Response('Unauthorized', { status: rejected });
      try {
        if (request.method === 'GET' && new URL(request.url).searchParams.get('stream') === '1') {
          // Native api-session/removed is irreversible in its client Session
          // object. Reversible trash has a separate authenticated notification.
          let close = () => {};
          const body = new ReadableStream({
            start(stream) {
              let closed = false, stop = () => {}, heartbeat: ReturnType<typeof setInterval> | undefined;
              const encoder = new TextEncoder();
              close = () => { if (closed) return; closed = true; stop(); if (heartbeat) clearInterval(heartbeat);
                request.signal.removeEventListener('abort', close); try { stream.close(); } catch {} };
              const send = (text: string) => { if (!closed) try { stream.enqueue(encoder.encode(text)); } catch { close(); } };
              stop = trash.subscribe(() => send('data: {"changed":true}\n\n'));
              request.signal.addEventListener('abort', close, { once: true });
              if (request.signal.aborted) { close(); return; }
              send('data: {"changed":true}\n\n');
              heartbeat = setInterval(() => send(': keepalive\n\n'), 15000);
            },
            cancel() { close(); },
          });
          return new Response(body, { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' } });
        }
        let result: unknown;
        if (request.method === 'GET') result = trash.list();
        else {
          if (!(request.headers.get('content-type') ?? '').startsWith('application/json'))
            throw new SessionTrashError('invalid_trash_request', '请求格式不正确。');
          const text = await request.text();
          if (text.length > 4096) throw new SessionTrashError('invalid_trash_request', '请求过长。', 413);
          let body: any; try { body = JSON.parse(text); } catch { throw new SessionTrashError('invalid_trash_request', '请求格式不正确。'); }
          result = await serialize(() => trash.mutate(body?.action, body?.session_id));
        }
        return Response.json(result, { headers: { 'Cache-Control': 'no-store' } });
      } catch (error: any) {
        const known = typeof error.code === 'string' && typeof error.status === 'number';
        return Response.json({ error: { code: known ? error.code : 'session_trash_failed',
          message: known ? error.message : '无法更新对话，请刷新后重试。' } }, { status: known ? error.status : 400 });
      }
    },
  }), 'harless-session-trash-api');
}
