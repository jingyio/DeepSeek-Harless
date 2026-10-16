#!/usr/bin/env python3
"""Recompile witnessed old paper-flow predictions for the current MCP surface.

The output is a private, shadow-only sidecar for the shared online interceptor.
It neither imports old execution permissions nor certifies a model skip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.native_motif_compiler import digest

P = 'mcp__paper_checks__'
CURRENT = {
    P + 'pin_paper_citations': 'case_id',
    P + 'read_pinned_paper_citations': 'source_id',
    P + 'read_pinned_citation_records': 'citation_id',
    P + 'fetch_pinned_cited_preprint_metadata': 'citation_id',
    P + 'fetch_pinned_formal_reference_metadata': 'citation_id',
    P + 'recover_pinned_formal_reference_queries': 'citation_id',
}
REPORT = {
    'paper-flow-1254fc79a35f': 'stage_then_finalize',
    'paper-flow-e4d6cba4afc9': 'stage_then_finalize',
    'paper-flow-f813f5b15671': 'failed_finalize_requires_model_repair',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_file(root: Path, relative: str, expected: str) -> None:
    path = root / relative
    if path.is_symlink() or not path.is_file() or sha(path) != expected:
        raise ValueError('paper_flow_training_source_changed')


def compile_bridge(old_path: Path, runs: Path, schemas_path: Path, output: Path) -> dict:
    private = (ROOT / '.local').resolve()
    old_path, runs, schemas_path = [p.resolve(strict=True) for p in (old_path, runs, schemas_path)]
    output = output.resolve()
    if (any('.local' not in p.parts for p in (old_path, runs, schemas_path)) or
            not output.is_relative_to(private)):
        raise ValueError('paper flow bridge stays in private .local')
    if output.exists(): raise FileExistsError(output)
    old = json.loads(old_path.read_text())
    body = {k: v for k, v in old.items() if k != 'manifest_digest'}
    if (old.get('schema_version') != 1 or old.get('scope') != 'source_bound_readonly_batch_shadow'
            or old.get('execution_policy') != 'shadow_only' or digest(body) != old.get('manifest_digest')):
        raise ValueError('invalid old paper flow library')
    if len(old.get('source_traces', {})) < 3 or len(old.get('motifs', [])) != 9:
        raise ValueError('incomplete old paper flow training')
    for run_id, trace in old['source_traces'].items():
        if Path(run_id).name != run_id: raise ValueError('invalid source trace name')
        source = runs / run_id
        checked_file(source, 'session-events.jsonl', trace['events_sha256'])
        checked_file(source, 'manifest.json', trace['manifest_sha256'])
        for request, expected in trace['requests'].items():
            if Path(request).name != request: raise ValueError('invalid request trace name')
            checked_file(source, 'requests/' + request, expected)
    schema = json.loads(schemas_path.read_text())
    approved = json.loads((ROOT / 'scenarios/paper_proofreading/scenario.json').read_text())['allowed_tools']
    if (not isinstance(schema, list) or
            sorted(row['name'] for row in schema) != sorted(approved)):
        raise ValueError('complete current paper MCP schema required')
    current = {row['name']: row['parameters'] for row in schema}
    for tool in CURRENT:
        if tool not in current or digest(current[tool]) != old['tool_schema_sha256'].get(tool):
            raise ValueError('paper flow tool parameter schema changed')
    candidates = []
    report = []
    for motif in old['motifs']:
        graph = motif['graph']
        if (motif['motif_id'] != 'paper-flow-' + digest(graph)[:12]
                or not motif['training_witnesses'] or motif['training_session_count'] !=
                len({row['session_id'] for row in motif['training_witnesses']})):
            raise ValueError('old paper flow graph or witness changed')
        for witness in motif['training_witnesses']:
            source = old['source_traces'].get(witness['run_id'])
            if not source or source['session_id'] != witness['session_id']:
                raise ValueError('unbound old paper flow witness')
        if motif['motif_id'] in REPORT:
            report.append({'legacy_motif_id': motif['motif_id'],
                           'current_mapping': REPORT[motif['motif_id']],
                           'execution_policy': 'model_owned_report_write'})
            continue
        if (graph['anchor_result'] not in ('success', 'task_start') or
                len(graph['nodes']) != 1 or graph.get('artifact') is not None or
                any(name not in CURRENT for name in graph['anchor']) or
                graph['nodes'][0]['tool'] not in CURRENT):
            raise ValueError('unexpected old paper flow candidate')
        node = graph['nodes'][0]
        if sorted(node['bindings']) != [CURRENT[node['tool']]]:
            raise ValueError('paper flow binding shape changed')
        param = CURRENT[node['tool']]
        binding = node['bindings'][param]
        if 'task_field' in binding:
            if (node['tool'] != P + 'pin_paper_citations' or graph['anchor'] or
                    graph['anchor_result'] != 'task_start' or binding != {'task_field': 'case_id'}):
                raise ValueError('paper flow task binding changed')
        elif (not isinstance(binding.get('source_fields'), list) or not binding['source_fields'] or
              any(row.get('tool') not in graph['anchor'] or row.get('field') != param
                  for row in binding['source_fields'])):
            raise ValueError('paper flow source binding changed')
        candidates.append({'motif_id': motif['motif_id'], 'graph': graph,
                           'training_session_count': motif['training_session_count'],
                           'witness_count': len(motif['training_witnesses'])})
    if len(candidates) != 6 or len(report) != 3:
        raise ValueError('old paper flow migration count changed')
    result = {'schema_version': 1, 'kind': 'paper_flow_current_shadow',
              'execution_policy': 'shadow_only', 'scene': 'paper-proofreading',
              'old_library_sha256': sha(old_path),
              'current_tool_schemas_sha256': sha(schemas_path),
              'tool_schema_hashes': {tool: digest(current[tool]) for tool in sorted(CURRENT)},
              'source_trace_hashes': {name: row['events_sha256'] for name, row in old['source_traces'].items()},
              'candidates': candidates, 'report_migrations': report,
              'limitations': ['same-paper training variants', 'shadow prediction only',
                              'report writes and external identity judgments remain model-owned']}
    result['manifest_digest'] = digest(result)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    output.chmod(0o600)
    return {'shadow_candidates': len(candidates), 'report_migrations': len(report),
            'manifest_digest': result['manifest_digest'], 'model_requests': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('old-library', 'training-runs', 'schemas', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compile_bridge(args.old_library, args.training_runs, args.schemas, args.output)))
