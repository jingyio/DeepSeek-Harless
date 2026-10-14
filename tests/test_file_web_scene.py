"""Files Web adapter reuses the bounded PlanScene inside one server-owned task copy."""
from __future__ import annotations
import sys
import zipfile
from pathlib import Path

import pytest
pytest.importorskip('mcp')

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scenarios/file-management'))
from common import digest, snapshot  # noqa: E402
from plan_tools import PlanScene  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402


def spec(work: Path, task: str, writable: bool) -> dict:
    inputs = work / 'inputs'
    inputs.mkdir(parents=True)
    (inputs / '.experiment-copy').write_text(task)
    (inputs / 'note.txt').write_text('alpha beta', encoding='utf-8')
    return {
        'schema_version': 1, 'scope_kind': 'harless_web_task', 'task_id': task,
        'family': 'web_files', 'objective': 'Organize approved copy', 'rules': ['No overwrite'],
        'workspace': str(inputs), 'initial_snapshot': snapshot(inputs), 'previous_snapshot': {},
        'allowed_operations': ['copy', 'move', 'quarantine'] if writable else [],
        'write_grant': {'schema_version': 1, 'max_actions': 6 if writable else 0,
                        'allow_restore': writable,
                        'allowed_ops': ['copy', 'move', 'quarantine'] if writable else [],
                        'source_paths': ['note.txt'] if writable else [],
                        'destination_prefixes': ['organized/', 'copies/', 'quarantine/'] if writable else []},
    }


def test_web_file_scene_read_only_and_isolated(tmp_path, monkeypatch):
    work = tmp_path / 'member-a' / 'work'
    task = 'task_read_only'
    monkeypatch.setenv('FM_WEB_WORKSPACE', str(work))
    row = spec(work, task, False)
    scene = PlanScene(row, work / 'file-results' / (task + '-' + digest(row)[:16]))
    assert scene.read_task()['write_grant']['max_actions'] == 0
    file_id = scene.list_files()['files'][0]['file_id']
    source = scene.pin_file(file_id)
    assert scene.read_file(source['source_id'])['text'] == 'alpha beta'
    with pytest.raises(ToolError):
        scene.preview_actions([{'op': 'copy', 'file_ids': [file_id], 'destination': 'copies/note.txt'}])
    (work / 'inputs' / 'note.txt').write_text('uploaded after preview', encoding='utf-8')
    revised = {**row, 'initial_snapshot': snapshot(work / 'inputs')}
    next_scene = PlanScene(revised, work / 'file-results' / (task + '-' + digest(revised)[:16]))
    assert next_scene.read_task()['input_sha256'] == digest(revised)
    assert next_scene.list_files()['files'][0]['sha256'] != row['initial_snapshot']['note.txt']
    foreign = {**row, 'task_id': 'task_foreign', 'workspace': str(tmp_path / 'member-b' / 'inputs')}
    with pytest.raises(ValueError, match='server-bound session'):
        PlanScene(foreign, work / 'file-results' / ('task_foreign-' + digest(foreign)[:16]))


def test_web_file_scene_authorized_copy_and_receipt(tmp_path, monkeypatch):
    work = tmp_path / 'member-a' / 'work'
    task = 'task_copy'
    monkeypatch.setenv('FM_WEB_WORKSPACE', str(work))
    row = spec(work, task, True)
    scene = PlanScene(row, work / 'file-results' / (task + '-' + digest(row)[:16]))
    scene.read_task()
    file_id = next(item['file_id'] for item in scene.list_files()['files'] if item['path'] == 'note.txt')
    with pytest.raises(ToolError):
        scene.preview_actions([{'op': 'copy', 'file_ids': [file_id], 'destination': 'outside/note.txt'}])
    preview = scene.preview_actions([{'op': 'copy', 'file_ids': [file_id], 'destination': 'copies/note.txt'}])
    with pytest.raises(TypeError):
        scene.execute_plan(preview['plan_id'])
    token = scene.authorize_plan(preview['plan_id'])
    receipt = scene.execute_plan(preview['plan_id'], token['authorization_id'])
    assert receipt['status'] == 'executed_verified'
    assert (work / 'inputs' / 'copies' / 'note.txt').read_text() == 'alpha beta'
    assert scene.execute_plan(preview['plan_id'], token['authorization_id']) == receipt
    assert scene.restore_plan(preview['plan_id'], token['authorization_id'])['status'] == 'restored_verified'
    assert not (work / 'inputs' / 'copies' / 'note.txt').exists()


def test_web_file_scene_rejects_compressed_office_xml_bomb(tmp_path, monkeypatch):
    work = tmp_path / 'member-a' / 'work'
    task = 'task_zip_limit'
    monkeypatch.setenv('FM_WEB_WORKSPACE', str(work))
    row = spec(work, task, False)
    with zipfile.ZipFile(work / 'inputs' / 'large.docx', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('word/document.xml', b'<root>' + b'a' * (4 * 1024 * 1024 + 1) + b'</root>')
    row['initial_snapshot'] = snapshot(work / 'inputs')
    scene = PlanScene(row, work / 'file-results' / (task + '-' + digest(row)[:16]))
    scene.read_task()
    file_id = next(item['file_id'] for item in scene.list_files()['files'] if item['path'] == 'large.docx')
    handle = scene.pin_file(file_id)['source_id']
    result = scene.read_file(handle)
    assert result['status'] == 'unreadable' and result['diagnostic'] == 'ValueError'


def test_web_file_scene_bounds_excel_metadata(tmp_path, monkeypatch):
    work = tmp_path / 'member-a' / 'work'
    task = 'task_excel_preview'
    monkeypatch.setenv('FM_WEB_WORKSPACE', str(work))
    row = spec(work, task, False)
    cells = ''.join(f'<row><c t="inlineStr"><is><t>entry-{number}</t></is></c></row>' for number in range(60))
    with zipfile.ZipFile(work / 'inputs' / 'sheet.xlsx', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('xl/worksheets/sheet1.xml', '<worksheet><sheetData>' + cells + '</sheetData></worksheet>')
    row['initial_snapshot'] = snapshot(work / 'inputs')
    scene = PlanScene(row, work / 'file-results' / (task + '-' + digest(row)[:16]))
    scene.read_task()
    file_id = next(item['file_id'] for item in scene.list_files()['files'] if item['path'] == 'sheet.xlsx')
    result = scene.read_file(scene.pin_file(file_id)['source_id'])
    assert result['status'] == 'readable'
    assert result['metadata']['row_count'] == 60
    assert len(result['metadata']['rows']) == 50 and result['metadata']['rows_truncated'] is True
