import hashlib
import json
import os
from pathlib import Path
import pytest
from src.adapters.scenario import prepare_scenario, ROOT
from src.adapters.harless_scenarios import prepare_scene_registry, _configure_attachment_parsers


def prepared(tmp_path, registry=None):
    initial = prepare_scenario(ROOT / 'scenarios/example/scenario.json')
    output = tmp_path / 'run'; (output / 'presets').mkdir(parents=True)
    return prepare_scene_registry(ROOT, registry or ROOT / 'config/harless-diagnostics.json', default_id='example',
        prepared_default=initial, output=output, embedding_endpoint='http://127.0.0.1:9876/v1/embeddings', embedding_model='diagnostic')


def test_registry_builds_separate_presets_without_using_task_prompt_as_instructions(tmp_path):
    scenes = prepared(tmp_path)
    assert [scene['id'] for scene in scenes] == ['example', 'portfolio-v1', 'portfolio-v2']
    assert len({scene['preset'] for scene in scenes}) == 3
    assert all('instructions' not in scene for scene in scenes)
    assert scenes[1]['certified_input_sha256'] == hashlib.sha256((ROOT / 'benchmarks/research_decision_portfolio_v1/cases/l_retrieval_persistence/task.md').read_text().strip().encode()).hexdigest()
    preset = tmp_path / 'run/presets/sss-scene-portfolio-v1/agent.cordis.yml'
    assert 'research_portfolio_fixture' in preset.read_text()
    # POSIX mode bits do not describe Windows ACLs; retain the security check on POSIX.
    if os.name == 'posix':
        assert (preset.stat().st_mode & 0o777) == 0o600


@pytest.mark.parametrize('change', ['version', 'duplicate', 'unsupported', 'rsi'])
def test_registry_refuses_invalid_registration_before_runtime(tmp_path, change):
    value = json.loads((ROOT / 'config/harless-diagnostics.json').read_text())
    if change == 'version': value['schema_version'] = 2
    if change == 'duplicate': value['scenes'][1]['id'] = 'example'
    if change == 'unsupported': value['scenes'][0]['matcher'] = 'keyword'
    if change == 'rsi': value['scenes'][0]['rsi'] = {'manifest': 'anything'}
    registry = tmp_path / 'registry.json'; registry.write_text(json.dumps(value))
    with pytest.raises(ValueError): prepared(tmp_path, registry)


def test_product_scenes_bind_real_backends_or_explicit_unavailability(tmp_path):
    scenes = prepared(tmp_path, ROOT / 'config/harless-scenes.json')
    rows = {scene['id']: scene for scene in scenes}
    assert rows['ppt']['scenario'] == 'scenarios/research_ppt/web-scenario.json'
    assert rows['ppt']['adapter'] == 'ppt'
    assert 'SSS_PPT_JOB' in json.dumps(rows['ppt']['mcp_rows'])
    assert rows['ppt']['instructions'].startswith('完成科研 PPT 任务。')
    assert '__HARLESS_SESSION_WORKSPACE__' in json.dumps(rows['ppt']['mcp_rows'])
    assert rows['new-scene']['allowed_tools'] == ['mcp__workspace__list_files', 'mcp__workspace__read_file']
    assert rows['files']['scenario'] == 'scenarios/file-management/web-scenario.json'
    assert rows['files']['adapter'] == 'files'
    assert len(rows['files']['allowed_tools']) == 17
    assert 'FM_WEB_WORKSPACE' in json.dumps(rows['files']['mcp_rows'])
    assert '__HARLESS_SESSION_WORKSPACE__' in json.dumps(rows['files']['mcp_rows'])
    assert 'examples/' not in rows['files']['scenario']
    for identity in ('paper-proofreading', 'research-data-analysis'):
        assert rows[identity]['allowed_tools']
        if identity == 'paper-proofreading': assert 'unavailable_reason' not in rows[identity]
        else: assert rows[identity].get('unavailable_reason') in (None, 'data_report_python_dependencies_missing')
        assert rows[identity]['adapter'] == ('data-report' if identity == 'research-data-analysis' else 'workspace')
        assert '__HARLESS_SESSION_WORKSPACE__' in json.dumps(rows[identity]['mcp_rows'])
        assert 'examples/' not in rows[identity]['scenario'] and 'portfolio' not in rows[identity]['scenario']


def parser_fixture(tmp_path):
    pdf, antiword = tmp_path / 'pdf', tmp_path / 'antiword'
    for path in (pdf / 'bin', pdf / 'lib/x86_64-linux-gnu', antiword / 'usr/bin', antiword / 'usr/share/antiword'):
        path.mkdir(parents=True)
    for path in (pdf / 'bin/pdfinfo', pdf / 'bin/pdftotext', antiword / 'usr/bin/antiword', antiword / 'usr/share/antiword/UTF-8.txt'):
        path.write_text('public dependency fixture')
    scene = {'mcp_rows': [{'config': {'serverName': 'research_report', 'env': {'HARLESS_REPORT_WORKSPACE': '__HARLESS_SESSION_WORKSPACE__'}}}]}
    return pdf, antiword, scene


def test_report_attachment_environment_forwards_only_validated_parser_paths(tmp_path, monkeypatch):
    pdf, antiword, scene = parser_fixture(tmp_path)
    monkeypatch.setenv('HARLESS_PDF_TOOLCHAIN_ROOT', str(pdf))
    monkeypatch.setenv('HARLESS_ANTIWORD_BIN', str(antiword / 'usr/bin/antiword'))
    monkeypatch.setenv('ANTIWORDHOME', '/owner/private')
    monkeypatch.setenv('PRIVATE_KEY', 'not-forwarded')
    _configure_attachment_parsers(scene)
    env = scene['mcp_rows'][0]['config']['env']
    assert env == {'HARLESS_REPORT_WORKSPACE': '__HARLESS_SESSION_WORKSPACE__', 'HARLESS_PDF_TOOLCHAIN_ROOT': str(pdf),
                   'HARLESS_ANTIWORD_BIN': str(antiword / 'usr/bin/antiword'), 'ANTIWORDHOME': str(antiword / 'usr/share/antiword')}
    assert scene['pdf_toolchain_root'] == str(pdf) and scene['antiword_root'] == str(antiword)


def test_optional_report_extractors_do_not_inherit_unconfigured_ambient_environment(tmp_path, monkeypatch):
    _, _, scene = parser_fixture(tmp_path)
    monkeypatch.delenv('HARLESS_PDF_TOOLCHAIN_ROOT', raising=False)
    monkeypatch.delenv('HARLESS_ANTIWORD_BIN', raising=False)
    monkeypatch.setenv('ANTIWORDHOME', '/owner/private')
    _configure_attachment_parsers(scene)
    assert scene['mcp_rows'][0]['config']['env'] == {'HARLESS_REPORT_WORKSPACE': '__HARLESS_SESSION_WORKSPACE__'}


def test_report_parser_configuration_rejects_user_directories_and_missing_mapping(tmp_path, monkeypatch):
    pdf, antiword, scene = parser_fixture(tmp_path)
    monkeypatch.setenv('HARLESS_PDF_TOOLCHAIN_ROOT', str(pdf))
    monkeypatch.delenv('HARLESS_ANTIWORD_BIN', raising=False)
    (pdf / '.env').write_text('private')
    with pytest.raises(ValueError, match='isolated Poppler'):
        _configure_attachment_parsers(scene)
    (pdf / '.env').unlink()
    monkeypatch.setenv('HARLESS_ANTIWORD_BIN', str(antiword / 'usr/bin/antiword'))
    (antiword / 'usr/share/antiword/UTF-8.txt').unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        _configure_attachment_parsers(scene)


def test_report_parser_symlinks_are_not_followed(tmp_path, monkeypatch):
    pdf, _, scene = parser_fixture(tmp_path)
    linked = tmp_path / 'redirected'
    try:
        linked.symlink_to(pdf, target_is_directory=True)
    except OSError:
        pytest.skip('symlink permission unavailable')
    monkeypatch.setenv('HARLESS_PDF_TOOLCHAIN_ROOT', str(linked))
    with pytest.raises(ValueError, match='fixed installation paths'):
        _configure_attachment_parsers(scene)
