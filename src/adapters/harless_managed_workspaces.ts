/** Account-local workspace creation. Browser input is a name, never a host path. */
import { createHash, randomUUID } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, renameSync, realpathSync, lstatSync, existsSync } from 'node:fs';
import { join, resolve, isAbsolute, dirname } from 'node:path';
import { clientRequestSchema } from '@deepseek-ai/dsh-client-connection';

export class ManagedWorkspaceError extends Error {
  code: string; status: number;
  constructor(code: string, message: string, status = 400) { super(message); this.code = code; this.status = status; }
}
const forbidden = () => new ManagedWorkspaceError('gateway/forbidden', '请通过“新建工作区”填写名称，平台会自动创建独立目录。', 403);
export function workspaceDisplayName(value: unknown): string {
  if (typeof value !== 'string' || /[\x00-\x1f\x7f/\\:]/.test(value)) throw new ManagedWorkspaceError('invalid_workspace_name', '名称不能包含路径分隔符或控制字符。');
  const name = value.normalize('NFC').trim();
  if (!name || [...name].length > 64 || name === '.' || name === '..') throw new ManagedWorkspaceError('invalid_workspace_name', '请输入 1–64 个字符的工作区名称。');
  return name;
}
const nameKey = (name: string) => name.normalize('NFKC').toLocaleLowerCase('en-US');
const view = (workspace: any) => ({ workspaceId: workspace.id ?? workspace.workspaceId, path: workspace.path,
  title: workspace.title, sessionIds: [...workspace.sessionIds], createdAt: workspace.createdAt, updatedAt: workspace.updatedAt });
/** Public location is an opaque account-local address, never a host directory. */
export const publicWorkspaceView = (workspace: any) => ({ ...view(workspace), path: '/workspaces/' + (workspace.id ?? workspace.workspaceId) });

export function protectWorkspaceProjection(controller: any) {
  if (!controller) return;
  const follow = controller.follow.bind(controller);
  controller.follow = async function* (signal: AbortSignal) {
    for await (const frame of follow(signal)) {
      if (frame.type === 'baseline') yield { ...frame, value: { ...frame.value, items: frame.value.items.map(publicWorkspaceView) } };
      else if (frame.type === 'upsert') yield { ...frame, workspace: publicWorkspaceView(frame.workspace) };
      else yield frame;
    }
  };
  for (const name of ['rename', 'insertSessionBefore']) {
    const original = controller[name].bind(controller);
    controller[name] = async (...args: any[]) => {
      const result = await original(...args);
      return { ...result, workspace: publicWorkspaceView(result.workspace) };
    };
  }
}

export function createManagedWorkspaceService(output: string, principal: string, registry: any) {
  if (typeof principal !== 'string' || !principal) throw Error('Missing managed workspace principal');
  mkdirSync(output, { recursive: true, mode: 0o700 });
  const parent = realpathSync(output);
  const managed = join(parent, 'managed-workspaces');
  if (existsSync(managed) && lstatSync(managed).isSymbolicLink()) throw forbidden();
  mkdirSync(managed, { recursive: true, mode: 0o700 });
  if (realpathSync(managed) !== managed) throw forbidden();
  const root = join(managed, createHash('sha256').update(principal).digest('hex'));
  if (existsSync(root) && lstatSync(root).isSymbolicLink()) throw forbidden();
  mkdirSync(root, { recursive: true, mode: 0o700 });
  const index = join(root, 'workspaces.json');
  const state = existsSync(index) ? JSON.parse(readFileSync(index, 'utf8')) : { version: 1, principal, entries: {} };
  if (state.version !== 1 || state.principal !== principal || !state.entries || typeof state.entries !== 'object' || Array.isArray(state.entries))
    throw Error('Managed workspace ownership record is invalid');
  const save = () => { const temporary = index + '.' + randomUUID() + '.tmp'; writeFileSync(temporary, JSON.stringify(state), { mode: 0o600 }); renameSync(temporary, index); };
  let pending: Promise<unknown> = Promise.resolve();
  const safeDirectory = (id: string) => {
    if (!/^[a-f0-9-]{36}$/.test(id) || realpathSync(managed) !== managed || realpathSync(root) !== root) throw forbidden();
    const path = join(root, id);
    if (existsSync(path) && (lstatSync(path).isSymbolicLink() || realpathSync(path) !== path)) throw forbidden();
    return path;
  };
  async function create(input: any) {
    if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).some(key => !['name', 'request_id'].includes(key)))
      throw new ManagedWorkspaceError('invalid_workspace_request', '新建工作区只需要名称。');
    const name = workspaceDisplayName(input.name);
    if (typeof input.request_id !== 'string' || !/^[A-Za-z0-9_-]{16,128}$/.test(input.request_id))
      throw new ManagedWorkspaceError('invalid_workspace_request', '请求标识无效，请重新打开新建工作区。');
    const operation = pending.then(async () => {
      let entry = state.entries[input.request_id];
      if (entry && entry.name !== name) throw new ManagedWorkspaceError('workspace_request_conflict', '此请求已用于另一个名称，请重新打开新建工作区。', 409);
      const fresh = !entry;
      if (!entry) {
        entry = { id: randomUUID(), name };
      }
      const path = safeDirectory(entry.id);
      if (registry.list().some((row: any) => resolve(row.path) !== path && nameKey(row.title) === nameKey(name)))
        throw new ManagedWorkspaceError('workspace_name_conflict', '你已有同名工作区，请换一个名称。', 409);
      if (fresh) { state.entries[input.request_id] = entry; save(); }
      mkdirSync(path, { recursive: true, mode: 0o700 });
      const workspace = await registry.create(path, name);
      return { workspace: view(workspace) };
    });
    pending = operation.catch(() => undefined);
    return operation;
  }
  function adopt(path: unknown) {
    if (typeof path === 'string' && path.startsWith('/workspaces/')) {
      const known = registry.list().find((row: any) => path === '/workspaces/' + row.id);
      if (!known) throw forbidden();
      path = known.path; // Continue through the same server-side path guard.
    }
    if (typeof path !== 'string' || !isAbsolute(path) || path.includes('\0')) throw forbidden();
    // Original registered workspaces remain valid; the public API can no longer
    // turn an arbitrary server directory into a newly registered workspace.
    const canonical = resolve(path);
    const known = registry.list().find((workspace: any) => resolve(workspace.path) === canonical);
    if (!known) throw forbidden();
    if (dirname(canonical) === root) safeDirectory(canonical.slice(root.length + 1));
    return { workspace: view(known), created: false };
  }
  return { root, create, adopt };
}

/** Exact Connection Fetch routes keep the host's normal authentication fence. */
export function registerManagedWorkspaceRoutes(ctx: any, { output, principal }: { output: string; principal: string }) {
  const service = createManagedWorkspaceService(output, principal, ctx.workspaceRegistry);
  protectWorkspaceProjection(ctx.workspaceController);
  const headers = { 'Cache-Control': 'no-store' };
  const reject = (request: Request) => ctx.connection.requestRejection?.(request);
  ctx.effect(() => ctx.connection.fetch.register({ path: '/api/harless/workspaces', methods: ['POST'], requestBody: 'buffered',
    fetch: async (request: Request) => {
      const denied = reject(request); if (denied) return new Response('', { status: denied });
      try {
        if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') return new Response('', { status: 415 });
        const text = await request.text(); if (text.length > 4096) return new Response('', { status: 413 });
        let input; try { input = JSON.parse(text); } catch { throw new ManagedWorkspaceError('invalid_json', '请求格式无效。'); }
        const result = await service.create(input);
        return Response.json({ workspace: publicWorkspaceView(result.workspace) }, { headers });
      } catch (error: any) {
        return Response.json({ error: { code: error instanceof ManagedWorkspaceError ? error.code : 'workspace_create_failed',
          message: error instanceof ManagedWorkspaceError ? error.message : '工作区暂时无法创建，请重试。' } },
        { status: error instanceof ManagedWorkspaceError ? error.status : 500, headers });
      }
    } }), 'geneloop-managed-workspace-create');
  for (const endpoint of ['workspace/create', 'directoryPicker/list', 'directoryPicker/createDirectory', 'directoryPicker/pick']) {
    ctx.effect(() => ctx.connection.fetch.register({ path: '/api/' + endpoint, methods: ['POST'], requestBody: 'buffered',
      fetch: async (request: Request) => {
        const denied = reject(request); if (denied) return new Response('', { status: denied });
        if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') return new Response('', { status: 415 });
        let message: any;
        try { message = clientRequestSchema.parse(await request.json()); } catch { return new Response('', { status: 400 }); }
        let result;
        try {
          if (message.method !== endpoint || !message.payload || Object.keys(message.payload).join(',') !== 'args') throw forbidden();
          if (endpoint !== 'workspace/create') throw forbidden();
          const args = message.payload.args;
          if (!args || Object.keys(args).join(',') !== 'request' || !args.request || Object.keys(args.request).join(',') !== 'path') throw forbidden();
          const adopted = service.adopt(args.request.path);
          result = { ok: true, value: { ...adopted, workspace: publicWorkspaceView(adopted.workspace) } };
        } catch (error: any) {
          result = { ok: false, error: { code: 'gateway/forbidden', message: forbidden().message, details: {} } };
        }
        return Response.json({ type: 'server-response', rpcId: message.rpcId, result }, { headers });
      } }), 'geneloop-managed-workspace-' + endpoint);
  }
  return service;
}
