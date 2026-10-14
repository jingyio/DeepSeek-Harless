/** Explicit member RPC boundary; desktop file previews intentionally allow broader reads. */
import { realpathSync } from 'node:fs';
import { dirname, basename, resolve, relative, isAbsolute, sep } from 'node:path';
import { RemoteError } from '@deepseek-ai/dsh-typert-protocol';
const denied = () => new RemoteError('gateway/forbidden', '只允许访问当前账号的会话工作区。', {});
const inside = (root: string, path: string) => {
  const part = relative(root, path);
  return part === '' || (!isAbsolute(part) && part !== '..' && !part.startsWith('..' + sep));
};
function canonical(path: string): string {
  try { return realpathSync(path); }
  catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    const parent = dirname(path); if (parent === path) throw denied();
    return resolve(canonical(parent), basename(path));
  }
}
export function guardMemberFileRpc(gateway: any, lookup: (id: string) => Promise<any>, roots: string[]) {
  const allowed = roots.map(root => canonical(resolve(root)));
  const accountPath = (path: string) => {
    if (typeof path !== 'string' || !isAbsolute(path) || path.includes('\0')) throw denied();
    const target = canonical(path); if (!allowed.some(root => inside(root, target))) throw denied(); return target;
  };
  const scopedPath = (scope: any, path: string) => {
    const root = accountPath(scope?.workspaceRoot);
    if (typeof path !== 'string' || path.includes('\0')) throw denied();
    const target = canonical(resolve(root, path)); if (!inside(root, target)) throw denied(); return target;
  };
  async function check(request: any) {
    let scope: any; const args = { ...request.args };
    if (request.namespace === 'workspaceFiles') {
      if (typeof args.workspaceFileScopeId !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(args.workspaceFileScopeId)) throw denied();
      scope = await lookup(args.workspaceFileScopeId); accountPath(scope?.workspaceRoot);
      if (['list','stat','read','readAll','readBytes','readRelated'].includes(request.method)) {
        args.path = scopedPath(scope, args.path);
        if (request.method === 'readRelated') {
          const related = args.relativePath;
          if (typeof related !== 'string' || isAbsolute(related) || /^[a-z][a-z\d+.-]*:/i.test(related)) throw denied();
          scopedPath(scope, resolve(dirname(args.path), related.replaceAll('\\', '/')));
        }
      }
    } else if (request.namespace === 'workspace' && request.method === 'create') {
      args.request = { ...args.request, path: accountPath(args.request?.path) };
    } else if (request.namespace === 'directoryPicker' && ['list','createDirectory'].includes(request.method)) {
      args.path = accountPath(args.path ?? roots[0]);
    }
    return { request: { ...request, args }, scope };
  }
  const invoke = async (request: any) => {
    const checked = await check(request), result = await gateway.invoke(checked.request);
    if (checked.scope && result?.absolutePath) scopedPath(checked.scope, result.absolutePath);
    return result;
  };
  return { invoke, scope: (scope: any) => ({ ...scope, workspaceRoot: accountPath(scope?.workspaceRoot) }) };
}
