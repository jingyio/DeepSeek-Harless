"""Compile negative tool patterns from settled real traces, without model calls.

Like motif_core.offline.failure_evolution, historical failures are not permission
to block a new task. The online guard also needs a current failure, an actually
delivered warning, an unchanged binding and a locally verified version anchor.
"""
import json
import re
from collections import defaultdict
from pathlib import Path
from src.adapters.script_motif_compiler import digest, sha

RUNTIME_FILES = ('src/adapters/script_negative_compiler.py',
                 'src/adapters/script_negative_runtime.ts',
                 'src/adapters/script_motif_web.ts')


def leaves(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from leaves(item, (*path, key))
    elif not isinstance(value, list):
        yield list(path), value


def collect_negative(task):
    task = Path(task)
    effective = json.loads((task / 'effective-config.json').read_text())
    state = json.loads((task / 'task-state.json').read_text())
    if effective.get('provider_mode') != 'real' or state.get('status') not in ('completed', 'failed', 'cancelled'):
        raise ValueError('settled_real_trace_required')
    config = json.loads((task / 'model-request-config.json').read_text())
    events_raw = (task / 'events.jsonl').read_bytes()
    calls, rows = {}, []
    for event in map(json.loads, events_raw.splitlines()):
        data = event.get('data', {})
        if event.get('type') == 'tool/call':
            args = data.get('arguments', {})
            try: args = json.loads(args) if isinstance(args, str) else args
            except ValueError: continue
            calls[data['callId']] = (data['name'], args)
        if event.get('type') != 'tool/result': continue
        for block in data.get('message', {}).get('content', []):
            call_id = block.get('toolCallId')
            if call_id not in calls or block.get('isError'): continue
            tool, args = calls.pop(call_id)
            # Shell text, transport failures, opaque errors and negative-guard
            # denials are not promoted to deterministic failure conditions.
            if not tool.startswith('mcp__') or not isinstance(args, dict): continue
            texts = [b.get('text', '') for b in block.get('content', []) if b.get('type') == 'text']
            if len(texts) != 1: continue
            try: value = json.loads(texts[0])
            except ValueError: continue
            if not isinstance(value, dict): continue
            code = value.get('validation_error')
            if code is not None and (not isinstance(code, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_:-]{0,127}', code)):
                continue
            anchors = [(p, v) for p, v in leaves(args) if isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v)]
            echoed = [(p, q) for p, v in anchors for q, w in leaves(value) if v == w]
            rows.append({'tool': tool, 'code': code, 'argument_shape': sorted(args),
                         'false_paths': [p for p, v in leaves(value) if v is False],
                         'anchors': echoed, 'binding_sha256': digest(args),
                         'call_id': call_id, 'task_id': task.name,
                         'events_sha256': sha(events_raw), 'tools_sha256': config['tools_sha256']})
    return rows


def compile_negative(rows, implementation_locks, runtime_locks):
    groups = defaultdict(list)
    for row in rows:
        if row['code']:
            groups[(row['tool'], row['code'], row['tools_sha256'])].append(row)
    rules = []
    for (tool, code, schema), failures in sorted(groups.items()):
        if len({(r['task_id'], r['call_id']) for r in failures}) < 2: continue
        contrasts = [r for r in rows if r['tool'] == tool and r['tools_sha256'] == schema and not r['code']]
        common = set(map(lambda a: json.dumps(a, sort_keys=True), failures[0]['anchors']))
        for row in failures[1:]: common &= {json.dumps(a, sort_keys=True) for a in row['anchors']}
        anchors = [json.loads(a) for a in sorted(common)]
        if len(anchors) > 8: anchors = []  # Oversized bindings stay prompt-only.
        flags = {json.dumps(p) for p in failures[0].get('false_paths', [])}
        for row in failures[1:]: flags &= {json.dumps(p) for p in row.get('false_paths', [])}
        # A flag false in successful calls (e.g. semantic_quality_accepted) is
        # not a failure outcome. Learn the contrast instead of listing tools.
        flags -= {json.dumps(p) for row in contrasts for p in row.get('false_paths', [])}
        failure_flags = [json.loads(p) for p in sorted(flags)][:8]
        rule = {'tool': tool, 'failure_code': code, 'tools_sha256': schema,
                'failure_flags': failure_flags,
                'version_slots': [{'argument_path': a, 'result_path': b} for a, b in anchors],
                'retry_policy': 'warn_then_exact_version_block' if anchors and contrasts and failure_flags else 'prompt_only',
                'certification': {'scope': 'trace_failure_recurrence_and_successful_contrast_not_causal_or_quality_proof',
                    'failures': [{k: r[k] for k in ('task_id', 'call_id', 'events_sha256')} for r in failures],
                    'success_contrasts': [{k: r[k] for k in ('task_id', 'call_id', 'events_sha256')} for r in contrasts]}}
        rule['id'] = 'negative_' + digest(rule)[:16]
        rules.append(rule)
    body = {'kind': 'negative_tool_motif_library', 'version': 1, 'rules': rules[:32],
            'implementation_locks': implementation_locks, 'runtime_locks': runtime_locks,
            'compilation_model_requests': 0}
    return {**body, 'digest': digest(body)}
