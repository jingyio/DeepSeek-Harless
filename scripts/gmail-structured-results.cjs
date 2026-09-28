// Extract only protocol-generated identifiers from the read-only Gmail bridge.
// Keep the complete upstream text unchanged for the model. If its layout differs
// or a subject injects extra lines, do not emit structured fields.
const { createHash } = require('node:crypto');

const OPEN = '<untrusted-tool-output>\n';
const CLOSE = '</untrusted-tool-output>';
const ID = '[A-Za-z0-9_-]{1,256}';
const METADATA_MARKER = 'SSS_STRUCTURED_METADATA_V1 ';

function payload(result) {
  if (result?.isError || result?.structuredContent ||
      !Array.isArray(result?.content) || result.content.length !== 1 ||
      result.content[0]?.type !== 'text') return null;
  const text = result.content[0].text;
  if (typeof text !== 'string' || !text.startsWith(OPEN) ||
      !text.endsWith(CLOSE)) return null;
  return text.slice(OPEN.length, -CLOSE.length).trim();
}

function searchMetadata(result) {
  const body = payload(result);
  if (body === null) return null;
  const ids = [];
  if (body) {
    for (const block of body.split(/\n\n/)) {
      const lines = block.split('\n');
      if (lines.length !== 4 ||
          !new RegExp(`^ID: (${ID})$`).test(lines[0]) ||
          !lines[1].startsWith('Subject: ') ||
          !lines[2].startsWith('From: ') ||
          !lines[3].startsWith('Date: ')) return null;
      ids.push(lines[0].slice(4));
    }
  }
  if (new Set(ids).size !== ids.length) return null;
  return { message_ids: ids, count: ids.length,
    result_digest: createHash('sha256').update(JSON.stringify(ids)).digest('hex') };
}

function readMetadata(result, args) {
  const body = payload(result);
  const messageId = args?.messageId;
  if (body === null || typeof messageId !== 'string' ||
      !new RegExp(`^${ID}$`).test(messageId)) return null;
  const first = body.split('\n', 1)[0];
  const match = first.match(new RegExp(`^Thread ID: (${ID})$`));
  if (!match) return null;
  return { message_id: messageId, thread_id: match[1],
    source_version: messageId };
}

function attachMetadata(result, metadata) {
  return metadata ? { ...result, structuredContent: metadata,
    // DSH merges MCP text blocks and drops structuredContent in tool/result.
    // A marked first line survives that merge for the audited Gmail bridge.
    content: [{ type: 'text', text: METADATA_MARKER + JSON.stringify(metadata) },
      ...result.content] } : result;
}

module.exports = { searchMetadata, readMetadata, attachMetadata, METADATA_MARKER };
