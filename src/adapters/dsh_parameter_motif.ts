/** Versioned explicit bindings -> trace-derived independent read/fetch nodes. */
import { readFileSync, realpathSync, appendFileSync, mkdirSync } from 'node:fs';
import { resolve, relative, isAbsolute, join } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { digest, syntheticToolStreamBatch } from '../motif_core/online_skill_runtime.mjs';
import { attachMotifInterceptor } from './dsh_online_motif.mjs';

export const name = 'sss-parameter-motif-probe';
export const inject = ['llm', 'agents'];
const sha = (p: string) => createHash('sha256').update(readFileSync(p)).digest('hex');
const text = (r: any) => (r?.content ?? []).filter((c: any) => c.type === 'text').map((c: any) => c.text).join('\n');
const normalizedQuery = (s: string) => s.normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
function literalTitles(raw: string): string[] {
  const titles: string[] = [];
  for (const m of raw.matchAll(/\btitle\s*=\s*([{\"])/gi)) {
    const opener = m[1], start = m.index! + m[0].length;
    let depth = 1, escaped = false, end = -1;
    for (let i = start; i < raw.length; i++) {
      const c = raw[i];
      if (escaped) { escaped = false; continue; }
      if (c === '\\') { escaped = true; continue; }
      if (opener === '"' && c === '"') { end = i; break; }
      if (opener === '{') { if (c === '{') depth++; if (c === '}' && --depth === 0) { end = i; break; } }
    }
    if (end >= 0) {
      const title = raw.slice(start, end).replace(/[{}]/g, '').replace(/\s+/g, ' ').trim();
      if (title && !title.includes('\\')) titles.push(title);
    }
  }
  return titles;
}
export function crossrefArguments(proto: any, item: any): any {
  const spec = proto.arguments?.url, parts = spec?.query;
  if (spec?.base !== 'https://api.crossref.org/works' || !Array.isArray(parts) || parts.length !== 3 ||
      new Set(parts.map((p: any) => p.name)).size !== 3 || typeof item.query !== 'string' ||
      item.query.length < 1 || item.query.length > 512) throw Error('invalid Crossref contract');
  const slot = parts.filter((p: any) => p.slot === 'query');
  const rows = parts.find((p: any) => p.name === 'rows'), select = parts.find((p: any) => p.name === 'select');
  const allowed = new Set(['DOI', 'title', 'container-title', 'issued', 'author', 'type', 'published', 'URL', 'publisher']);
  if (slot.length !== 1 || !['query.bibliographic', 'query.title'].includes(slot[0].name) ||
      typeof rows?.value !== 'string' || !/^[1-5]$/.test(rows.value) || typeof select?.value !== 'string' ||
      !select.value.split(',').includes('DOI') || !select.value.split(',').includes('title') ||
      select.value.split(',').some((f: string) => !allowed.has(f)) ||
      parts.some((p: any) => Object.keys(p).some(k => !['name', 'slot', 'value'].includes(k)) ||
          (p.slot ? p.slot !== 'query' || p.value !== undefined : p.name !== 'rows' && p.name !== 'select')))
    throw Error('invalid Crossref parameters');
  // Match Python urllib.urlencode, including '*' and '~' (URLSearchParams differs).
  const encode = (s: string) => encodeURIComponent(s).replace(/[!'()*]/g, c => '%' + c.charCodeAt(0).toString(16).toUpperCase()).replace(/%20/g, '+');
  return { url: spec.base + '?' + parts.map((p: any) => encode(p.name) + '=' + encode(p.slot ? item.query : p.value)).join('&') };
}
export function crossrefResult(body: string, url: string): boolean {
  if (!body.startsWith('Fetched ' + url + ' (HTTP 200)') || body.length > 1000000) return false;
  const start = body.indexOf('{'); if (start < 0) return false;
  let depth = 0, quoted = false, escaped = false, end = -1;
  for (let i = start; i < body.length; i++) {
    const c = body[i];
    if (escaped) { escaped = false; continue; }
    if (quoted && c === '\\') { escaped = true; continue; }
    if (c === '"') quoted = !quoted;
    if (!quoted) { if (c === '{') depth++; if (c === '}' && --depth === 0) { end = i + 1; break; } }
  }
  if (end < 0) return false;
  try {
    const data = JSON.parse(body.slice(start, end)), items = data.message?.items;
    return data.status === 'ok' && Array.isArray(items) && items.every((r: any) =>
      r && typeof r.DOI === 'string' && /^10\.\d{4,9}\/\S+$/i.test(r.DOI) &&
      Array.isArray(r.title) && r.title.length && r.title.every((t: any) => typeof t === 'string' && t.trim()));
  } catch { return false; }
}
function local(work: string, value: string): string {
  if (typeof value !== 'string' || isAbsolute(value) || value.split('/').includes('..')) throw Error('external binding');
  const p = realpathSync(resolve(work, value));
  if (relative(work, p).startsWith('..') || isAbsolute(relative(work, p))) throw Error('symlink escape');
  return p;
}
export function completeRead(result: any, path: string): boolean {
  const body = text(result);
  if (!body.includes('<path>' + path + '</path>')) return false;
  const raw = readFileSync(path, 'utf8');
  const expected = raw.replace(/\r\n/g, '\n').replace(/\n$/, '').split('\n');
  const section = body.split('<content>')[1]?.split('</content>')[0];
  if (!section || expected.length > 2000 || raw.length > 100000) return false;
  const rows = [...section.matchAll(/^(\d+): (.*)$/gm)];
  return rows.length === expected.length && rows.every((r, i) => Number(r[1]) === i + 1 && r[2] === expected[i]);
}
export function createParameterInterceptor({ library, work, sessionId, bindingPath, bindingHash, schemaHashes, toolOrder,
                                            mode = 'shadow', audit = () => {}, anchorTool = 'read', boundSources = null }: any): any {
  const unsigned = Object.fromEntries(Object.entries(library).filter(([k]) => k !== 'manifest_digest'));
  if (library.manifest_digest !== digest(unsigned) || library.certification_scope !== 'parameterized_continuation_probe' || !['shadow', 'execute'].includes(mode)) throw Error('invalid parameter library');
  let ready = false, used = false, halted = false, pending: any = null;
  let shadow: any = null;
  const seen = new Set();
  const bindingFile = local(work, bindingPath);
  const currentBinding = () => {
    if (sha(bindingFile) !== bindingHash) throw Error('binding changed');
    const b = JSON.parse(readFileSync(bindingFile, 'utf8'));
    if (!(b.schema_version === 1 || (b.schema_version === 2 && boundSources)) || b.library_digest !== library.manifest_digest || !Array.isArray(b.items) || !b.items.length || b.items.length > 8 || new Set(b.items.map((i: any) => i.item_id)).size !== b.items.length) throw Error('invalid selected input set');
    if (boundSources) b.sources = boundSources;
    for (const s of b.sources ?? []) if (sha(local(work, s.path)) !== s.sha256) throw Error('source changed');
    return b;
  };
  const proposals = () => {
    const b = currentBinding();
    const motif = library.motifs.find((m: any) => m.motif_id === b.motif_id);
    if (!motif?.training_witnesses?.length || motif.authorization !== 'explicit_versioned_input_binding_only') throw Error('unwitnessed motif');
    const proto = motif.prototype;
    return b.items.map((item: any) => {
      if (!item.item_id || typeof item.item_id !== 'string') throw Error('missing item identity');
      if (proto.tool === 'read' && proto.contract === 'complete-local-text-read-v1') {
        const path = local(work, item.file_path);
        if (!/^[a-f0-9]{64}$/.test(item.sha256) || sha(path) !== item.sha256) throw Error('file changed');
        const content = readFileSync(path, 'utf8');
        if (Buffer.byteLength(content) > 100000 || content.replace(/\n$/, '').split('\n').length > 2000) throw Error('read exceeds proof contract');
        return { tool: 'read', arguments: { file_path: path }, item, path };
      }
      if (proto.tool === 'web_fetch' && proto.contract === 'arxiv-page-fetch-v1' && /^[0-9]{4}\.[0-9]{4,5}(v[0-9]+)?$/.test(item.id)) {
        const source = b.sources?.find((s: any) => s.path === item.source_path);
        if (!source) throw Error('missing query provenance');
        const bib = readFileSync(local(work, source.path), 'utf8');
        if (!bib.includes(item.id)) throw Error('identifier not witnessed in source');
        const url = proto.arguments.url.template.replace('{id}', item.id);
        if (url !== 'https://arxiv.org/abs/' + item.id) throw Error('network template changed');
        return { tool: 'web_fetch', arguments: { url }, item };
      }
      if (proto.tool === 'web_fetch' && proto.contract === 'crossref-search-fetch-v1') {
        if (!b.sources?.some((s: any) => s.path === item.source_path)) throw Error('missing query provenance');
        const source = readFileSync(local(work, item.source_path), 'utf8');
        if (typeof item.query !== 'string' || !normalizedQuery(item.query) ||
            !literalTitles(source).some(title => normalizedQuery(title) === normalizedQuery(item.query)))
          throw Error('query not witnessed in source title');
        return { tool: 'web_fetch', arguments: crossrefArguments(proto, item), item, contract: proto.contract };
      }
      throw Error('unsupported parameter contract');
    });
  };
  const resultOK = (p: any, exec: any, result: any) => {
    if (result?.isError || exec.name !== p.tool) return false;
    if (p.tool === 'read') {
      if (Object.keys(exec.arguments ?? {}).some(k => !['file_path', 'offset', 'limit'].includes(k)) || resolve(work, exec.arguments?.file_path ?? '') !== p.path) return false;
    } else if (digest(exec.arguments) !== digest(p.arguments)) return false;
    if (p.tool === 'read') return sha(p.path) === p.item.sha256 && completeRead(result, p.path);
    const body = text(result);
    if (p.contract === 'crossref-search-fetch-v1') return crossrefResult(body, p.arguments.url);
    // Collection certification only: never certify the paper's scientific claim.
    const escaped = p.item.id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return body.startsWith('Fetched ' + p.arguments.url + ' (HTTP 200)') &&
      new RegExp('arXiv:\\s*' + escaped + '(?:v[0-9]+)?(?=[^0-9.]|$)').test(body) &&
      /Title:\s*\S/.test(body) && /Authors:\s*\S/.test(body) &&
      !/Access Denied|Too Many Requests|captcha|403 Forbidden/i.test(body);
  };
  return {
    observe(id: string, exec: any, result: any) {
      if (id !== sessionId) return;
      if (pending?.calls.has(exec.callId)) {
        const p = pending.calls.get(exec.callId);
        let ok = false;
        try { currentBinding(); ok = resultOK(p, exec, result); } catch {}
        pending.failed ||= !ok;
        pending.calls.delete(exec.callId);
        audit({ kind: 'parameter_result', item_id: p.item.item_id, verified: ok, call_id: exec.callId });
        if (!pending.calls.size) {
          audit({ kind: pending.failed ? 'bypass_result_unverified' : 'model_request_skipped_verified', tool_count: pending.width });
          halted ||= pending.failed; pending = null;
        }
        return;
      }
      if (shadow) {
        for (const p of shadow) if (!seen.has(p.item.item_id) && exec.name === p.tool &&
            (p.tool === 'read' ? resolve(work, exec.arguments?.file_path ?? '') === p.path : digest(exec.arguments) === digest(p.arguments))) {
          let ok = false; try { currentBinding(); ok = resultOK(p, exec, result); } catch {}
          seen.add(p.item.item_id); audit({ kind: 'shadow_result', item_id: p.item.item_id, verified: ok });
        }
      }
      if (mode === 'execute' && ready && !used && !pending) {
        try {
          for (const p of proposals()) if (!seen.has(p.item.item_id) && resultOK(p, exec, result)) {
            seen.add(p.item.item_id); audit({ kind: 'native_collection_satisfied', item_id: p.item.item_id });
          }
        } catch {}
      }
      if (exec.name === anchorTool && resolve(work, exec.arguments?.file_path ?? '') === bindingFile && !result?.isError) {
        let reason: string | null = null;
        try { currentBinding(); ready = anchorTool === 'write'
          ? typeof exec.arguments.content === 'string' && exec.arguments.content === readFileSync(bindingFile, 'utf8')
          : completeRead(result, bindingFile); } catch (e: any) { ready = false; reason = e.message; }
        if (ready && mode === 'shadow') { try { shadow = proposals(); } catch (e: any) { ready = false; reason = e.message; } }
        audit({ kind: 'parameter_anchor', verified: ready, ...(reason ? { reason } : {}) });
      }
    },
    async intercept(id: string, request: any, next: any) {
      if (id !== sessionId || !ready || used || halted || pending) return next();
      try {
        const offered = new Map((request.tools ?? []).map((t: any) => [t.name, t]));
        if (digest((request.tools ?? []).map((t: any) => t.name)) !== digest(toolOrder)) throw Error('tool order changed');
        const ps = proposals().filter((p: any) => !seen.has(p.item.item_id));
        if (!ps.length) { used = true; audit({ kind: 'selection_already_satisfied' }); return next(); }
        for (const p of ps) if (digest((offered.get(p.tool) as any)?.parameters) !== schemaHashes[p.tool]) throw Error('tool schema changed');
        used = true;
        audit({ kind: mode === 'shadow' ? 'shadow_candidate' : 'motif_bypass_attempt', tool_count: ps.length,
                motif_id: currentBinding().motif_id, join: 'all_selected_items' });
        if (mode === 'shadow') { shadow = ps; return next(); }
        const calls = ps.map((p: any) => ({ callId: 'sss-parameter-' + randomUUID(), proposal: p }));
        pending = { calls: new Map(calls.map((c: any) => [c.callId, c.proposal])), width: calls.length, failed: false };
        return syntheticToolStreamBatch(calls);
      } catch (e: any) { audit({ kind: 'parameter_deferred', reason: e.message }); halted = true; return next(); }
    },
  };
}
/** Model-authored selection is an authorization proposal, never a learned decision. */
export function createSelectedParameterInterceptor(config: any): any {
  const { work, sessionId, library, catalogPath, catalogHash, bindingPath, audit = () => {} } = config;
  const catalogFile = local(work, catalogPath);
  const plans = new Set<string>();
  let catalogRead = false, active: any = null, outstanding = 0;
  const stableCatalog = () => {
    if (sha(catalogFile) !== catalogHash) throw Error('catalog changed');
    const catalog = JSON.parse(readFileSync(catalogFile, 'utf8'));
    if (catalog.library_digest !== library.manifest_digest) throw Error('catalog library changed');
    for (const s of catalog.sources) if (sha(local(work, s.path)) !== s.sha256) throw Error('catalog source changed');
    return catalog;
  };
  const childAudit = (row: any) => {
    if (row.kind === 'motif_bypass_attempt') outstanding = row.tool_count;
    if (row.kind === 'parameter_result') outstanding--;
    audit(row);
  };
  return {
    observe(id: string, exec: any, result: any) {
      if (id !== sessionId) return;
      active?.observe(id, exec, result);
      const path = resolve(work, exec.arguments?.file_path ?? '');
      if (exec.name === 'read' && path === catalogFile) {
        try { stableCatalog(); catalogRead = !result?.isError && completeRead(result, catalogFile); }
        catch { catalogRead = false; }
        audit({ kind: 'selection_catalog', verified: catalogRead });
      }
      if (exec.name !== 'write' || path !== resolve(work, bindingPath)) return;
      // A new invalid plan must not leave an older shadow/execute plan armed.
      if (outstanding) { audit({ kind: 'selection_deferred', reason: 'pending results' }); return; }
      active = null;
      try {
        if (!catalogRead || result?.isError) throw Error('missing successful catalog/write anchor');
        const catalog = stableCatalog();
        const file = local(work, bindingPath);
        const content = readFileSync(file, 'utf8');
        if (typeof exec.arguments.content !== 'string' || exec.arguments.content !== content) throw Error('write content mismatch');
        const b = JSON.parse(content), key = digest(b);
        if (b.schema_version === 2 && Object.keys(b).some(k => !['schema_version', 'catalog_sha256', 'library_digest', 'motif_id', 'items'].includes(k))) throw Error('unsupported selection field');
        if (plans.has(key)) throw Error('replayed selection');
        if (!((b.schema_version === 1 && digest(b.sources) === digest(catalog.sources)) ||
              (b.schema_version === 2 && b.catalog_sha256 === catalogHash)) || b.library_digest !== library.manifest_digest || !Array.isArray(b.items) || !b.items.length || b.items.length > 8 ||
            new Set(b.items.map((i: any) => i.item_id)).size !== b.items.length) throw Error('invalid selection scope');
        const motif = library.motifs.find((m: any) => m.motif_id === b.motif_id);
        if (!motif) throw Error('unknown selected motif');
        for (const item of b.items) {
          if (motif.prototype.tool === 'read') {
            if (!catalog.read_items.some((allowed: any) => digest(allowed) === digest(item))) throw Error('read outside catalog');
          } else if (motif.prototype.tool === 'web_fetch') {
            const allowedItems = motif.prototype.contract === 'crossref-search-fetch-v1'
              ? (catalog.metadata_query_items ?? []) : catalog.query_items;
            if (!allowedItems.some((allowed: any) => digest(allowed) === digest(item))) throw Error('query outside catalog');
          } else throw Error('unsupported selected tool');
        }
        plans.add(key);
        active = createParameterInterceptor({ ...config, bindingHash: sha(file), anchorTool: 'write', boundSources: catalog.sources, audit: childAudit });
        active.observe(id, exec, result);
        audit({ kind: 'selection_accepted', binding_digest: key, item_ids: b.items.map((i: any) => i.item_id), motif_id: b.motif_id });
      } catch (e: any) { audit({ kind: 'selection_deferred', reason: e.message }); }
    },
    async intercept(id: string, request: any, next: any) {
      // Include all frozen sources at every continuation, not just the selected item.
      try { stableCatalog(); } catch (e: any) {
        active = null; audit({ kind: 'selection_deferred', reason: e.message }); return next();
      }
      return active ? active.intercept(id, request, next) : next();
    },
  };
}
export function apply(ctx: any): void {
  const config = JSON.parse(readFileSync(process.env.SSS_PARAMETER_CONFIG!, 'utf8'));
  const library = JSON.parse(readFileSync(config.library_path, 'utf8'));
  const work = realpathSync(config.work);
  const dir = join(work, '..', 'parameter-motif'); mkdirSync(dir, { recursive: true, mode: 0o700 });
  const audit = (r: any) => appendFileSync(join(dir, 'audit.jsonl'), JSON.stringify(r) + '\n', { mode: 0o600 });
  const factory = config.catalog_path ? createSelectedParameterInterceptor : createParameterInterceptor;
  const interceptor = factory({ library, work, sessionId: config.session_id,
    catalogPath: config.catalog_path, catalogHash: config.catalog_hash,
    bindingPath: config.binding_path, bindingHash: config.binding_hash, schemaHashes: config.schema_hashes,
    toolOrder: config.tool_order, mode: config.mode, audit });
  attachMotifInterceptor(ctx, { task: { session_id: config.session_id }, promptHash: config.prompt_sha256,
    interceptor, audit: (kind: string, reason: string) => audit({ kind, reason }) });
}
