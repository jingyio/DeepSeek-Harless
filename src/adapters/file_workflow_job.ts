/** Durable task limits and lifecycle. Fixed file tools may read, never mutate, this ledger. */
import { createHash } from 'node:crypto';
import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, readdirSync,
  renameSync, writeFileSync, lstatSync } from 'node:fs';
import { dirname, join, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

export function canonical(value: any): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
export function digest(value: any): string { return createHash('sha256').update(canonical(value)).digest('hex'); }
const sha = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');
const units = (v: number) => { if (!Number.isFinite(v) || v < 0 || v > 1000) throw Error('invalid cost'); return Math.ceil(v * 1e9); };
const hex = (v: any) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
function writeDurable(path: string, value: any, exclusive = false) {
  const target = exclusive ? path : path + '.tmp';
  const fd = openSync(target, exclusive ? 'wx' : 'w', 0o600);
  try { writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fsyncSync(fd); } finally { closeSync(fd); }
  if (!exclusive) renameSync(target, path);
}
export class FileJob {
  root: string; path: string; events: string;
  constructor(root: string, path: string) {
    this.root = resolve(root); this.path = resolve(path); this.events = this.path + '.events';
    if (!this.path.startsWith(resolve(root, '.local') + sep)) throw Error('job must be private');
    for (let p = this.path; p !== this.root; p = dirname(p)) if (existsSync(p) && lstatSync(p).isSymbolicLink()) throw Error('job symlink refused');
  }
  load(): any {
    const names = readdirSync(this.events).filter(n => /^\d{6}\.json$/.test(n)).sort();
    if (!names.length) throw Error('empty job ledger');
    let prior: string | null = null, state: any;
    for (let i = 0; i < names.length; i++) {
      if (names[i] !== String(i + 1).padStart(6, '0') + '.json') throw Error('job ledger gap');
      const row = JSON.parse(readFileSync(join(this.events, names[i]), 'utf8'));
      const { event_sha256, ...body } = row;
      if (body.sequence !== i + 1 || body.previous_sha256 !== prior || digest(body) !== event_sha256) throw Error('job ledger integrity failed');
      state = body.state; prior = event_sha256;
    }
    if (state.schema_version !== 1 || state.sequence !== names.length || !hex(state.task_sha256) || !hex(state.execution_version_sha256)) throw Error('invalid job state');
    return state;
  }
  commit(state: any, kind: string, detail: any) {
    const sequence = state.sequence + 1;
    const previous = state.sequence ? JSON.parse(readFileSync(join(this.events, String(state.sequence).padStart(6, '0') + '.json'), 'utf8')).event_sha256 : null;
    state.sequence = sequence;
    const body = { sequence, previous_sha256: previous, kind, detail, state };
    mkdirSync(dirname(this.path), { recursive: true, mode: 0o700 }); mkdirSync(this.events, { recursive: true, mode: 0o700 });
    // An existing sequence is a concurrent-writer conflict, never an overwrite.
    writeDurable(join(this.events, String(sequence).padStart(6, '0') + '.json'), { ...body, event_sha256: digest(body) }, true);
    writeDurable(this.path, state);
    return state;
  }
  validateBinding(state: any) {
    if (sha(state.task_file) !== state.task_sha256) throw Error('frozen task/permission changed');
  }
  apply(command: string, arg: any = {}): any {
    if (command === 'init') {
      if (existsSync(this.events) || existsSync(this.path)) throw Error('job already exists; cannot reset');
      const task = resolve(arg.task_file), delivery = resolve(arg.delivery_root);
      if (![task, delivery].every(p => p.startsWith(resolve(this.root, '.local') + sep)) || !hex(arg.execution_version_sha256)) throw Error('invalid job binding');
      const limits = arg.limits;
      const count = (value:any, minimum=1, maximum=100) => value===null || Number.isSafeInteger(value)&&value>=minimum&&value<=maximum;
      if (!limits || !(limits.budget_usd===null || Number.isFinite(limits.budget_usd)&&limits.budget_usd>=0&&limits.budget_usd<=1000)
        || !count(limits.max_requests) || !count(limits.max_steps)
        || !count(limits.max_output,1,393216) || !count(limits.max_repairs,0,2)) throw Error('invalid frozen limits');
      const state = { schema_version: 1, sequence: 0, task_file: task, task_sha256: sha(task), delivery_root: delivery,
        execution_version_sha256: arg.execution_version_sha256, limits, status: 'running', spent_units: 0,
        requests: 0, steps: 0, repairs: 0, checks: 0, pending: {}, accepted: false, motif_disabled: true };
      return { state: this.commit(state, 'initialized', {}) };
    }
    const s = this.load();
    if (command === 'state') return { state: s };
    this.validateBinding(s);
    const running = () => { if (s.status !== 'running') throw Error('job is inactive: ' + s.status); };
    const reached = (field:string,value:number) => s.limits[field]!==null && value>=s.limits[field];
    const costReached = (value:number) => s.limits.budget_usd!==null && value>=Math.floor(s.limits.budget_usd*1e9);
    if (command === 'reserve') {
      const amount = units(arg.upper_usd);
      if (typeof arg.model !== 'string' || !hex(arg.request_sha256)) throw Error('invalid request reservation');
      if (s.status !== 'running' || reached('max_requests',s.requests) || reached('max_steps',s.steps)
        || s.limits.budget_usd!==null && s.spent_units + amount > Math.floor(s.limits.budget_usd * 1e9)) {
        if(s.status==='running' && (reached('max_requests',s.requests)||reached('max_steps',s.steps)||costReached(s.spent_units)))s.status='limit_exhausted';
        this.commit(s, 'request_denied', { reason: 'inactive_or_original_limit' }); return { admitted: false, state: s };
      }
      const id = ++s.requests; s.steps++; s.spent_units += amount;
      s.pending[id] = { amount, model: arg.model, request_sha256: arg.request_sha256 };
      return { admitted: true, request_id: id, state: this.commit(s, 'request_reserved', { id, amount }) };
    }
    if (command === 'settle') {
      const pending = s.pending[arg.request_id];
      if (!pending || pending.model !== arg.model) throw Error('unknown/already settled request');
      const observed = arg.observed_usd === null ? null : units(arg.observed_usd);
      const released = observed === null ? 0 : Math.max(0, pending.amount - observed);
      if (observed !== null) s.spent_units += observed - pending.amount;
      delete s.pending[arg.request_id];
      return { observed_usd: observed === null ? null : observed / 1e9, released_usd: released / 1e9,
        state: this.commit(s, 'request_settled', { request_id: arg.request_id, observed, released }) };
    }
    if (command === 'log') return { state: this.commit(s, 'proxy_accounting', arg) };
    if (command === 'cancel' || command === 'revoke') {
      if (s.status === 'completed') throw Error('completed job cannot be cancelled');
      s.status = command === 'cancel' ? 'cancelled' : 'revoked';
    } else if (command === 'pause') { running(); s.status = 'paused';
    } else if (command === 'resume') {
      if (s.status !== 'paused') throw Error('only an explicitly paused job can resume');
      if (arg.execution_version_sha256 !== s.execution_version_sha256) throw Error('execution version changed');
      s.status = 'running';
    } else if (command === 'begin-check') {
      running(); if (s.limits.max_repairs!==null && s.checks >= s.limits.max_repairs + 1) throw Error('acceptance check limit exhausted');
      const round = s.checks++; return { round, state: this.commit(s, 'acceptance_started', { round }) };
    } else if (command === 'repair') {
      running(); if (reached('max_repairs',s.repairs) || costReached(s.spent_units)
        || reached('max_requests',s.requests) || reached('max_steps',s.steps)) {
          s.status='failed';this.commit(s,'repair_denied',{reason:'original_limit'});throw Error('original repair/budget limit exhausted');
        }
      s.repairs++; s.motif_disabled = true;
    } else if (command === 'accept') { running(); s.accepted = true; s.status = 'completed';
    } else if (command === 'fail') { running(); s.status = 'failed';
    } else throw Error('unknown job command');
    return { state: this.commit(s, command, arg) };
  }
}
const entry = fileURLToPath(import.meta.url);
if (process.argv[1] && resolve(process.argv[1]) === entry) {
  try {
    const root = resolve(dirname(entry), '../..');
    const arg = JSON.parse(readFileSync(0, 'utf8') || '{}');
    process.stdout.write(JSON.stringify(new FileJob(root, process.argv[2]).apply(process.argv[3], arg)) + '\n');
  } catch (error: any) { process.stdout.write(JSON.stringify({ error: error.message }) + '\n'); process.exitCode = 2; }
}
