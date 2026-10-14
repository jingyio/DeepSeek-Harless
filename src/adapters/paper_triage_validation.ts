/** One authoritative structural validator shared by the explicit tool and hook.
 * It neither evaluates generated code nor certifies bibliographic judgments.
 */
import { createHash } from 'node:crypto';
import { constants, openSync, closeSync, fstatSync, readFileSync, readdirSync, lstatSync } from 'node:fs';
import { resolve, join, relative, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { validateJsonSchemaValue } from '@deepseek-ai/dsh-tools';

export const triageSchemaPath = fileURLToPath(new URL('../../schemas/paper-citation-triage.schema.json', import.meta.url));
export const triageSchema = JSON.parse(readFileSync(triageSchemaPath, 'utf8'));
export const sha256 = (bytes: any): string => createHash('sha256').update(bytes).digest('hex');
const pairKey = (p: any) => JSON.stringify([p.key, p.arxiv_id]);
const plain = (p: any) => p !== null && typeof p === 'object' && !Array.isArray(p);

export function readBoundedFile(path: string, limit = 1000000): Buffer {
  const absolute = resolve(path);
  // No symlink component, even when the final file itself is regular.
  for (let p = absolute;; p = resolve(p, '..')) {
    if (lstatSync(p).isSymbolicLink()) throw Error('symlink_path');
    if (p === resolve(p, '..')) break;
  }
  const fd = openSync(absolute, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0));
  try {
    const before = fstatSync(fd);
    if (!before.isFile() || before.size > limit) throw Error('invalid_file_or_size');
    const bytes = readFileSync(fd), after = fstatSync(fd);
    if (bytes.length > limit || before.size !== after.size || before.mtimeMs !== after.mtimeMs)
      throw Error('file_changed_during_read');
    return bytes;
  } finally { closeSync(fd); }
}

export function snapshotSource(root: string): Record<string, string> {
  const result: Record<string,string> = {}; let total = 0;
  function visit(dir: string, depth: number) {
    if (depth > 20 || lstatSync(dir).isSymbolicLink()) throw Error('invalid_source_tree');
    for (const item of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, item.name);
      if (item.isSymbolicLink()) throw Error('symlink_source');
      if (item.isDirectory()) visit(path, depth + 1);
      else if (item.isFile()) {
        const bytes = readBoundedFile(path, 50000000); total += bytes.length;
        result[relative(root, path).split('\\').join('/')] = sha256(bytes);
        if (Object.keys(result).length > 256 || total > 50000000) throw Error('source_size_limit');
      } else throw Error('non_regular_source');
    }
  }
  visit(resolve(root), 0); return result;
}

export function sourceUnchanged(config: any): boolean {
  try {
    const actual = snapshotSource(config.source_root);
    if (JSON.stringify(Object.keys(actual).sort()) !== JSON.stringify(Object.keys(config.source_files).sort())) return false;
    return Object.entries(actual).every(([p,h]) => config.source_files[p] === h) &&
      Object.entries(config.code_files ?? {}).every(([p,h]) => sha256(readBoundedFile(p)) === h);
  } catch { return false; }
}

export function acceptEvidencePacket(packet: any, config: any): boolean {
  try {
    const refs = packet.references;
    if (packet.schema_version !== 1 || packet.case_id !== config.case_id ||
        packet.version_sha256 !== config.source_version ||
        packet.scope !== 'active_manuscript_literal_cite_keys_only' ||
        !/^source-[0-9a-f]{32}$/.test(packet.citation_id) ||
        refs.citation_id !== packet.citation_id || refs.source_id !== packet.source_id ||
        refs.version_sha256 !== packet.version_sha256 || !sourceUnchanged(config)) return false;
    if (!Array.isArray(refs.requested_keys) || refs.requested_keys.length > 64 ||
        JSON.stringify(refs.requested_keys) !== JSON.stringify(packet.diagnostic.cited_keys) ||
        !Array.isArray(refs.records)) return false;
    const pairs = new Set<string>();
    for (const row of refs.records) {
      if (!refs.requested_keys.includes(row.key) || typeof row.raw_bibtex !== 'string' ||
          sha256(row.raw_bibtex) !== row.record_sha256 ||
          config.source_files[row.bib_file] !== row.bib_file_sha256) return false;
      for (const m of row.raw_bibtex.matchAll(/(?<!\d)(\d{4}\.\d{4,5})(?!\d)/g))
        pairs.add(pairKey({key:row.key, arxiv_id:m[1]}));
    }
    if (!Array.isArray(packet.required_reference_pairs) || packet.required_reference_pairs.length !== pairs.size ||
        packet.required_reference_pairs.some((p: any) => !pairs.has(pairKey(p))) ||
        new Set(packet.required_reference_pairs.map(pairKey)).size !== pairs.size) return false;
    return JSON.stringify(refs.required_reference_pairs) === JSON.stringify(packet.required_reference_pairs);
  } catch { return false; }
}

export function validateTriage(document: any, packet: any): any {
  const errors = validateJsonSchemaValue(triageSchema, document).slice(0, 32);
  const rows = Array.isArray(document?.references) ? document.references : [];
  const expected = new Set<string>(packet.required_reference_pairs.map(pairKey));
  const actual = rows.filter(plain).map(pairKey), seen = new Set(actual);
  const missing = [...expected].filter(p => !seen.has(p));
  const extra = [...seen].filter(p => !expected.has(p));
  if (actual.length !== seen.size) errors.push('duplicate_reference_pair');
  if (missing.length) errors.push('missing_reference_pairs');
  if (extra.length) errors.push('unexpected_reference_pairs');
  const known = new Set(packet.references.requested_keys);
  const issues = Array.isArray(document?.citation_issues) ? document.citation_issues : [];
  const reported = new Set(issues.flatMap((r: any) => Array.isArray(r?.keys) ? r.keys : []));
  if ([...reported].some(k => !known.has(k))) errors.push('citation_issue_key_outside_scope');
  for (const key of [...packet.references.missing_keys, ...Object.keys(packet.references.duplicate_keys)])
    if (!reported.has(key)) errors.push('unreported_source_citation_problem:' + key);
  for (const row of rows) {
    if (!plain(row)) continue;
    for (const url of Array.isArray(row.source_urls) ? row.source_urls : []) {
      try { if (!['http:', 'https:'].includes(new URL(url).protocol)) throw Error(); }
      catch { errors.push('invalid_source_url:' + row.key); }
    }
    if (row.evidence_status === '已获取' && (!Array.isArray(row.source_urls) || !row.source_urls.length))
      errors.push('obtained_evidence_without_source:' + row.key);
  }
  return {schema_version:1, check:'paper_citation_triage_structure', status:errors.length ? 'needs_repair' : 'passed',
    errors:errors.slice(0,64), expected_pairs:expected.size, actual_rows:rows.length,
    missing_pairs:missing.map(p=>JSON.parse(p)), unexpected_pairs:extra.map(p=>JSON.parse(p)),
    semantic_quality:'not_reviewed', formal_publication_verified:false,
    source_content_verified:false};
}

export function checkReport(config: any, packet: any): any {
  const failed = (reason: string) => ({schema_version:1, check:'paper_citation_triage_structure',
    status:'needs_repair', errors:[reason], semantic_quality:'not_reviewed', formal_publication_verified:false});
  if (!packet || !acceptEvidencePacket(packet, config)) return failed('no_current_source_bound_evidence');
  try {
    const bytes = readBoundedFile(join(config.work, 'triage.json'));
    const document = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(bytes));
    const checked = validateTriage(document, packet);
    if (!sourceUnchanged(config)) return failed('source_changed_during_report_check');
    return {...checked, report_sha256:sha256(bytes), source_version:config.source_version};
  } catch (e: any) {
    // Report only bounded error classes, never file contents or arbitrary paths.
    return failed(e instanceof SyntaxError ? 'invalid_json' : 'report_unreadable_or_changed');
  }
}

export function validateCheckConfig(config: any): void {
  if (config?.schema_version !== 1 || !['off','shadow','enforce'].includes(config.mode) ||
      !/^[a-z][a-z0-9_]{1,39}$/.test(config.case_id ?? '') || !config.session_id ||
      !/^[0-9a-f]{64}$/.test(config.source_version ?? '') ||
      !isAbsolute(config.work ?? '') || !isAbsolute(config.source_root ?? '') ||
      resolve(config.work) === resolve(config.source_root) || !plain(config.source_files) ||
      Object.entries(config.source_files).some(([p,h]) => isAbsolute(p) || p.split(/[\\/]/).includes('..') ||
        typeof h !== 'string' || !/^[a-f0-9]{64}$/.test(h)) || !sourceUnchanged(config))
    throw TypeError('Invalid or changed private paper check configuration');
}
