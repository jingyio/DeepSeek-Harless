/** Native request recovery policy; never re-submit a task or a tool call. */
export const WEB_RETRY_POLICY = Object.freeze({
  mode: 'normal' as const,
  // This is a consecutive transient-failure recovery budget, not a task,
  // account, token, cost or total-request cap. Success opens a fresh step.
  maxRetries: 5,
  retryableCodes: Object.freeze(['EMPTY_RESPONSE', 'RATE_LIMIT', 'SERVER', 'TIMEOUT', 'TRANSPORT']),
  backoff: Object.freeze({initialDelayMs: 500, maxDelayMs: 30_000, jitterRatio: 0.2}),
});

/** Classify structured native failures. HTTP 429 alone means rate limiting. */
export function taskFailureStatus(error: unknown): 'budget_exhausted' | 'cancelled' | 'failed' {
  const seen = new Set<unknown>(), pending = [error];
  for (let i=0;i<pending.length && i<8;i++) {
    const value = pending[i] as {code?: unknown; name?: unknown; failure?: unknown; error?: unknown; cause?: unknown};
    if (!value || typeof value !== 'object' || seen.has(value)) continue;
    seen.add(value);
    if (value.code === 'ABORTED' || value.name === 'AbortError') return 'cancelled';
    if (['QUOTA','budget_exhausted','BUDGET_EXHAUSTED','GENELOOP_BUDGET_EXHAUSTED','insufficient_quota','quota_exceeded'].includes(String(value.code))) return 'budget_exhausted';
    // Trust the adapter's explicit transient/permanent classification over
    // diagnostic messages or HTTP numbers embedded in a chained cause.
    if (['RATE_LIMIT','SERVER','TIMEOUT','TRANSPORT','AUTH','INVALID_REQUEST'].includes(String(value.code))) return 'failed';
    for (const nested of [value.failure,value.error,value.cause]) {
      if (nested && typeof nested === 'object' && !seen.has(nested)) pending.push(nested);
    }
  }
  return 'failed';
}
