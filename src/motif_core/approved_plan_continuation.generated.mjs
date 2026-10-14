// Generated from approved_plan_continuation.ts; do not edit.
/** Authority is the frozen caller task + approved contracts + native MCP results.
 * This policy declares a boundary; the parameter chain is independently mined.
 * No document text, similarity score or lone boolean may authorize continuation.
 */
import { createHash } from 'node:crypto';


function canonical(v      )         {
  if (Array.isArray(v)) return `[${v.map(canonical).join(',')}]`;
  if (v && typeof v === 'object') return `{${Object.keys(v).sort()
    .map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}`;
  return JSON.stringify(v);
}
export const policyDigest = (v      )         => createHash('sha256').update(canonical(v)).digest('hex');
const hex = (v      )          => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const keys = (v      , names          )          => !!v && typeof v === 'object' &&
  !Array.isArray(v) && Object.keys(v).sort().join(',') === [...names].sort().join(',');

export function validatePolicy(p      )       {
  if (!keys(p, ['schema_version', 'kind', 'steps']) || p.schema_version !== 1 ||
      p.kind !== 'approved_plan_continuation' || !Array.isArray(p.steps) || p.steps.length !== 3 ||
      new Set(p.steps.map((s      ) => s?.tool)).size !== 3 || p.steps.some((s      ) =>
        !keys(s, ['tool', 'param', 'receipt_field', 'success_status', 'input_schema_sha256']) ||
        typeof s.tool !== 'string' || !s.tool || !hex(s.input_schema_sha256) ||
        ['param', 'receipt_field', 'success_status'].some(k =>
          typeof s[k] !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(s[k])))) {
    throw new TypeError('invalid approved-plan continuation policy');
  }
}

export function validateContinuationManifest(m      )       {
  const hasPolicy = Object.values(m.contracts).some((c      ) => c.continuation_policy !== undefined) ||
    m.artifacts.some((a      ) => a.continuation_policy_digest !== undefined);
  if ((hasPolicy && m.schema_version !== 2) || (!hasPolicy && m.schema_version === 2)) {
    throw new TypeError('continuation policy requires online manifest v2');
  }
  for (const [tool, c] of Object.entries(m.contracts)                    ) {
    if (c.continuation_policy === undefined) continue;
    const p = c.continuation_policy;
    validatePolicy(p);
    const step = p.steps.find((s      ) => s.tool === tool);
    if (!step || c.read_only !== true || c.observed_anchor ||
        canonical(c.required_params) !== canonical([step.param]) ||
        Object.keys(c.default_params).length || !c.output_fields.includes(step.receipt_field) ||
        m.version_fields[tool] !== 'execution_version_sha256') {
      throw new TypeError('continuation conflicts with approved tool contract');
    }
  }
  for (const a of m.artifacts) {
    const p = m.contracts[a.tools[0]]?.continuation_policy;
    if (!a.tools.some((t        ) => m.contracts[t]?.continuation_policy !== undefined) &&
        a.continuation_policy_digest === undefined) continue;
    if (!p || a.continuation_policy_digest !== policyDigest(p) ||
        canonical(a.tools) !== canonical(p.steps.map((s      ) => s.tool)) ||
        a.code_nodes?.length || a.transfer_evidence.length !== 2 ||
        a.tools.some((t        ) => canonical(m.contracts[t]?.continuation_policy) !== canonical(p))) {
      throw new TypeError('continuation lacks a certified complete policy chain');
    }
    for (let i = 1; i < 3; i++) {
      const edges = a.transfer_evidence.filter((e      ) => e.to_tool === a.tools[i]);
      if (edges.length !== 1 || edges[0].from_tool !== a.tools[i - 1] ||
          edges[0].from_field !== p.steps[i - 1].receipt_field ||
          edges[0].to_param !== p.steps[i].param ||
          (edges[0].version_relation ?? 'same_source') !== 'same_source') {
        throw new TypeError('continuation needs fully witnessed receipt parameters');
      }
    }
  }
}

export function validateTaskContinuation(task      , manifest      )       {
  if (task.continuation_policy_digests === undefined) return; // Old task: no grant authority.
  const allowed = new Set(manifest.artifacts.map((a      ) => a.continuation_policy_digest).filter(Boolean));
  const ds = task.continuation_policy_digests;
  if (!Array.isArray(ds) || ds.length > 8 || new Set(ds).size !== ds.length ||
      ds.some((d      ) => !hex(d) || !allowed.has(d))) {
    throw new TypeError('task continuation permission is outside certified scope');
  }
}

export function validGrant(output      , policy      , index        , task      )          {
  const g = output?.continuation_grant;
  const s = policy.steps[index];
  return keys(g, ['schema_version', 'policy_sha256', 'task_input_version', 'execution_version',
    'plan_id', 'completed_steps', 'receipt']) && g.schema_version === 1 &&
    g.policy_sha256 === policyDigest(policy) && task.continuation_policy_digests?.includes(g.policy_sha256) &&
    g.completed_steps === index + 1 && output.status === s.success_status &&
    hex(g.task_input_version) && hex(g.execution_version) &&
    g.task_input_version === task.input_version && output.task_sha256 === g.task_input_version &&
    output.execution_version_sha256 === g.execution_version &&
    typeof g.plan_id === 'string' && /^source-[a-f0-9]{32}$/.test(g.plan_id) &&
    typeof g.receipt === 'string' && /^(?:source|dataset|result)-[a-f0-9]{32}$/.test(g.receipt) &&
    output[s.receipt_field] === g.receipt;
}

export function closedContinuation({ artifact, prefix, task, manifest, availableTools, args, nextTool }      )       {
  const policy = manifest.contracts[artifact.tools[0]]?.continuation_policy;
  if (!policy || !task.continuation_policy_digests?.includes(artifact.continuation_policy_digest)) return null;
  // Bind every actual schema, including the already executed anchor. A change
  // anywhere in the finite permission scope requires fresh certification.
  if (policy.steps.some((s      ) => policyDigest(availableTools.get(s.tool)?.parameters ?? null) !==
      s.input_schema_sha256)) return null;
  if (prefix.some((r      , i        ) => !validGrant(r.output, policy, i, task))) return null;
  const root = prefix[0].output.continuation_grant;
  if (prefix[0].arguments[policy.steps[0].param] !== root.plan_id || prefix.some((r      ) =>
      ['policy_sha256', 'task_input_version', 'execution_version', 'plan_id'].some(k =>
        r.output.continuation_grant[k] !== root[k]))) return null;
  const index = artifact.tools.indexOf(nextTool);
  if (index !== prefix.length || index < 1 || index > 2 ||
      !keys(args, [policy.steps[index].param]) ||
      args[policy.steps[index].param] !== prefix.at(-1).output.continuation_grant.receipt) return null;
  return { policy, index, root };
}

export function verifyContinuationResult(expected      , output      , task      )          {
  return validGrant(output, expected.policy, expected.index, task) &&
    ['policy_sha256', 'task_input_version', 'execution_version', 'plan_id'].every(k =>
      output.continuation_grant[k] === expected.root[k]);
}
