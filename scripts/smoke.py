#!/usr/bin/env python3
"""Offline tool wiring check, not an Agent quality/cost benchmark."""
import asyncio
import hashlib
import json
import os
import sys
from collections import Counter, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcp import Client, StdioServerParameters
from src.adapters.harness_runtime import create_harness
from src.adapters.scenario import prepare_scenario

calls = Counter()


async def invoke(client, name, args):
    result = await client.call_tool(name, args)
    if result.is_error:
        raise RuntimeError(f'{name}: MCP error')
    calls[name] += 1
    return json.loads(result.content[0].text)


async def check_demo():
    params = StdioServerParameters(command=sys.executable,
        args=[str(ROOT / 'scenarios/example/server.py')], cwd=ROOT)
    async with Client(params) as client:
        offered = {tool.name for tool in (await client.list_tools()).tools}
        assert offered == {'pin_note', 'read_pinned_note'}
        for object_id in ['note:alpha', 'note:beta']:
            pin = await invoke(client, 'pin_note', {'object_id': object_id})
            read = await invoke(client, 'read_pinned_note', {'source_id': pin['source_id']})
            assert pin['version_sha256'] == read['version_sha256']
        denied = await client.call_tool('read_pinned_note', {'source_id': 'invented'})
        assert denied.is_error


async def check_portfolio(version):
    directory = ROOT / f'benchmarks/research_decision_portfolio_v{version}'
    lock = json.loads((directory / 'fixtures.lock.json').read_text(encoding='utf-8'))
    for filename, digest in lock['sha256'].items():
        assert hashlib.sha256((directory / filename).read_bytes()).hexdigest() == digest
    cases = sorted((directory / 'cases').iterdir())
    objects_read = 0
    for case in cases:
        params = StdioServerParameters(command=sys.executable,
            args=[str(directory / 'mock_apps_server.py')], cwd=ROOT,
            env={'PYTHONPATH': str(ROOT), 'SSS_PORTFOLIO_CASE': case.name})
        async with Client(params, read_timeout_seconds=20) as client:
            offered = {tool.name for tool in (await client.list_tools()).tools}
            assert offered == {'read_event','pin_resource','read_pinned','read_rows',
                               'aggregate_rate','compare_tables','find_dependents','locate_excerpt'}
            event = await invoke(client, 'read_event', {'event_id': f'event:{case.name}:01'})
            pending, seen, datasets = deque(event['root_objects']), set(), []
            while pending:
                object_id = pending.popleft()
                if object_id in seen: continue
                seen.add(object_id)
                pin = await invoke(client, 'pin_resource', {'object_id': object_id})
                read = await invoke(client, 'read_pinned', {'source_id': pin['source_id']})
                assert pin['version_sha256'] == read['version_sha256']
                objects_read += 1
                value = read['value']
                if 'dataset_id' in value:
                    datasets.append(value)
                    await invoke(client, 'read_rows', {'dataset_id': value['dataset_id']})
                    await invoke(client, 'aggregate_rate', {'dataset_id': value['dataset_id'],
                        'group_by': value['metric']['allowed_groups'][0]})
                else:
                    pending.extend(value['links'])
                    if len(value.get('text', '')) >= 3:
                        located = await invoke(client, 'locate_excerpt', {
                            'source_id': pin['source_id'], 'exact_text': value['text'][:50]})
                        assert located['version_sha256'] == read['version_sha256']
                dependents = await invoke(client, 'find_dependents', {'object_id': object_id})
                pending.extend(row['object_id'] for row in dependents['claims'])
            for older, newer in zip(datasets, datasets[1:]):
                if older['metric']['id'] == newer['metric']['id']:
                    await invoke(client, 'compare_tables', {'previous_dataset_id': older['dataset_id'],
                        'current_dataset_id': newer['dataset_id']})
    return {'cases_passed':len(cases), 'objects_read':objects_read}


async def main():
    await check_demo()
    rows = {f'portfolio_v{version}': await check_portfolio(version) for version in [1,2]}
    prepared = prepare_scenario(ROOT / 'scenarios/example/scenario.json')
    workspace = ROOT / '.local/smoke/harness'; workspace.mkdir(parents=True, exist_ok=True)
    # Explicitly closed local endpoint: even an unexpected model request cannot
    # reach the provider. Starting the SDK performs initialization only.
    env = {'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),
           'DEEPSEEK_BASE_URL':'http://127.0.0.1:9','DEEPSEEK_API_KEY':'sss-offline-smoke',
           'SSS_ONLINE_MOTIF_MANIFEST':'','SSS_ONLINE_MOTIF_TASK':''}
    with create_harness(root=ROOT, patches=(prepared['patch'],), env=env,
                        cwd=str(workspace), runtime_cwd=str(workspace)):
        pass
    print(json.dumps({**rows,'tool_calls':dict(calls),'sdk_initialized':True,
                     'paid_model_requests':0,'scope':'offline tool and fixture checks only'}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
