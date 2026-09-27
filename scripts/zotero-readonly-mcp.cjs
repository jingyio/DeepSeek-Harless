#!/usr/bin/env node
// Zotero 9 local API has no write support. Expose only verified read-oriented tools.
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const { ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');

const allowed = new Set([
  'zotero_get_annotations', 'zotero_get_notes', 'zotero_get_page_layout',
  'zotero_get_item_metadata', 'zotero_get_item_fulltext', 'zotero_get_attachment_path',
  'zotero_get_collections', 'zotero_get_collection_items', 'zotero_get_item_children',
  'zotero_get_tags', 'zotero_list_libraries', 'zotero_get_recent',
  'zotero_read_pdf_pages', 'zotero_search_items', 'zotero_search_by_tag',
  'zotero_search_by_citation_key', 'zotero_advanced_search',
  'zotero_get_search_database_status', 'zotero_search_collections',
  'zotero_get_pdf_outline', 'zotero_write_capabilities',
]);

async function main() {
  const upstream = new Client({ name: 'sss-zotero-readonly-bridge', version: '1.0.0' });
  const child = new StdioClientTransport({ command: process.env.SSS_ZOTERO_UPSTREAM,
    env: { ...process.env, ZOTERO_LOCAL: 'true', ZOTERO_MCP_SCHEMA_REFRESH: '0' } });
  await upstream.connect(child);
  const server = new Server({ name: 'sss-zotero-readonly', version: '1.0.0' }, { capabilities: { tools: {} } });
  server.setRequestHandler(ListToolsRequestSchema, async () => {
    const result = await upstream.listTools();
    return { tools: result.tools.filter((tool) => allowed.has(tool.name)) };
  });
  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    if (!allowed.has(name)) return { isError: true, content: [{ type: 'text', text: 'Zotero write tools are unavailable for this local Zotero 9 connection.' }] };
    return upstream.callTool({ name, arguments: args ?? {} });
  });
  await server.connect(new StdioServerTransport());
  process.on('SIGINT', () => { void upstream.close().finally(() => process.exit(0)); });
  process.on('SIGTERM', () => { void upstream.close().finally(() => process.exit(0)); });
}
main().catch((error) => { process.stderr.write(`Zotero bridge failed: ${error.message}\n`); process.exitCode = 1; });
