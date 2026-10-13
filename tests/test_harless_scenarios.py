import hashlib
import json
from pathlib import Path
import pytest
from src.adapters.scenario import prepare_scenario, ROOT
from src.adapters.harless_scenarios import prepare_scene_registry


def prepared(tmp_path, registry=None):
    initial = prepare_scenario(ROOT / 'scenarios/example/scenario.json')
    output = tmp_path / 'run'; (output / 'presets').mkdir(parents=True)
    return prepare_scene_registry(ROOT, registry or ROOT / 'config/harless-scenes.json', default_id='example',
        prepared_default=initial, output=output, embedding_endpoint='http://127.0.0.1:9876/v1/embeddings', embedding_model='diagnostic')


def test_registry_builds_separate_presets_without_using_task_prompt_as_instructions(tmp_path):
    scenes = prepared(tmp_path)
    assert [scene['id'] for scene in scenes] == ['example', 'portfolio-v1', 'portfolio-v2']
    assert len({scene['preset'] for scene in scenes}) == 3
    assert all('instructions' not in scene for scene in scenes)
    assert scenes[1]['certified_input_sha256'] == hashlib.sha256((ROOT / 'benchmarks/research_decision_portfolio_v1/cases/l_retrieval_persistence/task.md').read_text().strip().encode()).hexdigest()
    preset = tmp_path / 'run/presets/sss-scene-portfolio-v1/agent.cordis.yml'
    assert 'research_portfolio_fixture' in preset.read_text()
    assert (preset.stat().st_mode & 0o777) == 0o600


@pytest.mark.parametrize('change', ['version', 'duplicate', 'unsupported', 'rsi'])
def test_registry_refuses_invalid_registration_before_runtime(tmp_path, change):
    value = json.loads((ROOT / 'config/harless-scenes.json').read_text())
    if change == 'version': value['schema_version'] = 2
    if change == 'duplicate': value['scenes'][1]['id'] = 'example'
    if change == 'unsupported': value['scenes'][0]['matcher'] = 'keyword'
    if change == 'rsi': value['scenes'][0]['rsi'] = {'manifest': 'anything'}
    registry = tmp_path / 'registry.json'; registry.write_text(json.dumps(value))
    with pytest.raises(ValueError): prepared(tmp_path, registry)
