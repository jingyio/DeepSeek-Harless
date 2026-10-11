// Deterministic MCP protocol/permission checks. No Google or model requests.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { InMemoryTransport } = require('@modelcontextprotocol/sdk/inMemory.js');
const config = require('../scenarios/mail-calendar-collaboration/scenario.json');
const state = fs.mkdtempSync(path.join(os.tmpdir(), 'sss-mail-calendar-protocol-'));
process.env.GMAIL_MCP_STATE_DIR = path.join(state, 'mail');
process.env.SSS_GOOGLE_CALENDAR_STATE = path.join(state, 'calendar');
for (const server of config.servers) {
  const env = server.env;
  for (const name of ['SSS_GMAIL_TOOL_ALLOWLIST', 'SSS_CALENDAR_TOOL_ALLOWLIST']) {
    if (env[name]) process.env[name] = env[name];
  }
}
const mail = require('../scripts/gmail-guarded-mcp.cjs');
const calendar = require('../scripts/calendar-guarded-mcp.cjs');
const slots = { calendarId: 'test-calendar', timeZone: 'Asia/Shanghai', durationMinutes: 60,
  timeWindows: [{ start: '2026-10-12T10:00:00+08:00', end: '2026-10-12T12:00:00+08:00' }] };
const tools = ['search_emails', 'read_email', 'get_thread', 'list_inbox_threads', 'get_inbox_with_threads',
  'list-calendars', 'list-events', 'search-events', 'get-event', 'get-freebusy', 'get-current-time',
  'send_email', 'create-event', 'delete-event'];
function upstream() {
  const calls = [];
  return { calls,
    async listTools() { return { tools: tools.map(name => ({ name, description: 'Synthetic protocol fixture', inputSchema: { type: 'object' } })) }; },
    async callTool(request) {
      calls.push(request);
      if (request.name === 'get-freebusy') return { content: [{ type: 'text', text: JSON.stringify({ calendars: {
        'test-calendar': { busy: [{ start: '2026-10-12T10:00:00+08:00', end: '2026-10-12T11:00:00+08:00' }] },
      } }) }] };
      return { content: [{ type: 'text', text: JSON.stringify({ source: request.name, arguments: request.arguments }) }] };
    },
  };
}
async function connect(factory) {
  const provider = upstream();
  const server = factory.createServer(provider);
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: 'offline-protocol-diagnostic', version: '1' });
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  return { client, server, provider, close: async () => { await client.close(); await server.close(); } };
}
test.after(() => fs.rmSync(state, { recursive: true, force: true }));

test('advertised MCP tools exactly match scenario normalized names and hide all review/write paths', async () => {
  for (const [name, factory] of [[config.servers[0].server_name, mail], ['calendar', calendar]]) {
    const connection = await connect(factory);
    try {
      const response = await connection.client.listTools();
      assert.deepEqual(response.tools.map(tool => `mcp__${name}__${tool.name.replaceAll('-', '_')}`).sort(),
        config.allowed_tools.filter(tool => tool.startsWith(`mcp__${name}__`)).sort());
      assert.ok(!response.tools.some(tool => /^(send_email|create-event|delete-event|open.*review)$/.test(tool.name)));
    } finally { await connection.close(); }
  }
});

test('forbidden calls are rejected by each MCP service without dispatch or preview creation', async () => {
  for (const [factory, names] of [[mail, ['send_email', 'open_email_review', 'delete_email']],
    [calendar, ['create-event', 'open-event-review', 'delete-event']]]) {
    const connection = await connect(factory);
    try {
      for (const name of names) {
        const response = await connection.client.callTool({ name, arguments: {} });
        assert.equal(response.isError, true);
        assert.match(response.content[0].text, /scope/);
      }
      assert.equal(connection.provider.calls.length, 0);
    } finally { await connection.close(); }
  }
});

test('read calls preserve runtime arguments; local email preview never calls Google', async () => {
  const connection = await connect(mail);
  try {
    await connection.client.callTool({ name: 'get_thread', arguments: { threadId: 'runtime-thread-17' } });
    assert.deepEqual(connection.provider.calls[0], { name: 'get_thread', arguments: { threadId: 'runtime-thread-17' } });
    const response = await connection.client.callTool({ name: 'prepare_email', arguments: {
      to: ['colleague@example.org'], subject: '需要澄清', body: '请核对截止时间。', replyToMessageId: 'abcdef1234567890',
    } });
    const preview = JSON.parse(response.content[0].text);
    assert.equal(preview.sent, false);
    assert.equal(preview.status, 'prepared');
    assert.equal(preview.email.replyToMessageId, 'abcdef1234567890');
    assert.equal(connection.provider.calls.length, 1);
    assert.equal(fs.statSync(path.join(state, 'mail/outbox', preview.id + '.json')).mode & 0o077, 0);
  } finally { await connection.close(); }
});

test('calendar slot computation and revalidation execute through MCP; preview stays local', async () => {
  const connection = await connect(calendar);
  try {
    const found = JSON.parse((await connection.client.callTool({ name: 'find-available-slots', arguments: slots })).content[0].text);
    assert.equal(found.earliest.start, '2026-10-12T11:00:00+08:00');
    const validation = JSON.parse((await connection.client.callTool({ name: 'validate-slot', arguments: {
      ...slots, candidateStart: '2026-10-12T10:00:00+08:00', candidateEnd: '2026-10-12T11:00:00+08:00',
    } })).content[0].text);
    assert.equal(validation.valid, false);
    const response = await connection.client.callTool({ name: 'prepare-event', arguments: {
      calendarId: slots.calendarId, summary: '待审协调方案', start: found.earliest.start, end: found.earliest.end, timeZone: slots.timeZone,
    } });
    assert.equal(JSON.parse(response.content[0].text).created, false);
    assert.equal(connection.provider.calls.length, 2);
  } finally { await connection.close(); }
});
