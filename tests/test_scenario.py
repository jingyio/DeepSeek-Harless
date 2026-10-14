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


@pytest.mark.parametrize('bad', ['foreign_tool', 'unbounded', 'bool', 'extra', 'statuses'])
def test_completion_policy_cannot_widen_tools_or_retry_budget(bad):
    data = config()
    policy = {'tool': data['allowed_tools'][0], 'statuses': ['preview'], 'max_continuations': 2}
    if bad == 'foreign_tool': policy['tool'] = 'mcp__outside__publish'
    elif bad == 'unbounded': policy['max_continuations'] = 3
    elif bad == 'bool': policy['max_continuations'] = True
    elif bad == 'extra': policy['arbitrary_plugin'] = 'file:///tmp/other.ts'
    else: policy['statuses'] = ['not valid']
    data['completion_guard'] = policy
    with tempfile.TemporaryDirectory() as temp, pytest.raises(ValueError): prepare(data, temp)


def test_completion_row_is_shared_by_sdk_patch_and_web_preset():
    data = config(); data['completion_guard'] = {'tool': data['allowed_tools'][0], 'statuses': ['preview'], 'max_continuations': 1}
    with tempfile.TemporaryDirectory() as temp:
        prepared = prepare(data, temp)
        row = prepared['agent_plugins'][0]
        assert row['config']['artifact_root'] == str(ROOT / '.local')
        assert row['name'].endswith('/src/adapters/dsh_completion_guard.ts')
        assert 'sss-completion-guard' in Path(prepared['patch']).read_text()


@pytest.mark.parametrize('value',[3,True,-1])
def test_acceptance_repair_limit_cannot_be_expanded(value):
    data=config();data['acceptance_guard']={'kind':'file_management','max_repairs':value}
    with tempfile.TemporaryDirectory() as temp,pytest.raises(ValueError):prepare(data,temp)

def test_acceptance_uses_fixed_verifier_and_replaces_missing_receipt_loop():
    data=config();data['servers'][0]['server_name']='file_management';data['allowed_tools']=['mcp__file_management__submit_report']
    data['completion_guard']={'tool':data['allowed_tools'][0],'statuses':['delivered'],'max_continuations':2}
    data['acceptance_guard']={'kind':'file_management','max_repairs':2}
    with tempfile.TemporaryDirectory() as temp:
        prepared=prepare(data,temp)
        assert [p['id'] for p in prepared['agent_plugins']]==['sss-acceptance-guard']
        assert prepared['required_env']==['FM_OUTPUT','FM_TASK_FILE']
        assert prepared['agent_plugins'][0]['config']['max_repairs']==2

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

@pytest.mark.parametrize('requested', ['deepseek-pro', 'deepseek-v4-pro'])
def test_pro_cli_alias_uses_official_budgeted_model_before_any_paid_call(requested):
    import subprocess
    import sys
    from src.adapters.deepseek_cost_gate import PEAK_USD_PER_MILLION
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/run-scenario.py'),
        '--model', requested], cwd=ROOT, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    preview = json.loads(result.stdout)
    assert preview['requested_model'] == requested and preview['model'] == 'deepseek-v4-pro'
    assert preview['model'] in PEAK_USD_PER_MILLION and preview['model_call_enabled'] is False
    assert preview['reasoning_effort'] == 'off'


def test_ptc_presentation_uses_upstream_transport_with_isolated_deployment():
    result = prepare_scenario(ROOT / 'scenarios/example/scenario.json', tool_presentation='ptc')
    patch = Path(result['patch']).read_text()
    assert result['tool_presentation'] == 'ptc'
    assert 'mode: ptc' in patch and 'dsh_code_container.ts' in patch
    assert all(tool.startswith('mcp__') for tool in result['allowed_tools'])
    assert 'run_code' not in result['allowed_tools']  # Infrastructure is not a new underlying MCP permission.

def test_entry_motif_is_explicit_fixed_plugin_and_cannot_mix_with_ptc():
    result=prepare_scenario(ROOT/'scenarios/example/scenario.json',entry_motif=True)
    assert 'dsh_entry_motif.ts' in Path(result['patch']).read_text()
    normal=prepare_scenario(ROOT/'scenarios/example/scenario.json')
    assert 'dsh_entry_motif.ts' not in Path(normal['patch']).read_text()
    with pytest.raises(ValueError):prepare_scenario(ROOT/'scenarios/example/scenario.json',entry_motif=True,tool_presentation='ptc')
    with pytest.raises(ValueError):prepare_scenario(ROOT/'scenarios/example/scenario.json',entry_motif='file:///arbitrary.ts')


def test_presentation_rejects_unknown_modes():
    with pytest.raises(ValueError, match='presentation'):
        prepare_scenario(ROOT / 'scenarios/example/scenario.json', tool_presentation='arbitrary-shell')
