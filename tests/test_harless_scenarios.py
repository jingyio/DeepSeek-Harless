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
    assert rows['ppt']['scenario'] == 'scenarios/ppt_master/scenario.json'
    assert rows['ppt']['adapter'] == 'ppt'
    assert rows['ppt']['ppt_execution_strategy']=='ppt_master'
    # Five scene MCP tools plus the approved common native tool set. Do not
    # conflate an expanded public tool surface with additional PPT MCP tools.
    common = json.loads((ROOT/'config/geneloop-capabilities.json').read_text(encoding='utf-8'))['tools']
    ppt_tools = json.loads((ROOT/'scenarios/ppt_master/scenario.json').read_text(encoding='utf-8'))['allowed_tools']
    assert len(ppt_tools) == 5
    assert rows['ppt']['allowed_tools'] == [*ppt_tools, *common]
    assert 'mcp__ppt_master__read_skill_entry' in rows['ppt']['allowed_tools']
    assert not any(t.startswith('mcp__ppt__') for t in rows['ppt']['allowed_tools'])
    assert rows['ppt']['instructions'].startswith('完成用户的 PPT 任务。')
    lock=json.loads((ROOT/'scenarios/ppt_master/skill-lock.json').read_text(encoding='utf-8'))
    assert rows['ppt']['design_skill_sha256']==lock['files']['SKILL.md']
    assert rows['ppt']['skill_package_sha256']==lock['package_sha256']
    assert rows['ppt']['instructions_sha256']==hashlib.sha256(rows['ppt']['instructions'].encode()).hexdigest()
    assert all('design_skill_sha256' not in rows[key] for key in ['paper-proofreading','research-data-analysis','new-scene'])
    assert 'scenarios/ppt_master/server.py' in json.dumps(rows['ppt']['mcp_rows']).replace('\\\\','/')
    assert {'read_image','read','write','edit','glob','grep','ask_user_question','todo_write','skill','present','subagent'} <= set(common)
    assert rows['new-scene']['allowed_tools'] == ['mcp__workspace__list_files', 'mcp__workspace__read_file', *common]
    for scene in rows.values():
        if not scene.get('adapter'): continue
        assert scene['common_tools'] == common
        assert set(common) <= set(scene['allowed_tools'])
    assert rows['files']['scenario'] == 'scenarios/file-management/web-scenario.json'
    assert rows['files']['adapter'] == 'files'
    file_tools = json.loads((ROOT/'scenarios/file-management/web-scenario.json').read_text(encoding='utf-8'))['allowed_tools']
    assert len(file_tools) == 13 and all(name.startswith('mcp__file_management__') for name in file_tools)
    assert rows['files']['allowed_tools'] == [*file_tools, *common]
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


def test_paper_default_library_and_generic_export_survive_without_private_deployment(tmp_path, monkeypatch):
    monkeypatch.delenv('HARLESS_PAPER_RUNTIME_BUNDLE', raising=False)
    monkeypatch.delenv('HARLESS_PAPER_RENDERER_ROOT', raising=False)
    row = next(s for s in prepared(tmp_path, ROOT/'config/harless-scenes.json') if s['id']=='paper-proofreading')
    assert row['runtime_kind'] == 'paper_document_read_v1'
    assert row['runtime_mode'] == 'execute'
    assert row['binding_policy'] == 'approved_uploaded_reads_v1'
    registry=json.loads((ROOT/'config/harless-scenes.json').read_text(encoding='utf-8'))
    current=next(item for item in registry['scenes'] if item['id']=='paper-proofreading')['rsi']['runtime_bundle']
    assert row['runtime_library'] == str(ROOT/current/'library.json')
    assert 'rsi_unavailable_reason' not in row and 'output_unavailable_reason' not in row
    assert row['paper_reference_output_unavailable_reason'] == 'paper_renderer_not_deployed'
    assert 'mcp__paper_checks__export_review_report' in row['allowed_tools']
    assert 'mcp__paper_checks__collect_current_local_citation_evidence' in row['allowed_tools']
    scene_tools = json.loads((ROOT/row['scenario']).read_text(encoding='utf-8'))['allowed_tools']
    common = json.loads((ROOT/'config/geneloop-capabilities.json').read_text(encoding='utf-8'))['tools']
    assert len(scene_tools) == 24 and all(name.startswith('mcp__paper_checks__') for name in scene_tools)
    assert row['allowed_tools'] == [*scene_tools, *common]
    assert '每项发现只给一条保留原始事实的最小建议' in row['instructions']


def test_invalid_explicit_paper_library_fails_closed_without_breaking_generic_export(tmp_path, monkeypatch):
    monkeypatch.setenv('HARLESS_PAPER_RUNTIME_BUNDLE', str(tmp_path/'missing'))
    monkeypatch.setenv('HARLESS_PAPER_RENDERER_ROOT', str(tmp_path/'missing-renderer'))
    row = next(s for s in prepared(tmp_path, ROOT/'config/harless-scenes.json') if s['id']=='paper-proofreading')
    assert row['rsi_unavailable_reason'] == 'runtime_bundle_certification_invalid'
    assert 'runtime_kind' not in row
    assert 'output_unavailable_reason' not in row
    assert row['paper_reference_output_unavailable_reason'] == 'paper_renderer_deployment_invalid'


def parser_fixture(tmp_path):
    pdf, antiword = tmp_path / 'pdf', tmp_path / 'antiword'
    for path in (pdf / 'bin', pdf / 'lib/x86_64-linux-gnu', antiword / 'usr/bin', antiword / 'usr/share/antiword'):
        path.mkdir(parents=True)
    for path in (pdf / 'bin/pdfinfo', pdf / 'bin/pdftotext', antiword / 'usr/bin/antiword', antiword / 'usr/share/antiword/UTF-8.txt'):
        path.write_text('public dependency fixture')
    scene = {'mcp_rows': [{'config': {'serverName': 'research_report', 'env': {'HARLESS_REPORT_WORKSPACE': '__HARLESS_SESSION_WORKSPACE__'}}}]}
    return pdf, antiword, scene


def test_report_attachment_environment_forwards_only_validated_parser_paths(tmp_path, monkeypatch):
    monkeypatch.delenv('GENELOOP_PDF_OCR_ROOT', raising=False)
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
    monkeypatch.delenv('GENELOOP_PDF_OCR_ROOT', raising=False)
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


def test_ocr_rejects_unpinned_languages_and_private_resource_directories(tmp_path, monkeypatch):
    root=tmp_path/'ocr';languages=root/'tessdata';languages.mkdir(parents=True)
    (languages/'eng.traineddata').write_bytes(b'not the pinned model')
    (languages/'chi_sim.traineddata').write_bytes(b'not the pinned model')
    monkeypatch.setenv('GENELOOP_PDF_OCR_ROOT',str(root))
    with pytest.raises(ValueError,match='hash mismatch'):
        _configure_attachment_parsers({'mcp_rows':[]})
    (root/'.env').write_text('private')
    with pytest.raises(ValueError,match='unapproved resources'):
        _configure_attachment_parsers({'mcp_rows':[]})
