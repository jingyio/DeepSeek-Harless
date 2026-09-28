#!/usr/bin/env node
// Read Gmail and prepare local emails. Actual sending requires the human review page.
const { execFileSync } = require('node:child_process');

// macOS desktop apps can use the system proxy while stdio MCP children do not.
// Carry that setting into both Gmail reads and the later human-reviewed send.
if (process.platform === 'darwin' && !process.env.HTTPS_PROXY && !process.env.https_proxy) {
  try {
    const settings = execFileSync('/usr/sbin/scutil', ['--proxy'],
      { encoding: 'utf8', timeout: 1500 });
    const setting = (key) => settings.match(new RegExp(`^\\s*${key}\\s*:\\s*(\\S+)`, 'm'))?.[1];
    const host = setting('HTTPSProxy');
    const port = Number(setting('HTTPSPort'));
    if (setting('HTTPSEnable') === '1' && host && Number.isInteger(port) &&
        port > 0 && port <= 65535) {
      const proxy = new URL(`http://${host}:${port}`);
      process.env.HTTPS_PROXY = proxy.href;
      process.env.https_proxy = proxy.href;
      const bypass = new Set((process.env.NO_PROXY || process.env.no_proxy || '')
        .split(',').map((value) => value.trim()).filter(Boolean));
      bypass.add('127.0.0.1');
      bypass.add('localhost');
      process.env.NO_PROXY = [...bypass].join(',');
      process.env.no_proxy = process.env.NO_PROXY;
    }
  } catch { /* A missing system proxy leaves the explicit environment alone. */ }
}

const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { ListToolsRequestSchema, CallToolRequestSchema, ErrorCode } = require('@modelcontextprotocol/sdk/types.js');
const path = require('path');
const outbox = require('./gmail-outbox.cjs');
const reviewWeb = require('./gmail-review-web.cjs');
const { searchMetadata, readMetadata, attachMetadata } = require('./gmail-structured-results.cjs');
const reviewPages = new Map();
const READ_TIMEOUT_MS = 25000;

async function openReview(id) {
  if (!reviewPages.has(id)) {
    const page = await reviewWeb.start(id, { quiet: true, open: process.env.SSS_NO_OPEN !== '1' });
    reviewPages.set(id, page);
    page.server.once('close', () => reviewPages.delete(id));
  }
}

const allowed = new Set([
  'search_emails',
  'read_email',
  'get_thread',
  'list_inbox_threads',
  'get_inbox_with_threads',
  'list_drafts',
  'get_draft',
  'list_email_labels',
]);
const localTools = [
  {
    name: 'prepare_email',
    description: 'Prepare a plain-text new email or reply in the local review queue. For a reply, pass the original Gmail message ID as replyToMessageId. Does not create a Gmail draft or send mail. Give the review ID to the user, who must review and send it separately.',
    inputSchema: {
      type: 'object', required: ['to', 'subject', 'body'], additionalProperties: false,
      properties: {
        to: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 20 },
        cc: { type: 'array', items: { type: 'string' }, maxItems: 20 },
        bcc: { type: 'array', items: { type: 'string' }, maxItems: 20 },
        subject: { type: 'string', maxLength: 200 },
        body: { type: 'string', maxLength: 100000 },
        replyToMessageId: { type: 'string', description: 'Optional Gmail message ID of the email being replied to.' },
      },
    },
  },
  {
    name: 'list_prepared_emails',
    description: 'List locally prepared emails and their review status. Does not access Gmail.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'get_prepared_email',
    description: 'Read one locally prepared email, including its full text, for review. Does not access Gmail.',
    inputSchema: { type: 'object', required: ['id'], properties: { id: { type: 'string' } }, additionalProperties: false },
  },
  {
    name: 'open_email_review',
    description: 'Open a local browser review page for one prepared email. The human can inspect and explicitly send there. This tool itself never sends mail.',
    inputSchema: { type: 'object', required: ['id'], properties: { id: { type: 'string' } }, additionalProperties: false },
  },
  {
    name: 'send_email',
    description: 'Request to send a plain-text email: save an exact local preview and open the human review page. This tool returns sent=false; Gmail is contacted to send only after the human confirms on that page. For a reply, supply replyToMessageId. Never describe this tool call as a completed send.',
    inputSchema: {
      type: 'object', required: ['to', 'subject', 'body'], additionalProperties: false,
      properties: {
        to: { type: 'array', items: { type: 'string' }, minItems: 1, maxItems: 20 },
        cc: { type: 'array', items: { type: 'string' }, maxItems: 20 },
        bcc: { type: 'array', items: { type: 'string' }, maxItems: 20 },
        subject: { type: 'string', maxLength: 200 },
        body: { type: 'string', maxLength: 100000 },
        replyToMessageId: { type: 'string' },
      },
    },
  },
];
const exposedNames = process.env.SSS_GMAIL_TOOL_ALLOWLIST
  ? new Set(process.env.SSS_GMAIL_TOOL_ALLOWLIST.split(',').map((name) => name.trim()))
  : null;
if (exposedNames && [...exposedNames].some((name) =>
    !allowed.has(name) && !localTools.some((tool) => tool.name === name))) {
  throw new Error('Gmail tool allowlist includes an unknown tool');
}

function scopeError(name, args) {
  if (exposedNames && !exposedNames.has(name)) return 'Gmail tool is outside this task scope.';
  if (name === 'search_emails' && process.env.SSS_GMAIL_ALLOWED_QUERY &&
      args?.query !== process.env.SSS_GMAIL_ALLOWED_QUERY) {
    return 'Gmail query is outside this task scope.';
  }
  if (name === 'read_email' && process.env.SSS_GMAIL_ALLOWED_MESSAGE_ID &&
      args?.messageId !== process.env.SSS_GMAIL_ALLOWED_MESSAGE_ID) {
    return 'Gmail message is outside this task scope.';
  }
  if ((name === 'prepare_email' || name === 'send_email') &&
      process.env.SSS_GMAIL_ALLOWED_RECIPIENT &&
      (args?.to?.length !== 1 ||
       args.to[0] !== process.env.SSS_GMAIL_ALLOWED_RECIPIENT ||
       args?.cc?.length || args?.bcc?.length)) {
    return 'Gmail recipient is outside this task scope.';
  }
  return null;
}

async function main() {
  const upstream = new Client({ name: 'sss-gmail-readonly-bridge', version: '1.0.0' });
  const child = new StdioClientTransport({
    command: path.join(__dirname, '../node_modules/.bin/gmail-mcp'),
    env: { ...process.env, GMAIL_MCP_DRY_RUN: 'true' },
  });
  await upstream.connect(child);

  const server = new Server(
    { name: 'sss-google-gmail-readonly', version: '1.0.0' },
    { capabilities: { tools: {} } },
  );
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const result = await upstream.listTools();
    return { tools: [...result.tools.filter((tool) => allowed.has(tool.name)), ...localTools]
      .filter((tool) => !exposedNames || exposedNames.has(tool.name)) };
  });
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    const denied = scopeError(name, args);
    if (denied) return { isError: true, content: [{ type: 'text', text: denied }] };
    try {
      if (name === 'prepare_email') {
        const record = outbox.prepare(args ?? {});
        return { content: [{ type: 'text', text: JSON.stringify({ id: record.id, status: record.status, email: record.email, sha256: record.sha256, nextTool: 'open_email_review', reviewCommand: `npm run gmail:review-web -- ${record.id}`, sent: false }) }] };
      }
      if (name === 'list_prepared_emails') return { content: [{ type: 'text', text: JSON.stringify(outbox.list()) }] };
      if (name === 'get_prepared_email') return { content: [{ type: 'text', text: JSON.stringify(outbox.read(args?.id)) }] };
      if (name === 'open_email_review') {
        const record = outbox.read(args?.id);
        if (record.status !== 'prepared') throw new Error(`Email status is ${record.status}`);
        await openReview(record.id);
        return { content: [{ type: 'text', text: JSON.stringify({ opened: true, id: record.id, sent: false, note: 'Review the local browser page. Only the human confirmation on that page can send.' }) }] };
      }
      if (name === 'send_email') {
        const email = outbox.payload(args ?? {});
        const sha256 = outbox.digest(email);
        const recent = outbox.list().find((item) => item.status === 'prepared' && item.sha256 === sha256
          && Date.now() - Date.parse(item.createdAt) < 10 * 60 * 1000);
        const record = recent ? outbox.read(recent.id) : outbox.prepare(email);
        await openReview(record.id);
        return { content: [{ type: 'text', text: JSON.stringify({ id: record.id, status: 'awaiting_human_review', sent: false, reviewOpened: true, email: record.email, note: 'The email has NOT been sent. The human must confirm in the browser.' }) }] };
      }
    } catch (error) {
      return { isError: true, content: [{ type: 'text', text: error.message }] };
    }
    if (!allowed.has(name)) {
      return { isError: true, content: [{ type: 'text', text: 'This Gmail MCP cannot send or modify Gmail messages.' }] };
    }
    try {
      const result = await upstream.callTool(
        { name, arguments: args ?? {} }, undefined,
        { timeout: READ_TIMEOUT_MS, maxTotalTimeout: READ_TIMEOUT_MS },
      );
      const metadata = name === 'search_emails' ? searchMetadata(result)
        : name === 'read_email' ? readMetadata(result, args) : null;
      // DSH drops structuredContent and merges MCP text blocks in tool/result.
      // The helper prefixes verified fields with a protocol marker; the full
      // untrusted upstream text remains in the following block for the model.
      return attachMetadata(result, metadata);
    } catch (error) {
      const message = error?.code === ErrorCode.RequestTimeout
        ? 'Gmail read did not complete within 25 seconds. Check the connection and retry; no email was sent or modified.'
        : 'Gmail read failed. Check the connection or account authorization; no email was sent or modified.';
      return { isError: true, content: [{ type: 'text',
        text: message }] };
    }
  });
  await server.connect(new StdioServerTransport());

  process.on('SIGINT', () => { void upstream.close().finally(() => process.exit(0)); });
  process.on('SIGTERM', () => { void upstream.close().finally(() => process.exit(0)); });
}

main().catch((error) => {
  process.stderr.write(`Gmail bridge failed: ${error.message}\n`);
  process.exitCode = 1;
});
