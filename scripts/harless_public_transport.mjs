/** Browser-only metadata/error projection. Never rewrite model or file payloads. */
import WebSocket, { WebSocketServer } from 'ws';

export const REMOTE_MUX_PATH = '/api/remote.mux';
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const publicMessages = new Map([
  ['gateway/cancelled', '请求已取消。'],
  ['session/not-found', '该对话暂时不可用，请刷新后重试。'],
  ['session/agent-busy', '当前回复尚未结束，请稍后重试。'],
  ['session/model-unavailable', '所选模型暂时不可用，请稍后重试。'],
  ['model_budget_unavailable', '所选模型的推理模式超出当前任务预算，请选择 Off 后重试。'],
  ['model_not_allowed', '暂时无法切换到所选模型，请等待当前回复结束后重试，并检查模型及推理模式。'],
]);
export function publicTransportError(error) {
  const code = typeof error?.code === 'string' && /^[a-z][a-z0-9_-]*(?:\/[a-z][a-z0-9_-]*)?$/.test(error.code)
    ? error.code : 'gateway/internal';
  return { code, message: publicMessages.get(code) ?? '请求未能完成，请稍后重试。', details: {} };
}

/** Return original bytes for success, including attachment base64 and user text. */
export function publicRpcBytes(bytes) {
  const value = JSON.parse(bytes.toString('utf8'));
  if (!record(value) || value.type !== 'server-response' || !record(value.result) || value.result.ok !== false)
    return bytes;
  return Buffer.from(JSON.stringify({ ...value, result: { ok: false, error: publicTransportError(value.result.error) } }));
}

export function isNativeRpcResponse(req, response) {
  const path = new URL(req.url, 'http://127.0.0.1').pathname;
  return req.method === 'POST' && /^\/api\/[^/]+\/[^/]+$/.test(path) &&
    !path.startsWith('/api/harless/') && !path.startsWith('/api/sss/') &&
    !response.headers['content-disposition'] &&
    response.headers['content-type']?.split(';', 1)[0].trim().toLowerCase() === 'application/json';
}

/** This only buffers unary JSON RPC, never SSE or file downloads. */
export function forwardPublicRpc(response, res, headers) {
  const parts = [];
  response.on('data', chunk => parts.push(chunk));
  response.once('end', () => {
    if (res.destroyed) return;
    let body, status = response.statusCode ?? 502;
    try {
      // The gateway requests identity. Fail closed if an upstream ignores it;
      // compressed diagnostics must never bypass the structured projection.
      const coding = String(response.headers['content-encoding'] ?? 'identity').trim().toLowerCase();
      if (coding !== 'identity') throw Error('Unexpected RPC content encoding');
      body = publicRpcBytes(Buffer.concat(parts));
    }
    catch {
      status = 502;
      body = Buffer.from(JSON.stringify({ error: publicTransportError(undefined) }));
    }
    const next = { ...headers, 'content-length': body.length };
    for (const name of ['transfer-encoding', 'content-encoding', 'etag', 'content-md5', 'digest']) delete next[name];
    res.writeHead(status, next); res.end(body);
  });
}

/** Track only $events stream IDs; unrelated native streams stay byte-identical. */
export function createRemoteProjection() {
  const events = new Set();
  return {
    observe(data, binary) {
      if (binary) return;
      try {
        const value = JSON.parse(data.toString());
        if (value.type === 'open' && typeof value.streamId === 'string') {
          if (value.endpoint === '$events') events.add(value.streamId);
          else events.delete(value.streamId);
        }
      } catch {} // The authoritative mux validates the unchanged client request.
    },
    project(data, binary) {
      if (binary) return data;
      const value = JSON.parse(data.toString());
      let projected;
      if (value.type === 'error') projected = { ...value, error: publicTransportError(value.error) };
      if (events.has(value.streamId) && value.type === 'item' && record(value.value)) {
        const item = value.value;
        if (item.type === 'ready' && record(item.host))
          projected = { ...value, value: { ...item, host: { ...item.host, home: '' } } };
        if (item.type === 'emit' && item.event === 'api-session/error')
          projected = { ...value, value: { ...item, args: [item.args?.[0], '当前请求未能完成，请稍后重试。'] } };
        if (item.type === 'emit' && item.event === 'api-session/added' && record(item.args?.[0])) {
          const summary = { ...item.args[0] }; delete summary.cwd;
          projected = { ...value, value: { ...item, args: [summary, ...item.args.slice(1)] } };
        }
      }
      if (value.type === 'end' || value.type === 'error') events.delete(value.streamId);
      return projected ? Buffer.from(JSON.stringify(projected)) : data;
    },
  };
}

/**
 * Reframe just the native mux using ws's public API; do not parse raw WS frames.
 * Browser auth and Origin checks happen in the caller before this is reached.
 * Ping/pong are forwarded, so the upstream heartbeat still tests the browser.
 */
export function createPublicRemoteBridge() {
  const selected = new WeakMap(), active = new Set();
  const server = new WebSocketServer({ noServer: true, clientTracking: false, perMessageDeflate: false,
    autoPong: false, handleProtocols: (_protocols, req) => selected.get(req) || false });
  let stopped = false;
  return {
    upgrade(req, socket, head, backend, headers) {
      if (stopped || socket.destroyed) { socket.destroy(); return; }
      const forwarded = { ...headers };
      for (const name of Object.keys(forwarded)) if (/^sec-websocket-/i.test(name) || /^(connection|upgrade)$/i.test(name)) delete forwarded[name];
      const protocols = typeof req.headers['sec-websocket-protocol'] === 'string'
        ? req.headers['sec-websocket-protocol'].split(',').map(value => value.trim()) : [];
      let downstream, upstream;
      const projection = createRemoteProjection();
      const pair = { close: () => { upstream?.terminate(); downstream?.terminate(); socket.destroy(); } };
      const fail = () => {
        if (!downstream && !socket.destroyed) socket.end('HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\nContent-Length: 0\r\n\r\n');
        upstream?.terminate(); downstream?.terminate(); active.delete(pair);
      };
      active.add(pair);
      socket.once('close', () => { upstream?.terminate(); active.delete(pair); });
      // HTTP upgrade sockets can remain half-open before ws takes ownership.
      socket.once('end', () => { if (!downstream) pair.close(); });
      socket.once('error', () => pair.close());
      try {
        upstream = new WebSocket(`ws://127.0.0.1:${backend.port}${req.url}`, protocols, {
          headers: forwarded, autoPong: false, perMessageDeflate: false, handshakeTimeout: 12000,
          followRedirects: false,
        });
      } catch { fail(); return; }
      upstream.once('error', fail);
      upstream.once('unexpected-response', (_request, response) => { response.resume(); fail(); });
      upstream.once('open', () => {
        if (stopped || socket.destroyed) { pair.close(); return; }
        upstream.pause(); selected.set(req, upstream.protocol);
        try {
          server.handleUpgrade(req, socket, head, client => {
            downstream = client;
            const connect = (source, target, project) => {
              let pending = 0;
              source.on('message', (data, binary) => {
                if (target.readyState !== WebSocket.OPEN) return;
                try {
                  const value = project(data, binary);
                  pending++; source.pause();
                  target.send(value, { binary }, error => {
                    if (error) { fail(); return; }
                    if (--pending === 0 && source.readyState === WebSocket.OPEN) source.resume();
                  });
                } catch { fail(); }
              });
              source.on('ping', data => { if (target.readyState === WebSocket.OPEN) target.ping(data); });
              source.on('pong', data => { if (target.readyState === WebSocket.OPEN) target.pong(data); });
              source.once('close', code => {
                if (target.readyState === WebSocket.OPEN) target.close(code === 1005 || code === 1006 ? 1001 : code);
                active.delete(pair);
              });
              source.once('error', fail);
            };
            connect(client, upstream, (data, binary) => { projection.observe(data, binary); return data; });
            connect(upstream, client, (data, binary) => projection.project(data, binary));
            upstream.resume();
          });
        } catch { fail(); }
      });
    },
    close() {
      if (stopped) return;
      stopped = true;
      for (const pair of active) pair.close();
      active.clear(); server.close();
    },
  };
}
