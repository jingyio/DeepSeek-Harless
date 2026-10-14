import http from 'node:http';
import net from 'node:net';
import { spawn } from 'node:child_process';
import { randomBytes, createHash, createHmac, timingSafeEqual, scrypt as scryptCallback, scryptSync } from 'node:crypto';
import { promisify } from 'node:util';
import { readFileSync, writeFileSync, renameSync, mkdirSync, existsSync, chmodSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';

const scrypt = promisify(scryptCallback);
const dummyHash = 'scrypt-v1$anonymous-login$' + scryptSync('dummy-password', 'anonymous-login', 64,
  { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 }).toString('hex');
const sha = value => createHash('sha256').update(value).digest('hex');
const random = (size = 32) => randomBytes(size).toString('base64url');
const json = (res, status, value, headers = {}) => send(res, status, JSON.stringify(value), {
  'content-type': 'application/json; charset=utf-8', ...headers,
});
function send(res, status, body, headers = {}) {
  res.writeHead(status, { 'cache-control': 'no-store', 'x-content-type-options': 'nosniff',
    'referrer-policy': 'no-referrer', ...headers });
  res.end(body);
}
function store(path, value) {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  const tmp = path + '.' + random(8) + '.tmp';
  writeFileSync(tmp, JSON.stringify(value, null, 2) + '\n', { mode: 0o600 });
  renameSync(tmp, path); chmodSync(path, 0o600);
}
function read(path, fallback) {
  try { return JSON.parse(readFileSync(path, 'utf8')); }
  catch (error) { if (error.code === 'ENOENT') return fallback; throw error; }
}
const usernamePattern = /^[a-z][a-z0-9_-]{2,31}$/;
const displayNameValid = value => typeof value === 'string' && value.trim().length >= 1 &&
  value.trim().length <= 40 && !/[\x00-\x1f\x7f]/.test(value);
const passwordValid = value => typeof value === 'string' && value.length >= 10 &&
  Buffer.byteLength(value) <= 256;
const publicUser = user => ({ id: user.id, username: user.username,
  displayName: user.displayName, createdAt: user.createdAt, role: user.role });
async function hashPassword(password) {
  const salt = random(24);
  const key = await scrypt(password, salt, 64, { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
  return `scrypt-v1$${salt}$${key.toString('hex')}`;
}
async function verifyPassword(password, stored) {
  if (typeof stored !== 'string' || !stored.startsWith('scrypt-v1$')) return false;
  const [, salt, expected] = stored.split('$');
  if (!/^[a-f0-9]{128}$/.test(expected ?? '')) return false;
  const key = await scrypt(password, salt, 64, { N: 32768, r: 8, p: 1, maxmem: 64 * 1024 * 1024 });
  return timingSafeEqual(key, Buffer.from(expected, 'hex'));
}
function bodyJson(req, limit = 4096) {
  return new Promise((resolve, reject) => {
    let size = 0, parts = [];
    req.on('data', part => { size += part.length; if (size > limit) { reject(Error('请求内容过大')); req.destroy(); } else parts.push(part); });
    req.on('end', () => { try { resolve(JSON.parse(Buffer.concat(parts).toString('utf8'))); }
      catch { reject(Error('请求格式无效')); } });
    req.on('error', reject);
  });
}
function requestOnce(port, path, headers = {}, timeout = 12000) {
  return new Promise((resolve, reject) => {
    const req = http.request({ host: '127.0.0.1', port, path, method: 'GET', headers, timeout }, res => {
      res.resume(); res.on('end', () => resolve({ status: res.statusCode, headers: res.headers }));
    });
    req.on('error', reject); req.on('timeout', () => req.destroy(Error('backend timeout'))); req.end();
  });
}
function cookieOf(headers) {
  const row = headers['set-cookie'];
  const cookie = Array.isArray(row) ? row.find(value => value.startsWith('dsh-auth-')) : row;
  if (!cookie?.startsWith('dsh-auth-')) throw Error('DSH did not issue its internal cookie');
  return cookie.split(';', 1)[0];
}
function tokenFromFile(path) {
  const value = new URL(readFileSync(path, 'utf8').trim()).searchParams.get('token');
  if (!value || !/^[A-Za-z0-9_-]{40,100}$/.test(value)) throw Error('Invalid owner DSH launch token');
  return value;
}
function safePath(url) {
  if (typeof url !== 'string' || !url.startsWith('/') || url.startsWith('//') || /[\x00-\x1f\\]/.test(url)) return false;
  try { return !new URL(url, 'http://local').searchParams.has('token'); } catch { return false; }
}
function errorCode(error) { return typeof error?.code === 'string' ? error.code : 'error'; }

export function createGateway(config) {
  const dataDir = config.dataDir;
  const dbPath = join(dataDir, 'accounts.json');
  mkdirSync(dataDir, { recursive: true, mode: 0o700 });
  chmodSync(dataDir, 0o700);
  const db = read(dbPath, { version: 1, users: [], invites: [], sessions: [], ownerClaim: null });
  if (db.version !== 1 || !Array.isArray(db.users) || !Array.isArray(db.invites) || !Array.isArray(db.sessions)) throw Error('Invalid account database');
  const save = () => store(dbPath, db);
  const backends = new Map(), pending = new Map(), failures = new Map(), startupErrors = new Map();
  const memberChildren = new Set(), sockets = new Set();
  let closing = false;
  const origin = new URL(config.publicOrigin).origin;
  // Reject a stale host patch before anybody can register into a backend that
  // cannot start. The patch must be generated from the same source checkout.
  const memberPatchTemplate = config.memberPatch ? (() => {
    const sourceUri = pathToFileURL(config.sourceDir).href.replace(/\/?$/, '/');
    const patch = config.memberPatch.filter(row => !row.insert ||
      !row.insert.some(item => String(item.name ?? '').includes('dsh_paper_revision_web')))
      .map(row => structuredClone(row));
    for (const row of patch) if (row.insert) row.insert = row.insert.map(item => {
      const name = String(item.name);
      if (name.startsWith('file:') && !name.startsWith(sourceUri)) throw Error('Plugin is outside source directory');
      return { ...item, name: name.startsWith(sourceUri) ? 'file:///app/src/' + name.slice(sourceUri.length) : name };
    });
    return patch;
  })() : null;
  const taskPrefix = user => sha(user.id).slice(0, 8);
  const delegate = (user, purpose) => createHmac('sha256', config.adminToken ?? 'test-only')
    .update(purpose + ':' + user.id).digest('base64url');
  const routeOwner = new Map();
  const scopedPort = config.scopedBudgetPort;
  const readBounded = (req, max = 8192) => new Promise((resolve, reject) => {
    let size = 0, parts = [];
    req.on('data', part => { size += part.length; if (size > max) { reject(Error('body too large')); req.destroy(); } else parts.push(part); });
    req.on('end', () => resolve(Buffer.concat(parts))); req.on('error', reject);
  });
  const findDelegated = (secret, purpose) => {
    if (typeof secret !== 'string') return null;
    const actual = Buffer.from(secret);
    return db.users.find(user => { const expected = Buffer.from(delegate(user, purpose));
      return actual.length === expected.length && timingSafeEqual(actual, expected);
    }) ?? null;
  };
  const scopedForward = (targetPort, path, method, headers, body, res, after) => {
    const upstream = http.request({ host: '127.0.0.1', port: targetPort, path, method,
      headers: { ...headers, host: `127.0.0.1:${targetPort}`, 'content-length': body?.length ?? 0 }, timeout: 120000 }, response => {
      if (after) after(response.statusCode);
      const outgoing = { ...response.headers }; delete outgoing['set-cookie'];
      res.writeHead(response.statusCode ?? 502, outgoing); response.pipe(res);
    });
    upstream.on('error', () => { if (!res.headersSent) send(res, 502, 'budget service unavailable'); else res.destroy(); });
    upstream.end(body);
  };
  const scopedBudget = scopedPort ? http.createServer(async (req, res) => {
    try {
      const path = new URL(req.url ?? '/', 'http://local');
      if (req.method === 'POST' && path.pathname === '/v1/chat/completions') {
        const auth = req.headers.authorization;
        const user = typeof auth === 'string' && auth.startsWith('Bearer ') ? findDelegated(auth.slice(7), 'model') : null;
        const session = req.headers['x-deepseek-harness-session-id'];
        if (!user || routeOwner.get(session) !== user.id) return json(res, 403, { error: 'No approved user turn' });
        const body = await readBounded(req, 2 * 1024 * 1024);
        return scopedForward(config.upstreamBrokerPort, '/v1/chat/completions', 'POST',
          { ...req.headers, authorization: `Bearer ${config.apiKey}` }, body, res);
      }
      const user = findDelegated(req.headers['x-sss-control-token'], 'control');
      if (!user) return json(res, 403, { error: 'Invalid user budget token' });
      const prefix = taskPrefix(user);
      const ownedBudget = value => typeof value === 'string' &&
        new RegExp(`^turn-${prefix}[a-f0-9]{24}$`).test(value);
      if (req.method === 'GET' && path.pathname === '/tasks/stats') {
        const session = path.searchParams.get('session_id');
        if (!ownedBudget(session)) return json(res, 403, { error: 'Budget belongs to another account' });
        return scopedForward(config.upstreamControlPort, req.url, 'GET',
          { 'x-sss-control-token': config.memberPolicy.control_token }, null, res);
      }
      if (req.method !== 'POST') return json(res, 404, { error: 'Unknown budget route' });
      const body = await readBounded(req);
      const value = JSON.parse(body.toString('utf8'));
      if (path.pathname === '/tasks/register') {
        if (!ownedBudget(value.session_id) || value.task_id !== value.session_id.slice(5) ||
            typeof value.budget_usd !== 'number' || value.budget_usd > config.memberPolicy.budget_usd)
          return json(res, 403, { error: 'Invalid account task registration' });
      } else if (path.pathname === '/tasks/activate' || path.pathname === '/tasks/cancel') {
        if (!ownedBudget(value.session_id)) return json(res, 403, { error: 'Budget belongs to another account' });
      } else if (path.pathname === '/bind' || path.pathname === '/unbind') {
        if (!ownedBudget(value.budget_session_id) || !/^session-[a-f0-9-]{36}$/.test(value.session_id) ||
            (path.pathname === '/unbind' && routeOwner.get(value.session_id) !== user.id) ||
            (path.pathname === '/bind' && routeOwner.has(value.session_id) && routeOwner.get(value.session_id) !== user.id))
          return json(res, 403, { error: 'Session belongs to another account' });
        return scopedForward(config.upstreamBrokerPort, path.pathname, 'POST',
          { 'content-type': 'application/json', 'x-sss-control-token': config.memberPolicy.control_token }, body, res,
          status => { if (status === 200) {
            if (path.pathname === '/bind') routeOwner.set(value.session_id, user.id);
            else routeOwner.delete(value.session_id);
          } });
      } else return json(res, 404, { error: 'Unknown budget route' });
      return scopedForward(config.upstreamControlPort, path.pathname, 'POST',
        { 'content-type': 'application/json', 'x-sss-control-token': config.memberPolicy.control_token }, body, res);
    } catch (error) { if (!res.headersSent) json(res, 400, { error: 'Invalid scoped budget request' }); else res.destroy(); }
  }) : null;
  const cookieName = 'harless_sess';
  const secure = new URL(origin).protocol === 'https:' ? 'Secure; ' : '';
  const cookie = (value, age) => `${cookieName}=${value}; Path=/; HttpOnly; ${secure}SameSite=Lax${age === undefined ? '' : `; Max-Age=${age}`}`;
  const sessionFor = req => {
    const raw = (req.headers.cookie ?? '').split(';').map(s => s.trim()).find(s => s.startsWith(cookieName + '='));
    const value = raw?.slice(cookieName.length + 1);
    if (!value || !/^[A-Za-z0-9_-]{30,100}$/.test(value)) return null;
    const row = db.sessions.find(s => s.hash === sha(value) && s.expiresAt > Date.now());
    return row ? db.users.find(u => u.id === row.userId) ?? null : null;
  };
  const requireOrigin = req => {
    const requestOrigin = req.headers.origin;
    return requestOrigin === origin && req.headers['sec-fetch-site'] !== 'cross-site';
  };
  const issueSession = (res, user) => {
    const value = random();
    db.sessions = db.sessions.filter(s => s.expiresAt > Date.now());
    db.sessions.push({ hash: sha(value), userId: user.id, expiresAt: Date.now() + 7 * 86400000 });
    save();
    json(res, 200, { user: publicUser(user) }, { 'set-cookie': cookie(value) });
  };
  const limit = (key, max, windowMs) => {
    const now = Date.now(); const row = failures.get(key) ?? { count: 0, until: now + windowMs };
    if (row.until < now) { row.count = 0; row.until = now + windowMs; }
    row.count++; failures.set(key, row); return row.count <= max;
  };
  const throttle = (req, name, max = 8, windowMs = 15 * 60000) => {
    const forwarded = req.headers['cf-connecting-ip'];
    const client = typeof forwarded === 'string' && /^[0-9a-fA-F:.]{3,45}$/.test(forwarded) ? forwarded : req.socket.remoteAddress;
    return limit(`${client}:${name}`, max, windowMs);
  };
  const register = async (req, res, claim = false) => {
    if (!throttle(req, 'register', 12, 3600000)) return json(res, 429, { error: '请稍后再试' });
    const body = await bodyJson(req);
    const username = String(body.username ?? '').toLowerCase();
    const name = body.displayName;
    if (!usernamePattern.test(username) || !displayNameValid(name) || !passwordValid(body.password))
      return json(res, 400, { error: '用户名需为 3–32 位英文或数字；名称不超过 40 字；密码至少 10 位' });
    if (db.users.some(u => u.username === username)) return json(res, 409, { error: '用户名已被使用' });
    const proof = String(claim ? body.claimCode : body.inviteCode ?? '').trim();
    const proofHash = sha(proof);
    const invite = db.invites.find(i => i.hash === proofHash && !i.usedBy);
    if (claim ? (!db.ownerClaim || db.ownerClaim !== proofHash || db.users.some(u => u.role === 'owner')) : !invite)
      return json(res, 400, { error: claim ? '所有者激活链接无效或已使用' : '邀请码无效或已使用' });
    const passwordHash = await hashPassword(body.password);
    if (db.users.some(u => u.username === username) || (claim ? db.ownerClaim !== proofHash : invite.usedBy))
      return json(res, 409, { error: '注册状态已变化，请重试' });
    const user = { id: claim ? 'owner' : random(16), username,
      displayName: name.trim(), passwordHash, role: claim ? 'owner' : 'member', createdAt: new Date().toISOString() };
    db.users.push(user);
    if (claim) db.ownerClaim = null; else invite.usedBy = user.id;
    issueSession(res, user);
  };
  const accountApi = async (req, res, path, user) => {
    if (req.method === 'GET' && path === '/api/account/me')
      return json(res, 200, { user: user ? publicUser(user) : null, registration: 'invite' });
    if (req.method !== 'POST' || !requireOrigin(req)) return json(res, 403, { error: '请求来源无效' });
    if (path === '/api/account/register') return register(req, res);
    if (path === '/api/account/claim') return register(req, res, true);
    if (path === '/api/account/login') {
      const body = await bodyJson(req);
      const username = String(body.username ?? '').toLowerCase();
      if (!throttle(req, 'login:' + username, 8)) return json(res, 429, { error: '尝试次数过多，请 15 分钟后再试' });
      const found = db.users.find(u => u.username === username);
      const verified = await verifyPassword(String(body.password ?? ''), found?.passwordHash ?? dummyHash);
      if (!found || !verified) return json(res, 401, { error: '用户名或密码不正确' });
      return issueSession(res, found);
    }
    if (!user) return json(res, 401, { error: '请先登录' });
    if (path === '/api/account/invites') {
      if (user.role !== 'owner') return json(res, 403, { error: '仅所有者可创建邀请码' });
      if (!throttle(req, 'invites', 12, 3600000)) return json(res, 429, { error: '请稍后再试' });
      const body = await bodyJson(req);
      if (!await verifyPassword(String(body.currentPassword ?? ''), user.passwordHash))
        return json(res, 403, { error: '当前密码不正确' });
      if (!Number.isInteger(body.count) || body.count < 1 || body.count > 20)
        return json(res, 400, { error: '每次可创建 1–20 个邀请码' });
      return json(res, 200, { codes: createInvites({ db, save }, body.count) });
    }
    if (path === '/api/account/logout') {
      const raw = (req.headers.cookie ?? '').split(';').map(s => s.trim()).find(s => s.startsWith(cookieName + '='));
      db.sessions = db.sessions.filter(s => s.hash !== sha(raw?.slice(cookieName.length + 1) ?? ''));
      save(); return json(res, 200, { ok: true }, { 'set-cookie': cookie('', 0) });
    }
    if (path === '/api/account/profile') {
      const body = await bodyJson(req);
      if (!displayNameValid(body.displayName)) return json(res, 400, { error: '名称需为 1–40 字' });
      if (body.username !== undefined) {
        const next = String(body.username).toLowerCase();
        if (!usernamePattern.test(next)) return json(res, 400, { error: '用户名需为 3–32 位英文、数字、下划线或连字符' });
        if (db.users.some(u => u.id !== user.id && u.username === next)) return json(res, 409, { error: '用户名已被使用' });
        user.username = next;
      }
      user.displayName = body.displayName.trim(); save();
      return json(res, 200, { user: publicUser(user) });
    }
    if (path === '/api/account/password') {
      if (!throttle(req, 'password', 8)) return json(res, 429, { error: '尝试次数过多，请稍后再试' });
      const body = await bodyJson(req);
      if (!passwordValid(body.newPassword)) return json(res, 400, { error: '新密码至少 10 位' });
      if (!await verifyPassword(String(body.currentPassword ?? ''), user.passwordHash))
        return json(res, 403, { error: '当前密码不正确' });
      user.passwordHash = await hashPassword(body.newPassword);
      db.sessions = db.sessions.filter(s => s.userId !== user.id);
      save(); return json(res, 200, { ok: true, reauth: true }, { 'set-cookie': cookie('', 0) });
    }
    return json(res, 404, { error: '接口不存在' });
  };
  const ownerBackend = async () => {
    const token = tokenFromFile(config.ownerTokenFile);
    const cached = backends.get('owner');
    if (cached?.token === token) return cached;
    const port = config.ownerPort;
    const response = await requestOnce(port, '/?token=' + encodeURIComponent(token));
    if (response.status !== 303) throw Error('Owner backend authentication failed');
    const backend = { port, cookie: cookieOf(response.headers), owner: true, token };
    backends.set('owner', backend); return backend;
  };
  const allocatePort = () => new Promise((resolve, reject) => {
    const server = net.createServer(); server.once('error', reject);
    server.listen(0, '127.0.0.1', () => { const port = server.address().port; server.close(() => resolve(port)); });
  });
  const memberBackend = async user => {
    if (closing) throw Error('网关正在重启，请稍后重试');
    if (backends.has(user.id)) return backends.get(user.id);
    if (pending.has(user.id)) return pending.get(user.id);
    if (pending.size >= 8) throw Error('当前启动人数较多，请稍后重试');
    const promise = (async () => {
      const port = await allocatePort();
      const userDir = join(config.membersDir, user.id);
      for (const sub of ['', 'dsh', 'workspace', 'tasks/tasks', 'config']) mkdirSync(join(userDir, sub), { recursive: true, mode: 0o700 });
      const policy = { ...config.memberPolicy, output: '/user/tasks',
        allowed_tools: [], resources: {}, ownership_legacy_outputs: [], budget_task_prefix: taskPrefix(user),
        endpoint: `http://127.0.0.1:${scopedPort}/v1`,
        control_endpoint: `http://127.0.0.1:${scopedPort}`,
        budget_broker_endpoint: `http://127.0.0.1:${scopedPort}`,
        control_token: delegate(user, 'control') };
      store(join(userDir, 'config', 'policy.json'), policy);
      if (!memberPatchTemplate) throw Error('Member host patch unavailable');
      const patch = structuredClone(memberPatchTemplate);
      patch.push({ insert: [{ name: 'file:///app/src/adapters/dsh_member_workspace.ts' }] });
      const preset = patch.find(row => row.id === 'agent-presets');
      if (!preset) throw Error('Agent preset patch unavailable');
      preset.config = { ...preset.config, roots: [{ path: '/user/config/presets', trust: 'system' }] };
      store(join(userDir, 'config', 'host.patch.yml'), patch);
      mkdirSync(join(userDir, 'config', 'presets', 'sss-task'), { recursive: true, mode: 0o700 });
      store(join(userDir, 'config', 'presets', 'sss-task', 'preset.yml'), { name: 'DeepSeek Harless · 我的工作区' });
      store(join(userDir, 'config', 'presets', 'sss-task', 'agent.cordis.yml'), [{ id: 'sss-persona',
        name: '@deepseek-ai/dsh-persona', config: { prefix: 'Complete the bounded task within this user workspace.',
          suffix: 'Do not claim access to another account or private materials.' } }]);
      const bin = '/opt/node/bin/node';
      const args = ['--unshare-user', '--unshare-pid', '--uid', '1000', '--gid', '1000', '--die-with-parent',
        '--ro-bind', '/usr', '/usr', '--ro-bind', '/bin', '/bin', '--ro-bind', '/lib', '/lib',
        '--ro-bind', '/lib64', '/lib64', '--ro-bind', '/etc', '/etc', '--dev', '/dev', '--proc', '/proc',
        '--tmpfs', '/tmp', '--dir', '/opt', '--ro-bind', config.nodeRoot, '/opt/node',
        '--dir', '/app', '--ro-bind', config.nodeModules, '/app/node_modules',
        '--ro-bind', config.sourceDir, '/app/src', '--bind', userDir, '/user',
        '--chdir', '/user/workspace', bin, '/app/node_modules/@deepseek-ai/dsh/lib/bin.js',
        '--profile', 'web', '--patch', '/user/config/host.patch.yml', '--host', '127.0.0.1',
        '--port', String(port), '--no-open', '--trusted-host', new URL(config.publicOrigin).host];
      const env = { PATH: '/opt/node/bin:/usr/bin:/bin', HOME: '/user/workspace', DSH_HOME: '/user/dsh',
        SSS_WEB_POLICY: '/user/config/policy.json', DEEPSEEK_API_KEY: delegate(user, 'model'),
        HARLESS_GATEWAY_ENABLED: '1',
        // Member profile trees are small. Polling avoids exhausting a shared
        // server's per-UID inotify quota when several backends start together.
        CHOKIDAR_USEPOLLING: '1', CHOKIDAR_INTERVAL: '1000',
        NO_PROXY: 'localhost,127.0.0.1,::1', no_proxy: 'localhost,127.0.0.1,::1',
        LANG: 'C.UTF-8', PYTHONUTF8: '1' };
      const child = spawn('/usr/bin/bwrap', args, { env, stdio: ['ignore', 'pipe', 'pipe'] });
      memberChildren.add(child);
      child.once('exit', () => memberChildren.delete(child));
      child.once('error', () => memberChildren.delete(child));
      let output = '';
      const login = await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(Error('User backend startup timed out')), 30000);
        const done = (error, value) => { clearTimeout(timeout); error ? reject(error) : resolve(value); };
        const collect = chunk => { output += chunk.toString();
          if (output.length > 16000) output = output.slice(-16000);
          const match = output.match(new RegExp(`http://127\\.0\\.0\\.1:${port}/\\?token=([A-Za-z0-9_-]+)`));
          if (match) done(null, match[1]);
        };
        child.stdout.on('data', collect); child.stderr.on('data', collect);
        child.once('error', done); child.once('exit', code => done(Error(`User backend exited (${code}); ${output.replace(/token=[^\s]+/g, 'token=[redacted]').slice(-400)}`)));
      }).catch(error => { child.kill(); throw error; });
      const response = await requestOnce(port, '/?token=' + encodeURIComponent(login));
      if (response.status !== 303) { child.kill(); throw Error('User backend authentication failed'); }
      const backend = { port, cookie: cookieOf(response.headers), child, owner: false };
      child.once('exit', (code, signal) => {
        if (backends.get(user.id) === backend) backends.delete(user.id);
        console.warn('Member backend stopped:', user.id, code, signal);
      });
      backends.set(user.id, backend); return backend;
    })().finally(() => pending.delete(user.id));
    pending.set(user.id, promise); return promise;
  };
  const backendFor = user => user.role === 'owner' ? ownerBackend() : memberBackend(user);
  const memberReady = (res, user) => {
    if (!user) return json(res, 401, { error: '请先登录' });
    if (user.role === 'owner' || backends.has(user.id)) return json(res, 200, { ready: true });
    const failed = startupErrors.get(user.id);
    if (failed && Date.now() - failed.at < 5000)
      return json(res, 503, { error: '工作区启动失败，正在重试', detail: failed.code }, { 'retry-after': '5' });
    startupErrors.delete(user.id);
    if (!pending.has(user.id)) void memberBackend(user).catch(error => {
      startupErrors.set(user.id, { at: Date.now(), code: errorCode(error) });
      console.error('Member backend startup failed:', user.id, String(error?.stack ?? error).replace(/token=[A-Za-z0-9_-]+/g, 'token=[redacted]'));
    });
    return json(res, 202, { ready: false }, { 'retry-after': '2' });
  };
  const proxyHeaders = (req, backend) => {
    const headers = { ...req.headers, host: `127.0.0.1:${backend.port}`, cookie: backend.cookie,
      'accept-encoding': 'identity' };
    delete headers['cf-connecting-ip']; delete headers['x-forwarded-for']; delete headers['x-forwarded-host'];
    delete headers['proxy-authorization']; delete headers['x-real-ip']; delete headers['content-length'];
    if (req.headers['content-length']) headers['content-length'] = req.headers['content-length'];
    if (headers.origin) headers.origin = `http://127.0.0.1:${backend.port}`;
    if (headers.referer) headers.referer = `http://127.0.0.1:${backend.port}/`;
    return headers;
  };
  const proxy = async (req, res, user) => {
    const backend = await backendFor(user);
    const upstream = http.request({ host: '127.0.0.1', port: backend.port, path: req.url,
      method: req.method, headers: proxyHeaders(req, backend), timeout: 120000 }, response => {
      const headers = { ...response.headers, 'cache-control': response.headers['cache-control'] ?? 'no-store' };
      delete headers['set-cookie']; delete headers['content-security-policy-report-only'];
      res.writeHead(response.statusCode ?? 502, headers); response.pipe(res);
    });
    upstream.on('error', () => { if (!res.headersSent) send(res, 502, '工作区暂时不可用，请刷新重试。'); else res.destroy(); });
    req.pipe(upstream);
  };
  const server = http.createServer(async (req, res) => {
    try {
      if (!safePath(req.url)) return send(res, 400, '无效地址');
      const url = new URL(req.url, origin), path = url.pathname;
      const user = sessionFor(req);
      if (path === '/api/internal/admin' && config.adminToken && req.method === 'POST') {
        const supplied = req.headers['x-harless-admin'];
        const expected = Buffer.from(config.adminToken);
        const actual = Buffer.from(typeof supplied === 'string' ? supplied : '');
        if (!['127.0.0.1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress) ||
            actual.length !== expected.length || !timingSafeEqual(actual, expected))
          return json(res, 403, { error: 'forbidden' });
        const input = await bodyJson(req);
        if (input.action === 'invite') return json(res, 200, { codes: createInvites({ db, save }, input.count ?? 1) });
        if (input.action === 'claim') return json(res, 200, { code: createOwnerClaim({ db, save }) });
        return json(res, 400, { error: 'invalid action' });
      }
      if (path.startsWith('/api/account/')) return accountApi(req, res, path, user);
      if (path === '/api/workspace/ready' && req.method === 'GET') return memberReady(res, user);
      if (path === '/account' || path === '/login' || path === '/register' || path === '/claim' || path === '/starting') {
        const html = readFileSync(config.accountHtml, 'utf8');
        return send(res, 200, html, { 'content-type': 'text/html; charset=utf-8',
          'content-security-policy': "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'self'; base-uri 'none'; form-action 'self'" });
      }
      if (!user) return send(res, 303, '', { location: '/login' });
      if (user.role === 'member' && !backends.has(user.id)) {
        if (req.method === 'GET' && (path === '/' || req.headers['sec-fetch-dest'] === 'document'))
          return send(res, 303, '', { location: '/starting?next=' + encodeURIComponent(req.url) });
        return json(res, 503, { error: '工作区正在启动，请稍后重试' }, { 'retry-after': '2' });
      }
      await proxy(req, res, user);
    } catch (error) {
      console.error('Gateway request failed:', String(error?.stack ?? error).replace(/token=[A-Za-z0-9_-]+/g, 'token=[redacted]'));
      if (!res.headersSent) json(res, 500, { error: '服务暂时不可用', detail: errorCode(error) });
      else res.destroy();
    }
  });
  server.on('upgrade', async (req, socket, head) => {
    try {
      if (!safePath(req.url)) { socket.destroy(); return; }
      const user = sessionFor(req);
      if (!user) { socket.end('HTTP/1.1 401 Unauthorized\r\nConnection: close\r\n\r\n'); return; }
      const backend = await backendFor(user);
      if (closing || socket.destroyed) { socket.destroy(); return; }
      const upstream = net.connect(backend.port, '127.0.0.1');
      upstream.once('connect', () => {
        const headers = proxyHeaders(req, backend);
        let request = `${req.method} ${req.url} HTTP/1.1\r\n`;
        for (const [key, value] of Object.entries(headers)) request += `${key}: ${value}\r\n`;
        upstream.write(request + '\r\n'); if (head.length) upstream.write(head);
        socket.pipe(upstream).pipe(socket);
      });
      upstream.on('error', () => socket.destroy()); socket.on('error', () => upstream.destroy());
      upstream.once('close', () => socket.destroy()); socket.once('close', () => upstream.destroy());
    } catch { socket.destroy(); }
  });
  server.on('connection', socket => {
    sockets.add(socket); socket.once('close', () => sockets.delete(socket));
  });
  return { server, scopedBudget, db, save, backends, close: () => {
    if (closing) return;
    closing = true;
    // Include booting children, and upgraded/idle browser connections that
    // server.close() otherwise keeps alive during an ordinary SIGTERM restart.
    for (const child of memberChildren) child.kill();
    for (const socket of sockets) socket.destroy();
    server.close(); scopedBudget?.close();
  } };
}

export function createOwnerClaim(gateway) {
  if (gateway.db.users.some(user => user.role === 'owner')) throw Error('Owner already registered');
  const code = random(24); gateway.db.ownerClaim = sha(code); gateway.save(); return code;
}
export function createInvites(gateway, count = 1) {
  if (!Number.isInteger(count) || count < 1 || count > 20) throw Error('Invalid invite count');
  const codes = Array.from({ length: count }, () => random(18));
  for (const code of codes) gateway.db.invites.push({ hash: sha(code), createdAt: new Date().toISOString(), usedBy: null });
  gateway.save(); return codes;
}

if (process.argv[1] && import.meta.url === new URL('file://' + process.argv[1]).href) {
  const config = read(process.argv[2], null);
  if (!config) throw Error('Gateway config file required');
  const mode = process.argv[3];
  if (mode === 'claim' || mode === 'invite') {
    const body = { action: mode, count: Number(process.argv[4] ?? 1) };
    try {
      const response = await new Promise((resolve, reject) => {
        const request = http.request({ host: '127.0.0.1', port: config.port, path: '/api/internal/admin', method: 'POST',
          headers: { 'x-harless-admin': config.adminToken, 'content-type': 'application/json' }, timeout: 3000 }, res => {
          let data = ''; res.on('data', part => data += part); res.on('end', () => resolve({ status: res.statusCode, data: JSON.parse(data) }));
        });
        request.on('error', reject); request.end(JSON.stringify(body));
      });
      if (response.status !== 200) throw Error('Gateway admin command rejected');
      console.log(mode === 'claim' ? response.data.code : response.data.codes.join('\n'));
    } catch (error) {
      if (error.code !== 'ECONNREFUSED') throw error;
      const offline = createGateway(config);
      console.log(mode === 'claim' ? createOwnerClaim(offline) : createInvites(offline, body.count).join('\n'));
    }
  } else {
    const sourceEnv = process.env.DEEPSEEK_API_KEY;
    if (!sourceEnv) throw Error('DEEPSEEK_API_KEY required for user workspaces');
    const gateway = createGateway({ ...config, apiKey: sourceEnv });
    if (gateway.scopedBudget) gateway.scopedBudget.listen(config.scopedBudgetPort, '127.0.0.1');
    gateway.server.listen(config.port, '127.0.0.1', () => console.log('Harless account gateway ready on loopback'));
    process.on('SIGTERM', () => gateway.close()); process.on('SIGINT', () => gateway.close());
  }
}
