/** 与现有 Python node() 一致：stdin JSON、stdout 单条 JSON、格式失败 exit 2。 */
import {readFileSync} from 'node:fs';
import {policyHash, policySchema, validatePolicy} from './layout-policy.js';

function exactKeys(value: Record<string, unknown>, expected: string[]): boolean {
  return Object.keys(value).sort().join(',') === expected.sort().join(',');
}

try {
  const input: unknown = JSON.parse(readFileSync(0, 'utf8'));
  let candidate = input;
  if (input !== null && typeof input === 'object' && !Array.isArray(input) &&
      Object.hasOwn(input, 'action')) {
    const envelope = input as Record<string, unknown>;
    if (envelope.action === 'schema' && exactKeys(envelope, ['action'])) {
      console.log(JSON.stringify({schema: policySchema, validator_version: 'ppt-layout-policy-v1',
        scope: 'layout_parameters_only', certified: false, active: false}));
      process.exit(0);
    }
    if (envelope.action !== 'validate' || !exactKeys(envelope, ['action', 'policy'])) {
      throw new Error('仅支持 schema 和 validate，且不接受额外请求字段');
    }
    candidate = envelope.policy;
  }
  const policy = validatePolicy(candidate);
  // 格式合法不代表视觉质量认证，不产生启用、晋级或写文件副作用。
  console.log(JSON.stringify({valid: true, policy, policy_digest: policyHash(policy), schema: policySchema,
    validator_version: 'ppt-layout-policy-v1', scope: 'layout_parameters_only',
    certified: false, active: false}));
} catch (error) {
  console.log(JSON.stringify({valid: false, certified: false, active: false,
    scope: 'layout_parameters_only', error: error instanceof Error ? error.message : '布局策略校验失败'}));
  process.exitCode = 2;
}
