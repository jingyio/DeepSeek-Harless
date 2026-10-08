#!/usr/bin/env node
// Expose only the existing SSS test calendar to a read-only benchmark Agent.
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const path = require('path');
const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
const { availabilityTools, callAvailability } = require('./calendar-availability.cjs');

const calendarId = process.env.SSS_BENCH_CALENDAR_ID;
if (!calendarId) throw new Error('SSS_BENCH_CALENDAR_ID is required');
const allowed = new Set(['list-calendars', 'list-events', 'search-events', 'get-event', 'get-freebusy']);

function eventView(event) {
  return Object.fromEntries(['id', 'summary', 'start', 'end', 'status', 'updated', 'calendarId']
    .filter(key => event[key] !== undefined).map(key => [key, event[key]]));
}

function scopedArgs(name, input) {
  const args = { ...(input || {}) };
  if (name === 'list-calendars') return args;
  if (name === 'get-freebusy') {
    if (!Array.isArray(args.calendars) || args.calendars.length !== 1 || args.calendars[0]?.id !== calendarId) {
      throw new Error('Only the SSS test calendar may be queried');
    }
    return args;
  }
  if (args.calendarId !== undefined && args.calendarId !== calendarId) {
    throw new Error('Only the SSS test calendar may be queried');
  }
  args.calendarId = calendarId;
  return args;
}

async function main() {
  const upstream = new Client({ name: 'sss-calendar-scoped-benchmark', version: '1.0.0' });
  const transport = new StdioClientTransport({
    command: path.join(__dirname, '../node_modules/.bin/google-calendar-mcp'),
    args: ['start'], env: { ...process.env, ENABLED_TOOLS: [...allowed].join(',') },
  });
  await upstream.connect(transport);
  const server = new Server({ name: 'sss-calendar-scoped-benchmark', version: '1.0.0' },
    { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const result = await upstream.listTools();
    return { tools: [...result.tools.filter(tool => allowed.has(tool.name)), ...availabilityTools] };
  });
  server.setRequestHandler(CallToolRequestSchema, async request => {
    const { name, arguments: input } = request.params;
    try {
      if (availabilityTools.some(tool => tool.name === name)) {
        const data = await callAvailability(upstream, name, input, calendarId);
        return { content: [{ type: 'text', text: JSON.stringify(data) }] };
      }
      if (!allowed.has(name)) throw new Error('Read-only test-calendar tools only');
      const result = await upstream.callTool({ name, arguments: scopedArgs(name, input) });
      if (result.isError) return result;
      const part = result.content.find(x => x.type === 'text');
      if (!part) throw new Error('Calendar tool has no JSON result');
      const data = JSON.parse(part.text);
      let view;
      if (name === 'list-calendars') {
        const calendars = (data.calendars || []).filter(x => x.id === calendarId)
          .map(x => Object.fromEntries(['id', 'summary', 'timeZone', 'accessRole']
            .filter(key => x[key] !== undefined).map(key => [key, x[key]])));
        if (calendars.length !== 1) throw new Error('Dedicated SSS test calendar is unavailable');
        view = { calendars, totalCount: 1 };
      } else if (name === 'get-event') {
        if (!data.event || data.event.calendarId !== calendarId) throw new Error('Out-of-scope event result');
        view = { event: eventView(data.event) };
      } else if (name === 'list-events' || name === 'search-events') {
        if (!Array.isArray(data.events) || data.events.some(x => x.calendarId !== calendarId)) {
          throw new Error('Out-of-scope event listing');
        }
        view = { events: data.events.map(eventView), totalCount: data.totalCount };
      } else {
        if (!data.calendars || Object.keys(data.calendars).some(id => id !== calendarId)) {
          throw new Error('Out-of-scope free/busy result');
        }
        view = data;
      }
      return { content: [{ type: 'text', text: JSON.stringify(view) }] };
    } catch (error) {
      return { isError: true, content: [{ type: 'text', text: error.message }] };
    }
  });
  await server.connect(new StdioServerTransport());
  process.on('SIGINT', () => { void upstream.close().finally(() => process.exit(0)); });
  process.on('SIGTERM', () => { void upstream.close().finally(() => process.exit(0)); });
}
main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
