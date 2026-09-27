#!/usr/bin/env node
// Calendar reads plus locally reviewed event creation. MCP calls never write to Google Calendar.
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
const path = require('path');
const outbox = require('./calendar-outbox.cjs');
const reviewWeb = require('./calendar-review-web.cjs');

const allowed = new Set([
  'list-calendars', 'list-events', 'search-events', 'get-event',
  'list-colors', 'get-freebusy', 'get-current-time',
]);
const eventProperties = {
  calendarId: { type: 'string', description: 'Google Calendar ID; defaults to primary' },
  summary: { type: 'string', maxLength: 200 },
  description: { type: 'string', maxLength: 10000 },
  start: { type: 'string', description: 'ISO timestamp with offset, for example 2026-09-25T15:00:00+08:00' },
  end: { type: 'string', description: 'ISO timestamp with offset, later than start' },
  timeZone: { type: 'string', description: 'Optional IANA time zone, for example Asia/Shanghai' },
  attendees: { type: 'array', items: { type: 'string' }, maxItems: 20 },
};
const eventSchema = { type: 'object', required: ['summary', 'start', 'end'], additionalProperties: false, properties: eventProperties };
const localTools = [
  { name: 'prepare-event', description: 'Save an exact local event preview. Does not create a Google Calendar event.', inputSchema: eventSchema },
  { name: 'list-prepared-events', description: 'List local event previews and their status.', inputSchema: { type: 'object', properties: {}, additionalProperties: false } },
  { name: 'open-event-review', description: 'Open the local browser review page for one prepared event. Only the human can confirm creation there.', inputSchema: { type: 'object', required: ['id'], properties: { id: { type: 'string' } }, additionalProperties: false } },
  { name: 'create-event', description: 'Prepare an event and open a local human review page. Returns created=false; this tool never writes to Google Calendar. The human must confirm in the browser.', inputSchema: eventSchema },
];
const reviewPages = new Map();
async function openReview(id) {
  if (!reviewPages.has(id)) {
    const page = await reviewWeb.start(id, { quiet: true, open: process.env.SSS_NO_OPEN !== '1' });
    reviewPages.set(id, page);
    page.server.once('close', () => reviewPages.delete(id));
  }
}

async function main() {
  const upstream = new Client({ name: 'sss-calendar-guarded-bridge', version: '1.0.0' });
  const child = new StdioClientTransport({
    command: path.join(__dirname, '../node_modules/.bin/google-calendar-mcp'),
    args: ['start'], env: { ...process.env, ENABLED_TOOLS: [...allowed].join(',') },
  });
  await upstream.connect(child);
  const server = new Server({ name: 'sss-google-calendar-guarded', version: '1.0.0' }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const result = await upstream.listTools();
    return { tools: [...result.tools.filter((tool) => allowed.has(tool.name)), ...localTools] };
  });
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    try {
      if (name === 'prepare-event') {
        const record = outbox.prepare(args ?? {});
        return { content: [{ type: 'text', text: JSON.stringify({ id: record.id, status: record.status, event: record.event, sha256: record.sha256, created: false, nextTool: 'open-event-review' }) }] };
      }
      if (name === 'list-prepared-events') return { content: [{ type: 'text', text: JSON.stringify(outbox.list()) }] };
      if (name === 'open-event-review') {
        const record = outbox.read(args?.id);
        if (record.status !== 'prepared') throw new Error(`Event status is ${record.status}`);
        await openReview(record.id);
        return { content: [{ type: 'text', text: JSON.stringify({ opened: true, id: record.id, created: false }) }] };
      }
      if (name === 'create-event') {
        const event = outbox.payload(args ?? {});
        const sha256 = outbox.digest(event);
        const recent = outbox.list().find((item) => item.status === 'prepared' && item.sha256 === sha256
          && Date.now() - Date.parse(item.createdAt) < 10 * 60 * 1000);
        const record = recent ? outbox.read(recent.id) : outbox.prepare(event);
        await openReview(record.id);
        return { content: [{ type: 'text', text: JSON.stringify({ id: record.id, status: 'awaiting_human_review', created: false, event: record.event }) }] };
      }
    } catch (error) { return { isError: true, content: [{ type: 'text', text: error.message }] }; }
    if (!allowed.has(name)) return { isError: true, content: [{ type: 'text', text: 'Calendar write tools require human review and are not directly available.' }] };
    return upstream.callTool({ name, arguments: args ?? {} });
  });
  await server.connect(new StdioServerTransport());
  process.on('SIGINT', () => { void upstream.close().finally(() => process.exit(0)); });
  process.on('SIGTERM', () => { void upstream.close().finally(() => process.exit(0)); });
}
main().catch((error) => { process.stderr.write(`Calendar bridge failed: ${error.message}\n`); process.exitCode = 1; });
