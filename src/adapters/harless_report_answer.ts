/** Display-only numeric binding. Original model text and task events are never rewritten. */
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, readFileSync, realpathSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

export const REPORT_ANSWER_BINDING = 'verified-report-tokens-v1';
const sha = (bytes: Uint8Array) => createHash('sha256').update(bytes).digest('hex');
const token = /\{\{([^{}\n]{1,120})\}\}/g;
// Code examples explain the tool contract and must keep their literal syntax.
const protectedCode = /(`{3,}|~{3,})[^\n]*\n[\s\S]*?(?:\n\1[^\n]*(?:\n|$)|$)|(`+)[^\n]*?\2/g;
const markdownText = (text: string) => text.replace(/[\\`*_{}\[\]<>|]/g, '\\$&');
const within = (root: string, path: string) => {
  const rel = relative(realpathSync(root), realpathSync(path));
  return Boolean(rel && rel !== '..' && !rel.startsWith('..' + sep) && !rel.startsWith(sep));
};
function proseParts(text: string) {
  const parts: { text: string; code: boolean }[] = []; let end = 0;
  for (const match of text.matchAll(protectedCode)) {
    parts.push({ text: text.slice(end, match.index), code: false }, { text: match[0], code: true });
    end = match.index! + match[0].length;
  }
  parts.push({ text: text.slice(end), code: false }); return parts;
}
export const hasReportPlaceholders = (text: string) => proseParts(text).some(part => !part.code && [...part.text.matchAll(token)].length > 0);

type Context = { answer: string; workspace: string; eventsPath: string; startedAt?: string; finishedAt?: string };
type Catalog = { id: string; sha256: string; values: Map<string, string> };

function verifiedCatalogs(context: Context): Catalog[] {
  const start = Date.parse(context.startedAt ?? ''), end = Date.parse(context.finishedAt ?? '');
  if (!Number.isFinite(start) || !Number.isFinite(end) || start > end || !existsSync(context.eventsPath)) return [];
  const stat = lstatSync(context.eventsPath);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1 || stat.size > 32 * 1024 * 1024) return [];
  const calls = new Set<string>(), catalogs = new Map<string, Catalog>();
  for (const line of readFileSync(context.eventsPath, 'utf8').split('\n')) {
    try {
      const event = JSON.parse(line);
      if (!Number.isFinite(event.time) || event.time < start || event.time > end) continue;
      if (event.type === 'tool/call' && event.data?.name === 'mcp__research_report__build_evidence' && typeof event.data.callId === 'string') calls.add(event.data.callId);
      if (event.type !== 'tool/result') continue;
      for (const part of event.data?.message?.content ?? []) {
        if (part.type !== 'tool-result' || part.isError || !calls.has(part.toolCallId)) continue;
        for (const content of part.content ?? []) {
          if (content.type !== 'text') continue;
          const receipt = JSON.parse(content.text), proof = receipt._provenance, id = receipt.evidence_id;
          if (receipt.ok !== true || !/^rra-evidence-[a-f0-9]{32}$/.test(id) || !/^[a-f0-9]{64}$/.test(proof?.record_sha256)) continue;
          // Ignore caller-supplied paths; the expected record is derived from
          // the task's own workspace and receipt ID, then matched exactly.
          const path = join(context.workspace, 'outputs/report/records', id + '.json');
          if (!existsSync(path) || !within(context.workspace, path) || realpathSync(path) !== proof.record_path) continue;
          const file = lstatSync(path);
          if (!file.isFile() || file.isSymbolicLink() || file.nlink !== 1 || file.size > 1024 * 1024) continue;
          const bytes = readFileSync(path);
          if (sha(bytes) !== proof.record_sha256) continue;
          const record = JSON.parse(bytes.toString('utf8')), payload = record.payload;
          if (record.id !== id || record.kind !== 'evidence' || payload?.passed !== true ||
              record.workspace_id !== proof.workspace_id || record.source_version !== receipt.source_version ||
              record.source_version !== proof.study_sha256 || payload.plan_id !== proof.plan_id ||
              !/^rra-verified_analysis-[a-f0-9]{32}$/.test(payload.verified_id)) continue;
          const observed = receipt.results ?? receipt.available_placeholders;
          if (!observed || typeof observed !== 'object') continue;
          const values = new Map<string, string>();
          for (const [name, item] of Object.entries(payload.available_placeholders ?? {}) as [string, any][]) {
            if (values.size >= 128 || !/^[a-z][a-z0-9_]{0,63}$/.test(name) || item?.token !== '{{' + name + '}}' ||
                typeof item.display !== 'string' || !item.display.length || item.display.length > 256 || /[\x00-\x1f]/.test(item.display) ||
                !(typeof item.value === 'number' && Number.isFinite(item.value) || typeof item.value === 'string') ||
                observed[name]?.value !== item.value || observed[name]?.display !== item.display) continue;
            values.set(name, item.display);
          }
          if (values.size) catalogs.set(id, { id, sha256: proof.record_sha256, values });
        }
      }
    } catch { /* Missing, changed, malformed or unrelated evidence never supplies a value. */ }
  }
  return [...catalogs.values()];
}

export function bindReportAnswer(context: Context) {
  if (!hasReportPlaceholders(context.answer)) return {};
  let catalogs: Catalog[] = [];
  try { catalogs = verifiedCatalogs(context); } catch { /* Presentation still explains unresolved values. */ }
  // Multiple statistical plans can give the same token different meanings.
  // Do not choose the newest file or merge catalogs by field name.
  const catalog = catalogs.length === 1 ? catalogs[0] : undefined;
  const bound = new Set<string>(), unresolved = new Set<string>();
  const answer_display = proseParts(context.answer).map(part => part.code ? part.text : part.text.replace(token, (_raw, name) => {
    const value = catalog?.values.get(name);
    if (value === undefined) { unresolved.add(name); return '【未绑定：' + markdownText(name) + '】'; }
    bound.add(name); return markdownText(value);
  })).join('');
  return { answer_display, answer_binding: { version: REPORT_ANSWER_BINDING,
    source_answer_sha256: sha(Buffer.from(context.answer)),
    status: unresolved.size ? 'unresolved' : 'bound', bound_tokens: [...bound].sort(), unresolved_tokens: [...unresolved].sort(),
    reason: !catalog ? catalogs.length > 1 ? 'ambiguous_task_evidence' : 'no_verified_task_evidence' : unresolved.size ? 'unknown_evidence_token' : null,
    evidence_id: catalog?.id ?? null, evidence_sha256: catalog?.sha256 ?? null } };
}
