#!/usr/bin/env node
// Restrict the DSH-facing Calendar MCP surface to read-only operations.
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} = require('@modelcontextprotocol/sdk/types.js');

const allowed = new Set([
  'list-calendars',
  'list-events',
  'search-events',
  'get-event',
  'list-colors',
  'get-freebusy',
  'get-current-time',
]);

async function main() {
  const upstream = new Client({ name: 'sss-calendar-readonly-bridge', version: '1.0.0' });
  const child = new StdioClientTransport({
    command: require('path').join(__dirname, '../node_modules/.bin/google-calendar-mcp'),
    args: ['start'],
    env: { ...process.env, ENABLED_TOOLS: [...allowed].join(',') },
  });
  await upstream.connect(child);

  const server = new Server(
    { name: 'sss-google-calendar-readonly', version: '1.0.0' },
    { capabilities: { tools: {} } },
  );
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const result = await upstream.listTools();
    return { tools: result.tools.filter((tool) => allowed.has(tool.name)) };
  });
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    if (!allowed.has(name)) {
      return { isError: true, content: [{ type: 'text', text: 'Tool is not available in the read-only Calendar bridge.' }] };
    }
    return upstream.callTool({ name, arguments: args ?? {} });
  });
  await server.connect(new StdioServerTransport());

  process.on('SIGINT', () => { void upstream.close().finally(() => process.exit(0)); });
  process.on('SIGTERM', () => { void upstream.close().finally(() => process.exit(0)); });
}

main().catch((error) => {
  process.stderr.write(`Calendar bridge failed: ${error.message}\n`);
  process.exitCode = 1;
});
