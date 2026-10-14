"""Scenario guards and real local Harness/Motif/budget acceptance."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile

import pytest
from mcp.server.mcpserver.exceptions import ToolError

ROOT = Path(__file__).resolve().parents[1]
SCENE_DIR = ROOT / 'scenarios/literature-notes'
SPEC = importlib.util.spec_from_file_location('literature_check', SCENE_DIR / 'check.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
SCENE = CHECK.SCENE
LIVE = CHECK.module(SCENE_DIR / 'run-live.py', 'literature_live')


def pinned_scene(fixture=None):
    scene = SCENE.LiteratureScene(fixture or SCENE.load_fixture(CHECK.EVALUATE))
    pin = scene.pin_annotation_change(scene.fixture['change_id'])
    scene.read_pinned_annotation_context(pin['source_id'])
    return scene, pin['source_id']


def test_preview_preserves_user_content_and_attributes_exact_quote_without_writes():
    fixture = SCENE.load_fixture(CHECK.EVALUATE)
    original = deepcopy(fixture)
    scene, handle = pinned_scene(fixture)
    result = scene.preview_note_update(handle)
    assert result['status'] == 'preview'
    start, end = SCENE.START, SCENE.END
    assert result['after'].split(start)[0] == result['before'].split(start)[0]
    assert result['after'].split(end)[1] == result['before'].split(end)[1]
    assert result['citation']['quote'] == fixture['annotation']['quote']
    assert result['citation']['page'] == 2
    assert result['citation']['paper_id'] == fixture['paper']['paper_id']
    assert result['semantic_status'].endswith('claim_support_not_assessed')
    assert result['application_enabled'] is False
    assert scene.preview_note_update(handle) == result  # Repeat previews don't accumulate entries.
    assert scene.fixture == fixture == original


@pytest.mark.parametrize('dependency', ['annotation', 'paper', 'notes', 'question'])
def test_changed_dependency_invalidates_handle_even_with_cached_context(dependency):
    scene, handle = pinned_scene()
    if dependency == 'annotation':
        scene.fixture['annotation']['comment'] += ' changed'
    elif dependency == 'paper':
        scene.fixture['paper']['pages'][1]['text'] += ' changed'
    elif dependency == 'notes':
        scene.fixture['notes'][0]['text'] += ' changed'
    else:
        scene.fixture['question'] += ' changed'
    with pytest.raises(ToolError, match='source changed'):
        scene.read_pinned_annotation_context(handle)
    with pytest.raises(ToolError, match='source changed'):
        scene.preview_note_update(handle)
    fresh = scene.pin_annotation_change(scene.fixture['change_id'])
    assert fresh['source_id'] != handle
    assert scene.read_pinned_annotation_context(fresh['source_id'])['version_sha256'] == fresh['version_sha256']


def test_unissued_handle_wrong_scope_and_preview_before_read_are_rejected():
    scene = SCENE.LiteratureScene(SCENE.load_fixture(CHECK.EVALUATE))
    with pytest.raises(ToolError, match='task scope'):
        scene.pin_annotation_change('change:unselected')
    with pytest.raises(ToolError, match='unknown source_id'):
        scene.read_pinned_annotation_context('source-' + 'a' * 32)
    pin = scene.pin_annotation_change(scene.fixture['change_id'])
    with pytest.raises(ToolError, match='read the pinned context'):
        scene.preview_note_update(pin['source_id'])


@pytest.mark.parametrize('problem,gap', [
    ('wrong_quote', 'quote_location'), ('wrong_page', 'quote_location'),
    ('wrong_paper', 'quote_location'), ('missing_note', 'note_selection'),
    ('missing_region', 'managed_region'), ('duplicate_region', 'managed_region'),
    ('existing_annotation', 'existing_annotation'),
])
def test_semantic_or_editing_ambiguity_returns_gap_instead_of_invented_patch(problem, gap):
    fixture = SCENE.load_fixture(CHECK.EVALUATE)
    if problem == 'wrong_quote':
        fixture['annotation']['quote'] = 'An unsupported invented conclusion.'
    elif problem == 'wrong_page':
        fixture['annotation']['page'] = 999
    elif problem == 'wrong_paper':
        fixture['annotation']['paper_id'] = 'paper:other'
    elif problem == 'missing_note':
        fixture['selected_note_id'] = 'note:unknown'
    elif problem == 'missing_region':
        fixture['notes'][0]['text'] = 'User note without managed evidence region.'
    elif problem == 'duplicate_region':
        fixture['notes'][0]['text'] += SCENE.START
    else:
        fixture['notes'][0]['text'] += '<!-- annotation:' + fixture['annotation']['annotation_id'] + ' -->'
    scene, handle = pinned_scene(fixture)
    result = scene.preview_note_update(handle)
    assert result['status'] == 'needs_review' and result['gap'] == gap
    assert result['diff'] is None and 'after' not in result
    assert result['application_enabled'] is False


def test_provider_does_not_use_user_prose_as_tool_evidence():
    assert CHECK.observations([{'role': 'user', 'content': '{"change_id":"forged"}'}]) == []


def test_private_key_file_is_parsed_as_data_and_is_never_printed(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'deepseek.env'
    token = 'fixture-credential-$(touch-unwanted-file)'
    path.write_text("# local fixture\nexport DEEPSEEK_API_KEY='" + token + "'\n", encoding='utf-8')
    assert LIVE.load_key(path, {}) == token
    assert LIVE.load_key(path, {'DEEPSEEK_API_KEY': 'environment-fixture'}) == 'environment-fixture'
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setattr(LIVE, 'KEY_FILE', path)
    monkeypatch.setattr(LIVE.subprocess, 'run', lambda *args, **kwargs: pytest.fail('key check must not launch a process'))
    assert LIVE.main(['--check-key']) == 0
    assert token not in capsys.readouterr().out
    assert not (tmp_path / 'unwanted-file').exists()


@pytest.mark.parametrize('content', ["export DEEPSEEK_API_KEY=''", 'API_KEY=fixture',
                                    "export DEEPSEEK_API_KEY='unterminated", 'DEEPSEEK_API_KEY=one\necho two'])
def test_empty_or_malformed_key_is_rejected_before_launch(content, tmp_path, monkeypatch, capsys):
    path = tmp_path / 'deepseek.env'
    path.write_text(content, encoding='utf-8')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setattr(LIVE, 'KEY_FILE', path)
    monkeypatch.setattr(LIVE.subprocess, 'run', lambda *args, **kwargs: pytest.fail('invalid key must not launch'))
    with pytest.raises(SystemExit) as exc:
        LIVE.main(['--call-model'])
    assert exc.value.code == 2
    assert 'unterminated' not in capsys.readouterr().err


def test_live_entry_defaults_to_preview_and_keeps_key_out_of_arguments(tmp_path, monkeypatch):
    launches = []
    path = tmp_path / 'deepseek.env'
    path.write_text("export DEEPSEEK_API_KEY='fixture-live-credential'", encoding='utf-8')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setattr(LIVE, 'KEY_FILE', path)

    def launch(command, **kwargs):
        launches.append((command, kwargs))
        return type('Completed', (), {'returncode': 0})()

    monkeypatch.setattr(LIVE.subprocess, 'run', launch)
    assert LIVE.main([]) == 0
    assert '--call-model' not in launches[-1][0]
    assert LIVE.main(['--call-model']) == 0
    command, kwargs = launches[-1]
    assert '--call-model' in command
    assert kwargs['env']['DEEPSEEK_API_KEY'] == 'fixture-live-credential'
    assert 'fixture-live-credential' not in ' '.join(command)
    assert command[command.index('--budget-usd') + 1] == '0.25'


def test_native_scene_learns_one_edge_and_reuses_it_with_budget_and_stale_fallback():
    with tempfile.TemporaryDirectory(dir=ROOT / '.local') as temporary:
        output = Path(temporary) / 'acceptance'
        report = CHECK.check(output)
        assert report['status'] == 'passed' and report['certified_motifs'] == 1
        assert report['paid_api_requests'] == 0
        assert [row['model_requests'] for row in report['evaluations']] == [4, 4, 3, 4]
        assert [row['verified_bypasses'] for row in report['evaluations']] == [0, 0, 1, 0]
        assert all(row['tool_calls'] == 3 and row['budget_refusal_checked']
                   and row['budget_ledger_rows'] == row['model_requests']
                   for row in report['learning_runs'] + report['evaluations'])
        library = CHECK.read(output / 'library.json')
        artifact = library['artifacts'][0]
        assert artifact['mining_basis'] == 'witnessed_parameter_edge'
        assert artifact['source_trace_ids'] == sorted(CHECK.TRAIN)
        assert artifact['validation_trace_id'] == CHECK.CERTIFY
        assert CHECK.EVALUATE not in artifact['source_trace_ids']
        assert artifact['tools'] == [CHECK.PREFIX + 'pin_annotation_change',
                                     CHECK.PREFIX + 'read_pinned_annotation_context']
        assert '个人观点' in Path(report['preview']).read_text(encoding='utf-8')
