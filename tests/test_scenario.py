"""Scenario configuration must not disclose secrets or widen tool capabilities."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from src.adapters.scenario import ROOT, prepare_scenario
from src.adapters.harness_runtime import create_harness


def config():
    return json.loads((ROOT / 'scenarios/example/scenario.json').read_text(encoding='utf-8'))


def prepare(data, temporary):
    data['prompt'] = str(ROOT / 'scenarios/example/prompt.md')
    path = Path(temporary) / 'scenario.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return prepare_scenario(path)


def test_env_reference_survives_harness_start_without_serializing_secret():
    data = config()
    data['servers'][0]['env'] = {'DEMO_SECRET': {'from_env': 'SSS_TEST_SECRET'}}
    with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'SSS_TEST_SECRET':'PRIVATE_TEST_VALUE'}):
        prepared = prepare(data, temp)
        text = Path(prepared['patch']).read_text(encoding='utf-8')
        assert 'PRIVATE_TEST_VALUE' not in text
        assert prepared['required_env'] == ['SSS_TEST_SECRET']
        with create_harness(root=ROOT, patches=(prepared['patch'],),
                            cwd=temp, runtime_cwd=temp,
                            env={'SSS_SCENARIO_TOOLS':json.dumps(prepared['allowed_tools']),
                                 'DEEPSEEK_BASE_URL':'http://127.0.0.1:9',
                                 'DEEPSEEK_API_KEY':'sss-offline-test'}):
            pass


def test_http_mcp_headers_keep_environment_references():
    data = config()
    data['servers'] = [{'server_name':'demo','transport':'streamable-http',
                        'url':'http://127.0.0.1:8765/mcp',
                        'headers':{'Authorization':{'from_env':'DEMO_MCP_AUTH'}}}]
    with tempfile.TemporaryDirectory() as temp:
        prepared = prepare(data, temp)
        assert prepared['required_env'] == ['DEMO_MCP_AUTH']
        assert 'streamable-http' in Path(prepared['patch']).read_text(encoding='utf-8')


@pytest.mark.parametrize('mutation', ['unknown_tool','duplicate_server','injection','unknown_field'])
def test_bad_config_cannot_widen_or_inject(mutation):
    data = config()
    if mutation == 'unknown_tool': data['allowed_tools'] = ['mcp__outside__write']
    if mutation == 'duplicate_server': data['servers'].append(data['servers'][0].copy())
    if mutation == 'injection': data['servers'][0]['env'] = {'SECRET':{'from_env':'x];process.exit(0);['}}
    if mutation == 'unknown_field': data['servers'][0]['shell'] = True
    with tempfile.TemporaryDirectory() as temp, pytest.raises(ValueError):
        prepare(data, temp)


def test_demo_source_version_change_blocks_old_handle():
    import importlib.util
    spec = importlib.util.spec_from_file_location('demo', ROOT / 'scenarios/example/server.py')
    demo = importlib.util.module_from_spec(spec); spec.loader.exec_module(demo)
    pin = demo.pin_note('note:alpha')
    demo.NOTES['note:alpha'] = 'Changed evidence'
    from mcp.server.mcpserver.exceptions import ToolError
    with pytest.raises(ToolError, match='changed'):
        demo.read_pinned_note(pin['source_id'])
