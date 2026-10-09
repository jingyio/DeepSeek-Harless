#!/usr/bin/env python3
"""Rebuild and accept the public, historical Motif example without cloud calls."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from src.adapters.dsh_trajectory import (
    extract_dsh_trace, infer_dsh_provenance, mine_witnessed_parameter_edges,
)
from src.adapters.harness_runtime import create_harness
from src.adapters.scenario import prepare_scenario
from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.edge_compiler import (
    compile_witnessed_edge_motif, certify_witnessed_edge_motif,
)
from src.motif_core.offline.library_builder import library_from_certified

BUNDLE = ROOT / 'examples/motif-library/research-portfolio-v1'
CORPUS = ROOT / 'benchmarks/research_decision_portfolio_v1'
PREFIX = 'mcp__research_portfolio_fixture__'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'scripts' / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_integrity(bundle=BUNDLE):
    lock = read(bundle / 'files.lock.json')
    if lock['schema_version'] != 1:
        raise ValueError('unsupported example lock')
    for name, expected in lock['sha256'].items():
        path = (ROOT / name).resolve(strict=True)
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('changed example input: ' + name)


def rebuild(bundle=BUNDLE):
    """Preserve original artifacts; public fixture identities are checked anew."""
    check_integrity(bundle)
    contracts = parse_tool_contracts(read(ROOT / 'config/research-portfolio-tool-contracts.json'))
    traces, identities = [], []
    workspace = ROOT / '.local/motif-example'
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=workspace) as temporary:
        for row in read(bundle / 'provenance.json')['traces']:
            copied = Path(temporary) / row['case']
            shutil.copytree(bundle / 'evidence' / row['case'], copied)
            identity = load_trace_identity(copied / 'task-identity.json', copied / 'events.jsonl', ROOT / '.local')
            identities.append(identity)
            events = [json.loads(line) for line in (copied / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
            traces.append(extract_dsh_trace(events, contracts, trace_id=row['trace_id'],
                task_fingerprint=identity['research_decision_id'],
                provenance_by_call_id=infer_dsh_provenance(events, contracts)))
        require_distinct_decisions(identities)
        artifacts = []
        # Fixture pin_resource is an object lookup, not a same-content read.
        # This contract policy annotates mined edges; it does not prescribe a DAG.
        for candidate in mine_witnessed_parameter_edges(traces[:2]):
            if candidate['to_tool'] == PREFIX + 'pin_resource' and candidate['to_param'] == 'object_id':
                candidate['version_relation'] = 'object_lookup'
            try:
                artifact = certify_witnessed_edge_motif(
                    compile_witnessed_edge_motif(candidate, traces[:2], contracts), traces[2], contracts)
            except ValueError:
                continue  # Unsupported candidates must not enter the executable library.
            artifacts.append(artifact)
    library = library_from_certified(artifacts)
    if library != read(bundle / 'library.json'):
        raise ValueError('recompiled artifacts differ from the historical library')
    manifest = load_script('export-online-motif-manifest.py').export_manifest(
        library, read(ROOT / 'config/research-portfolio-tool-contracts.json'),
        version_fields=read(ROOT / 'config/research-portfolio-online-version-fields.json'))
    if manifest != read(bundle / 'online-manifest.json'):
        raise ValueError('re-exported online manifest differs from the distributed example')
    return library, manifest


async def replay_public_evidence(bundle=BUNDLE):
    """Every shared observation must reproduce through actual scoped MCP calls."""
    calls = 0
    for row in read(bundle / 'provenance.json')['traces']:
        params = StdioServerParameters(command=sys.executable,
            args=[str(CORPUS / 'mock_apps_server.py')], cwd=ROOT,
            env={'SSS_PORTFOLIO_CASE': row['case']})
        events = [json.loads(line) for line in
                  (bundle / 'evidence' / row['case'] / 'events.jsonl').read_text(encoding='utf-8').splitlines()]
        async with Client(params) as client:
            for call, result in zip(events[::2], events[1::2], strict=True):
                data = call['data']
                observed = await client.call_tool(data['name'].removeprefix(PREFIX), json.loads(data['arguments']))
                expected = json.loads(result['data']['message']['content'][0]['content'][0]['text'])
                if observed.is_error or json.loads(observed.content[0].text) != expected:
                    raise ValueError('public MCP observation changed: ' + row['case'])
                calls += 1
    return calls


def tool_observations(messages):
    """Only consume structured MCP JSON from tool messages, never source IDs in prose."""
    values = []
    for message in messages:
        if message.get('role') != 'tool':
            continue
        try:
            value = json.loads(message.get('content', ''))
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def next_fixture_action(values, event_id):
    event = next((value for value in values if value.get('event_id') == event_id), None)
    if event is None:
        return PREFIX + 'read_event', {'event_id': event_id}
    reads = {value['object_id']: value for value in values if isinstance(value.get('value'), dict)}
    pins = {value['object_id']: value for value in values if 'source_id' in value and 'value' not in value}
    dependents = {value['object_id']: value for value in values if isinstance(value.get('claims'), list)}
    wanted = list(event['root_objects'])
    for value in reads.values():
        wanted.extend(value['value'].get('links', []))
    for value in dependents.values():
        wanted.extend(claim['object_id'] for claim in value['claims'])
    for object_id in dict.fromkeys(wanted):
        if object_id not in pins:
            return PREFIX + 'pin_resource', {'object_id': object_id}
        if object_id not in reads:
            return PREFIX + 'read_pinned', {'source_id': pins[object_id]['source_id']}
        if object_id not in dependents:
            return PREFIX + 'find_dependents', {'object_id': object_id}
    return None, {'scope': 'protocol_only', 'read_objects': sorted(reads),
                  'source_versions': {key: reads[key]['version_sha256'] for key in sorted(reads)}}


def provider_handler(event_id):
    class LocalFixtureProvider(BaseHTTPRequestHandler):
        calls = []
        embedding_calls = 0
        failures = []

        def log_message(self, *_args):
            pass

        def do_POST(self):
            try:
                self.respond()
            except Exception as exc:
                self.failures.append(type(exc).__name__ + ': ' + str(exc))
                self.send_error(500)

        def respond(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path == '/v1/embeddings':
                # Transport fixture only; these vectors do not evaluate semantic matching.
                type(self).embedding_calls += 1
                data = {'data': [{'index': i, 'embedding': [1.0, 0.0]} for i in range(len(body['input']))]}
                answer = json.dumps(data).encode()
                self.send_response(200); self.send_header('Content-Type', 'application/json')
            elif self.path == '/v1/chat/completions':
                if len(self.calls) >= 24:
                    raise ValueError('local fixture request limit reached')
                self.calls.append(body)
                tool, args = next_fixture_action(tool_observations(body['messages']), event_id)
                delta = {'role': 'assistant'}
                if tool:
                    delta['tool_calls'] = [{'index': 0, 'id': 'fixture-call-' + str(len(self.calls)),
                        'type': 'function', 'function': {'name': tool, 'arguments': json.dumps(args)}}]
                else:
                    delta['content'] = json.dumps(args, ensure_ascii=False, sort_keys=True)
                base = {'id': 'fixture', 'created': 1, 'model': body['model'], 'object': 'chat.completion.chunk'}
                chunks = [{**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                          {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls' if tool else 'stop'}]}]
                answer = (''.join('data: ' + json.dumps(chunk) + '\n\n' for chunk in chunks) + 'data: [DONE]\n\n').encode()
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
            else:
                raise ValueError('unexpected local endpoint')
            self.send_header('Content-Length', str(len(answer))); self.end_headers(); self.wfile.write(answer)
    return LocalFixtureProvider


def acceptance_run(mode, *, stale=False):
    task = read(BUNDLE / 'task.json')
    task['session_id'] = 'sss-example-' + uuid4().hex
    prepared = prepare_scenario(ROOT / 'scenarios/portfolio-v1/scenario.json', case='l_retrieval_persistence')
    handler = provider_handler('event:l_retrieval_persistence:01')
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/motif-example') as temporary:
        workspace = Path(temporary)
        # Isolate credentials/profile and sessions from the user's normal Harness.
        env = {'DSH_HOME': str(workspace / 'dsh'), 'DEEPSEEK_API_KEY': 'local-fixture-only',
               'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools']),
               'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': ''}
        patches = [prepared['patch']]
        with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            endpoint = f'http://127.0.0.1:{server.server_port}'
            env['DEEPSEEK_BASE_URL'] = endpoint + '/v1'
            try:
                if mode != 'baseline':
                    if stale:
                        task['source_versions'] = {key: '0' * 64 for key in task['source_versions']}
                    task_path = workspace / 'task.json'; save(task_path, task)
                    online = load_script('prepare-online-motif.py').prepare(BUNDLE / 'online-manifest.json', task_path)
                    patches.append(online['patch'])
                    env.update(SSS_ONLINE_MOTIF_MANIFEST=online['manifest'], SSS_ONLINE_MOTIF_TASK=online['task'],
                        SSS_ONLINE_MOTIF_MODE=mode, SSS_MOTIF_EMBEDDING_ENDPOINT=endpoint + '/v1/embeddings',
                        SSS_MOTIF_EMBEDDING_MODEL='fixture-vectors-not-a-semantic-model',
                        SSS_MOTIF_MIN_SIMILARITY='0.8', SSS_MOTIF_MIN_MARGIN='0.1',
                        SSS_ONLINE_MOTIF_PROMPT_SHA256=prepared['prompt_sha256'])
                with create_harness(root=ROOT, patches=tuple(patches), env=env, cwd=temporary,
                    runtime_cwd=temporary, provider='deepseek-official', model='deepseek-flash',
                    max_tokens=1000, request_timeout_seconds=20) as harness:
                    result = harness.run(prepared['prompt'], session_id=task['session_id'])
                if handler.failures or result.finish_reason != 'completed':
                    raise ValueError('local Harness loop failed: ' + str(handler.failures))
                calls = [event for event in result.events if event.get('type') == 'tool/call']
                if not handler.calls or any({tool['function']['name'] for tool in body['tools']} !=
                    set(prepared['allowed_tools']) for body in handler.calls):
                    raise ValueError('Harness offered a different tool surface')
                audit_file = workspace / '.local/online-motif' / (hashlib.sha256(task['session_id'].encode()).hexdigest() + '.jsonl')
                audits = [json.loads(line) for line in audit_file.read_text(encoding='utf-8').splitlines()] if audit_file.exists() else []
                return {'mode': mode, 'stale': stale, 'model_requests': len(handler.calls),
                    'tool_calls': len(calls), 'verified_bypasses': sum(row['kind'] == 'model_request_skipped_verified' for row in audits),
                    'shadow_candidates': sum(row['kind'] == 'shadow_candidate' for row in audits),
                    'embedding_requests': handler.embedding_calls, 'answer': json.loads(result.final_response)}
            finally:
                server.shutdown(); worker.join(timeout=5)


def check_harness():
    rows = [acceptance_run('baseline'), acceptance_run('shadow'),
            acceptance_run('execute'), acceptance_run('execute', stale=True)]
    baseline, shadow, execute, stale = rows
    expected = sorted(read(CORPUS / 'cases/l_retrieval_persistence/sources.json')['objects'])
    if any(row['answer'] != baseline['answer'] or row['answer']['read_objects'] != expected for row in rows):
        raise ValueError('baseline and Motif did not deliver the same fresh fixture evidence')
    if not (execute['verified_bypasses'] > 0 and execute['model_requests'] < baseline['model_requests']
            and shadow['shadow_candidates'] > 0 and shadow['verified_bypasses'] == 0
            and shadow['model_requests'] == baseline['model_requests']
            and stale['verified_bypasses'] == 0 and stale['model_requests'] == baseline['model_requests']):
        raise ValueError('execute/shadow/stale fallback acceptance failed')
    return [{key: value for key, value in row.items() if key != 'answer'} for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=['check', 'rebuild'], default='check')
    args = parser.parse_args()
    library, manifest = rebuild()
    output = ROOT / '.local/motif-example/rebuilt'; output.mkdir(parents=True, exist_ok=True)
    save(output / 'library.json', library); save(output / 'online-manifest.json', manifest)
    result = {'status': 'passed', 'certified_motifs': len(library['artifacts']),
              'library_digest': library['library_digest'], 'rebuilt_output': str(output.relative_to(ROOT)),
              'paid_api_requests': 0, 'reasoning_effort': 'off', 'scope': 'structural_and_protocol_only'}
    if args.action == 'check':
        result['replayed_public_tool_calls'] = asyncio.run(replay_public_evidence())
        result['harness_checks'] = check_harness()
    save(output / 'acceptance.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
