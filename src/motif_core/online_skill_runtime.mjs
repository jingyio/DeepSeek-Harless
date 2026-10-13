/** Bounded online continuation of independently certified read-only Motifs. */

import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const PURE_CODE_WORKER = fileURLToPath(new URL('./pure_code.py', import.meta.url));

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

export async function runPureCode(expression, input) {
  if (typeof expression !== 'string' || expression.length > 500 ||
      JSON.stringify(input).length > 8000) {
    throw new TypeError('pure code input exceeds the bounded contract');
  }
  const request = JSON.stringify({ expression, input });
  const stdout = await new Promise((resolve, reject) => {
    const child = execFile(process.env.SSS_PURE_CODE_PYTHON ?? 'python3',
      ['-I', '-S', PURE_CODE_WORKER],
      { timeout: 1500, maxBuffer: 4000,
        env: { PYTHONIOENCODING: 'utf-8' } },
      (error, output) => error ? reject(error) : resolve(output));
    child.stdin.end(request);
  });
  const output = JSON.parse(stdout);
  if (!scalar(output?.output)) throw new TypeError('pure code returned no bounded string');
  return output.output;
}

/** Compile witnessed parameter edges into bounded code stored with one skill. */
export function compileLocalPrograms(artifact) {
  const programs = {};
  for (const target of artifact.tools.slice(1)) {
    const steps = artifact.transfer_evidence
      .filter((edge) => edge.to_tool === target)
      .map((edge) => ({ op: 'copy_verified_field',
        from_tool: edge.from_tool, from_field: edge.from_field,
        to_param: edge.to_param }));
    if (steps.length) {
      const body = { language: 'sss-local-ops-v1', target_tool: target, steps };
      programs[target] = { ...body, program_digest: digest(body) };
    }
  }
  return programs;
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
  for (const contract of Object.values(manifest.contracts)) {
    if (!contract || contract.read_only !== true ||
        !Array.isArray(contract.required_params) ||
        !Array.isArray(contract.output_fields) ||
        !contract.default_params || typeof contract.default_params !== 'object') {
      throw new TypeError('online manifest includes a non-read or invalid tool');
    }
  }
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
    const anchor = manifest.contracts[artifact.tools[0]];
    if (artifact.tools.some((tool, index) =>
        manifest.contracts[tool]?.observed_anchor === true && index !== 0)) {
      throw new TypeError('observed anchor must start the Motif');
    }
    if (anchor?.observed_anchor === true &&
        (artifact.tools.length !== 2 ||
         artifact.tools[0] !== 'mcp__scoped_gmail_request__search_emails' ||
         artifact.tools[1] !== 'mcp__scoped_gmail_request__read_email' ||
         !anchor.output_fields.includes('selected_message_id') ||
         manifest.version_fields[artifact.tools[0]] !== 'selected_message_id' ||
         manifest.version_fields[artifact.tools[1]] !== 'source_version' ||
         manifest.contracts[artifact.tools[1]]?.required_params?.join(',') !== 'messageId' ||
         artifact.transfer_evidence.length !== 1 ||
         artifact.transfer_evidence[0].from_field !== 'selected_message_id' ||
         artifact.transfer_evidence[0].to_param !== 'messageId')) {
      throw new TypeError('dynamic Gmail anchor needs one unique read edge');
    }
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
          !manifest.contracts[edge.to_tool].required_params.includes(edge.to_param) ||
          (edge.version_relation !== undefined &&
           edge.version_relation !== 'same_source' &&
           edge.version_relation !== 'object_lookup' &&
           edge.version_relation !== 'lookup_index') ||
          (['object_lookup', 'lookup_index'].includes(edge.version_relation) &&
           (edge.to_param !== 'object_id' ||
            !/(?:^|\.)(?:[a-z][a-z0-9_]*_id)$/.test(edge.from_field) ||
            !manifest.version_fields[edge.to_tool]))) {
        throw new TypeError('online parameter edge is not certified by contracts');
      }
    }
    if (canonical(artifact.local_programs) !==
        canonical(compileLocalPrograms(artifact))) {
      throw new TypeError('Motif local code differs from certified parameter edges');
    }
    const codeNodes = artifact.code_nodes ?? [];
    if (!Array.isArray(codeNodes) || codeNodes.length > 1 ||
        (codeNodes.length && artifact.tools.length !== 2)) {
      throw new TypeError('unsupported dynamic Motif code graph');
    }
    if (codeNodes.length) {
      const node = codeNodes[0];
      const body = Object.fromEntries(['kind', 'language', 'expression',
        'from_tool', 'from_field', 'to_tool', 'to_param']
        .map((key) => [key, node[key]]));
      if (node.kind !== 'pure_code' ||
          node.language !== 'sss-pure-python-expr-v1' ||
          typeof node.expression !== 'string' ||
          !node.expression.length || node.expression.length > 500 ||
          node.from_tool !== artifact.tools[0] ||
          node.to_tool !== artifact.tools[1] ||
          !manifest.contracts[node.from_tool].output_fields.includes(node.from_field) ||
          !manifest.contracts[node.to_tool].required_params.includes(node.to_param) ||
          artifact.transfer_evidence.some((edge) => edge.to_param === node.to_param) ||
          node.program_digest !== digest(body) ||
          node.node_id !== `code_${digest(body).slice(0, 16)}` ||
          canonical(artifact.code_dag) !== canonical({
            nodes: [node.from_tool, node.node_id, node.to_tool],
            edges: [[node.from_tool, node.node_id], [node.node_id, node.to_tool]]
          })) {
        throw new TypeError('dynamic Motif code node differs from certified gap');
      }
    } else if (artifact.code_dag) {
      throw new TypeError('unbound dynamic Motif code graph');
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
    if (!manifest.contracts[tool] ||
        !(scalar(version) || (Array.isArray(version) &&
          version.length > 0 && version.length <= 32 &&
          version.every(scalar) && new Set(version).size === version.length))) {
      throw new TypeError('invalid source version scope');
    }
    if (version === '@observed' &&
        manifest.contracts[tool].observed_anchor !== true) {
      throw new TypeError('observed version needs an approved anchor');
    }
    if (version === '@from_anchor' && !manifest.artifacts.some((artifact) =>
        artifact.tools[1] === tool &&
        manifest.contracts[artifact.tools[0]]?.observed_anchor === true)) {
      throw new TypeError('derived version needs an approved observed anchor');
    }
  }
  if (task.object_versions !== undefined &&
      (!task.object_versions || typeof task.object_versions !== 'object' ||
       Array.isArray(task.object_versions) ||
       Object.keys(task.object_versions).length > 64 ||
       Object.entries(task.object_versions).some(([id, version]) =>
         !/^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[A-Za-z0-9_]+$/.test(id) ||
         !/^[a-f0-9]{64}$/.test(version)))) {
    throw new TypeError('invalid approved object version scope');
  }
  if (task.lookup_versions !== undefined &&
      (!task.lookup_versions || typeof task.lookup_versions !== 'object' ||
       Array.isArray(task.lookup_versions) ||
       Object.entries(task.lookup_versions).some(([tool, scoped]) =>
         !manifest.version_fields[tool] || !scoped ||
         typeof scoped !== 'object' || Array.isArray(scoped) ||
         Object.keys(scoped).length > 64 ||
         Object.entries(scoped).some(([id, version]) =>
           !/^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[A-Za-z0-9_]+$/.test(id) ||
           !/^[a-f0-9]{64}$/.test(version))))) {
    throw new TypeError('invalid approved lookup version scope');
  }
  return task;
}

/** Successful MCP results are the only source of inferred parameter edges. */
export function observation(result, toolName = '') {
  if (result?.isError || result?.value?.isError) return null;
  const value = result?.value ?? result;
  if (value?.structuredContent && typeof value.structuredContent === 'object') {
    return value.structuredContent;
  }
  const text = value?.content?.find((block) => block?.type === 'text')?.text;
  if (typeof text !== 'string') return null;
  if (toolName === 'mcp__scoped_gmail_request__search_emails' ||
      toolName === 'mcp__scoped_gmail_request__read_email') {
    const marker = 'SSS_STRUCTURED_METADATA_V1 ';
    const split = text.indexOf('\n');
    if (split > marker.length && text.startsWith(marker) &&
        text.slice(split + 1).startsWith('<untrusted-tool-output>\n') &&
        text.trimEnd().endsWith('</untrusted-tool-output>')) {
      try {
        const parsed = JSON.parse(text.slice(marker.length, split));
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
      } catch { return null; }
    }
  }
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch { return null; }
}

export async function bindNext(artifact, nextTool, prefix, task, manifest,
                               codeRunner = runPureCode) {
  const params = { ...manifest.contracts[nextTool].default_params };
  for (const param of manifest.contracts[nextTool].required_params) {
    const steps = artifact.local_programs[nextTool]?.steps.filter((step) =>
      step.to_param === param) ?? [];
    const code = artifact.code_nodes?.find((node) =>
      node.to_tool === nextTool && node.to_param === param);
    if (steps.length > 1 || (steps.length && code)) return null;
    const taskValue = task.bindings[nextTool]?.[param];
    if (steps.length === 1) {
      const producer = prefix.find((row) => row.name === steps[0].from_tool);
      const value = field(producer?.output, steps[0].from_field);
      if (!scalar(value) || (taskValue !== undefined && taskValue !== value)) return null;
      params[param] = value;
    } else if (code) {
      const producer = prefix.find((row) => row.name === code.from_tool);
      const input = field(producer?.output, code.from_field);
      if (input === undefined) return null;
      let value;
      try { value = await codeRunner(code.expression, input); }
      catch { return null; }
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
      const steps = artifact.local_programs[tool]?.steps.filter((step) =>
        step.to_param === param) ?? [];
      if (steps.length > 1) return false;
      const expected = steps.length === 1
        ? field(prefix.find((row) => row.name === steps[0].from_tool)?.output,
          steps[0].from_field)
        : task.bindings[tool]?.[param];
      if (expected === undefined && index === 0 && steps.length === 0) {
        // The model already chose and ran the first tool. A successful,
        // version-matched observation may anchor its opaque inputs; they need
        // not have existed when the structured task was created.
        if (!scalar(actual[param])) return false;
      } else if (!scalar(expected) || actual[param] !== expected) return false;
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
      if (!offeredSchemaMatches(availableTools, nextTool, manifest.contracts[nextTool])) {
        continue;
      }
      const args = await bindNext(artifact, nextTool, prefix, task, manifest);
      if (!args) continue;
      candidates.push({ artifact, nextTool, args, length,
        description: artifact.tools.slice(length)
          .map((tool) => manifest.contracts[tool].description).join('\n') });
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

const versionAllowed = (task, manifest, tool, value) => scalar(value) &&
  (task.source_versions[tool] === '@observed' &&
   manifest.contracts[tool]?.observed_anchor === true ? true :
    Array.isArray(task.source_versions[tool])
      ? task.source_versions[tool].includes(value)
      : task.source_versions[tool] === value);

function validObservedAnchor(row) {
  const output = row.output;
  const id = output?.selected_message_id;
  return row.name === 'mcp__scoped_gmail_request__search_emails' &&
    output?.count === 1 && Array.isArray(output.message_ids) &&
    output.message_ids.length === 1 && output.message_ids[0] === id &&
    typeof id === 'string' && /^[0-9a-f]{16,32}$/.test(id) &&
    output.result_digest === createHash('sha256')
      .update(JSON.stringify(output.message_ids)).digest('hex');
}

function matchingPrefixes(artifact, history, length, task, manifest) {
  let partial = [[]];
  for (const tool of artifact.tools.slice(0, length)) {
    const next = [];
    for (const prefix of partial) {
      const after = prefix.length ? prefix.at(-1).historyIndex + 1 : 0;
      for (let index = after; index < history.length; index++) {
        const row = history[index];
        if (row.name === tool && row.ok &&
            row.inputVersion === task.input_version &&
            manifest.version_fields[tool] &&
            versionAllowed(task, manifest, tool, row.sourceVersion) &&
            (manifest.contracts[tool].observed_anchor !== true ||
             validObservedAnchor(row))) {
          next.push([...prefix, { ...row, historyIndex: index }]);
          if (next.length > 128) return [];
        }
      }
    }
    partial = next;
    if (!partial.length) break;
  }
  return partial.filter((prefix) =>
    witnessedPrefix(artifact, prefix, task, manifest) &&
    artifact.transfer_evidence.every((edge) => {
      const from = prefix.find((row) => row.name === edge.from_tool);
      const to = prefix.find((row) => row.name === edge.to_tool);
      if (!from || !to) return true;
      if (edge.version_relation === 'object_lookup') {
        const objectId = field(from.output, edge.from_field);
        return scalar(objectId) && to.arguments?.[edge.to_param] === objectId &&
          task.object_versions?.[objectId] === to.sourceVersion;
      }
      if (edge.version_relation === 'lookup_index') {
        const objectId = field(from.output, edge.from_field);
        return scalar(objectId) && to.arguments?.[edge.to_param] === objectId &&
          task.lookup_versions?.[edge.to_tool]?.[objectId] === to.sourceVersion;
      }
      return from.sourceVersion === to.sourceVersion;
    }));
}

function offeredSchemaMatches(availableTools, tool, contract) {
  const offered = availableTools.get(tool);
  const required = contract.required_params;
  return offered?.parameters?.type === 'object' &&
    Array.isArray(offered.parameters.required ?? []) &&
    // A witnessed operator can require an explicit target even when the API
    // permits an implicit front document. We always supply that bound target.
    // Conversely, every API-required argument must be covered by the operator.
    (offered.parameters.required ?? []).every((param) =>
      required.includes(param) || Object.hasOwn(contract.default_params, param)) &&
    [...required, ...Object.keys(contract.default_params)]
      .every((param) => Object.hasOwn(offered.parameters.properties ?? {}, param));
}

// A model-selected, versioned source can be dereferenced without another
// semantic choice only when the certified edge supplies the entire input.
// Keep this deliberately narrower than a general one-candidate Motif: a
// unique statistic, PDF page, or write action may still encode a decision.
function isClosedSourceRead(row, manifest) {
  const artifact = manifest.artifacts.find((item) => item.motif_id === row.motif_id);
  const contract = manifest.contracts[row.tool];
  const sourceContract = manifest.contracts[artifact?.tools?.[0]];
  const edges = artifact.transfer_evidence.filter((edge) => edge.to_tool === row.tool);
  // A PPT/document pin is a structural source selection already frozen by
  // the task's file hash. Reading the returned source handle is therefore a
  // closed continuation, provided the contract exposes the same provenance
  // fields as the witnessed edge. Keep the naming and shape checks narrow so
  // an arbitrary read tool cannot bypass semantic matching.
  const documentPinRead = /(?:^|__)pin_source$/.test(artifact?.tools?.[0] ?? '') &&
    /(?:^|__)read_source$/.test(row.tool) &&
    sourceContract?.required_params?.length === 1 &&
    sourceContract.required_params[0] === 'document_id' &&
    sourceContract.output_fields?.includes('source_id') &&
    sourceContract.output_fields?.includes('version_sha256');
  return row.version_relation === 'same_source' &&
    row.code_node_ids.length === 0 &&
    contract.read_only === true &&
    contract.required_params.length === 1 &&
    contract.required_params[0] === 'source_id' &&
    Object.keys(contract.default_params).length === 0 &&
    edges.length === 1 && edges[0].to_param === 'source_id' &&
    edges[0].from_field === 'source_id' &&
    (/(?:^|__)read_pinned_[a-z0-9_]+$/.test(row.tool) || documentPinRead);
}

function isClosedUniqueMessageRead(row, manifest) {
  const artifact = manifest.artifacts.find((item) => item.motif_id === row.motif_id);
  return row.version_relation === 'same_source' &&
    row.code_node_ids.length === 0 &&
    manifest.contracts[artifact.tools[0]]?.observed_anchor === true &&
    row.tool === 'mcp__scoped_gmail_request__read_email' &&
    manifest.contracts[row.tool].required_params.join(',') === 'messageId' &&
    Object.keys(manifest.contracts[row.tool].default_params).length === 0 &&
    artifact.transfer_evidence.length === 1 &&
    artifact.transfer_evidence[0].from_field === 'selected_message_id' &&
    artifact.transfer_evidence[0].to_param === 'messageId';
}

// Zotero pins identify either an item or an annotation. The same source_id
// cannot be read through both typed endpoints, even if historical traces
// happened to contain both tool names.
function sourceKindMatches(tool, prefix) {
  const kind = tool === 'mcp__scoped_zotero_read__read_pinned_zotero_item'
    ? 'item' : tool === 'mcp__scoped_zotero_read__read_pinned_zotero_annotation'
      ? 'annotation' : null;
  return kind === null || prefix[0]?.output?.kind === kind;
}

/** Find independent, provenance-bound continuations in interleaved tool history. */
export async function proposeReadyBatch({ manifest, task, history, availableTools,
                                         similarity, minSimilarity, minMargin,
                                         usedPrefixes = new Set(), maxBatch = 8 }) {
  const barrier = history.findLastIndex((row) => row.barrier === true);
  history = history.slice(barrier + 1);
  if (!history.length || typeof similarity !== 'function' ||
      !(minSimilarity >= 0 && minSimilarity <= 1) ||
      !(minMargin >= 0 && minMargin <= 1) ||
      !Number.isSafeInteger(maxBatch) || maxBatch < 1 || maxBatch > 8) return [];
  const candidates = [];
  let codeAttempts = 0;
  for (const artifact of manifest.artifacts) {
    for (let length = 1; length < artifact.tools.length; length++) {
      const nextTool = artifact.tools[length];
      if (!manifest.version_fields[nextTool] ||
          !offeredSchemaMatches(availableTools, nextTool, manifest.contracts[nextTool])) continue;
      for (const prefix of matchingPrefixes(artifact, history, length, task, manifest)) {
        if (!sourceKindMatches(nextTool, prefix)) continue;
        if (artifact.code_nodes?.length && ++codeAttempts > 8) return [];
        const args = await bindNext(artifact, nextTool, prefix, task, manifest);
        if (!args) continue;
        const edges = artifact.transfer_evidence.filter((edge) => edge.to_tool === nextTool);
        const codeNodes = artifact.code_nodes?.filter((node) =>
          node.to_tool === nextTool) ?? [];
        if (!edges.length && !codeNodes.length) continue;
        const versions = new Set([
          ...edges.map((edge) => edge.version_relation === 'object_lookup'
            ? task.object_versions?.[args[edge.to_param]]
            : edge.version_relation === 'lookup_index'
              ? task.lookup_versions?.[nextTool]?.[args[edge.to_param]]
            : prefix.find((row) => row.name === edge.from_tool)?.sourceVersion),
          ...codeNodes.map((node) =>
            prefix.find((row) => row.name === node.from_tool)?.sourceVersion),
        ]);
        if (versions.size !== 1) continue;
        const expectedVersion = [...versions][0];
        if (task.source_versions[nextTool] === '@from_anchor') {
          if (!(length === 1 &&
              manifest.contracts[artifact.tools[0]].observed_anchor === true &&
              edges.length === 1 &&
              (edges[0].version_relation ?? 'same_source') === 'same_source' &&
              expectedVersion === prefix[0].sourceVersion)) continue;
        } else if (!versionAllowed(task, manifest, nextTool, expectedVersion)) continue;
        const lastIndex = prefix.at(-1).historyIndex;
        if (history.slice(lastIndex + 1).some((row) =>
          row.name === nextTool && digest(row.arguments) === digest(args))) continue;
        const prefixKey = digest([artifact.motif_id, nextTool,
          prefix.map((row) => row.callId ?? row.historyIndex)]);
        if (usedPrefixes.has(prefixKey)) continue;
        candidates.push({ motif_id: artifact.motif_id,
          certified_digest: artifact.certified_digest, tool: nextTool,
          arguments: args, expected_version: expectedVersion,
          version_relation: edges.length === 1 ?
            (edges[0].version_relation ?? 'same_source') : 'mixed',
          validation_task_fingerprint: artifact.validation_task_fingerprint,
          prefix_key: prefixKey,
          root_key: String(prefix[0].callId ?? prefix[0].historyIndex),
          prefix_length: length, supporting_task_count: artifact.supporting_task_count,
          code_node_ids: codeNodes.map((node) => node.node_id),
          code_program_digests: codeNodes.map((node) => node.program_digest),
          // Match the task against the certified remaining path. A navigation
          // step alone may say little about the purpose of the read it enables.
          description: artifact.tools.slice(length)
            .map((tool) => manifest.contracts[tool].description).join('\n') });
      }
    }
  }
  if (!candidates.length) return [];
  const roots = new Map();
  for (const candidate of candidates) {
    const rows = roots.get(candidate.root_key) ?? [];
    rows.push(candidate);
    roots.set(candidate.root_key, rows);
  }
  const closedRoots = new Set([...roots.entries()]
    .filter(([, rows]) =>
      (new Set(rows.map((row) => digest([row.tool, row.arguments]))).size === 1 &&
        rows.every((row) => isClosedSourceRead(row, manifest) ||
          isClosedUniqueMessageRead(row, manifest))))
    .map(([root]) => root));
  const query = `${task.intent}\nRecent tools: ${history.slice(-4)
    .map((row) => row.name).join(', ')}`;
  const semanticCandidates = candidates.filter((row) => !closedRoots.has(row.root_key));
  const scores = semanticCandidates.length
    ? await similarity(query, semanticCandidates.map((row) => row.description)) : [];
  if (!Array.isArray(scores) || scores.length !== semanticCandidates.length ||
      scores.some((score) => typeof score !== 'number' || !Number.isFinite(score))) return [];
  let scoreIndex = 0;
  const ranked = candidates.map((row) => {
    const closed = closedRoots.has(row.root_key);
    const similarityScore = closed ? null : scores[scoreIndex++];
    return { ...row, similarity: similarityScore,
    selection_basis: closed ? (isClosedUniqueMessageRead(row, manifest)
      ? 'closed_unique_message_read' : 'closed_source_read') : 'semantic_score',
    score: (closed ? 0.8 : similarityScore * 0.8) +
      Math.min(row.supporting_task_count, 5) / 5 * 0.1 +
      row.prefix_length / manifest.artifacts.find((a) => a.motif_id === row.motif_id).tools.length * 0.1 };
  });
  const byRoot = new Map();
  for (const row of ranked) {
    const group = byRoot.get(row.root_key) ?? [];
    group.push(row);
    byRoot.set(row.root_key, group);
  }
  const selected = [];
  for (const group of byRoot.values()) {
    const alternatives = new Map();
    for (const row of group) {
      const key = digest([row.tool, row.arguments]);
      const prior = alternatives.get(key);
      if (!prior || row.score > prior.score) alternatives.set(key, row);
    }
    const rows = [...alternatives.values()];
    if (rows.length === 1) {
      if (rows[0].selection_basis.startsWith('closed_') ||
          rows[0].similarity >= minSimilarity) selected.push(rows[0]);
      continue;
    }
    // Independently certified object references in one event are sibling
    // reads. Other competing successors may encode a scientific choice.
    if (rows.every((row) => ['object_lookup', 'lookup_index']
        .includes(row.version_relation) && row.similarity >= minSimilarity &&
        row.validation_task_fingerprint === rows[0].validation_task_fingerprint &&
        row.supporting_task_count >= 2)) selected.push(...rows);
  }
  if (!selected.length) return [];
  selected.sort((a, b) => b.score - a.score || a.prefix_key.localeCompare(b.prefix_key));
  // Distinct roots are independent read-only continuations. A batch limit is
  // transport capacity, not semantic ambiguity; execute a stable prefix and
  // reconsider the remaining roots after their results are observed.
  const distinct = [];
  const calls = new Set();
  for (const row of selected) {
    const key = digest([row.tool, row.arguments]);
    if (!calls.has(key)) { distinct.push(row); calls.add(key); }
    if (distinct.length === maxBatch) break;
  }
  return distinct;
}

export function syntheticToolStream(callId, proposal) {
  return syntheticToolStreamBatch([{ callId, proposal }]);
}

export function syntheticToolStreamBatch(calls) {
  if (!Array.isArray(calls) || !calls.length || calls.length > 8) {
    throw new TypeError('synthetic tool batch must contain 1–8 calls');
  }
  return (async function* () {
    // DeepSeek thinking mode requires reasoning_content on every previous
    // assistant turn when tools are present. This is a transparent runtime
    // provenance marker, not fabricated model reasoning.
    const provenance = 'SSS runtime executed certified read-only tool continuations.';
    yield { type: 'block-start', index: 0, blockType: 'reasoning' };
    yield { type: 'reasoning-delta', index: 0, text: provenance };
    yield { type: 'block-end', index: 0,
      block: { type: 'reasoning', text: provenance } };
    for (const [index, { callId, proposal }] of calls.entries()) {
      const args = JSON.stringify(proposal.arguments);
      yield { type: 'block-start', index: index + 1, blockType: 'tool-call' };
      yield { type: 'tool-call-delta', index: index + 1, id: callId,
        name: proposal.tool, argumentsDelta: args };
      yield { type: 'block-end', index: index + 1, block: { type: 'tool-call',
        id: callId, name: proposal.tool, arguments: args } };
    }
    yield { type: 'finish', reason: { kind: 'tool-calls' } };
  })();
}

export { digest };
