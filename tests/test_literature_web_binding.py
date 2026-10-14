"""Session/task isolation and fail-closed source/delivery boundaries (no model)."""
import importlib.util
import json
from pathlib import Path
import shutil
from uuid import uuid4
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import POPPLER, corpus
from pdf_tools import ROOT, FIELDS, digest
from web_pdf_tools import WebPdfScene

spec = importlib.util.spec_from_file_location('web_pdf_binding_test', ROOT / 'scenarios/literature-notes/web-binding.py')
BIND = importlib.util.module_from_spec(spec); spec.loader.exec_module(BIND)


@pytest.fixture
def binding(corpus):
    directory, _ = corpus
    run = ROOT / '.local/web/runs' / ('test-' + uuid4().hex)
    def create(question='问题一', **changes):
        request = {'content': [{'type': 'text', 'text': question}], 'resources': [], **changes}
        return BIND.prepare({'request': request, 'papers_dir': str(directory), 'output': str(run / 'tasks' / uuid4().hex)})
    yield create, directory
    shutil.rmtree(run, ignore_errors=True)


@POPPLER
def test_questions_bind_separate_preset_and_mcp_state(binding):
    create, _ = binding
    first, second = create('  问题一原始字节  '), create('问题二')
    assert first['directory'] != second['directory'] and first['task_sha256'] != second['task_sha256']
    a, b = WebPdfScene(Path(first['directory'])), WebPdfScene(Path(second['directory']))
    assert a.scene.list_pdfs()['question'] == '  问题一原始字节  '
    assert b.scene.list_pdfs()['question'] == '问题二'
    pid = a.scene.list_pdfs()['papers'][0]['paper_id']
    sid = a.scene.pin_pdf_context(pid, '1')['source_id']
    with pytest.raises(ToolError): b.scene.read_pinned_pdf_context(sid)
    assert a.scene.delivery != b.scene.delivery


@POPPLER
def test_unregistered_paths_versions_and_attachments_rejected_before_admission(binding):
    create, _ = binding
    for resources in ([{'resource_id': '/tmp/arbitrary.pdf'}], [{'resource_id': 'pdf:library', 'version': 'stale'}],
                      [{'resource_id': 'pdf:library'}, {'resource_id': 'pdf:library'}]):
        with pytest.raises(ValueError): create(resources=resources)
    with pytest.raises(ValueError): create(content=[{'type': 'file', 'receiptId': 'invented'}])
    assert create(resources=[{'resource_id': 'pdf:library'}])['sources'][0]['resource_id'] == 'pdf:library'


@POPPLER
def test_source_change_after_preview_rejects_execution(binding):
    create, directory = binding; value = create()
    task_dir = Path(value['directory']); BIND.check(task_dir)
    path = next(directory.glob('*.pdf')); path.write_bytes(path.read_bytes() + b'\n% changed')
    with pytest.raises(ValueError, match='变化'): BIND.check(task_dir)
    with pytest.raises(ValueError): WebPdfScene(task_dir)


@POPPLER
def test_automatic_review_and_final_synthesis_are_required_with_explicit_gap_delivery(binding):
    create, _ = binding; value = create(); scene = WebPdfScene(Path(value['directory']))
    with pytest.raises(ToolError): scene.deliver_research_notes('不能跳过复核')
    papers = [{'paper_id': p['paper_id'], 'fields': [{'name': f, 'status': 'not_extracted',
        'statement': '尚未提取。', 'citations': []} for f in FIELDS]} for p in scene.scene.list_pdfs()['papers']]
    draft = {'papers': papers, 'synthesis': '待复核'}
    preview = scene.preview_research_notes(draft)
    assert preview['status'] == 'pending_automatic_review' and scene.round == 1
    with pytest.raises(ToolError): scene.preview_research_notes(draft)
    for round_number in (1, 2):
        assert scene.round == round_number
        decisions = []
        for cid in scene.repair.targets:
            scene.read_claim_repair_packet(cid)
            decisions.append({'claim_id': cid, 'verdict': 'not_extracted', 'reason': '测试明确保留缺口'})
        scene.submit_claim_repair(decisions, '测试不提供科研结论')
    assert scene.phase == 'synthesis'
    with pytest.raises(ToolError): scene.deliver_research_notes('必须先读完整表')
    scene.read_final_synthesis()
    final = scene.deliver_research_notes('测试只验任务隔离与收据')
    assert final['status'] == 'delivered_with_gaps' and final['gap_count'] == 10
    assert final['human_review_required'] is False
    with pytest.raises(ToolError): scene.deliver_research_notes('不能重交付')
    (scene.directory / 'empty-events.jsonl').write_text('')
    with pytest.raises(ValueError, match='native delivery'): BIND.collect({'directory': str(scene.directory),
        'events': str(scene.directory / 'empty-events.jsonl')})

@POPPLER
def test_second_round_replays_original_quotes_with_claim_scope_and_rejected_diagnostics(binding):
    create, _ = binding; value = create(); scene = WebPdfScene(Path(value['directory']))
    papers = []
    for p in scene.scene.list_pdfs()['papers']:
        pin = scene.scene.pin_pdf_context(p['paper_id'], '1')
        context = scene.scene.read_pinned_pdf_context(pin['source_id'])
        alias = context['quote_spans'][0]['citation_id']
        papers.append({'paper_id': p['paper_id'], 'fields': [{'name': f, 'status': 'evidence',
            'statement': '测试待复核事实。', 'citations': [{'citation_id': alias}]} for f in FIELDS]})
    scene.preview_research_notes({'papers': papers, 'synthesis': '测试待复核'})
    cid = scene.repair.targets[0]
    for target in scene.repair.targets: scene.read_claim_repair_packet(target)
    # A real rejected proposal is retained as navigation, never permission.
    pending = scene.submit_claim_repair([{'claim_id': cid, 'verdict': 'revised', 'reason': '坏引用测试',
        'statement': '测试', 'citations': [{'citation_id': 'cite-' + '0' * 32}]}], '测试假设')
    assert pending['status'] == 'pending_claim_decisions'
    scene.submit_claim_repair([{'claim_id': target, 'verdict': 'withdrawn', 'reason': '测试撤回'}
                              for target in scene.repair.targets], '测试假设')
    packet = scene.read_claim_repair_packet(cid)
    assert scene.round == 2 and scene.repair.history is not None
    assert packet['previous_claim_context']['field']['status'] == 'evidence'
    assert packet['prior_rejected_proposal']['validation_error'].startswith('unknown citation_id')
    old = packet['previous_claim_context']['quotes'][0]
    assert (old['source_id'], old['quote_id']) in scene.repair.claim_allowed[cid]
    # The old context is replayed, but another claim cannot cite it without reading its packet.
    assert not scene.repair.claim_allowed[scene.repair.targets[-1]]


@POPPLER
def test_reading_tools_cannot_bypass_review_claim_quotas(binding):
    import asyncio
    from web_pdf_tools import make_server
    create, _ = binding; scene = WebPdfScene(Path(create()['directory']))
    server = make_server(scene)
    papers = [{'paper_id': p['paper_id'], 'fields': [{'name': f, 'status': 'not_extracted',
        'statement': '测试缺口', 'citations': []} for f in FIELDS]} for p in scene.scene.list_pdfs()['papers']]
    scene.preview_research_notes({'papers': papers, 'synthesis': '测试'})
    async def run():
        with pytest.raises(ToolError, match='phase'):
            await server._tool_manager.call_tool('prepare_pdf', {'paper_id': papers[0]['paper_id']}, context=None)
    asyncio.run(run())

def test_literature_web_launcher_fails_closed_without_task_binding(tmp_path):
    import socket
    import subprocess
    import sys
    directory = tmp_path / 'papers'
    directory.mkdir()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    run_id = uuid4().hex
    output = ROOT / '.local/web/runs' / run_id
    result = subprocess.run([sys.executable, str(ROOT / 'scenarios/literature-notes/run-web.py'),
        '--papers-dir', str(directory), '--port', str(port), '--run-id', run_id],
        cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert 'literature_web_not_integrated' in result.stderr
    assert not output.exists()
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1', port)) != 0
