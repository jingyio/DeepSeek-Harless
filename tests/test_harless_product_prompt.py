"""Web-only trusted persona configuration; never starts a server or model."""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.adapters.scenario import ROOT, prepare_scenario
from src.adapters.harless_product_prompt import product_persona, product_system_prompt
from src.adapters.harless_scenarios import prepare_scene_registry


@pytest.mark.parametrize('python_parent', ['neutral', 'GeneLoop'])
def test_sdk_defaults_are_unchanged_and_web_identity_does_not_rewrite_task_text(tmp_path, monkeypatch, python_parent):
    # A product name in an interpreter or checkout path is ordinary MCP config.
    # This preparation-only diagnostic never runs the synthetic interpreter.
    monkeypatch.setattr(sys, 'executable', str(tmp_path / python_parent / 'python'))
    scenario = ROOT / 'scenarios/example/scenario.json'
    sdk = prepare_scenario(scenario)
    web = prepare_scenario(scenario, web_deployment=True)
    sdk_patch = Path(sdk['patch']).read_text(encoding='utf-8')
    web_patch = Path(web['patch']).read_text(encoding='utf-8')
    sdk_prompt_header = sdk_patch.split('\n- {', 1)[0]
    sdk_overrides = [json.loads(line[2:]) for line in sdk_patch.splitlines() if line.startswith('- {"id": "system-prompt"')]
    assert 'GeneLoop' not in sdk_prompt_header and 'includeHarnessIdentity' not in sdk_prompt_header
    assert sdk_overrides == []
    rows = [json.loads(line[2:]) for line in web_patch.splitlines() if line.startswith('- {"id": "system-prompt"')]
    assert next(row['config'] for row in rows if row.get('id') == 'system-prompt') == product_system_prompt()
    assert web['prompt'] == sdk['prompt']
    assert web['prompt_sha256'] == sdk['prompt_sha256']
    assert web['allowed_tools'] == sdk['allowed_tools'] and web['mcp_rows'] == sdk['mcp_rows']
    assert prepare_scenario(scenario)['patch_sha256'] == sdk['patch_sha256']
    with pytest.raises(ValueError, match='web_deployment'):
        prepare_scenario(scenario, web_deployment='true')


def test_web_registry_personas_keep_mcp_identifiers_and_disable_runtime_context(tmp_path):
    initial = prepare_scenario(ROOT / 'scenarios/example/scenario.json', web_deployment=True)
    scenes = prepare_scene_registry(ROOT, ROOT / 'config/harless-diagnostics.json', default_id='example',
        prepared_default=initial, output=tmp_path, embedding_endpoint='http://127.0.0.1:9', embedding_model='diagnostic')
    for scene in scenes[1:]:
        rows = json.loads((tmp_path / 'presets' / scene['preset'] / 'agent.cordis.yml').read_text(encoding='utf-8'))
        assert rows[0]['config'] == product_persona()
        assert rows[0]['name'] == '@deepseek-ai/dsh-persona'
        assert any(row['name'] == '@deepseek-ai/dsh-mcp-client' for row in rows[1:])
        assert 'complete' not in rows[0]['config']


@pytest.mark.parametrize('public_origin', [None, 'https://geneloop.example:3443'])
def test_default_web_preset_and_host_patch_remove_source_surface_context(tmp_path, public_origin):
    spec = importlib.util.spec_from_file_location('web_product_prompt', ROOT / 'scripts/harness-web.py')
    web = importlib.util.module_from_spec(spec); spec.loader.exec_module(web)
    args = SimpleNamespace(scenario='new-scene', case='', real_model=False, mode='baseline',
        embedding_endpoint='', embedding_model='diagnostic', fixture='normal', frozen=True,
        manifest=None, task=None, glm=None, port=3080, public_origin=public_origin, budget_usd=.25,
        request_limit=None, run_budget_usd=.25, run_request_limit=None)
    web.prepare(args, tmp_path, 'http://127.0.0.1:9/v1')
    patch = json.loads((tmp_path / 'host.patch.yml').read_text(encoding='utf-8'))
    assert next(row['config'] for row in patch if row.get('id') == 'system-prompt') == product_system_prompt()
    assert next(row['config'] for row in patch if row.get('id') == 'web-runtime') == {
        'openBrowser': False, 'printUrl': True, 'surfaceContext': False,
        'trustedHosts': ['geneloop.example:3443'] if public_origin else []}
    rows = json.loads((tmp_path / 'presets/sss-task/agent.cordis.yml').read_text(encoding='utf-8'))
    assert rows[0]['config'] == product_persona()
    assert (tmp_path / 'prompt.md').read_text(encoding='utf-8') == (ROOT / 'scenarios/general/prompt.md').read_text(encoding='utf-8')
