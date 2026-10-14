/** Bounded postcondition repair in the original Harness session and budget. */
import { createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join, resolve, sep } from 'node:path';
import { createUserMessage } from '@deepseek-ai/dsh-llm';

export const name = 'sss-acceptance-guard';
export const inject = ['agents', 'tools'];
type Policy = { kind: 'file_management'; max_repairs: number; project_root: string;
  python: string; task_file: string; delivery_root: string; archive_root: string };
export function validatePolicy(p: any): Policy {
  if (!p || Object.keys(p).sort().join(',') !== 'archive_root,delivery_root,kind,max_repairs,project_root,python,task_file'
      || p.kind !== 'file_management' || !Number.isInteger(p.max_repairs) || p.max_repairs < 0 || p.max_repairs > 2
      || ['project_root','python','task_file','delivery_root','archive_root'].some(k => typeof p[k] !== 'string' || !p[k]))
    throw new TypeError('Invalid bounded acceptance policy');
  const base = resolve(p.project_root, '.local') + sep;
  if ([p.task_file, p.delivery_root, p.archive_root].some(x => !resolve(x).startsWith(base)))
    throw new TypeError('Acceptance files must stay in the project private directory');
  return p;
}
export function createAcceptanceGuard(policy: Policy, evaluate: (round: number, receipt: any, events: any[], signal: AbortSignal) => Promise<any>) {
  validatePolicy(policy);
  let repairs = 0, checks = 0, receipt: any = null, accepted = false;
  return {
    observe(exec: any, result: any) {
      accepted = false;
      if (exec.name !== 'mcp__file_management__submit_report' || result?.isError) return;
      try {
        const text = result.content?.filter((x: any) => x.type === 'text');
        if (text?.length === 1) receipt = JSON.parse(text[0].text);
      } catch { /* Invalid receipts are rejected by the fixed verifier. */ }
    },
    async stop(events: any[], signal: AbortSignal) {
      if (signal.aborted || accepted) return null;
      const result = await evaluate(checks++, receipt, events, signal);
      if (signal.aborted) return null;
      if (result?.fatal === true || typeof result?.passed !== 'boolean' || !Array.isArray(result?.errors))
        throw new Error('TASK_ACCEPTANCE_VERIFIER_FAILED');
      if (result.passed) { accepted = true; return null; }
      if (result.repairable === false) throw new Error('TASK_ACCEPTANCE_NOT_REPAIRABLE: ' + JSON.stringify(result.errors));
      if (repairs >= policy.max_repairs) throw new Error('TASK_ACCEPTANCE_FAILED: bounded repair exhausted');
      return { repair: ++repairs, errors: result.errors,
        instruction: '任务程序验收未通过。现在关闭本会话全部Motif自动执行，使用普通DeepSeek Harness修复同一个原任务。'
          + '原权限、工具、任务目标、验收口径和剩余预算均不变，不得请求扩大权限、重启任务、清空记录或绕过校验。'
          + '先核对read_task/list_files和已有操作回执；只修正失败内容，必要时使用已有授权的restore_plan，再正确执行。'
          + '修复后必须再次submit_report；系统会按同一口径复验。不得把失败描述成成功。'
          + '\n程序诊断：' + JSON.stringify(result.errors).slice(0, 12000) };
    },
    state: () => ({ repairs, checks, accepted }),
  };
}
function verifier(policy: Policy, sessionId: string, taskSha: string) {
  const archive = join(policy.archive_root, createHash('sha256').update(sessionId).digest('hex'));
  return (round: number, receipt: any, events: any[], signal: AbortSignal) => new Promise<any>((accept, reject) => {
    const child = spawn(policy.python, [join(policy.project_root, 'scripts/validate-file-delivery.py'),
      '--task-file', policy.task_file, '--task-sha256', taskSha, '--delivery-root', policy.delivery_root,
      '--archive-root', archive, '--round', String(round)],
      { cwd: policy.project_root, env: process.env, stdio: ['pipe','pipe','pipe'], signal });
    let stdout = '', stderr = '';
    const timer = setTimeout(() => { child.kill(); reject(new Error('Acceptance verifier timeout')); }, 30000);
    child.stdout.setEncoding('utf8'); child.stderr.setEncoding('utf8');
    child.stdout.on('data', value => { stdout += value; if (stdout.length > 1024 * 1024) child.kill(); });
    child.stderr.on('data', value => { stderr = (stderr + value).slice(-4000); });
    child.on('error', error => { clearTimeout(timer); reject(error); });
    child.on('close', code => {
      clearTimeout(timer);
      try { const value = JSON.parse(stdout); if (code !== 0 && !value.fatal) throw Error(stderr); accept(value); }
      catch { reject(new Error('Acceptance verifier failed: ' + stderr)); }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify({ receipt, events }));
  });
}
export function apply(ctx: any, value: Policy) {
  const policy = validatePolicy(value);
  const taskSha = createHash('sha256').update(readFileSync(policy.task_file)).digest('hex');
  const histories = new Map<string, any[]>();
  ctx.on('session/event', (session: any, event: any) => {
    const events = histories.get(session.id); if (events) events.push(event);
  }, { global: true });
  ctx.on('agent/created', ({ agent }: any) => {
    const events: any[] = []; histories.set(agent.session.id, events);
    const guard = createAcceptanceGuard(policy, verifier(policy, agent.session.id, taskSha));
    agent.ctx.on('tools/result', (exec: any, result: any) => {
      if (!exec.agent || exec.agent === agent) guard.observe(exec, result);
    });
    agent.ctx.on('agent/turn-stopping', async ({ signal }: any) => {
      let decision;
      try { decision = await guard.stop(events, signal); } catch (error) { if (signal.aborted) return; throw error; }
      if (decision) agent.steer(createUserMessage({ content: [{ type: 'text', text: decision.instruction }],
        source: { kind: 'task-acceptance-repair', session_id: agent.session.id, repair: decision.repair,
          mode: 'ordinary_harness', max_repairs: policy.max_repairs, model_requests_skipped_verified: 0 } }));
    });
  });
}
