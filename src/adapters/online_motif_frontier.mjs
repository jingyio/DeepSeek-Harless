/** Bounded online continuation of independently certified read-only Motifs. */

import { createHash } from 'node:crypto';

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) =>
      `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function digest(value) {
  return createHash('sha256').update(canonical(value)).digest('hex');
}

const scalar = (value) => typeof value === 'string' && value.length > 0 &&
  value.length <= 500 && !/[\x00-\x1f]/.test(value);
const field = (value, path) => path.split('.').reduce((item, part) =>
  item && typeof item === 'object' ? item[part] : undefined, value);

export function validateOnlineManifest(manifest) {
  if (!manifest || manifest.schema_version !== 1 ||
      !/^[a-f0-9]{64}$/.test(manifest.source_library_digest ?? '') ||
      !Array.isArray(manifest.artifacts) || !manifest.artifacts.length ||
      !manifest.contracts || typeof manifest.contracts !== 'object' ||
      !manifest.slot_rules || typeof manifest.slot_rules !== 'object' ||
      !manifest.version_fields || typeof manifest.version_fields !== 'object' ||
      manifest.manifest_digest !== digest(Object.fromEntries(
        Object.entries(manifest).filter(([key]) => key !== 'manifest_digest')))) {
    throw new TypeError('invalid or changed certified online Motif manifest');
  }
  const ids = new Set();
  for (const artifact of manifest.artifacts) {
    if (!scalar(artifact.motif_id) || ids.has(artifact.motif_id) ||
        !/^[a-f0-9]{64}$/.test(artifact.certified_digest ?? '') ||
        !Array.isArray(artifact.tools) || artifact.tools.length < 2 ||
        artifact.tools.length > 12 ||
        new Set(artifact.tools).size !== artifact.tools.length ||
        !Number.isSafeInteger(artifact.supporting_task_count) ||
        artifact.supporting_task_count < 2 ||
        !scalar(artifact.validation_task_fingerprint) ||
        !Array.isArray(artifact.transfer_evidence)) {
      throw new TypeError('online Motif lacks independent read-only evidence');
    }
    ids.add(artifact.motif_id);
    for (const tool of artifact.tools) {
      const contract = manifest.contracts[tool];
      if (!contract || contract.read_only !== true ||
          !Array.isArray(contract.required_params) ||
          !Array.isArray(contract.output_fields) ||
          !contract.default_params || typeof contract.default_params !== 'object' ||
          !scalar(contract.description) || contract.description.length > 160) {
        throw new TypeError('online Motif tool contract is invalid');
      }
    }
    for (const edge of artifact.transfer_evidence) {
      if (!artifact.tools.includes(edge.from_tool) ||
          !artifact.tools.includes(edge.to_tool) ||
          artifact.tools.indexOf(edge.from_tool) >= artifact.tools.indexOf(edge.to_tool) ||
          !manifest.contracts[edge.from_tool].output_fields.includes(edge.from_field) ||
          !manifest.contracts[edge.to_tool].required_params.includes(edge.to_param)) {
        throw new TypeError('online parameter edge is not certified by contracts');
      }
    }
  }
  for (const [tool, params] of Object.entries(manifest.slot_rules)) {
    if (!manifest.contracts[tool] || !params || typeof params !== 'object') {
      throw new TypeError('unknown structured-input slot');
    }
    for (const [param, pattern] of Object.entries(params)) {
      if (!manifest.contracts[tool].required_params.includes(param) ||
          typeof pattern !== 'string' || pattern.length > 120 ||
          /[\n\r]/.test(pattern)) {
        throw new TypeError('invalid structured-input slot pattern');
      }
      new RegExp(`^(?:${pattern})$`, 'u');
    }
  }
  for (const [tool, path] of Object.entries(manifest.version_fields)) {
    if (!manifest.contracts[tool] ||
        !manifest.contracts[tool].output_fields.includes(path)) {
      throw new TypeError('version guard is not an approved output field');
    }
  }
  return manifest;
}

/** Regex only converts explicit identifiers; it never chooses scientific meaning. */
export function parseStructuredTask(raw, manifest) {
  const task = typeof raw === 'string' ? JSON.parse(raw) : raw;
  if (!task || task.schema_version !== 1 || !scalar(task.task_id) ||
      !scalar(task.session_id) ||
      !scalar(task.intent) || task.intent.length > 1000 ||
      !scalar(task.input_version) || !task.bindings ||
      typeof task.bindings !== 'object' || !task.source_versions ||
      typeof task.source_versions !== 'object') {
    throw new TypeError('structured task needs identity, intent, bindings and versions');
  }
  for (const [tool, params] of Object.entries(task.bindings)) {
    if (!manifest.contracts[tool] || !params || typeof params !== 'object') {
      throw new TypeError('task binding names an unknown tool');
    }
    for (const [param, value] of Object.entries(params)) {
      const pattern = manifest.slot_rules[tool]?.[param];
      if (!pattern || !scalar(value) ||
          !new RegExp(`^(?:${pattern})$`, 'u').test(value)) {
        throw new TypeError('task identifier does not match an approved slot');
      }
    }
  }
  for (const [tool, version] of Object.entries(task.source_versions)) {
    if (!manifest.contracts[tool] || !scalar(version)) {
      throw new TypeError('invalid source version scope');
    }
  }
  return task;
}

/** Successful MCP results are the only source of inferred parameter edges. */
export function observation(result) {
  if (result?.isError || result?.value?.isError) return null;
  const value = result?.value ?? result;
  if (value?.structuredContent && typeof value.structuredContent === 'object') {
    return value.structuredContent;
  }
  const text = value?.content?.find((block) => block?.type === 'text')?.text;
  if (typeof text !== 'string') return null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch { return null; }
}

export function bindNext(artifact, nextTool, prefix, task, manifest) {
  const params = { ...manifest.contracts[nextTool].default_params };
  for (const param of manifest.contracts[nextTool].required_params) {
    const edges = artifact.transfer_evidence.filter((edge) =>
      edge.to_tool === nextTool && edge.to_param === param);
    if (edges.length > 1) return null;
    const taskValue = task.bindings[nextTool]?.[param];
    if (edges.length === 1) {
      const producer = prefix.find((row) => row.name === edges[0].from_tool);
      const value = field(producer?.output, edges[0].from_field);
      if (!scalar(value) || (taskValue !== undefined && taskValue !== value)) return null;
      params[param] = value;
    } else if (taskValue !== undefined) {
      params[param] = taskValue;
    } else return null;
  }
  return params;
}

function witnessedPrefix(artifact, prefix, task, manifest) {
  for (let index = 0; index < prefix.length; index++) {
    const tool = artifact.tools[index];
    const actual = prefix[index].arguments;
    if (!actual || typeof actual !== 'object') return false;
    for (const param of manifest.contracts[tool].required_params) {
      const edges = artifact.transfer_evidence.filter((edge) =>
        edge.to_tool === tool && edge.to_param === param);
      if (edges.length > 1) return false;
      const expected = edges.length === 1
        ? field(prefix.find((row) => row.name === edges[0].from_tool)?.output,
          edges[0].from_field)
        : task.bindings[tool]?.[param];
      if (!scalar(expected) || actual[param] !== expected) return false;
    }
    for (const [param, expected] of Object.entries(
      manifest.contracts[tool].default_params)) {
      if (Object.hasOwn(actual, param) && actual[param] !== expected) return false;
    }
  }
  return true;
}

export async function proposeNext({ manifest, task, history, availableTools,
                                    similarity, minSimilarity, minMargin }) {
  if (!history.length || typeof similarity !== 'function' ||
      !(minSimilarity >= 0 && minSimilarity <= 1) ||
      !(minMargin >= 0 && minMargin <= 1)) return null;
  const candidates = [];
  for (const artifact of manifest.artifacts) {
    for (let length = Math.min(history.length, artifact.tools.length - 1);
         length >= 1; length--) {
      const prefix = history.slice(-length);
      if (!prefix.every((row, index) => row.ok &&
          row.name === artifact.tools[index] &&
          !!manifest.version_fields[row.name] &&
          !!task.source_versions[row.name] &&
          row.inputVersion === task.input_version &&
          row.sourceVersion === task.source_versions[row.name])) continue;
      if (!witnessedPrefix(artifact, prefix, task, manifest)) continue;
      const nextTool = artifact.tools[length];
      const offered = availableTools.get(nextTool);
      const required = manifest.contracts[nextTool].required_params;
      if (!offered || offered.parameters?.type !== 'object' ||
          !Array.isArray(offered.parameters.required) ||
          canonical([...offered.parameters.required].sort()) !==
            canonical([...required].sort()) ||
          [...required, ...Object.keys(manifest.contracts[nextTool].default_params)]
            .some((param) => !Object.hasOwn(offered.parameters.properties ?? {}, param))) {
        continue;
      }
      const args = bindNext(artifact, nextTool, prefix, task, manifest);
      if (!args) continue;
      candidates.push({ artifact, nextTool, args, length,
        description: manifest.contracts[nextTool].description });
      break;
    }
  }
  if (!candidates.length) return null;
  const query = `${task.intent}\nRecent tools: ${history.slice(-4).map((row) => row.name).join(', ')}`;
  const scores = await similarity(query, candidates.map((row) => row.description));
  if (!Array.isArray(scores) || scores.length !== candidates.length ||
      scores.some((score) => typeof score !== 'number' || !Number.isFinite(score))) {
    return null;
  }
  const ranked = candidates.map((row, index) => ({ ...row, similarity: scores[index],
    score: scores[index] * 0.8 +
      Math.min(row.artifact.supporting_task_count, 5) / 5 * 0.1 +
      row.length / row.artifact.tools.length * 0.1 }))
    .sort((a, b) => b.score - a.score || a.artifact.motif_id.localeCompare(b.artifact.motif_id));
  const best = ranked[0];
  if (best.similarity < minSimilarity ||
      (ranked.length > 1 && best.score - ranked[1].score < minMargin)) return null;
  return { motif_id: best.artifact.motif_id,
    certified_digest: best.artifact.certified_digest,
    tool: best.nextTool, arguments: best.args, score: best.score,
    similarity: best.similarity, prefix_length: best.length };
}

export function syntheticToolStream(callId, proposal) {
  const args = JSON.stringify(proposal.arguments);
  return (async function* () {
    yield { type: 'block-start', index: 0, blockType: 'tool-call' };
    yield { type: 'tool-call-delta', index: 0, id: callId,
      name: proposal.tool, argumentsDelta: args };
    yield { type: 'block-end', index: 0, block: { type: 'tool-call',
      id: callId, name: proposal.tool, arguments: args } };
    yield { type: 'finish', reason: { kind: 'tool-calls' } };
  })();
}

export { digest };
