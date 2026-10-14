/** Phase capability boundary, identical for baseline/shadow/execute. */
import { resolve, join } from 'node:path';
import { existsSync, lstatSync } from 'node:fs';

export const name = 'sss-paper-bounded-evidence';
export const inject = ['agents'];
const prefix = 'mcp__paper_checks__';
const names = ['pin_paper_citations','read_pinned_paper_citations','read_pinned_citation_records',
  'fetch_pinned_cited_preprint_metadata'].map(n => prefix + n).concat(['web_fetch','write','edit']);

export function evidencePermission(call: any, work: string, caseId: string, composite = false,
                                   flowChecks = false, artifactRead = false, formal = false, recovery = false): string | undefined {
  const allowed = composite ? [prefix+'collect_paper_citation_evidence', 'web_fetch','write','edit','check_paper_triage'] : [...names];
  if (flowChecks) allowed.push('check_paper_triage');
  if (artifactRead) allowed.push('read_current_triage');
  if (formal) allowed.push(prefix+'fetch_pinned_formal_reference_metadata');
  if (recovery) allowed.push(prefix+'recover_pinned_formal_reference_queries');
  if (!allowed.includes(call.name)) return 'Tool is outside this citation evidence phase';
  if ([prefix+'pin_paper_citations',prefix+'collect_paper_citation_evidence'].includes(call.name) && call.arguments?.case_id !== caseId)
    return `This task may pin only its registered manuscript case. Use case_id=${JSON.stringify(caseId)}.`;
  if (call.name === 'write' || call.name === 'edit') {
    const path = call.arguments?.file_path;
    if (typeof path !== 'string' || resolve(work,path) !== join(work,'triage.json'))
      return 'This phase writes only triage.json in its task workspace';
    if (existsSync(resolve(work,path)) && lstatSync(resolve(work,path)).isSymbolicLink())
      return 'Report symlinks are not permitted';
  }
  return undefined;
}

export function apply(ctx: any): void {
  if (process.env.SSS_PAPER_BOUNDED_EVIDENCE !== '1' || !process.env.SSS_PAPER_CASE_ID)
    throw new TypeError('Bounded citation policy requires explicit phase opt-in');
  const work = resolve(process.cwd()), caseId = process.env.SSS_PAPER_CASE_ID;
  const composite = process.env.SSS_PAPER_COMPOSITE_EVIDENCE === '1';
  const flowChecks = process.env.SSS_PAPER_FLOW_DELIVERY === '1';
  const artifactRead = process.env.SSS_PAPER_ARTIFACT_READ === '1';
  const formal = process.env.SSS_PAPER_FORMAL_METADATA === '1';
  const recovery = Boolean(process.env.SSS_PAPER_QUERY_RECOVERY);
  ctx.on('agent/created', ({ agent }: any) => {
    // The checker is scoped; Harness restrictions filter inherited/global tools.
    const inherited = composite ? [prefix+'collect_paper_citation_evidence','web_fetch','write','edit'] : [...names];
    if (formal) inherited.push(prefix+'fetch_pinned_formal_reference_metadata');
    if (recovery) inherited.push(prefix+'recover_pinned_formal_reference_queries');
    agent.ctx.tools.restrict({ allow: inherited });
    agent.ctx.tools.guard((call: any) => evidencePermission(call,work,caseId,composite,flowChecks,artifactRead,formal,recovery));
  });
}
