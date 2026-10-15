"""Learn local, observer-triggered continuations from normal paper traces.

Only the *read-only check* is a candidate node. Its write/edit antecedent stays
model-owned. Output is a shadow probe, never an execution certificate. Tool
contracts are engineering inputs; edges and their witnesses come from traces.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath

from .native_motif_compiler import digest, jsonl, root_events

CHECK = 'check_paper_triage'
COLLECT = 'mcp__paper_checks__collect_paper_citation_evidence'
VALIDATOR_FILES = ('src/adapters/paper_triage_validation.ts',
                   'src/adapters/dsh_paper_delivery_check.ts',
                   'schemas/paper-citation-triage.schema.json')


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_path(value, work):
    """Normalize only the registered artifact, never arbitrary private paths."""
    if not isinstance(value, str) or '\\' in value or '\x00' in value:
        return None
    path = PurePosixPath(value)
    if '..' in path.parts:
        return None
    if path.is_absolute():
        try:
            path = path.relative_to(PurePosixPath(work))
        except ValueError:
            return None
    return str(path) if str(path) == 'triage.json' else None


def arguments(value):
    value = json.loads(value) if isinstance(value, str) else value
    if not isinstance(value, dict):
        raise ValueError('object tool arguments required')
    return value


def check_value(block):
    try:
        parts = block['content']
        if len(parts) != 1 or parts[0]['type'] != 'text':
            return None
        value = json.loads(parts[0]['text'])
        if (value.get('check') != 'paper_citation_triage_structure'
                or value.get('status') not in {'passed', 'needs_repair'}
                or value.get('semantic_quality') != 'not_reviewed'):
            return None
        for field in ('report_sha256', 'source_version'):
            if not isinstance(value.get(field), str) or len(value[field]) != 64 or any(
                    c not in '0123456789abcdef' for c in value[field]):
                return None
        return value
    except (ValueError, KeyError, TypeError):
        return None


def training_trace(run):
    run = Path(run)
    config = json.loads((run/'manifest.json').read_text())
    metrics = json.loads((run/'metrics.json').read_text())
    check_config = json.loads((run/'delivery-check-config.json').read_text())
    if (config['mode'] != 'baseline' or config['delivery_check_mode'] != 'off'
            or not config['composite_evidence'] or metrics['status'] != 'completed'
            or not all(metrics.get(k) is True for k in
                       ('source_unchanged', 'output_coverage_valid', 'delivery_check_passed'))
            or check_config['session_id'] != config['session_id']
            or check_config['source_version'] != config['input_version']):
        raise ValueError('completed normal baseline with frozen provenance required')
    receipts = sorted((run/'requests').glob('*.json'))
    events = root_events(run)
    if len(receipts) != metrics['actual_requests'] or len(
            [e for e in events if e['type'] == 'assistant/message']) != len(receipts):
        raise ValueError('request boundary mismatch')
    schemas = None
    for path in receipts:
        row = json.loads(path.read_text())
        current = {t['function']['name']: digest(t['function']['parameters']) for t in row['tools']}
        if schemas is not None and current != schemas:
            raise ValueError('tool schema changed within training run')
        schemas = current
    if not schemas or not {CHECK, 'write', 'edit', COLLECT} <= schemas.keys():
        raise ValueError('registered artifact tool contracts missing')
    return config, check_config, schemas, events, receipts


def compile_paper_shadow(runs):
    """Freeze candidates without reading evaluation traces or fitting text rules."""
    paths = [Path(p).resolve() for p in runs]
    if not paths or len(set(paths)) != len(paths) or len({p.name for p in paths}) != len(paths):
        raise ValueError('distinct named training runs required')
    groups, sources, sessions = defaultdict(list), {}, set()
    validator = None
    common_schemas = None
    for run in paths:
        config, check_config, schemas, events, receipts = training_trace(run)
        session = config['session_id']
        if session in sessions:
            raise ValueError('same session is not an independent training run')
        sessions.add(session)
        code = {p: config['code_sha256'][p] for p in VALIDATOR_FILES}
        if validator is not None and code != validator or common_schemas is not None and schemas != common_schemas:
            raise ValueError('training validator or tool contract drift')
        validator, common_schemas = code, schemas
        sources[run.name] = {'session_id': session, 'input_version': config['input_version'],
            'manifest_sha256': file_hash(run/'manifest.json'),
            'events_sha256': file_hash(run/'session-events.jsonl'),
            'requests': {p.name: file_hash(p) for p in receipts}}
        calls, declared = {}, {}
        ordinal, preceding, current, bound = 0, None, None, False
        for event in events:
            data = event.get('data', {})
            if event['type'] == 'assistant/message':
                ordinal += 1
                preceding, current = current, None
                tools = [b for b in data['message']['content'] if b.get('type') == 'tool-call']
                declared = {b['id']: (b['name'], arguments(b['arguments'])) for b in tools}
            elif event['type'] == 'tool/call':
                args = arguments(data['arguments'])
                if data['callId'] in calls or declared.get(data['callId']) != (data['name'], args):
                    raise ValueError('tool call identity differs from its model request')
                calls[data['callId']] = {**data, 'arguments': args, 'ordinal': ordinal,
                                         'preceding': preceding, 'declared_count': len(declared)}
            elif event['type'] == 'tool/result':
                for block in data.get('message', {}).get('content', []):
                    call = calls.get(block.get('toolCallId'))
                    if not call:
                        continue
                    ok = not data.get('error') and not block.get('isError')
                    if call['name'] == COLLECT:
                        # A failed refresh cannot leave an earlier binding alive.
                        try:
                            packet = json.loads(block['content'][0]['text'])
                            bound = bool(ok and packet['case_id'] == check_config['case_id']
                                         and packet['version_sha256'] == config['input_version'])
                        except (ValueError, KeyError, TypeError):
                            bound = False
                        current = None
                    elif call['name'] in {'write', 'edit'}:
                        current = None
                        if (ok and bound and call['declared_count'] == 1 and artifact_path(
                                call['arguments'].get('file_path'), check_config['work'])):
                            current = call
                    elif call['name'] == CHECK:
                        anchor = call['preceding']
                        value = check_value(block) if ok else None
                        if (anchor and call['declared_count'] == 1 and call['arguments'] == {}
                                and value and value['source_version'] == config['input_version']):
                            # For writes, the later check must refer to exactly the bytes generated.
                            if anchor['name'] == 'write' and hashlib.sha256(
                                    anchor['arguments']['content'].encode()).hexdigest() != value['report_sha256']:
                                continue
                            groups[anchor['name']].append({'run_id': run.name, 'session_id': session,
                                'anchor_call_id': anchor['callId'], 'check_call_id': call['callId'],
                                'anchor_request': anchor['ordinal'], 'check_request': call['ordinal'],
                                'input_version': config['input_version'],
                                'report_sha256': value['report_sha256'], 'check_status': value['status']})
                    else:
                        # Unknown interleaving is not silently folded into a continuation.
                        current = None
    motifs = []
    for tool, witnesses in sorted(groups.items()):
        graph = {'anchor': {'tool': tool, 'ownership': 'model', 'result': 'success',
                            'artifact_binding': 'arguments.file_path'},
                 'continuation': {'tool': CHECK, 'arguments': {}, 'read_only': True},
                 'artifact_role': 'registered_triage_report', 'artifact_relative_path': 'triage.json',
                 'handoff': 'after_check_or_any_guard_failure'}
        support = len({w['session_id'] for w in witnesses})
        motifs.append({'motif_id': 'paper-shadow-'+digest(graph)[:12], 'graph': graph,
                       'training_witnesses': witnesses, 'training_session_count': support,
                       'support': 'repeated_trace' if support >= 2 else 'single_trace_candidate',
                       'status': 'shadow_candidate_not_execution_certified'})
    library = {'schema_version': 1, 'scope': 'artifact_continuation_shadow_probe',
        'execution_policy': 'shadow_only', 'motifs': motifs, 'source_traces': sources,
        'tool_schema_sha256': common_schemas, 'validator_code_sha256': validator,
        'limitations': ['same-paper drafts are not independent paper decisions',
                        'engineering contracts, trace-derived local edges',
                        'no learned semantic repair, no automatic execution',
                        'all text remains excluded from strict whole-request counts']}
    library['manifest_digest'] = digest(library)
    return library
