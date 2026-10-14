/** Diagnostic paper adapter. Reuses the authoritative existing interceptor. */
import { installOnlineMotif } from './dsh_online_motif.mjs';

export const name = 'sss-paper-motif-diagnostic';
export const inject = ['llm', 'agents'];

export async function structuralOnlySimilarity(
  _query: string, _descriptions: string[],
): Promise<number[]> {
  // Any frontier requiring semantic ranking is handed back to the real model.
  // The shared matcher never calls this for a unique closed source read.
  return [];
}

/** Permission predicate, not a workflow: the workflow still comes from traces. */
export function closedCitationBatchRead(row: any, manifest: any): boolean {
  const target = 'mcp__paper_checks__read_pinned_citation_records';
  const parent = 'mcp__paper_checks__read_pinned_paper_citations';
  const artifact = manifest.artifacts.find((a: any) => a.motif_id === row.motif_id);
  const contract = manifest.contracts[target];
  const edges = artifact?.transfer_evidence.filter((e: any) => e.to_tool === target) ?? [];
  return row.tool === target && row.version_relation === 'same_source' &&
    row.code_node_ids?.length === 0 && contract?.read_only === true &&
    contract.required_params?.join(',') === 'citation_id' &&
    Object.keys(contract.default_params ?? {}).length === 0 &&
    edges.length === 1 && edges[0].from_tool === parent &&
    edges[0].from_field === 'citation_id' && edges[0].to_param === 'citation_id' &&
    Object.keys(row.arguments ?? {}).join(',') === 'citation_id' &&
    typeof row.arguments.citation_id === 'string' && /^source-[0-9a-f]{32}$/.test(row.arguments.citation_id);
}

export function apply(ctx: unknown): void {
  if (process.env.SSS_PAPER_MOTIF_DIAGNOSTIC !== '1') {
    throw new TypeError('Paper diagnostic execution requires explicit opt-in');
  }
  installOnlineMotif(ctx, {
    similarity: structuralOnlySimilarity,
    certificationScope: 'protocol_diagnostic',
    closedContinuation: closedCitationBatchRead,
  });
}
