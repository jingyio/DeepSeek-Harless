"""Session upload/version/restart diagnostics with real PDF extraction, no model."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import pytest
from test_literature_pdf import make_pdf

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'scenarios/literature-notes'
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('literature_session_tools', HERE / 'session_tools.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
pytestmark = pytest.mark.skipif(not shutil.which('pdfinfo') or not shutil.which('pdftotext'), reason='Poppler required')


@pytest.fixture
def scope():
    parent = ROOT / '.local/literature-session-tests'; parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as raw:
        work = Path(raw) / 'work'; sources = work / 'inputs'; sources.mkdir(parents=True)
        binding = work / 'literature'; binding.mkdir()
        pdf = sources / 'doc_1-paper.pdf'
        make_pdf(pdf, ['Independent public fixture: experiment A uses 2 seeds and requires replication.'])
        task = {'schema_version': 1, 'question': 'Inspect the fixture evidence.', 'sources': module.inventory(sources)}
        module.save_private(binding / 'task.json', task)
        module.save_private(work / 'approved-inputs.json', {'files': {pdf.name: hashlib.sha256(pdf.read_bytes()).hexdigest()}})
        yield binding, pdf


def test_private_parser_cache_and_handles_survive_the_same_task_restart(scope):
    binding, _ = scope
    a = module.SessionLiteratureScene(binding)
    pid = a.list_pdfs()['papers'][0]['paper_id']
    a.scene.prepare_pdf(pid)
    pin = a.scene.pin_pdf_context(pid, '1')
    read = a.scene.read_pinned_pdf_context(pin['source_id'])
    assert 'experiment A' in read['text']
    assert a.delegate.scene.cache == binding / 'cache'
    b = module.SessionLiteratureScene(binding)
    restored = b.scene.read_pinned_pdf_context(pin['source_id'])
    assert module.stable_result(restored) == module.stable_result(read)
    assert b.delegate.scene.cache == binding / 'cache'
    assert len(json.loads((binding / 'operations.json').read_text())['operations']) == 5


def test_changed_source_and_invented_task_root_cannot_reuse_old_evidence(scope):
    binding, pdf = scope
    a = module.SessionLiteratureScene(binding)
    a.list_pdfs()
    pdf.write_bytes(pdf.read_bytes() + b'\n% changed')
    with pytest.raises(module.ToolError, match='sources changed'):
        a.list_pdfs()
    task = json.loads((binding / 'task.json').read_text()); task['sources']['root'] = str(binding.parent.parent)
    module.save_private(binding / 'task.json', task)
    with pytest.raises(module.ToolError, match='this Session'):
        module.SessionLiteratureScene(binding).list_pdfs()


def test_failed_calls_and_code_version_are_not_erased_by_restart(scope):
    binding, _ = scope
    a = module.SessionLiteratureScene(binding)
    with pytest.raises(module.ToolError):
        a.scene.read_pinned_pdf_context('source-unissued')
    b = module.SessionLiteratureScene(binding)
    b.list_pdfs()
    ops = json.loads((binding / 'operations.json').read_text())['operations']
    assert not ops[0]['outcome']['ok'] and len(ops) == 2
    journal = json.loads((binding / 'operations.json').read_text()); journal['code_sha256'] = '0' * 64
    module.save_private(binding / 'operations.json', journal)
    with pytest.raises(module.ToolError, match='version changed'):
        module.SessionLiteratureScene(binding).list_pdfs()


def test_uncompleted_operation_is_recovered_only_inside_the_same_frozen_task(scope):
    binding, _ = scope
    a = module.SessionLiteratureScene(binding); listing = a.list_pdfs()
    journal = json.loads((binding / 'operations.json').read_text()); journal['operations'][0]['outcome'] = None
    module.save_private(binding / 'operations.json', journal)
    b = module.SessionLiteratureScene(binding); assert b.list_pdfs() == listing
    assert json.loads((binding / 'operations.json').read_text())['operations'][0]['outcome']['ok']
