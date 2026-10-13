/** Opt-in delivery receipt gate using the public Harness stop/steer lifecycle. */
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, readFileSync, realpathSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { createUserMessage } from '@deepseek-ai/dsh-llm';

export const name = 'sss-completion-guard';
export const inject = ['agents', 'tools'];
type Policy = { tool: string; statuses: string[]; max_continuations: number; artifact_root: string };
function canonical(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
export const digest = (value: any) => createHash('sha256').update(canonical(value)).digest('hex');
export function validatePolicy(value: any): Policy {
  if (!value || Object.keys(value).some(k => !['tool', 'statuses', 'max_continuations', 'artifact_root'].includes(k))
      || !/^mcp__[a-zA-Z0-9_]+$/.test(value.tool) || !Array.isArray(value.statuses)
      || !value.statuses.length || value.statuses.length > 4
      || value.statuses.some((s: any) => typeof s !== 'string' || !/^[a-z_]{1,40}$/.test(s))
      || !Number.isInteger(value.max_continuations) || value.max_continuations < 0 || value.max_continuations > 2
      || typeof value.artifact_root !== 'string' || !value.artifact_root) throw new TypeError('Invalid completion policy');
  return value;
}

export function createReceiptGuard(policy: Policy, verify = verifyReceipt) {
  validatePolicy(policy);
  let delivered = false, continuations = 0, pending: string[] = [];
  return {
    observe(exec: any, result: any) {
      if (exec.name !== policy.tool || result?.isError === true) return;
      const content = result?.content ?? [];
      const texts = content.filter((b: any) => b.type === 'text').map((b: any) => b.text);
      if (texts.length !== 1 || typeof texts[0] !== 'string') return;
      let receipt: any;
      try { receipt = JSON.parse(texts[0]); } catch { return; }
      if (Array.isArray(receipt.pending_claim_ids)) pending = receipt.pending_claim_ids.filter((x: any) => typeof x === 'string').slice(0, 100);
      if (policy.statuses.includes(receipt.status) && verify(receipt, policy.artifact_root)) delivered = true;
    },
    stop() {
      if (delivered) return null;
      if (continuations >= policy.max_continuations) throw new Error('TASK_MISSING_DELIVERY_RECEIPT: bounded continuation exhausted');
      return { continuation: ++continuations, pending_claim_ids: pending, tool: policy.tool,
        instruction: 'Runtime delivery check: no verified artifact receipt was published. '
          + 'Continue this same frozen task with the permitted tools and remaining budget. '
          + 'Actually read needed evidence and submit to ' + policy.tool + '. '
          + 'A promise to read or final text is not a delivery receipt. Do not guess citation IDs, '
          + 'invent findings, widen targets, or revise already accepted claims. Explicit evidence gaps are allowed.' };
    },
    state: () => ({ delivered, continuations, pending_claim_ids: [...pending] }),
  };
}

export function verifyReceipt(receipt: any, root: string) {
  if (typeof receipt.artifact !== 'string' || !/^[a-f0-9]{64}$/.test(receipt.artifact_sha256)) return false;
  try {
    const path = resolve(receipt.artifact), base = realpathSync(root);
    if (!existsSync(path) || lstatSync(path).isSymbolicLink() || !lstatSync(path).isFile()
        || lstatSync(path).size > 8 * 1024 * 1024 || !realpathSync(path).startsWith(base + sep)) return false;
    return digest(JSON.parse(readFileSync(path, 'utf8'))) === receipt.artifact_sha256;
  } catch { return false; }
}

export function apply(ctx: any, value: Policy) {
  const policy = validatePolicy(value);
  ctx.on('agent/created', ({ agent }: any) => {
    const guard = createReceiptGuard(policy);
    agent.ctx.on('tools/result', (exec: any, result: any) => {
      if (exec.agent && exec.agent !== agent) return;
      guard.observe(exec, result);
    });
    agent.ctx.on('agent/turn-stopping', ({ signal }: any) => {
      if (signal.aborted) return;
      const decision = guard.stop();
      if (!decision) return;
      agent.steer(createUserMessage({ content: [{ type: 'text', text: decision.instruction
        + (decision.pending_claim_ids.length ? '\nPending target IDs: ' + JSON.stringify(decision.pending_claim_ids) : '') }],
        source: { kind: 'task-completion-guard', session_id: agent.session.id,
          continuation: decision.continuation, expected_tool: policy.tool,
          model_requests_skipped_verified: 0 } }));
    });
  });
}
