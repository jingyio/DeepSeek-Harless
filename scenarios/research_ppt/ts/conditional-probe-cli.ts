/** 离线认证调用的 JSON 协议探针。不是生产插件/Agent，也不会执行工具。 */
import { proposeConditionalContinuation, validateConditionalCandidate, validateConditionalGuard,
  verifyConditionalResult } from './conditional-continuation.js';
const chunks: Buffer[] = [];
let length = 0;
for await (const chunk of process.stdin) {
  length += Buffer.byteLength(chunk);
  if (length > 2_000_000) throw new TypeError('conditional certification input exceeds bound');
  chunks.push(Buffer.from(chunk));
}
try {
  const request = JSON.parse(Buffer.concat(chunks).toString('utf8'));
  let result: unknown;
  if (request.op === 'validate') {
    validateConditionalCandidate(request.candidate);
    if (request.guard !== undefined) validateConditionalGuard(request.guard);
    result = { valid: true };
  } else if (request.op === 'propose') {
    result = proposeConditionalContinuation({ ...request.input,
      availableTools: new Map(request.input.availableTools), usedPrefixes: new Set(request.input.usedPrefixes ?? []) });
  } else if (request.op === 'verify') {
    result = verifyConditionalResult(request.proposal, request.execution, request.output, request.liveGuard);
  } else throw new TypeError('unknown conditional certification operation');
  process.stdout.write(JSON.stringify({ ok: true, result }) + '\n');
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error_type: error instanceof Error ? error.name : 'invalid_protocol' }) + '\n');
  process.exitCode = 1;
}
