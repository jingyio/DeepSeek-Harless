"""Synthetic Harness/MCP/Motif/budget acceptance; no cloud or user-app access."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.error
import urllib.request
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from mcp import Client, StdioServerParameters
from src.adapters.deepseek_cost_gate import State, create_server
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance, mine_witnessed_parameter_edges
from src.adapters.harness_runtime import create_harness
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.scenario import prepare_scenario
from src.adapters.task_identity import load_trace_identity, require_distinct_decisions
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.edge_compiler import compile_witnessed_edge_motif, certify_witnessed_edge_motif
from src.motif_core.offline.library_builder import library_from_certified

PREFIX = 'mcp__literature_notes__'
TRAIN = ('train_seed', 'train_protocol')
CERTIFY = 'certify_cost'
EVALUATE = 'eval_leakage'


def module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


SCENE = module(HERE / 'server.py', 'literature_scene')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    path.chmod(0o600)


def runtime_snapshot():
    """Bind diagnostics to actual runtime versions and scene source bytes."""
    return {'platform': platform.platform(), 'python': platform.python_version(),
            'node': subprocess.check_output(['node', '--version'], text=True).strip(),
            'sdk': importlib.metadata.version('deepseek-harness-sdk'),
            'mcp': importlib.metadata.version('mcp'),
            'dsh': read(ROOT / 'node_modules/@deepseek-ai/dsh/package.json')['version'],
            'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'git_status': subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).splitlines(),
            'scene_sha256': {str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in sorted(HERE.rglob('*'))
                             if path.is_file() and path.suffix in {'.json', '.py', '.md'}},
            'provider': 'loopback_protocol_fixture', 'model': 'deepseek-flash',
            'reasoning_effort': 'off', 'embedding': 'not_requested; closed_source_read',
            'compression_enabled': False, 'usage': 'synthetic; not provider billing'}


async def check_mcp():
    """Check the actual stdio schema, provenance handle and read-only preview."""
    params = StdioServerParameters(command=sys.executable,
        args=[str(HERE / 'server.py'), '--case', EVALUATE], cwd=ROOT)
    async with Client(params) as client:
        tools = (await client.list_tools()).tools
        schemas = [{**tool.model_dump(mode='json', by_alias=True), 'name': PREFIX + tool.name} for tool in tools]
        contracts = parse_tool_contracts(read(HERE / 'contracts.json'))
        bound = bind_mcp_descriptions(contracts, schemas)
        assert set(bound) == set(prepare_scenario(HERE / 'scenario.json', case=EVALUATE)['allowed_tools'])
        assert all(bound[name] == contracts[name] for name in bound)
        assert all(tool.annotations.read_only_hint is True for tool in tools)
        pin = await client.call_tool('pin_annotation_change', {'change_id': 'change:' + EVALUATE})
        assert not pin.is_error
        source_id = json.loads(pin.content[0].text)['source_id']
        context = await client.call_tool('read_pinned_annotation_context', {'source_id': source_id})
        assert not context.is_error
        preview = await client.call_tool('preview_note_update', {'source_id': source_id})
        assert not preview.is_error and json.loads(preview.content[0].text)['status'] == 'preview'
        denied = await client.call_tool('read_pinned_annotation_context', {'source_id': 'source-' + '0' * 32})
        assert denied.is_error
    return {'tool_schema_checked': True, 'unknown_handle_rejected': True, 'preview_checked': True}


def observations(messages):
    values = []
    for message in messages:
        if message.get('role') == 'tool':
            try:
                value = json.loads(message.get('content', ''))
            except (TypeError, ValueError):
                continue
            if isinstance(value, dict):
                values.append(value)
    return values


def next_action(values, change_id):
    """A fixed protocol fixture, not an LLM or a scientific quality oracle."""
    pin = next((row for row in values if row.get('change_id') == change_id), None)
    if pin is None:
        return PREFIX + 'pin_annotation_change', {'change_id': change_id}
    if not any(isinstance(row.get('context'), dict) for row in values):
        return PREFIX + 'read_pinned_annotation_context', {'source_id': pin['source_id']}
    preview = next((row for row in values if row.get('status') in {'preview', 'needs_review'}), None)
    if preview is None:
        return PREFIX + 'preview_note_update', {'source_id': pin['source_id']}
    return None, preview


def provider_handler(change_id):
    class FixtureProvider(BaseHTTPRequestHandler):
        calls = []
        failures = []

        def log_message(self, *_args):
            pass

        def do_POST(self):
            try:
                if self.path != '/v1/chat/completions':
                    raise ValueError('unexpected endpoint; no semantic embedding is needed for a closed read')
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if len(self.calls) >= 8:
                    raise ValueError('synthetic provider request limit reached')
                self.calls.append(body)
                tool, value = next_action(observations(body['messages']), change_id)
                delta = {'role': 'assistant'}
                if tool:
                    delta['tool_calls'] = [{'index': 0, 'id': 'fixture-' + str(len(self.calls)),
                        'type': 'function', 'function': {'name': tool, 'arguments': json.dumps(value)}}]
                else:
                    delta['content'] = json.dumps(value, ensure_ascii=False, sort_keys=True)
                base = {'id': 'fixture', 'created': 1, 'model': body['model'], 'object': 'chat.completion.chunk'}
                # Deliberately synthetic counters; the proxy must preserve them, not claim billing savings.
                usage = {'prompt_tokens': 100, 'prompt_cache_hit_tokens': 50,
                         'prompt_cache_miss_tokens': 50, 'completion_tokens': 20, 'total_tokens': 120}
                chunks = [{**base, 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                          {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls' if tool else 'stop'}]},
                          {**base, 'choices': [], 'usage': usage}]
                answer = (''.join('data: ' + json.dumps(row) + '\n\n' for row in chunks)
                          + 'data: [DONE]\n\n').encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(answer)))
                self.end_headers()
                self.wfile.write(answer)
            except Exception as exc:
                self.failures.append(type(exc).__name__ + ': ' + str(exc))
                self.send_error(500)
    return FixtureProvider


def run_case(output: Path, case: str, mode='baseline', *, manifest_path=None, stale=False):
    fixture = SCENE.load_fixture(case)
    directory = output / (case + '-' + mode + ('-stale' if stale else ''))
    directory.mkdir(mode=0o700)
    prepared = prepare_scenario(HERE / 'scenario.json', case=case)
    patches = [prepared['patch']]
    session_id = 'literature-' + uuid4().hex
    handler = provider_handler(fixture['change_id'])
    guard = NativeBudgetGuard(max_model_requests=8, max_observed_input_tokens=100_000)
    state = State(cap_usd=0.25, output_cap=2000, record=directory / 'cost-ledger.jsonl')
    env = {'DSH_HOME': str(directory / 'dsh'), 'DEEPSEEK_API_KEY': 'local-fixture-only',
           'SSS_SCENARIO_TOOLS': json.dumps(prepared['allowed_tools']),
           'SSS_ONLINE_MOTIF_MANIFEST': '', 'SSS_ONLINE_MOTIF_TASK': '',
           'SSS_BUDGET_GATE_ACTIVE': '1', 'SSS_BUDGET_CAP_USD': '0.25',
           'SSS_BUDGET_LEDGER': str(state.record)}
    with ThreadingHTTPServer(('127.0.0.1', 0), handler) as provider:
        endpoint = f'http://127.0.0.1:{provider.server_port}'
        gate = create_server('127.0.0.1', 0, endpoint, state)
        workers = [threading.Thread(target=server.serve_forever, daemon=True) for server in (provider, gate)]
        for worker in workers:
            worker.start()
        try:
            env['DEEPSEEK_BASE_URL'] = f'http://127.0.0.1:{gate.server_port}/v1'
            if mode != 'baseline':
                version = '0' * 64 if stale else SCENE.digest(fixture)
                task = {'schema_version': 1, 'task_id': 'synthetic-' + case,
                        'session_id': session_id, 'intent': fixture['question'],
                        'input_version': SCENE.digest(fixture),
                        'bindings': {PREFIX + 'pin_annotation_change': {'change_id': fixture['change_id']}},
                        'source_versions': {name: version for name in read(HERE / 'version-fields.json')}}
                save(directory / 'task.json', task)
                online = module(ROOT / 'scripts/prepare-online-motif.py', 'literature_prepare').prepare(
                    manifest_path, directory / 'task.json')
                patches.append(online['patch'])
                env.update(SSS_ONLINE_MOTIF_MANIFEST=online['manifest'], SSS_ONLINE_MOTIF_TASK=online['task'],
                           SSS_ONLINE_MOTIF_MODE=mode, SSS_ONLINE_MOTIF_PROMPT_SHA256=prepared['prompt_sha256'],
                           SSS_MOTIF_EMBEDDING_ENDPOINT=endpoint + '/v1/embeddings',
                           SSS_MOTIF_EMBEDDING_MODEL='unused-closed-read')
            save(directory / 'manifest.json', {'task_id': session_id, 'question': prepared['prompt'],
                 'scope': 'synthetic_protocol_only', 'case': case, 'mode': mode, 'stale': stale,
                 'source_sha256': SCENE.digest(fixture), 'budget_cap_usd': state.cap_usd,
                 'max_agent_steps': 8, 'max_output_tokens': 2000, 'reasoning_effort': 'off',
                 **{key: value for key, value in prepared.items() if key != 'prompt'}})
            with create_harness(root=ROOT, patches=tuple(patches), env=env, cwd=str(directory),
                                runtime_cwd=str(directory), provider='deepseek-official',
                                model='deepseek-flash', max_tokens=2000, request_timeout_seconds=20) as harness:
                result = harness.run(prepared['prompt'], session_id=session_id, on_notification=guard.on_notification)
            if result.finish_reason != 'completed' or handler.failures:
                raise ValueError('Harness fixture failed: ' + str(handler.failures))
            answer = json.loads(result.final_response)
            assert answer['status'] == 'preview' and answer['application_enabled'] is False
            assert answer['citation']['quote'] == fixture['annotation']['quote']
            assert answer['citation']['page'] == fixture['annotation']['page']
            assert answer['before'] == fixture['notes'][0]['text']
            assert '个人观点：此段由用户维护，不能改写。' in answer['after']
            calls = [event['data']['name'] for event in result.events if event.get('type') == 'tool/call']
            assert calls == prepared['allowed_tools']
            assert len(handler.calls) == state.request_count
            assert all({tool['function']['name'] for tool in body['tools']} == set(prepared['allowed_tools'])
                       for body in handler.calls)
            ledger = [json.loads(line) for line in state.record.read_text(encoding='utf-8').splitlines()]
            assert len(ledger) == len(handler.calls)
            assert all(row['response_usage']['prompt_cache_hit_tokens'] == 50 for row in ledger)
            # Exhaust the local accounting cap and check refusal BEFORE any upstream dispatch.
            state.cap_usd = state.reserved_usd
            request = urllib.request.Request(env['DEEPSEEK_BASE_URL'] + '/chat/completions',
                data=json.dumps(handler.calls[-1]).encode(), headers={'Content-Type': 'application/json'})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                opener.open(request, timeout=5)
                raise AssertionError('exhausted budget was not refused')
            except urllib.error.HTTPError as exc:
                assert exc.code == 429
            assert len(handler.calls) == state.request_count == len(ledger)
            event_path = directory / 'agent-events.jsonl'
            event_path.write_text(''.join(json.dumps(event, ensure_ascii=False) + '\n'
                                         for event in result.events), encoding='utf-8')
            event_path.chmod(0o600)
            save(directory / 'answer.json', answer)
            (directory / 'preview.diff').write_text(answer['diff'], encoding='utf-8')
            (directory / 'preview.diff').chmod(0o600)
            audit_path = directory / '.local/online-motif' / (hashlib.sha256(session_id.encode()).hexdigest() + '.jsonl')
            audits = [json.loads(line) for line in audit_path.read_text(encoding='utf-8').splitlines()] if audit_path.exists() else []
            metrics = {'case': case, 'mode': mode, 'stale': stale, 'model_requests': state.request_count,
                       'tool_calls': len(calls), 'verified_bypasses': sum(row['kind'] == 'model_request_skipped_verified' for row in audits),
                       'shadow_candidates': sum(row['kind'] == 'shadow_candidate' for row in audits),
                       'budget_ledger_rows': len(ledger), 'budget_refusal_checked': True,
                       'paid_api_requests': 0, 'scope': 'synthetic_protocol_only'}
            save(directory / 'metrics.json', metrics)
            return {'metrics': metrics, 'answer': answer, 'events': result.events, 'directory': directory}
        finally:
            for server in (gate, provider):
                server.shutdown()
            gate.server_close()
            for worker in workers:
                worker.join(timeout=5)


def learn_library(runs, output: Path):
    """Mine actual SDK traces; training/certification remain synthetic, not research evidence."""
    contracts = parse_tool_contracts(read(HERE / 'contracts.json'))
    freezer = module(ROOT / 'scripts/freeze-dsh-task-identity.py', 'literature_freeze')
    traces, identities = [], []
    for run in runs:
        directory = run['directory']
        identity = freezer.freeze(directory, 'synthetic-' + run['metrics']['case'], 'agent-events.jsonl')
        lock = load_trace_identity(identity, directory / 'agent-events.jsonl', ROOT / '.local')
        identities.append(lock)
        traces.append(extract_dsh_trace(run['events'], contracts, trace_id=run['metrics']['case'],
            task_fingerprint=lock['research_decision_id'],
            provenance_by_call_id=infer_dsh_provenance(run['events'], contracts)))
    require_distinct_decisions(identities)
    candidates = mine_witnessed_parameter_edges(traces[:2])
    artifacts = [certify_witnessed_edge_motif(
        compile_witnessed_edge_motif(candidate, traces[:2], contracts), traces[2], contracts)
        for candidate in candidates]
    library = library_from_certified(artifacts)
    exporter = module(ROOT / 'scripts/export-online-motif-manifest.py', 'literature_export')
    manifest = exporter.export_manifest(library, read(HERE / 'contracts.json'),
        slot_rules={PREFIX + 'pin_annotation_change': {'change_id': 'change:[a-z_]+'}},
        version_fields=read(HERE / 'version-fields.json'))
    save(output / 'library.json', library)
    save(output / 'online-manifest.json', manifest)
    save(output / 'learning-provenance.json', {'scope': 'synthetic_provider_sdk_traces',
         'identities': identities, 'candidates': candidates, 'scientific_quality_assessed': False})
    return library


def check(output: Path):
    output = output.resolve()
    if not output.is_relative_to(ROOT / '.local'):
        raise ValueError('private acceptance output must be under .local')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    save(output / 'runtime-snapshot.json', runtime_snapshot())
    mcp = asyncio.run(check_mcp())
    learning = [run_case(output, case) for case in (*TRAIN, CERTIFY)]
    library = learn_library(learning, output)
    manifest_path = output / 'online-manifest.json'
    baseline = run_case(output, EVALUATE)
    shadow = run_case(output, EVALUATE, 'shadow', manifest_path=manifest_path)
    execute = run_case(output, EVALUATE, 'execute', manifest_path=manifest_path)
    stale = run_case(output, EVALUATE, 'execute', manifest_path=manifest_path, stale=True)
    evaluations = [baseline, shadow, execute, stale]
    assert all(run['answer'] == baseline['answer'] for run in evaluations)
    assert execute['metrics']['verified_bypasses'] == 1
    assert execute['metrics']['model_requests'] == baseline['metrics']['model_requests'] - 1
    assert shadow['metrics']['shadow_candidates'] > 0 and shadow['metrics']['verified_bypasses'] == 0
    assert stale['metrics']['verified_bypasses'] == 0
    assert shadow['metrics']['model_requests'] == stale['metrics']['model_requests'] == baseline['metrics']['model_requests']
    summary = {'status': 'passed', 'scope': 'synthetic_protocol_only', 'paid_api_requests': 0,
               'shared_core_changed': False, 'certified_motifs': len(library['artifacts']),
               'mcp': mcp, 'learning_runs': [run['metrics'] for run in learning],
               'evaluations': [run['metrics'] for run in evaluations],
               'preview': str(execute['directory'] / 'preview.diff'),
               'runtime_snapshot': str(output / 'runtime-snapshot.json'),
               'limitations': ['No real Zotero/Obsidian connection', 'No real PDF extraction',
                               'Synthetic provider and usage; no scientific quality or cost claim']}
    save(output / 'acceptance.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=ROOT / '.local/literature-notes' / uuid4().hex)
    args = parser.parse_args()
    print(json.dumps(check(args.output), ensure_ascii=False, indent=2))
