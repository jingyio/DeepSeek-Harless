/** Scene-local dependency guards. A hand-written policy, not a learned Motif. */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';

type Node = { id: string; kind: string; deps: string[]; version?: string; reviewed?: boolean; source_bound?: boolean };
type Graph = { schema_version: number; nodes: Node[]; reuse_policy?: string };
type Current = { inputs: Record<string, string>; revoked_claim_ids: string[] };

function canonical(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  }
  return JSON.stringify(value);
}
export function hash(value: any): string {
  return createHash('sha256').update(canonical(value)).digest('hex');
}

export function plan(graph: Graph, graphSha: string, current: Current) {
  if (hash(graph) !== graphSha || graph.schema_version !== 1 || !Array.isArray(graph.nodes)
      || graph.nodes.length > 4000 || !current || typeof current.inputs !== 'object'
      || current.inputs === null || Array.isArray(current.inputs) || !Array.isArray(current.revoked_claim_ids)
      || current.revoked_claim_ids.some(id => typeof id !== 'string')) {
    throw new Error('invalid dependency envelope or digest');
  }
  const nodes = new Map<string, Node>();
  const kinds = new Set(['input', 'parse', 'citation', 'claim', 'note', 'synthesis']);
  for (const n of graph.nodes) {
    if (!n || typeof n.id !== 'string' || nodes.has(n.id) || !kinds.has(n.kind)
        || !Array.isArray(n.deps) || n.deps.some(d => typeof d !== 'string')
        || (n.kind === 'input' && (n.deps.length !== 0 || !/^[a-f0-9]{64}$/.test(n.version ?? '')))) {
      throw new Error('invalid or duplicate dependency node');
    }
    nodes.set(n.id, n);
  }
  if (Object.values(current.inputs).some(v => typeof v !== 'string' || !/^[a-f0-9]{64}$/.test(v))) {
    throw new Error('invalid current input version');
  }
  const revoked = new Set(current.revoked_claim_ids);
  for (const id of revoked) if (nodes.get(id)?.kind !== 'claim') throw new Error('unknown revoked claim');
  const states = new Map<string, { id: string; kind: string; reusable_candidate: boolean; reasons: string[] }>();
  const visiting = new Set<string>();
  function visit(id: string): any {
    if (states.has(id)) return states.get(id);
    const n = nodes.get(id);
    if (!n || visiting.has(id)) throw new Error('missing dependency or cycle');
    visiting.add(id);
    let reasons: string[] = [];
    if (n.kind === 'input') {
      if (current.inputs[id] !== n.version) reasons.push(id);
    } else {
      for (const d of n.deps) reasons.push(...visit(d).reasons);
      if (n.kind === 'claim' && (graph.reuse_policy === 'automatic_source_bound_unverified'
          ? n.source_bound !== true : n.reviewed !== true)) reasons.push((graph.reuse_policy === 'automatic_source_bound_unverified'
            ? 'source_binding_missing:' : 'support_review_missing:') + id);
      if (revoked.has(id)) reasons.push('review_revoked:' + id);
      if (n.deps.length === 0) throw new Error('derived node without dependencies');
    }
    const state = { id, kind: n.kind, reusable_candidate: reasons.length === 0,
      reasons: [...new Set(reasons)].sort() };
    visiting.delete(id); states.set(id, state); return state;
  }
  for (const n of graph.nodes) visit(n.id);
  const results = graph.nodes.map(n => states.get(n.id)!);
  return { schema_version: 1, graph_sha256: graphSha, current_sha256: hash(current), nodes: results,
    retained_claim_ids: results.filter(n => n.kind === 'claim' && n.reusable_candidate).map(n => n.id),
    invalidated_claim_ids: results.filter(n => n.kind === 'claim' && !n.reusable_candidate).map(n => n.id),
    scientific_truth_certified: false, learned_motif: false };
}

if (process.argv.includes('--stdio')) {
  try {
    const envelope = JSON.parse(readFileSync(0, 'utf8'));
    process.stdout.write(JSON.stringify(plan(envelope.graph, envelope.graph_sha256, envelope.current)) + '\n');
  } catch (error) {
    process.stderr.write(String(error) + '\n'); process.exitCode = 1;
  }
}
