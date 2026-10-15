/** Bootstrap one durable workspace inside each member's isolated DSH home. */
import { guardMemberFileRpc, memberTaskRoots } from './harless_member_file_scope.ts';
import { clientRequestSchema } from '@deepseek-ai/dsh-client-connection';
export const name = 'harless-member-workspace';
export const inject = ['workspaceRegistry', 'workspaceFiles', 'connection', 'typertGateway', 'typert'];

export async function apply(ctx: any) {
  const guard = guardMemberFileRpc(ctx.typertGateway,
    async id => ctx.typert.lookups.get('workspaceFileScope')?.resolve(id),
    ['/user/workspace', ...memberTaskRoots()]);
  // The public lookup resolver is shared by unary HTTP and the WebSocket
  // changes feed. Refuse old/foreign scopes before either carrier opens.
  const resolveScope = ctx.typert.lookups.get('workspaceFileScope').resolve;
  ctx.typert.lookups.configure('workspaceFileScope', async (id: string) => guard.scope(await resolveScope(id)));
  // Exact Fetch routes avoid method replacement on caller-scoped Cordis facades.
  // Workspace creation and directory browsing are handled for every account
  // by registerManagedWorkspaceRoutes; no native server-directory picker.
  for (const endpoint of ['workspaceFiles/list', 'workspaceFiles/stat', 'workspaceFiles/read',
    'workspaceFiles/readAll', 'workspaceFiles/readBytes', 'workspaceFiles/readRelated']) {
    const [namespace, method] = endpoint.split('/');
    ctx.connection.fetch.register({ path: '/api/' + endpoint, methods: ['POST'], requestBody: 'buffered',
      fetch: async (request: Request) => {
        if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') return new Response('', { status: 415 });
        let message: any;
        try { message = clientRequestSchema.parse(await request.json()); }
        catch { return new Response('invalid RPC envelope', { status: 400 }); }
        let result: any;
        try {
          if (message.method !== endpoint || !message.payload || Object.keys(message.payload).join(',') !== 'args') throw Error('invalid RPC endpoint');
          result = { ok: true, value: await guard.invoke({ namespace, method, args: message.payload.args, signal: request.signal }) };
        } catch (error: any) {
          result = { ok: false, error: { code: error.code ?? 'gateway/bad-request',
            message: error.code === 'gateway/forbidden' ? error.message : '工作区请求未通过检查。', details: {} } };
        }
        return Response.json({ type: 'server-response', rpcId: message.rpcId, result }, { headers: { 'Cache-Control': 'no-store' } });
      } });
  }
  await ctx.workspaceRegistry.create('/user/workspace', '我的工作区');
}
