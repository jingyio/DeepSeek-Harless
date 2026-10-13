"""PDF evidence safety and real protocol acceptance; no private corpus dependency."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile

import pytest
from mcp.server.mcpserver.exceptions import ToolError

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'scenarios/literature-notes'
sys.path.insert(0, str(HERE))
from pdf_tools import DEFAULT_QUESTION, FIELDS, PdfScene, inventory


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


RUN = module(HERE / 'run-pdf.py', 'test_pdf_run')
CHECK = module(HERE / 'check-pdf.py', 'test_pdf_check')
POPPLER = pytest.mark.skipif(not all(shutil.which(x) for x in ('pdfinfo', 'pdftotext')),
                            reason='real PDF tests require external Poppler')


def make_pdf(path, pages):
    """Generate a tiny public ASCII fixture with proper xref; no new test dependency."""
    objects = []
    ids = [4 + i * 2 for i in range(len(pages))]
    objects.append(b'<< /Type /Catalog /Pages 2 0 R >>')
    objects.append(('<< /Type /Pages /Count %s /Kids [%s] >>' % (
        len(ids), ' '.join('%s 0 R' % i for i in ids))).encode())
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    for page_id, text in zip(ids, pages):
        objects.append(('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                        '/Resources << /Font << /F1 3 0 R >> >> /Contents %s 0 R >>' % (page_id + 1)).encode())
        safe = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream = ('BT /F1 11 Tf 30 750 Td (' + safe + ') Tj ET').encode()
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
    pdf, offsets = bytearray(b'%PDF-1.4\n'), [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n')
    xref = len(pdf)
    pdf.extend(('xref\n0 %s\n0000000000 65535 f \n' % len(offsets)).encode())
    for offset in offsets[1:]:
        pdf.extend(('%010d 00000 n \n' % offset).encode())
    pdf.extend(('trailer\n<< /Size %s /Root 1 0 R >>\nstartxref\n%s\n%%%%EOF\n' % (len(offsets), xref)).encode())
    path.write_bytes(pdf)


@pytest.fixture
def corpus():
    with tempfile.TemporaryDirectory(dir=ROOT / '.local') as temporary:
        directory = Path(temporary) / 'papers'; directory.mkdir()
        make_pdf(directory / '研究 A.PDF', ['The method uses two independent trials and reports a limited evaluation.',
                                         'A second page contains limitations and additional evidence.'])
        make_pdf(directory / 'B.pdf', ['A different method evaluates tool execution with an independent protocol.'])
        yield directory, Path(temporary) / 'cache'


def task(directory, question=DEFAULT_QUESTION):
    return {'schema_version': 1, 'question': question, 'sources': inventory(directory)}


def draft(scene):
    papers = []
    for row in scene.list_pdfs()['papers']:
        source = scene.pin_pdf_context(row['paper_id'], 1)['source_id']
        context = scene.read_pinned_pdf_context(source)
        papers.append({'paper_id': row['paper_id'], 'fields': [
            {'name': name, 'status': 'evidence', 'statement': 'Protocol fixture statement.',
             'citations': [{'source_id': source, 'quote': context['text'].strip()}]} for name in FIELDS]})
    return {'papers': papers, 'synthesis': 'Protocol fixture, not scientific conclusions.'}


def test_inventory_accepts_uppercase_pdf_and_rejects_escape(corpus):
    directory, _ = corpus
    assert len(inventory(directory)['papers']) == 2
    (directory / 'escape.pdf').symlink_to(directory / 'B.pdf')
    with pytest.raises(ValueError, match='symlinks'):
        inventory(directory)


@POPPLER
def test_parse_all_pages_and_disk_cache_has_identical_content(corpus):
    directory, cache = corpus
    cold = PdfScene(directory, cache, task(directory))
    first = cold.prepare_pdf(next(iter(cold.rows)))
    assert len(first['pages']) == int(first['metadata']['Pages'])
    warm = PdfScene(directory, cache, task(directory))
    second = warm.prepare_pdf(next(iter(warm.rows)))
    assert {k: v for k, v in first.items() if k != 'cache_stats'} == {
        k: v for k, v in second.items() if k != 'cache_stats'}
    assert cold.stats['parser_runs'] == 1 and warm.stats['disk_cache_hits'] == 1
    assert warm.stats['parser_runs'] == 0
    assert all(path.stat().st_mode & 0o077 == 0 for path in cache.glob('*.json'))


@POPPLER
def test_corrupt_cache_is_reparsed_and_off_policy_ignores_disk(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    paper_id = next(iter(scene.rows)); scene.prepare_pdf(paper_id)
    next(cache.glob('*.json')).write_text('{broken', encoding='utf-8')
    repaired = PdfScene(directory, cache, task(directory)); repaired.prepare_pdf(paper_id)
    assert repaired.stats['invalid_cache_entries'] == repaired.stats['parser_runs'] == 1
    off = PdfScene(directory, cache, task(directory), cache_policy='off'); off.prepare_pdf(paper_id)
    assert off.stats['disk_cache_hits'] == 0 and off.stats['parser_runs'] == 1


@POPPLER
def test_new_question_reuses_only_parsed_text_and_has_no_old_handles(corpus):
    directory, cache = corpus
    old = PdfScene(directory, cache, task(directory))
    paper_id = next(iter(old.rows)); old_source = old.pin_pdf_context(paper_id, 1)['source_id']
    new = PdfScene(directory, cache, task(directory, 'A different research question'))
    new.prepare_pdf(paper_id)
    assert new.list_pdfs()['question'] == 'A different research question'
    assert new.stats['disk_cache_hits'] == 1
    with pytest.raises(ToolError, match='unknown'):
        new.read_pinned_pdf_context(old_source)


@POPPLER
@pytest.mark.parametrize('operation', ['read', 'preview', 'list'])
def test_source_mutation_invalidates_even_memory_cached_data(corpus, operation):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    value = draft(scene)
    paper_id = value['papers'][0]['paper_id']
    source = value['papers'][0]['fields'][0]['citations'][0]['source_id']
    (directory / scene.rows[paper_id]['filename']).write_bytes(b'%PDF-changed')
    with pytest.raises(ToolError, match='changed'):
        if operation == 'read': scene.read_pinned_pdf_context(source)
        elif operation == 'preview': scene.preview_research_notes(value)
        else: scene.list_pdfs()


@POPPLER
def test_window_continuation_and_search_do_not_claim_absence(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    paper_id = next(iter(scene.rows))
    pin = scene.pin_pdf_context(paper_id, 1, length=20)
    context = scene.read_pinned_pdf_context(pin['source_id'])
    assert len(context['text']) == 20 and context['next_start'] == 20 and not context['page_complete']
    rest = scene.pin_pdf_context(paper_id, 1, start=20)
    assert scene.read_pinned_pdf_context(rest['source_id'])['next_start'] is None
    assert scene.search_pdf_text(paper_id, 'nonexistent')['absence_claim_supported'] is False
    with pytest.raises(ToolError): scene.pin_pdf_context(paper_id, 0)
    with pytest.raises(ToolError): scene.pin_pdf_context(paper_id, 1, length=12001)


@POPPLER
@pytest.mark.parametrize('failure', ['wrong_quote', 'blank_quote', 'wrong_paper', 'unread', 'missing_paper', 'duplicate_field'])
def test_preview_rejects_bad_evidence(corpus, failure):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    value = draft(scene)
    field = value['papers'][0]['fields'][0]
    if failure == 'wrong_quote': field['citations'][0]['quote'] = 'Invented results that never appear in the source.'
    elif failure == 'blank_quote': field['citations'][0]['quote'] = ' ' * 20
    elif failure == 'wrong_paper':
        field['citations'][0]['source_id'] = value['papers'][1]['fields'][0]['citations'][0]['source_id']
    elif failure == 'unread': scene.delivered.clear()
    elif failure == 'missing_paper': value['papers'].pop()
    else: value['papers'][0]['fields'][1]['name'] = FIELDS[0]
    with pytest.raises(ToolError): scene.preview_research_notes(value)


@POPPLER
def test_quote_failure_identifies_all_fields_without_accepting_rewritten_text(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    value = draft(scene)
    for paper in value['papers']:
        paper['fields'][0]['citations'][0]['quote'] = 'Invented result, absent from the source.'
    with pytest.raises(ToolError) as exc:
        scene.preview_research_notes(value)
    report = json.loads(str(exc.value).split(': ', 1)[1])
    assert len(report['errors']) == len(value['papers'])
    assert {issue['paper_id'] for issue in report['errors']} == {paper['paper_id'] for paper in value['papers']}
    assert all(issue['field'] == 'research_goal' and issue['citation_index'] == 0
               and issue['reason'] == 'quote_not_verbatim' for issue in report['errors'])


@POPPLER
def test_issued_quote_selection_copies_raw_source_and_checks_provenance(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    value = draft(scene)
    for paper in value['papers']:
        for field in paper['fields']:
            source_id = field['citations'][0]['source_id']
            span = scene.read_pinned_pdf_context(source_id)['quote_spans'][0]
            field['citations'] = [{'source_id': source_id, 'quote_id': span['quote_id']}]
    preview = scene.preview_research_notes(value)
    for check in preview['citation_checks']:
        page = scene._document(check['paper_id'])['pages'][check['page'] - 1]
        assert check['quote'] == page[check['quote_start']:check['quote_end']]
    value['papers'][0]['fields'][0]['citations'][0]['quote_id'] = 'q9999999'
    with pytest.raises(ToolError, match='unknown quote_id'):
        scene.preview_research_notes(value)
    value['papers'][0]['fields'][0]['citations'][0] = dict(value['papers'][1]['fields'][0]['citations'][0])
    with pytest.raises(ToolError, match='wrong_paper'):
        scene.preview_research_notes(value)


@POPPLER
def test_script_pin_returns_same_read_evidence_without_new_model_work(corpus, monkeypatch):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    monkeypatch.setenv('SSS_PDF_SCRIPT_READ', '1')
    pin = scene.pin_pdf_context(next(iter(scene.rows)), 1)
    assert pin['context'] == scene.read_pinned_pdf_context(pin['source_id'])
    assert pin['source_id'] in scene.delivered


@POPPLER
def test_preview_reports_gaps_and_never_claims_entailment(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    value = draft(scene)
    preview = scene.preview_research_notes(value)
    assert preview['status'] == 'preview' and not preview['claim_support_assessed']
    assert preview['research_quality'] == 'unreviewed' and len(preview['citation_checks']) == 10
    assert 'PDF 物理页' in preview['markdown']
    assert '| 论文 | 研究目标 |' in preview['markdown']
    value['papers'][0]['fields'][0].update(status='not_extracted', citations=[])
    assert scene.preview_research_notes(value)['status'] == 'needs_review'


def test_runner_preview_does_not_load_key_or_enable_cloud(corpus, monkeypatch, capsys):
    directory, _ = corpus
    launches = []
    def launch(command, **kwargs):
        launches.append((command, kwargs))
        return type('Result', (), {'returncode': 0, 'stdout': '{}\n', 'stderr': ''})()
    monkeypatch.setattr(RUN.subprocess, 'run', launch)
    monkeypatch.setattr(RUN, 'runtime_snapshot', lambda: {'scope': 'unit_fixture'})
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    assert RUN.main(['--papers-dir', str(directory)]) == 0
    command, kwargs = launches[0]
    assert '--call-model' not in command and 'DEEPSEEK_API_KEY' not in kwargs['env']
    assert kwargs['env']['SSS_PDF_ROOT'] == str(directory)
    assert command[command.index('--budget-usd') + 1] == '0.25'


def test_paid_entry_keeps_key_in_environment_and_rejects_unverified_completion(corpus, monkeypatch, capsys):
    directory, _ = corpus
    (ROOT / '.local/runs').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        launches = []
        def launch(command, **kwargs):
            launches.append((command, kwargs))
            return type('Result', (), {'returncode': 0, 'stderr': '', 'stdout': json.dumps({
                'output_dir': temporary, 'status': 'done'}) + '\n'})()
        monkeypatch.setattr(RUN.subprocess, 'run', launch)
        monkeypatch.setattr(RUN, 'runtime_snapshot', lambda: {'scope': 'unit_fixture'})
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'fixture-environment-key')
        assert RUN.main(['--papers-dir', str(directory), '--call-model']) == 2
        command, kwargs = launches[0]
        assert '--call-model' in command
        assert kwargs['env']['DEEPSEEK_API_KEY'] == 'fixture-environment-key'
        assert 'fixture-environment-key' not in ' '.join(command)
        output = capsys.readouterr().out
        assert 'fixture-environment-key' not in output and 'missing_preview' in output


def test_rate_retry_preserves_failed_attempt_and_reduces_remaining_budget(corpus, monkeypatch):
    directory, _ = corpus
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        run = Path(temporary)
        (run / 'agent-events.jsonl').write_text(json.dumps({'type': 'turn/end', 'data': {
            'reason': {'error': {'code': 'RATE_LIMIT', 'status': 429}}}}) + '\n')
        (run / 'cost-ledger.jsonl').write_text(json.dumps({'response_status': 429}) + '\n')
        calls = []
        def launch(command, **kwargs):
            calls.append(list(command))
            return type('Result', (), {'returncode': 2, 'stderr': '', 'stdout': json.dumps({
                'output_dir': str(run), 'budget_accounted_usd': 0.02}) + '\n'})()
        monkeypatch.setattr(RUN.subprocess, 'run', launch)
        monkeypatch.setattr(RUN, 'runtime_snapshot', lambda: {'scope': 'unit_fixture'})
        monkeypatch.setattr(RUN.time, 'sleep', lambda delay: None)
        monkeypatch.setattr(RUN, 'collect_preview', lambda *_: {'status': 'missing_preview'})
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'fixture')
        assert RUN.main(['--papers-dir', str(directory), '--call-model', '--rate-retries', '1']) == 2
        assert len(calls) == 2
        assert float(calls[0][calls[0].index('--budget-usd') + 1]) == 0.25
        assert float(calls[1][calls[1].index('--budget-usd') + 1]) == pytest.approx(0.23)


@POPPLER
def test_real_harness_mcp_and_budget_use_generated_pdf_sources_only(corpus):
    directory, _ = corpus
    report = CHECK.check(directory)
    assert report['status'] == 'passed' and report['paid_api_requests'] == 0
    assert report['cold']['parser_runs'] == report['warm']['disk_cache_hits'] == 2
    assert report['warm']['parser_runs'] == 0 and report['source_unchanged']
    assert report['harness']['model_requests'] == report['harness']['budget_ledger_rows'] == 9
    assert report['harness']['tool_calls'] == 8
    assert report['harness']['delivery']['citation_count'] == 2

@POPPLER
def test_delivery_receipt_rejects_modified_artifact(corpus, monkeypatch):
    from types import SimpleNamespace
    from pdf_tools import save_private
    directory, cache = corpus
    with tempfile.TemporaryDirectory(dir=ROOT / '.local') as temporary:
        output = Path(temporary); (output / 'delivery').mkdir()
        scene = PdfScene(directory, cache, task(directory), delivery=output / 'delivery')
        receipt = scene.preview_research_notes(draft(scene))
        save_private(output / 'task.json', scene.task)
        save_private(output / 'input-snapshot.json', {'scope': 'receipt_fixture'})
        run = output / 'run'; run.mkdir(); (run / 'agent-events.jsonl').write_text('{}\n')
        monkeypatch.setattr('src.adapters.dsh_trajectory.extract_dsh_trace',
            lambda *_args, **_kwargs: SimpleNamespace(records=[SimpleNamespace(
                name='mcp__literature_pdf__preview_research_notes', observation=receipt)]))
        assert RUN.collect_preview(run, output)['status'] == 'preview'
        payload = json.loads(Path(receipt['artifact']).read_text())
        payload['draft']['synthesis'] = 'tampered'
        save_private(Path(receipt['artifact']), payload)
        with pytest.raises(ValueError, match='content/version mismatch'):
            RUN.collect_preview(run, output)


def test_question_is_appended_to_frozen_prompt_and_auto_task_is_source_bound(corpus, monkeypatch):
    from pdf_tools import digest
    directory, _ = corpus
    launches = []
    original_run = RUN.subprocess.run
    def launch(command, **kwargs):
        if Path(command[0]).name in ('pdfinfo', 'pdftotext'):
            return original_run(command, **kwargs)
        launches.append((command, kwargs))
        return type('Result', (), {'returncode': 0, 'stderr': '', 'stdout': ''})()
    monkeypatch.setattr(RUN.subprocess, 'run', launch)
    monkeypatch.setattr(RUN, 'runtime_snapshot', lambda: {'scope': 'unit_fixture'})
    assert RUN.main(['--papers-dir', str(directory), '--question', '独立科研问题', '--mode', 'execute',
                     '--manifest', 'fixture.json', '--auto-motif-task']) == 0
    command, kwargs = launches[0]
    motif = json.loads(Path(command[command.index('--task') + 1]).read_text())
    task_file = Path(kwargs['env']['SSS_PDF_TASK_FILE'])
    frozen = json.loads(task_file.read_text())
    assert motif['input_version'] == digest(frozen) and motif['intent'] == frozen['question']
    assert motif['source_versions']['mcp__literature_pdf__read_pinned_pdf_context'] == motif['source_versions']['mcp__literature_pdf__pin_pdf_context']
    assert len(motif['source_versions']['mcp__literature_pdf__pin_pdf_context']) == 2
    assert '独立科研问题' in (task_file.parent / 'prompt.md').read_text()



def test_local_budget_denial_is_not_provider_rate_retry(corpus):
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        run = Path(temporary)
        (run / 'agent-events.jsonl').write_text(json.dumps({'type': 'turn/end', 'data': {
            'reason': {'error': {'code': 'RATE_LIMIT', 'status': 429}}}}) + '\n')
        (run / 'cost-ledger.jsonl').write_text(json.dumps({'response_status': 200}) + '\n')
        assert RUN.rate_limited(run) is False
        (run / 'cost-ledger.jsonl').write_text(json.dumps({'response_status': 429}) + '\n')
        assert RUN.rate_limited(run) is True

@POPPLER
def test_decimal_page_locator_is_strict_and_preserves_source_identity(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    paper_id = scene.list_pdfs()['papers'][0]['paper_id']
    assert scene.pin_pdf_context(paper_id, '1') == scene.pin_pdf_context(paper_id, 1)
    for locator in ('0', '01', '-1', '1.0', ' 1', '1e0', '10000000'):
        with pytest.raises(ToolError, match='canonical'):
            scene.pin_pdf_context(paper_id, locator)


@POPPLER
def test_document_scope_keeps_exact_window_and_parser_guards(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    paper_id = scene.list_pdfs()['papers'][0]['paper_id']
    first = scene.pin_pdf_context(paper_id, '1', length=20)
    second = scene.pin_pdf_context(paper_id, '1', start=20, length=20)
    assert first['document_version_sha256'] == second['document_version_sha256']
    assert first['source_id'] != second['source_id']
    assert first['version_sha256'] != second['version_sha256']
    read = scene.read_pinned_pdf_context(first['source_id'])
    assert read['start'] == 0 and read['end'] == 20
    scene.profile = {**scene.profile, 'quote_spans_version': 999}
    assert scene.document_version(paper_id) != first['document_version_sha256']
    with pytest.raises(ToolError, match='derived source changed'):
        scene.read_pinned_pdf_context(first['source_id'])


def test_pdf_string_anchor_reaches_existing_online_closed_read_and_integer_defers():
    import subprocess
    code = r'''
      import fs from 'node:fs';
      import {compileLocalPrograms,digest,proposeReadyBatch,validateOnlineManifest}
        from './src/motif_core/online_skill_runtime.mjs';
      const pin='mcp__literature_pdf__pin_pdf_context',read='mcp__literature_pdf__read_pinned_pdf_context';
      const raw=JSON.parse(fs.readFileSync('scenarios/literature-notes/pdf-contracts.json'));
      const artifact={motif_id:'unit-fixture-only',certified_digest:'a'.repeat(64),tools:[pin,read],
        supporting_task_count:2,validation_task_fingerprint:'unit-fixture-no-scientific-evidence',
        transfer_evidence:[{from_tool:pin,from_field:'source_id',to_tool:read,to_param:'source_id'}]};
      artifact.local_programs=compileLocalPrograms(artifact);
      const contracts=Object.fromEntries([pin,read].map(tool=>[tool,{...raw[tool],
        default_params:Object.fromEntries(raw[tool].default_params??[])}]));
      const manifest={schema_version:1,source_library_digest:'b'.repeat(64),artifacts:[artifact],contracts,
        slot_rules:{},version_fields:{[pin]:'version_sha256',[read]:'version_sha256'}};
      manifest.manifest_digest=digest(manifest);validateOnlineManifest(manifest);
      const task={schema_version:1,task_id:'unit',session_id:'unit',intent:'read source',input_version:'input',
        bindings:{},source_versions:{[pin]:['v1'],[read]:['v1']}};
      const row={name:pin,callId:'one',ok:true,arguments:{paper_id:'pdf:fixture',page:'1'},
        output:{source_id:'issued-fixture'},sourceVersion:'v1',inputVersion:'input'};
      const args={manifest,task,history:[row],availableTools:new Map([[read,{name:read,
        parameters:{type:'object',required:['source_id'],properties:{source_id:{type:'string'}}}}]]),
        similarity:async()=>{throw Error('embedding must not be used');},minSimilarity:.8,minMargin:.1};
      if((await proposeReadyBatch(args)).length!==1)throw Error('string locator did not match');
      if((await proposeReadyBatch({...args,history:[{...row,arguments:{...row.arguments,page:1}}]})).length!==0)
        throw Error('integer should not match existing string-only IR');
      if((await proposeReadyBatch({...args,history:[{...row,sourceVersion:'changed'}]})).length!==0)
        throw Error('source version drift must defer');
    '''
    result = subprocess.run(['node','--input-type=module','-'], input=code,text=True,capture_output=True,cwd=ROOT)
    assert result.returncode == 0, result.stderr

@POPPLER
def test_model_selected_plan_validates_all_windows_before_issuing_citations(corpus):
    from mcp.server.mcpserver.exceptions import ToolError
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    pid = next(iter(scene.rows)); version = scene.document_version(pid)
    good = {'page': '1', 'start': 0, 'length': 1200}
    with pytest.raises(ToolError):
        scene.read_pdf_evidence_plan(pid, version, [good, {'page': '999', 'start': 0, 'length': 1200}])
    assert not scene.delivered
    duplicate = scene.read_pdf_evidence_plan(pid, version, [good, good])
    assert len(duplicate['contexts']) == 1
    assert duplicate['normalization']['requested_to_contexts'] == [[0], [0]]
    value = scene.read_pdf_evidence_plan(pid, version, [good])
    context = value['contexts'][0]
    assert context == {'source_id': context['source_id'], **scene.read_pinned_pdf_context(context['source_id'])}
    assert not value['learned_motif'] and not value['scientific_truth_certified']
    with pytest.raises(ToolError): scene.read_pdf_evidence_plan(pid, '0' * 64, [good])

@pytest.mark.parametrize('table', [False, True])
def test_geometry_repairs_only_prose_and_preserves_every_word_and_page(table):
    from pdf_layout import repair_columns
    words = [str(i) if table else 'word' + str(i) for i in range(84)]
    lines = []
    for i in range(12):
        left = i % 2 == 0; x = 50 if left else 320
        parts = ''.join(f'<word xMin="{x+j*27}" xMax="{x+j*27+23}">{w}</word>' for j,w in enumerate(words[i*7:(i+1)*7]))
        lines.append(f'<line xMin="{x}" xMax="{x+200}">{parts}</line>')
    xml = ('<html xmlns="http://www.w3.org/1999/xhtml"><page width="612" height="792">'
           '<block xMin="50" xMax="558">'+''.join(lines)+'</block></page></html>').encode()
    original = ' '.join(words)
    pages, repairs = repair_columns(xml, [original])
    assert sorted(pages[0].split()) == sorted(words)
    assert bool(repairs) is (not table)
    if not table:
        assert pages[0].index('word77') > pages[0].index('word70')
        assert pages[0].index('word7 ') > pages[0].index('word70')
    else: assert pages == [original]
    with pytest.raises(ValueError, match='page counts'): repair_columns(xml, [original, 'extra'])

@POPPLER
def test_bbox_crash_keeps_valid_plain_text_with_unverified_layout_warning(corpus, monkeypatch):
    import subprocess
    directory, cache = corpus
    source = PdfScene(directory, cache, task(directory), cache_policy='off')
    original = subprocess.run
    def run(command, **kwargs):
        if '-bbox-layout' in command: raise subprocess.CalledProcessError(-6, command)
        return original(command, **kwargs)
    monkeypatch.setattr(subprocess, 'run', run)
    pid = next(iter(source.rows)); prepared = source.prepare_pdf(pid)
    assert prepared['layout_status'] == 'bbox_unavailable_original_text_retained_layout_unverified'
    assert not prepared['layout_repairs']
    result = source.read_pdf_evidence_plan(pid, prepared['document_version_sha256'], [{'page': '1', 'start': 0, 'length': 1200}])
    assert result['contexts'][0]['text'] and not result['scientific_truth_certified']

@POPPLER
def test_batch_final_guard_rejects_mid_read_mutation_and_clears_local_scope(corpus, monkeypatch):
    directory, cache = corpus; source = PdfScene(directory, cache, task(directory))
    pid = next(iter(source.rows)); version = source.document_version(pid)
    read = source.read_pinned_pdf_context
    def change(sid):
        result = read(sid)
        path = directory / source.rows[pid]['filename']; path.write_bytes(path.read_bytes() + b'\n% mutation')
        return result
    monkeypatch.setattr(source, 'read_pinned_pdf_context', change)
    with pytest.raises(ToolError, match='changed'):
        source.read_pdf_evidence_plan(pid, version, [{'page': '1', 'start': 0, 'length': 1200}])
    assert source._read_scope.get() is None
    with pytest.raises(ToolError, match='changed'): source._current(pid)


@POPPLER
def test_verified_read_scope_does_not_disable_guard_in_another_thread(corpus):
    from concurrent.futures import ThreadPoolExecutor
    directory, cache = corpus; source = PdfScene(directory, cache, task(directory))
    pid = next(iter(source.rows)); row, path = source._current(pid)
    token = source._read_scope.set((pid, row, path))
    try:
        path.write_bytes(path.read_bytes() + b'\n% mutation')
        with ThreadPoolExecutor(max_workers=1) as executor:
            with pytest.raises(ToolError, match='changed'): executor.submit(source._current, pid).result()
    finally: source._read_scope.reset(token)
