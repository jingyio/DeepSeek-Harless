"""Trace-derived parameter prototypes for bounded continuation proofs.

Separate from the exact native compiler. Selection of input items is explicit;
the compiler does not infer a scientific decision from adjacent tool calls.
"""
from collections import defaultdict
from pathlib import Path
import json
import re
from urllib.parse import urlsplit, parse_qsl

from .native_motif_compiler import digest, jsonl, root_events


def compile_parameter_library(exp: Path):
    """Legacy frozen five-run interface; preserve its artifact byte semantics."""
    runs = [(exp / 'runs' / f'baseline-{i:02d}', 'training' if i <= 3 else 'heldout')
            for i in range(1, 6)]
    return compile_parameter_runs(runs, source_experiment=exp.name, legacy_root=exp)


def crossref_payload(body):
    try:
        data, _ = json.JSONDecoder().raw_decode(body[body.index('{'):])
        message = data['message']
        if (data.get('status') != 'ok' or not isinstance(message, dict)
                or not isinstance(message.get('items'), list)):
            return None
        # Empty results are an observed lookup miss, not an execution failure.
        if any(not isinstance(row, dict) or not re.fullmatch(r'10\.\d{4,9}/\S+', row.get('DOI', ''), re.I)
               or not isinstance(row.get('title'), list) or not row['title']
               or not all(isinstance(t, str) and t.strip() for t in row['title'])
               for row in message['items']):
            return None
        return data
    except (ValueError, KeyError, TypeError):
        return None


def crossref_prototype(url_string, body):
    """Parameterize a witnessed search URL; constants are learned, not a route."""
    url = urlsplit(url_string)
    if (url.scheme != 'https' or url.netloc != 'api.crossref.org'
            or url.path != '/works' or url.fragment
            or not body.startswith('Fetched ' + url_string + ' (HTTP 200)')
            or crossref_payload(body) is None):
        return None
    pairs = parse_qsl(url.query, keep_blank_values=True)
    args = dict(pairs)
    key = next((k for k in ['query.bibliographic', 'query.title'] if k in args), None)
    allowed = {'DOI', 'title', 'container-title', 'issued', 'author', 'type', 'published', 'URL', 'publisher'}
    if (not key or len(pairs) != len(args) or set(args) != {key, 'rows', 'select'}
            or not re.fullmatch(r'[1-5]', args['rows']) or not 1 <= len(args[key]) <= 512
            or not {'DOI', 'title'} <= set(args['select'].split(',')) <= allowed):
        return None
    proto = {'tool': 'web_fetch', 'contract': 'crossref-search-fetch-v1', 'read_only': True,
             'arguments': {'url': {'base': 'https://api.crossref.org/works', 'query': [
                 {'name': k, **({'slot': 'query'} if k == key else {'value': v})} for k, v in pairs]}}}
    return proto, {'url': url_string, 'query': args[key]}


def compile_parameter_runs(runs, *, source_experiment, legacy_root=None):
    """Compile an explicit split; new callers get strict fresh metadata witnesses."""
    groups = defaultdict(list)
    parallel = defaultdict(list)
    if not runs or any(split not in {'training', 'heldout'} for _, split in runs):
        raise ValueError('explicit training/heldout split required')
    if len({Path(run).resolve() for run, _ in runs}) != len(runs):
        raise ValueError('duplicate or overlapping trace split')
    manifests = {}
    for run, split in runs:
        run = Path(run)
        cfg = json.loads((run / 'manifest.json').read_text())
        manifests[str(run) if legacy_root is None else run.name] = digest(cfg)
        versions = {(r.get('session_id'), r['call_id']): r['snapshot']
                    for r in jsonl(run / 'file-versions.jsonl')} if (run / 'file-versions.jsonl').exists() else {}
        calls = {}
        batch = defaultdict(list)
        for event in root_events(run):
            if event['type'] == 'tool/call':
                data = event['data']
                args = data['arguments']
                calls[data['callId']] = {**data, 'arguments': json.loads(args) if isinstance(args, str) else args}
            if event['type'] != 'tool/result':
                continue
            for block in event['data'].get('message', {}).get('content', []):
                call = calls.get(block.get('toolCallId'))
                if not call or block.get('isError'):
                    continue
                args = call['arguments']
                prototype = None
                dependency = None
                if call['name'] == 'read' and set(args) == {'file_path'}:
                    path = args['file_path']
                    prefix = ('/root/autodl-tmp/jjy/' + str(run.relative_to(legacy_root.parents[2])) + '/work/'
                              if legacy_root is not None else str(run / 'work') + '/')
                    # Permit copied server evidence without changing the old compiler.
                    if path.startswith(prefix):
                        path = path[len(prefix):]
                    elif path.startswith(str(run / 'work') + '/'):
                        path = path[len(str(run / 'work')) + 1:]
                    snap = versions.get((cfg['session_id'], call['callId']))
                    if snap and snap.get('complete') and path in snap['files']:
                        dependency = {'path': path, 'sha256': snap['files'][path]}
                        prototype = {'tool': 'read', 'arguments': {'file_path': {'slot': 'file_path'}},
                                     'contract': 'complete-local-text-read-v1', 'read_only': True}
                elif call['name'] == 'web_fetch' and set(args) == {'url'}:
                    url = urlsplit(args['url'])
                    body = '\n'.join(c.get('text', '') for c in block.get('content', []) if c.get('type') == 'text')
                    match = re.fullmatch(r'/abs/([0-9]{4}\.[0-9]{4,5}(?:v[0-9]+)?)', url.path)
                    if url.scheme == 'https' and url.netloc == 'arxiv.org' and not url.query and not url.fragment and match:
                        prototype = {'tool': 'web_fetch', 'arguments': {'url': {'template': 'https://arxiv.org/abs/{id}'}},
                                     'contract': 'arxiv-page-fetch-v1', 'read_only': True}
                        dependency = {'url': args['url'], 'id': match.group(1)}
                        if legacy_root is None and not (body.startswith('Fetched ' + args['url'] + ' (HTTP 200)')
                                and re.search(r'arXiv:\s*' + re.escape(match.group(1)) + r'(?:v\d+)?(?=[^0-9.]|$)', body)
                                and re.search(r'Title:\s*\S', body) and re.search(r'Authors:\s*\S', body)):
                            prototype = None
                    elif legacy_root is None:
                        found = crossref_prototype(args['url'], body)
                        if found: prototype, dependency = found
                if prototype:
                    key = digest(prototype)
                    groups[key].append({'run_id': run.name, 'session_id': cfg['session_id'],
                                        'call_id': call['callId'], 'step': call.get('step'),
                                        'split': split,
                                        'prototype': prototype, 'dependency': dependency,
                                        'result_sha256': digest(block.get('content', []))})
                    batch[call.get('step')].append(key)
        for step, keys in batch.items():
            for key in set(keys):
                if keys.count(key) >= 2:
                    parallel[key].append({'run_id': run.name, 'step': step, 'width': keys.count(key)})
    motifs = []
    for key, rows in sorted(groups.items()):
        train = [r for r in rows if r['split'] == 'training']
        heldout = [r for r in rows if r['split'] == 'heldout']
        if not train:
            continue
        motifs.append({'motif_id': 'parameter-' + key[:12], 'prototype': train[0]['prototype'],
                       'graph': {'nodes': [{'id': 'collect', 'foreach': 'selected_items', 'prototype': key}],
                                 'join': {'requires': 'all_selected_items', 'then': 'semantic_handoff'}},
                       'training_witnesses': train, 'heldout_witnesses': heldout,
                       'parallel_witnesses': parallel[key],
                       'authorization': 'explicit_versioned_input_binding_only',
                       'status': 'trace_derived_contract_probe',
                       'limitations': ['no automatic semantic selection', 'no historical request saving claim']})
    library = {'schema_version': 1, 'certification_scope': 'parameterized_continuation_probe',
               'motifs': motifs, 'source_experiment': source_experiment,
               'source_hashes': manifests,
               'policy': {'repeat_count_is_confidence_not_authorization': True,
                          'network_result_is_fresh_not_historical_hash': True,
                          'semantic_handoff_required': True}}
    library['manifest_digest'] = digest(library)
    return library
