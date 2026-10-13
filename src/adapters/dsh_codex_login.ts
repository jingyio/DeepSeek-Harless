/** Single-operator Codex OAuth control surface for the private Harness Web run. */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { credentialKey } from '@deepseek-ai/dsh-credentials';

export const name = 'sss-codex-login';
export const inject = ['authorization', 'credentials', 'connection', 'webServer'];

const key = credentialKey('llm-pi-ai', 'openai-codex');
type LoginState = { status: 'idle' | 'starting' | 'pending' | 'authorized' | 'cancelled' | 'failed';
  notice?: { message: string; url?: string; code?: string } };

export function apply(ctx: any) {
  let state: LoginState = { status: 'idle' };
  async function status() {
    const record = await ctx.credentials.readRecord(key);
    const flow = ctx.authorization.describe(key);
    return { signed_in: record !== undefined, available: flow !== undefined,
      in_flight: flow?.inFlight ?? false, ...state };
  }
  const api = { methods: ['GET', 'POST'] as const, requestBody: 'buffered' as const,
    fetch: async (request: Request) => {
      if (request.method === 'GET') return Response.json(await status(), { headers: { 'Cache-Control': 'no-store' } });
      if (request.headers.get('content-type')?.split(';')[0] !== 'application/json')
        return Response.json({ error: 'expected_json' }, { status: 415 });
      const body = await request.json().catch(() => null);
      if (!body || typeof body.action !== 'string') return Response.json({ error: 'invalid_action' }, { status: 400 });
      if (body.action === 'login') {
        if (!ctx.authorization.describe(key)) return Response.json({ error: 'codex_flow_unavailable' }, { status: 503 });
        if (ctx.authorization.describe(key).inFlight) return Response.json({ error: 'login_in_progress' }, { status: 409 });
        state = { status: 'starting' };
        void ctx.authorization.begin({ key, method: 'oauth', interaction: {
          notify: (notice: { message: string; url?: string; code?: string }) => {
            state = { status: 'pending', notice: { message: notice.message, url: notice.url, code: notice.code } };
          },
          prompt: async (prompt: { kind: string; options?: { id: string }[] }) => {
            if (prompt.kind === 'select' && prompt.options?.some((option) => option.id === 'device_code'))
              return 'device_code';
            throw new Error('Codex device authorization asked for an unsupported prompt');
          },
        } }).then((outcome: { status: 'authorized' | 'cancelled' }) => {
          state = { status: outcome.status };
        }).catch(() => { state = { status: 'failed' }; });
        return Response.json(await status(), { status: 202, headers: { 'Cache-Control': 'no-store' } });
      }
      if (body.action === 'cancel') {
        ctx.authorization.cancel(key);
        state = { status: 'cancelled' };
        return Response.json(await status(), { headers: { 'Cache-Control': 'no-store' } });
      }
      if (body.action === 'logout') {
        if (ctx.authorization.describe(key)?.inFlight) return Response.json({ error: 'login_in_progress' }, { status: 409 });
        await ctx.credentials.deleteRecord(key);
        state = { status: 'idle' };
        return Response.json(await status(), { headers: { 'Cache-Control': 'no-store' } });
      }
      return Response.json({ error: 'invalid_action' }, { status: 400 });
    } };
  ctx.effect(() => ctx.connection.fetch.register({ ...api, path: '/api/harless/codex-login' }), 'sss-codex-login-api');
  const panel = readFileSync(fileURLToPath(new URL('./codex_login_panel.html', import.meta.url)), 'utf8');
  ctx.effect(() => ctx.webServer.register({ kind: 'exact', path: '/codex-login', handler: (request: any, response: any) => {
    const rejected = ctx.connection.requestRejection(request);
    response.writeHead(rejected ?? 200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(rejected ? '请先打开本次 Harness 认证地址。' : panel);
  } }), 'sss-codex-login-panel');
  ctx.effect(() => ctx.webServer.tapIndex((html: string) => html.replace('</body>',
    '<a href="/codex-login" style="position:fixed;right:18px;bottom:118px;z-index:9999;padding:10px 15px;border-radius:8px;background:#216e67;color:#fff;text-decoration:none">Codex 登录</a></body>')), 'sss-codex-login-link');
}
