// Generated from source_dereference.ts; do not edit.
/** An explicit execution capability, independent of a tool's spelling. */







export function validateSourceDereferences(manifest          )       {
  for (const [tool, contract] of Object.entries(manifest.contracts)) {
    if (!Object.hasOwn(contract, 'source_dereference')) continue;
    const paths = manifest.artifacts.filter(a => a.tools.includes(tool));
    if (contract.source_dereference !== true || contract.read_only !== true ||
        contract.required_params.join(',') !== 'source_id' ||
        Object.keys(contract.default_params).length !== 0 ||
        !contract.output_fields.includes('source_id') ||
        manifest.version_fields[tool] !== 'source_version' ||
        Object.keys(manifest.slot_rules[tool] ?? {}).length !== 0 ||
        !paths.length || paths.some(a => {
          const edges = a.transfer_evidence;
          const anchor = a.tools[0];
          return a.tools.length !== 2 || a.tools[1] !== tool ||
            (a.code_nodes ?? []).length !== 0 || edges.length !== 1 ||
            edges[0].from_tool !== anchor || edges[0].to_tool !== tool ||
            edges[0].from_field !== 'source_id' || edges[0].to_param !== 'source_id' ||
            (edges[0].version_relation ?? 'same_source') !== 'same_source' ||
            manifest.version_fields[anchor] !== 'source_version' ||
            !manifest.contracts[anchor].output_fields.includes('source_id');
        })) throw new TypeError('source dereference requires one certified versioned handle edge');
  }
}

export function isSourceDereferenceName(tool        , contract     )          {
  return contract.source_dereference === true ||
    /(?:^|__)read_pinned_[a-z0-9_]+$/.test(tool);
}

/** Keep pin/read observations for the declared sources through bounded batches. */
export function sourceDereferenceHistoryCapacity(task     , manifest          )         {
  let capacity = 12;
  for (const [tool, contract] of Object.entries(manifest.contracts)) {
    if (contract.source_dereference !== true) continue;
    const versions = task.source_versions[tool];
    if (Array.isArray(versions)) capacity = Math.max(capacity, versions.length * 2 + 2);
  }
  return Math.min(64, capacity);
}
