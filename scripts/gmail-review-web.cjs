#!/usr/bin/env node
// Ephemeral localhost review page. Never expose this as a model tool.
const http = require('http');
const crypto = require('crypto');
const { spawn } = require('child_process');
const { loadReview, sendReviewed } = require('./gmail-review.cjs');

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
}

function page(title, inner) {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHtml(title)}</title><style>
  body{font:16px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f6f8;color:#17202a;margin:0;padding:32px}
  main{max-width:760px;margin:auto;background:white;border:1px solid #e3e6eb;border-radius:12px;padding:28px}
  h1{font-size:25px;margin:0 0 12px}dl{display:grid;grid-template-columns:100px 1fr;gap:9px 14px}dt{color:#596579}dd{margin:0;overflow-wrap:anywhere}
  pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f7f8fa;border:1px solid #e3e6eb;border-radius:8px;padding:16px}
  input{font:inherit;width:100%;box-sizing:border-box;padding:10px;border:1px solid #aeb7c2;border-radius:6px}
  button{font:inherit;padding:10px 18px;margin-top:14px;background:#a72323;color:white;border:0;border-radius:6px;cursor:pointer}
  .note{color:#596579}.error{color:#9d1d1d}
  </style></head><body><main>${inner}</main></body></html>`;
}

function reviewPage(context, action) {
  const { record, senderAddress, reply } = context;
  const email = record.email;
  return page('审核邮件', `<h1>发送前审核</h1><p class="note">这是一封待审邮件。页面不会自动发送；确认后将通过 Gmail API 发送。</p>
  <dl><dt>发件账号</dt><dd>${escapeHtml(senderAddress)}</dd><dt>收件人</dt><dd>${escapeHtml(email.to.join(', '))}</dd>
  ${email.cc.length ? `<dt>抄送</dt><dd>${escapeHtml(email.cc.join(', '))}</dd>` : ''}
  ${email.bcc.length ? `<dt>密送</dt><dd>${escapeHtml(email.bcc.join(', '))}</dd>` : ''}
  <dt>主题</dt><dd>${escapeHtml(email.subject)}</dd>
  ${reply ? `<dt>回复原邮件</dt><dd>${escapeHtml(reply.originalFrom)} · ${escapeHtml(reply.originalSubject)} · ${escapeHtml(email.replyToMessageId)}</dd>` : ''}
  <dt>审阅编号</dt><dd>${escapeHtml(record.id)}</dd><dt>内容指纹</dt><dd>${escapeHtml(record.sha256)}</dd></dl>
  <h2>正文</h2><pre>${escapeHtml(email.body)}</pre>
  <form method="post" action="${escapeHtml(action)}"><input type="hidden" name="sha256" value="${escapeHtml(record.sha256)}">
  <label for="confirmation">确认发送时，输入 <strong>SEND ${escapeHtml(record.id)}</strong></label>
  <input id="confirmation" name="confirmation" autocomplete="off" required>
  <button type="submit">发送这封邮件</button></form>
  <p class="note">不发送可直接关闭页面。发送结果不明时不会自动重试。</p>`);
}

function respond(res, status, html) {
  res.writeHead(status, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-store',
    'Referrer-Policy': 'same-origin',
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
  });
  res.end(html);
}

async function start(id, options = {}) {
  const secret = crypto.randomBytes(32).toString('hex');
  const route = `/${secret}`;
  const server = http.createServer(async (req, res) => {
    const origin = `http://127.0.0.1:${server.address().port}`;
    if (req.headers.host !== `127.0.0.1:${server.address().port}` || ![route, `${route}/send`].includes(req.url)) {
      respond(res, 404, page('未找到', '<h1>未找到</h1>')); return;
    }
    if (req.method === 'GET' && req.url === route) {
      try { respond(res, 200, reviewPage(await loadReview(id), `${route}/send`)); }
      catch (error) { respond(res, 400, page('无法审核', `<h1>无法审核</h1><p class="error">${escapeHtml(error.message)}</p>`)); }
      return;
    }
    if (req.method !== 'POST' || req.url !== `${route}/send` || req.headers.origin !== origin
        || !req.headers['content-type']?.startsWith('application/x-www-form-urlencoded')) {
      respond(res, 403, page('已拒绝', '<h1>请求已拒绝</h1>')); return;
    }
    let body = '';
    for await (const chunk of req) {
      body += chunk;
      if (body.length > 8192) { respond(res, 413, page('请求过大', '<h1>请求过大</h1>')); return; }
    }
    const fields = new URLSearchParams(body);
    if (fields.get('confirmation') !== `SEND ${id}`) {
      respond(res, 400, page('未发送', '<h1>未发送</h1><p>确认文字不匹配。邮件仍在待审队列。</p>')); return;
    }
    try {
      const context = await loadReview(id);
      if (fields.get('sha256') !== context.record.sha256) throw new Error('邮件内容已更改，请重新审核');
      const result = await sendReviewed(context);
      respond(res, 200, page('已发送', `<h1>邮件已发送</h1><p>Gmail 消息 ID：${escapeHtml(result.id)}</p>`));
      server.close();
    } catch (error) {
      respond(res, 400, page('发送未完成', `<h1>发送未完成</h1><p class="error">${escapeHtml(error.message)}</p>`));
    }
  });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  const url = `http://127.0.0.1:${server.address().port}${route}`;
  if (!options.quiet) process.stdout.write(`Open this local review page: ${url}\n`);
  if (options.open !== false && process.platform === 'darwin') {
    const opener = spawn('open', [url], { stdio: 'ignore' });
    opener.on('error', () => {});
    opener.unref();
  }
  const expiry = setTimeout(() => server.close(), 2 * 60 * 60 * 1000);
  expiry.unref();
  return { server, url };
}

if (require.main === module) {
  const id = process.argv[2];
  if (!id) { process.stderr.write('Usage: npm run gmail:review-web -- <review ID>\n'); process.exitCode = 2; }
  else start(id, { open: process.env.SSS_NO_OPEN !== '1' }).catch((error) => {
    process.stderr.write(`${error.message}\n`); process.exitCode = 1;
  });
}
module.exports = { start, escapeHtml, reviewPage };
