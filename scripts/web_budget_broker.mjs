/** Loopback-only bridge from one persistent DSH chat to separately budgeted turns. */
import { createServer, request as httpRequest } from 'node:http';
import { timingSafeEqual } from 'node:crypto';
import { readFileSync } from 'node:fs';

export function startBroker({ port, target, controlToken }) {
  const destination = new URL(target);
  if (destination.protocol !== 'http:' || destination.hostname !== '127.0.0.1' ||
      destination.pathname !== '/v1' || !Number.isInteger(port) || port < 0 || port > 65535 ||
      typeof controlToken !== 'string' || controlToken.length < 32) throw Error('Invalid budget broker configuration');
  const routes = new Map();
  const sameToken = supplied => {
    if (typeof supplied !== 'string') return false;
    const a = Buffer.from(supplied), b = Buffer.from(controlToken);
    return a.length === b.length && timingSafeEqual(a, b);
  };
  const reply = (res, status, value) => {
    const body = JSON.stringify(value);
    res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(body);
  };
  const server = createServer(async (req, res) => {
    if (req.url === '/bind' || req.url === '/unbind') {
      if (req.method !== 'POST' || !sameToken(req.headers['x-sss-control-token'])) {
        reply(res, 401, { error: 'Budget broker control authentication required' }); return;
      }
      let raw = '';
      try {
        for await (const chunk of req) {
          raw += chunk;
          if (raw.length > 4096) throw Error('Body too large');
        }
        const payload = JSON.parse(raw);
        if (Object.keys(payload).sort().join(',') !== 'budget_session_id,session_id' ||
            typeof payload.session_id !== 'string' || !/^session-[a-f0-9-]{36}$/.test(payload.session_id) ||
            typeof payload.budget_session_id !== 'string' || !/^turn-[a-f0-9]{32}$/.test(payload.budget_session_id))
          throw Error('Invalid budget route');
        const current = routes.get(payload.session_id);
        if (req.url === '/bind') {
          if (current && current !== payload.budget_session_id) { reply(res, 409, { error: 'Another turn is active' }); return; }
          routes.set(payload.session_id, payload.budget_session_id);
        } else {
          if (current && current !== payload.budget_session_id) { reply(res, 409, { error: 'Another turn is active' }); return; }
          routes.delete(payload.session_id);
        }
        reply(res, 200, { accepted: true });
      } catch { reply(res, 400, { error: 'Invalid budget broker control request' }); }
      return;
    }
    if (req.method !== 'POST' || req.url !== '/v1/chat/completions') {
      reply(res, 404, { error: 'Unknown model route' }); return;
    }
    const dshSession = req.headers['x-deepseek-harness-session-id'];
    const budgetSession = typeof dshSession === 'string' ? routes.get(dshSession) : undefined;
    if (!budgetSession) { reply(res, 403, { error: 'No confirmed turn budget' }); return; }
    const headers = { ...req.headers, host: destination.host,
      'x-deepseek-harness-session-id': budgetSession };
    delete headers['x-sss-control-token'];
    const upstream = httpRequest(destination.origin + req.url, { method: 'POST', headers }, incoming => {
      const responseHeaders = { ...incoming.headers };
      for (const name of ['connection', 'keep-alive', 'transfer-encoding', 'upgrade', 'proxy-authenticate',
        'proxy-authorization', 'te', 'trailer']) delete responseHeaders[name];
      res.writeHead(incoming.statusCode ?? 502, responseHeaders);
      incoming.pipe(res);
    });
    upstream.on('error', () => { if (!res.headersSent) reply(res, 502, { error: 'Budget service unavailable' }); else res.destroy(); });
    req.on('aborted', () => upstream.destroy());
    req.pipe(upstream);
  });
  server.listen(port, '127.0.0.1');
  return server;
}

if (process.argv[1] && import.meta.url === new URL('file://' + process.argv[1]).href) {
  const policy = JSON.parse(readFileSync(process.argv[2], 'utf8'));
  const port = Number(process.argv[3]);
  startBroker({ port, target: policy.endpoint, controlToken: policy.control_token });
  process.stdout.write(`Budget broker ready on 127.0.0.1:${port}\n`);
}
