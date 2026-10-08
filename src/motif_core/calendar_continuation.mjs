/** Execute one independently certified Calendar parameter continuation. */

import { createHash, randomUUID } from 'node:crypto';
import { digest, observation, syntheticToolStream } from './online_skill_runtime.mjs';

const FIND = 'mcp__calendar_fixture__find-available-slots';
const VALIDATE = 'mcp__calendar_fixture__validate-slot';
const REQUIRED = ['calendarId', 'timeZone', 'timeWindows', 'durationMinutes',
  'candidateStart', 'candidateEnd'];
const CARRY = ['calendarId', 'timeZone', 'timeWindows', 'durationMinutes'];
const OUTPUT = [['earliest.start', 'candidateStart'], ['earliest.end', 'candidateEnd']];
const SHA = /^[a-f0-9]{64}$/;

function field(value, path) {
  return path.split('.').reduce((row, key) => row && typeof row === 'object'
    ? row[key] : undefined, value);
}

export function validateCalendarArtifact(artifact) {
  if (!artifact || artifact.status !== 'trace_validated_read_only' ||
      !SHA.test(artifact.certified_digest ?? '') ||
      artifact.certified_digest !== digest(Object.fromEntries(
        Object.entries(artifact).filter(([key]) => key !== 'certified_digest'))) ||
      digest(artifact.tools) !== digest([FIND, VALIDATE]) ||
      artifact.source_trace_ids?.length < 2 ||
      artifact.validation_trace_id === undefined ||
      artifact.source_trace_ids.includes(artifact.validation_trace_id) ||
      Object.values(artifact.heldout_guard_checks ?? {}).some((value) => value !== true) ||
      Object.keys(artifact.heldout_guard_checks ?? {}).length !== 5 ||
      artifact.source_guard !== 'sourceSha256_equal_after_live_validation' ||
      digest(artifact.transfer_evidence?.map((row) => [row.from_tool, row.from_field,
        row.to_tool, row.to_param])) !== digest(OUTPUT.map(([from, to]) =>
        [FIND, from, VALIDATE, to])) ||
      digest(artifact.argument_carryover?.map((row) => [row.from_param, row.to_param])) !==
        digest(CARRY.map((param) => [param, param])) ||
      !artifact.transfer_evidence.every((row) =>
        digest(row.supporting_trace_ids) === digest(artifact.source_trace_ids))) {
    throw new TypeError('Calendar Motif lacks unchanged independent evidence');
  }
  return artifact;
}

function exactArguments(anchor, artifact) {
  const args = {};
  for (const row of artifact.argument_carryover) {
    const value = anchor.arguments?.[row.from_param];
    if (value === undefined) return null;
    args[row.to_param] = value;
  }
  for (const edge of artifact.transfer_evidence) {
    const value = field(anchor.output, edge.from_field);
    if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)$/.test(value)) return null;
    args[edge.to_param] = value;
  }
  if (digest(Object.keys(args).sort()) !== digest([...REQUIRED].sort()) ||
      typeof args.calendarId !== 'string' || !args.calendarId ||
      args.timeZone !== 'Asia/Shanghai' ||
      !Array.isArray(args.timeWindows) || args.timeWindows.length < 1 ||
      args.timeWindows.length > 8 ||
      args.timeWindows.some((window) => !window ||
        Object.keys(window).sort().join(',') !== 'end,start' ||
        ['start', 'end'].some((key) => typeof window[key] !== 'string' ||
          !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)$/.test(window[key]))) ||
      !Number.isSafeInteger(args.durationMinutes) ||
      args.durationMinutes < 1 || args.durationMinutes > 480) return null;
  return args;
}

/** The model chooses the calendar/windows first; this only copies witnessed inputs. */
export function createCalendarContinuation({ artifact, sessionId, audit = () => {} }) {
  validateCalendarArtifact(artifact);
  const state = { anchor: null, attempted: false, pending: null, halted: false };
  function observe(exec, result) {
    const output = observation(result, exec.name);
    if (exec.name === FIND) {
      if (state.anchor || state.attempted || !output ||
          !SHA.test(output.sourceSha256 ?? '') ||
          !output.earliest || typeof exec.arguments !== 'object') {
        state.halted = true;
        audit({ kind: 'calendar_anchor_rejected' });
        return;
      }
      state.anchor = { arguments: exec.arguments, output,
        sourceSha256: output.sourceSha256 };
      audit({ kind: 'calendar_anchor_observed', sourceSha256: output.sourceSha256 });
    } else if (state.pending && exec.callId === state.pending.callId) {
      const verified = exec.name === VALIDATE && output?.valid === true &&
        output?.isEarliest === true &&
        output.sourceSha256 === state.anchor.sourceSha256 &&
        digest(exec.arguments) === digest(state.pending.arguments);
      audit({ kind: verified ? 'model_request_skipped_verified' :
        'calendar_source_or_result_changed', sourceSha256: output?.sourceSha256 ?? null });
      state.pending = null;
      if (!verified) state.halted = true;
    } else if (state.anchor && !state.attempted &&
               exec.name !== 'mcp__calendar_fixture__list-events') {
      state.halted = true;
      audit({ kind: 'calendar_interleaving_rejected', tool: exec.name });
    }
  }
  function intercept(options, next) {
    if (options.sessionId !== sessionId || state.halted || !state.anchor ||
        state.attempted || state.pending) return next();
    const offered = options.tools?.find((tool) => tool.name === VALIDATE);
    if (!offered || digest([...(offered.parameters?.required ?? [])].sort()) !==
        digest([...REQUIRED].sort()) ||
        REQUIRED.some((param) => !Object.hasOwn(offered.parameters.properties ?? {}, param))) {
      audit({ kind: 'calendar_schema_changed' });
      return next();
    }
    const args = exactArguments(state.anchor, artifact);
    if (!args) {
      audit({ kind: 'calendar_binding_rejected' });
      return next();
    }
    const callId = `sss-motif-calendar-${randomUUID()}`;
    state.attempted = true;
    state.pending = { callId, arguments: args };
    audit({ kind: 'motif_bypass_attempt', motif_id: artifact.motif_id,
      certified_digest: artifact.certified_digest, tool: VALIDATE,
      selection_basis: 'closed_deterministic_validation', sourceSha256:
      state.anchor.sourceSha256 });
    return syntheticToolStream(callId, { tool: VALIDATE, arguments: args });
  }
  return { observe, intercept, state };
}
