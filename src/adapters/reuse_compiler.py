"""Trace-derived native operators for typed parameter/artifact mediation.

Certification proves schema-valid transport, not scientific correctness or
permission. Each invocation still needs a current semantic selection and goes
through the unchanged native tool guards. No historical argument values ship.
"""
import json
from collections import defaultdict
from pathlib import Path
from jsonschema import Draft202012Validator
from .script_motif_compiler import digest, sha

LOCKS = ['src/adapters/script_learning_store.ts', 'src/adapters/reuse_compiler.py', 'src/adapters/reuse_mediation.ts',
         'src/adapters/probe_motif_compiler.py', 'src/adapters/probe_frontier.ts',
         'src/adapters/script_motif_web.ts', 'src/adapters/script_motif_runtime.ts',
         'src/adapters/script_execution_frontier.ts', 'scripts/compile-reuse-library.py']


def successful(value):
    return isinstance(value, dict) and not value.get('validation_error') and not value.get('error') and not any(
        value.get(k) is False for k in ('exported', 'finalized', 'staged', 'ok', 'success'))


def collect(task):
    task = Path(task)
    cfg = json.loads((task / 'effective-config.json').read_text())
    state = json.loads((task / 'task-state.json').read_text())
    if cfg.get('provider_mode') != 'real' or state.get('status') != 'completed':
        raise ValueError('completed_real_task_required')
    schemas = {t['name']: t['parameters'] for t in cfg['tools'] if t['name'].startswith('mcp__')}
    raw = (task / 'events.jsonl').read_bytes()
    calls, rows, previous = {}, [], None
    for event in map(json.loads, raw.splitlines()):
        data = event.get('data', {})
        if event.get('type') == 'tool/call':
            try:
                args = data['arguments']; args = json.loads(args) if isinstance(args, str) else args
                calls[data['callId']] = (data['name'], args)
            except (KeyError, ValueError):
                continue
        if event.get('type') != 'tool/result':
            continue
        for block in data.get('message', {}).get('content', []):
            call_id = block.get('toolCallId')
            call = calls.pop(call_id, None)
            if not call or block.get('isError'):
                previous = None
                continue
            tool, args = call
            # Synthetic executions validate integration, never independently
            # teach the compiler its own choice was semantically justified.
            if tool not in schemas or str(call_id).startswith(('sss-reuse-', 'sss-script-')):
                previous = None
                continue
            try:
                value = block.get('structuredContent') or json.loads(next(c['text'] for c in block['content'] if c['type'] == 'text'))
                if not successful(value) or list(Draft202012Validator(schemas[tool]).iter_errors(args)):
                    previous = None
                    continue
            except (ValueError, KeyError, StopIteration):
                previous = None
                continue
            edges = []
            if previous:
                for param, target in args.items():
                    # Ambiguous equal literals (0/true/etc.) do not establish a
                    # parameter-flow witness. Learn only substantial values.
                    if len(json.dumps(target, ensure_ascii=False)) < 12:
                        continue
                    matches = [k for k, v in previous['result'].items() if v == target]
                    if len(matches) == 1:
                        edges.append({'from_tool': previous['tool'], 'result_pointer': '/' + matches[0].replace('~', '~0').replace('/', '~1'), 'parameter': param})
            rows.append({'tool': tool, 'schema': schemas[tool], 'edges': edges,
                         'task_id': task.name, 'call_id': call_id, 'events_sha256': sha(raw),
                         'arguments_sha256': digest(args), 'result_sha256': digest(value)})
            previous = {'tool': tool, 'result': value}
    return rows


def compile_library(rows, root, probe_rows=()):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['tool'], digest(row['schema']))].append(row)
    contracts = []
    for (tool, schema_sha), witnesses in sorted(groups.items()):
        if len({w['task_id'] for w in witnesses}) < 2:
            continue
        edges = {}
        for row in witnesses:
            for edge in row['edges']:
                edges.setdefault(digest(edge), (edge, set()))[1].add(row['task_id'])
        contracts.append({'tool': tool, 'schema_sha256': schema_sha,
                          'parameters': list(witnesses[0]['schema'].get('properties', {})),
                          'edges': [e for e, tasks in edges.values() if len(tasks) >= 2],
                          'certification': {'scope': 'schema_validated_real_calls_not_semantic_or_effect_authorization',
                                            'witnesses': [{k: w[k] for k in ('task_id', 'call_id', 'events_sha256', 'arguments_sha256', 'result_sha256')} for w in witnesses]}})
    from .probe_motif_compiler import compile_probes
    body = {'version': 1, 'kind': 'native_reuse_contract_library', 'contracts': contracts, 'probe_contracts': [p for p in compile_probes(probe_rows) if any(c['tool']==p['tool'] and c['schema_sha256']==p['schema_sha256'] for c in contracts)],
            'code_locks': {p: sha((Path(root) / p).read_bytes()) for p in LOCKS},
            'compilation_model_requests': 0}
    return {**body, 'digest': digest(body)}
