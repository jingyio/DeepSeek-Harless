/** Opt-in artifact checks through public Harness hooks; no new Agent loop.
 * This engineered policy is not counted as a learned Motif or model skip.
 */
import { appendFileSync, mkdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { observation } from '../motif_core/online_skill_runtime.mjs';
import { acceptEvidencePacket, checkReport, readBoundedFile, validateCheckConfig } from './paper_triage_validation.ts';
import { sha256, sourceUnchanged } from './paper_triage_validation.ts';

export const name = 'sss-paper-delivery-check';
export const inject = ['agents', 'tools'];
export const checkToolName = 'check_paper_triage';
const collect = 'mcp__paper_checks__collect_paper_citation_evidence';

export function createDeliveryChecker(config: any, audit: (row: any) => void = () => {}) {
  validateCheckConfig(config);
  let packet: any = null;
  let citations: any = null, records: any = null, preprints: any = null;
  function observe(exec: any, result: any): void {
    if (config.citation_flow === true && exec.name.startsWith('mcp__paper_checks__')) {
      const value = observation(result, exec.name);
      const valid = !result.isError && value?.version_sha256 === config.source_version;
      if (exec.name === 'mcp__paper_checks__pin_paper_citations') {
        packet = citations = records = preprints = null;
      } else if (exec.name === 'mcp__paper_checks__read_pinned_paper_citations') {
        packet = citations = records = preprints = null;
        if (valid && value.case_id === config.case_id && value.source_id === exec.arguments?.source_id)
          citations = value;
      } else if (exec.name === 'mcp__paper_checks__read_pinned_citation_records') {
        packet = records = null;
        if (valid && citations && value.citation_id === citations.citation_id &&
            exec.arguments?.citation_id === citations.citation_id && value.source_id === citations.source_id)
          records = value;
      } else if (exec.name === 'mcp__paper_checks__fetch_pinned_cited_preprint_metadata') {
        packet = preprints = null;
        if (valid && citations && value.citation_id === citations.citation_id &&
            exec.arguments?.citation_id === citations.citation_id) preprints = value;
      } else return;
      if (citations && records && (config.require_preprint_metadata !== true || preprints)) {
        const combined = {schema_version:1,case_id:config.case_id,source_id:citations.source_id,
          citation_id:citations.citation_id,version_sha256:config.source_version,
          scope:'active_manuscript_literal_cite_keys_only',diagnostic:citations.diagnostic,
          references:records,required_reference_pairs:records.required_reference_pairs,
          metadata:preprints?.metadata ?? null};
        if (acceptEvidencePacket(combined,config)) packet = combined;
      }
      audit({kind:'paper_evidence_bound',call_id:exec.callId,valid:packet !== null});
      return;
    }
    if (exec.name !== collect) return;
    // Failed/rejected refresh invalidates cached evidence, never keeps old success.
    packet = null;
    const value = observation(result, exec.name);
    if (exec.arguments?.case_id === config.case_id && acceptEvidencePacket(value, config)) packet = value;
    audit({kind:'paper_evidence_bound', call_id:exec.callId, valid:packet !== null});
  }
  function check(): any { return checkReport(config, packet); }
  function readArtifact(): any {
    if (!packet || !acceptEvidencePacket(packet,config)) throw Error('no_current_source_bound_evidence');
    const bytes = readBoundedFile(join(config.work,'triage.json'));
    const content = new TextDecoder('utf-8',{fatal:true}).decode(bytes);
    if (!sourceUnchanged(config)) throw Error('source_changed_during_artifact_read');
    return {schema_version:1,artifact:'triage.json',report_content:content,report_sha256:sha256(bytes),
      source_version:config.source_version,semantic_quality:'not_reviewed'};
  }
  async function after(exec: any, result: any, next: () => Promise<any>): Promise<any> {
    const decision = await next();
    if (config.mode === 'shadow' && config.read_artifact === true && exec.name === 'edit' && result.isError && decision.kind === 'accept' &&
        typeof exec.arguments?.file_path === 'string' &&
        resolve(config.work,exec.arguments.file_path) === join(config.work,'triage.json') && !exec.signal?.aborted) {
      try { audit({kind:'paper_recovery_snapshot',mode:'shadow',call_id:exec.callId,...readArtifact(),model_requests_skipped:0}); }
      catch { audit({kind:'paper_recovery_snapshot',mode:'shadow',call_id:exec.callId,status:'unavailable',model_requests_skipped:0}); }
    }
    if (config.mode === 'off' || !['write','edit'].includes(exec.name) || result.isError ||
        decision.kind !== 'accept' ||
        typeof exec.arguments?.file_path !== 'string' ||
        resolve(config.work, exec.arguments.file_path) !== join(config.work, 'triage.json')) return decision;
    if (exec.signal?.aborted) return decision;
    const checked = check();
    audit({kind:'paper_delivery_check', mode:config.mode, call_id:exec.callId, ...checked,
           model_requests_skipped:0});
    if (config.mode === 'shadow') return decision;
    const feedback = {type:'text', text:JSON.stringify({runtime_check:checked,
      note:'只检查结构、范围和来源版本；不认证文献判断。原文件已经写入，失败时应修正列出的问题。'})};
    if (checked.status !== 'passed') return {kind:'block', feedback:[feedback],
      ...(decision.additionalContexts ? {additionalContexts:decision.additionalContexts} : {})};
    // Preserve all downstream policy fields. Do not override another policy's value.
    if (Object.hasOwn(decision, 'value')) return decision;
    return {...decision, content:[...(decision.content ?? result.content), feedback]};
  }
  return {observe, check, readArtifact, after};
}

export function apply(ctx: any): void {
  const path = process.env.SSS_PAPER_CHECK_CONFIG;
  if (!path) throw TypeError('Paper delivery checks require explicit private configuration');
  const config = JSON.parse(readBoundedFile(path).toString('utf8'));
  if (resolve(config.work) !== resolve(process.cwd())) throw TypeError('Check workspace differs from Harness workspace');
  const auditFile = join(config.work, '.local', 'paper-delivery-check.jsonl');
  const audit = (row: any) => {
    mkdirSync(join(config.work, '.local'), {recursive:true, mode:0o700});
    appendFileSync(auditFile, JSON.stringify({...row, session_id:config.session_id})+'\n', {mode:0o600});
  };
  ctx.on('agent/created', ({agent}: any) => {
    if (agent.session.id !== config.session_id) return;
    const checker = createDeliveryChecker(config, audit);
    agent.ctx.tools.register({name:checkToolName,
      description:'校验当前任务 triage.json 的 JSON结构、完整覆盖、重复/越界和冻结来源；无需路径或案例参数。不认证文献真实性或版本判断。',
      parameters:{type:'object', properties:{}, additionalProperties:false},
      output:{schema:{type:'object'}, render:(_args: any,value: any)=>[{type:'text',text:JSON.stringify(value)}]},
      async execute(args: any) {
        if (!args || Object.keys(args).length) throw TypeError('This check uses only its registered artifact');
        const result = checker.check();
        audit({kind:'paper_explicit_delivery_check', ...result, model_requests_skipped:0});
        return result;
      }});
    if (config.read_artifact === true) agent.ctx.tools.register({name:'read_current_triage',
      description:'只读取得当前任务triage.json的完整原文及当前版本/摘要，供编辑失败或内容核对时使用；不读取其他文件，不修复报告。',
      parameters:{type:'object',properties:{},additionalProperties:false},
      output:{schema:{type:'object'},render:(_args:any,value:any)=>[{type:'text',text:JSON.stringify(value)}]},
      async execute(args:any) {
        if (!args || Object.keys(args).length) throw TypeError('Only the registered current artifact is readable');
        const result=checker.readArtifact();
        audit({kind:'paper_explicit_artifact_read',...result,model_requests_skipped:0});return result;
      }});
    agent.ctx.on('tools/result', checker.observe);
    agent.ctx.on('tools/post-execute', checker.after);
  });
}
