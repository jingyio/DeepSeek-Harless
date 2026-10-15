"""The historical citation tool chain only sees a task's approved input copy."""
from pathlib import Path
import asyncio
import hashlib
import json
import os
import sys
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from mcp import Client, StdioServerParameters

from scenarios.paper_proofreading.server import PaperEvidence, PaperOutput, create_citation_evidence, create_server
from src.adapters.paper_renderer import INPUT_SCHEMA, audit_pdf_content_coverage


def make_paper(root: Path):
    root.mkdir()
    (root / 'main.tex').write_text(
        r'\documentclass{article}\begin{document}\cite{alpha}\bibliography{references}\end{document}',
        encoding='utf-8')
    (root / 'references.bib').write_text('@article{alpha, title={A}, year={2020}}', encoding='utf-8')
    return create_citation_evidence(PaperEvidence(root))


def test_citation_chain_is_versioned_and_bound_to_one_input_directory(tmp_path):
    first = make_paper(tmp_path / 'first')
    second = make_paper(tmp_path / 'second')
    pin = first.pin('current', 'sources')
    batch = first.inspect_citations(pin['source_id'])
    records = first.read_citation_records(batch['citation_id'])
    assert batch['diagnostic']['cited_keys'] == ['alpha']
    assert [row['key'] for row in records['records']] == ['alpha']
    with pytest.raises(ValueError, match='unknown|expired'):
        second.read_citation_records(batch['citation_id'])
    (tmp_path / 'first' / 'references.bib').write_text('@article{alpha, title={Changed}}')
    with pytest.raises(ValueError, match='version changed'):
        first.read_citation_records(batch['citation_id'])


def test_historical_local_citation_sequence_reuses_bib_script_without_network(tmp_path, monkeypatch):
    first = make_paper(tmp_path / 'first')
    second = make_paper(tmp_path / 'second')
    monkeypatch.setattr(first, '_fetch_preprints', lambda *_: pytest.fail('local batch must not fetch metadata'))
    packet = first.collect_local_citation_evidence('current')
    assert packet['internal_steps'] == [
        'pin_sources', 'inspect_active_citations', 'read_original_bibliography']
    assert packet['diagnostic']['cited_keys'] == ['alpha']
    assert [row['key'] for row in packet['references']['records']] == ['alpha']
    assert packet['references']['records'][0]['raw_bibtex'].startswith('@article{alpha')
    assert packet['references']['version_sha256'] == packet['version_sha256']
    assert 'metadata' not in packet and packet['formal_publication_confirmed'] is False
    assert packet['title_needs_review_keys'] == []
    assert first.read_citation_records(packet['citation_id'])['version_sha256'] == packet['version_sha256']
    with pytest.raises(ValueError, match='unknown|expired'):
        second.read_citation_records(packet['citation_id'])
    (tmp_path / 'first' / 'references.bib').write_text('@article{alpha, title={Changed}}')
    with pytest.raises(ValueError, match='version changed'):
        first.read_citation_records(packet['citation_id'])


def test_local_citation_packet_flags_titles_needing_model_display(tmp_path):
    service = make_paper(tmp_path / 'paper')
    (tmp_path / 'paper/references.bib').write_text(
        r'@article{alpha, title={\tau-bench}, year={2024}}', encoding='utf-8')
    packet = service.collect_local_citation_evidence('current')
    assert packet['title_needs_review_keys'] == ['alpha']


def test_complete_bibliography_is_bounded_and_source_versioned(tmp_path):
    first = make_paper(tmp_path / 'first')
    bib = tmp_path / 'first' / 'references.bib'
    bib.write_text('\n'.join(f'@article{{entry{i}, title={{Title {i}}}}}' for i in range(25)) +
                   '\n@article{entry0, title={Duplicate}}', encoding='utf-8')
    pin = first.pin('current', 'sources')
    page1 = first.read_bibliography_page(pin['source_id'], 1)
    page3 = first.read_bibliography_page(pin['source_id'], 3)
    assert page1['entry_count'] == 26
    assert page1['page_count'] == 3
    assert [r['index'] for r in page1['records']] == list(range(1, 13))
    assert [r['key'] for r in page3['records']] == ['entry24', 'entry0']
    assert page3['authenticity_checked'] is False
    resolved = first.resolve_bibliography_keys(pin['source_id'], ['entry12', 'entry0'])
    assert resolved['records']['entry12']['index'] == 13
    assert resolved['duplicate_keys']['entry0'] == [1, 26]
    with pytest.raises(ValueError, match='out_of_range'):
        first.read_bibliography_page(pin['source_id'], 4)
    bib.write_text(bib.read_text() + '\n@article{new, title={Later}}', encoding='utf-8')
    with pytest.raises(ValueError, match='version changed'):
        first.read_bibliography_page(pin['source_id'], 1)


def test_ambiguous_main_and_arbitrary_case_are_rejected(tmp_path):
    root = tmp_path / 'inputs'
    root.mkdir()
    (root / 'part_a.tex').write_text('A')
    (root / 'part_b.tex').write_text('B')
    citations = create_citation_evidence(PaperEvidence(root))
    with pytest.raises(ValueError, match='unambiguous'):
        citations.pin('current', 'sources')
    current = make_paper(tmp_path / 'current')
    with pytest.raises(ValueError, match='authorised'):
        current.pin('foreign', 'sources')


def test_pdf_export_requires_this_task_approval_and_current_report_version(tmp_path):
    workspace = tmp_path / 'session'
    inputs = workspace / 'inputs'
    inputs.mkdir(parents=True)
    report = {key: [] if key in {'references', 'sources', 'issues'} else ''
              for key in INPUT_SCHEMA['required_root']}
    report['reference_count'] = 0
    report['citation_checks'] = {key: {'result': '', 'evidence': '', 'limitation': ''}
                                 for key in INPUT_SCHEMA['citation_checks_required']}
    raw = json.dumps(report).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (inputs / 'audit.json').write_bytes(raw)
    (workspace / 'approved-inputs.json').write_text(json.dumps({'files': {'audit.json': digest}}))
    grant = {'schema_version': 1, 'task_id': 'task-a', 'allow_output': False, 'audit_sha256': digest}
    (workspace / 'paper-output-grant.json').write_text(json.dumps(grant))
    output = PaperOutput(PaperEvidence(inputs), None)
    assert output.read_audit()['report_sha256'] == digest
    with pytest.raises(ValueError, match='not_authorized'):
        output.export(digest)
    grant['allow_output'] = True
    (workspace / 'paper-output-grant.json').write_text(json.dumps(grant))
    with pytest.raises(ValueError, match='stale_audit'):
        output.export('0' * 64)
    with pytest.raises(ValueError, match='not_deployed'):
        output.export(digest)
    (inputs / 'audit.json').write_bytes(raw + b' ')
    with pytest.raises(ValueError, match='approval_changed|file_version_changed_from_task_admission'):
        output.read_audit()


def test_model_generated_audit_is_bound_to_task_sources_and_grant(tmp_path):
    workspace = tmp_path / 'session'
    inputs = workspace / 'inputs'
    inputs.mkdir(parents=True)
    manuscript = b'\\cite{alpha}'
    (inputs / 'main.tex').write_bytes(manuscript)
    sources = {'main.tex': hashlib.sha256(manuscript).hexdigest()}
    (workspace / 'approved-inputs.json').write_text(json.dumps({'files': sources}))
    grant = {'schema_version': 1, 'task_id': 'task-a', 'allow_output': False,
             'audit_sha256': None}
    grant_path = workspace / 'paper-output-grant.json'
    grant_path.write_text(json.dumps(grant))
    output = PaperOutput(PaperEvidence(inputs), None)
    with pytest.raises(ValueError, match='not_authorized'):
        output.stage({'scope': 'Current manuscript'})
    grant['allow_output'] = True
    grant_path.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match='not_ready'):
        output.read_audit()
    rejected = output.stage({'references': [{'number': 1, 'key': 'alpha',
        'short_title': 'Unresolved alpha', 'status': '存疑', 'priority': 'P2',
        'source_ids': [], 'explanation': 'Local citation only'}]})
    assert rejected['staged'] is False
    assert rejected['missing_fields'] == ['references[0].evidence_files']
    assert rejected['draft_sha256'] is None
    assert not list((workspace / 'outputs' / 'paper-audits').rglob('draft.json'))
    first = output.stage({'scope': 'Only the uploaded main.tex was checked.'})
    assert first['staged'] is True
    extra = output.stage({'issues': [{'priority': 'P2', 'number_or_location': 'main.tex',
        'problem': 'Missing source', 'finding': 'Citation has no bibliography entry',
        'recommended_fix': 'Check the source', 'evidence': 'main.tex'}]}, first['draft_sha256'])
    assert extra['staged'] is False
    assert extra['validation_error'] == 'paper_audit_patch_extra_record_fields'
    assert extra['extra_fields'] == ['issues[0].evidence']
    assert extra['draft_sha256'] == first['draft_sha256']
    extra_check = output.stage({'citation_checks': {
        'duplicate_entries_detail': {'result': 'extra', 'evidence': 'main.tex',
                                     'limitation': 'none'}}}, first['draft_sha256'])
    assert extra_check['staged'] is False
    assert extra_check['validation_error'] == 'paper_audit_patch_extra_record_fields'
    assert extra_check['extra_fields'] == ['citation_checks.duplicate_entries_detail']
    too_many = output.stage({'notes': ['check'] * 10}, first['draft_sha256'])
    assert too_many == {'staged': False, 'draft_sha256': first['draft_sha256'],
                        'validation_error': 'paper_audit_batch_limit',
                        'field': 'notes', 'limit': 8, 'received': 10,
                        'semantic_quality_accepted': False}
    with pytest.raises(ValueError, match='stale_paper_audit_draft'):
        output.stage({'notes': ['stale writer']}, '0' * 64)
    checks = {key: {'result': 'not checked', 'evidence': 'main.tex',
                    'limitation': 'No external bibliography source supplied'}
              for key in INPUT_SCHEMA['citation_checks_required']}
    second = output.stage({'references': [{'number': 1, 'key': 'alpha',
        'short_title': 'Unresolved alpha', 'status': '存疑', 'priority': 'P2',
        'source_ids': [], 'explanation': 'Citation key is present; metadata was not supplied.',
        'evidence_files': ['main.tex']}], 'citation_checks': checks,
        'notes': ['No external metadata was verified']}, first['draft_sha256'])
    with pytest.raises(ValueError, match='stale_paper_audit_draft'):
        output.finalize(first['draft_sha256'])
    finalized = output.finalize(second['draft_sha256'])
    assert output.read_audit()['report_sha256'] == finalized['report_sha256']
    assert output.read_audit()['report']['reference_count'] == 1
    assert (inputs / 'main.tex').read_bytes() == manuscript
    with pytest.raises(ValueError, match='already_finalized'):
        output.stage({'notes': ['later']}, second['draft_sha256'])
    grant['task_id'] = 'task-b'
    grant_path.write_text(json.dumps(grant))
    with pytest.raises(ValueError, match='not_ready'):
        output.read_audit()
    grant['task_id'] = 'task-a'
    grant_path.write_text(json.dumps(grant))
    (inputs / 'main.tex').write_bytes(b'changed')
    with pytest.raises(ValueError, match='approval_changed|file_version_changed_from_task_admission'):
        output.read_audit()


def test_report_staging_mcp_schema_exposes_field_types(tmp_path):
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    stage = next(tool for tool in asyncio.run(create_server(inputs).list_tools())
                 if tool.name == 'stage_current_audit')
    fields = stage.input_schema['properties']
    assert 'string' in {branch['type'] for branch in fields['scope']['anyOf']}
    assert 'array' in {branch['type'] for branch in fields['notes']['anyOf']}
    assert 'object' in {branch['type'] for branch in fields['citation_checks']['anyOf']}
    assert 'integer' in {branch['type'] for branch in fields['remove_reference_number']['anyOf']}


def test_finalization_reports_partial_approved_bibliography_count(tmp_path):
    workspace = tmp_path / 'session'
    inputs = workspace / 'inputs'
    inputs.mkdir(parents=True)
    (inputs / 'main.tex').write_text(r'\cite{alpha}\bibliography{references}', encoding='utf-8')
    (inputs / 'references.bib').write_text(
        '@article{alpha, title={A}}\n@article{beta, title={B}}\n'
        '@article{beta, title={Duplicate B}}', encoding='utf-8')
    approved = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    (workspace / 'approved-inputs.json').write_text(json.dumps({'files': approved}))
    (workspace / 'paper-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'task-coverage', 'allow_output': True,
        'audit_sha256': None}))
    output = PaperOutput(PaperEvidence(inputs), None)
    checks = {key: {'result': '未完成', 'evidence': 'main.tex', 'limitation': '仅局部核对'}
              for key in INPUT_SCHEMA['citation_checks_required']}
    draft = output.stage({'scope': 'Only alpha was checked.', 'references': [{
        'number': 1, 'key': 'alpha', 'short_title': 'A', 'status': '存疑',
        'priority': 'P2', 'source_ids': [], 'explanation': '未核验真实性。',
        'evidence_files': ['references.bib']}], 'citation_checks': checks})
    assert draft['staged'] is True
    result = asyncio.run(create_server(inputs).call_tool('finalize_current_audit', {
        'expected_draft_sha256': draft['draft_sha256']}))
    finalized = json.loads(result.content[0].text)
    assert finalized['bibliography_coverage'] == {
        'source_entry_count': 3, 'source_unique_key_count': 2,
        'report_reference_count': 1, 'unreported_unique_keys_lower_bound': 1,
        'count_insufficient': True, 'semantic_quality_accepted': False}


def test_compact_bibliography_stage_copies_only_current_pinned_source(tmp_path):
    workspace = tmp_path / 'session'
    inputs = workspace / 'inputs'
    inputs.mkdir(parents=True)
    (inputs / 'main.tex').write_text(r'\cite{alpha}\bibliography{references}', encoding='utf-8')
    (inputs / 'references.bib').write_text(
        '@article{alpha, title={A {Current} Title}, year={2020}}\n'
        '@article{beta, title={Another Title}, year={2021}}\n'
        r'@article{gamma, title={\tau-bench}, year={2022}}', encoding='utf-8')
    approved = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    (workspace / 'approved-inputs.json').write_text(json.dumps({'files': approved}))
    (workspace / 'paper-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'task-a', 'allow_output': True, 'audit_sha256': None}))
    files = PaperEvidence(inputs)
    output = PaperOutput(files, None)
    citations = create_citation_evidence(files)
    source_id = citations.pin('current', 'sources')['source_id']
    decision = {'index': 1, 'key': 'alpha', 'status': '存疑', 'priority': 'P2',
                'explanation': '尚未完成权威来源核验。'}
    first = output.stage_bibliography(citations, source_id,
                                      [{key: value for key, value in decision.items() if key != 'index'}])
    assert first['staged'] is True and first['reference_count'] == 1
    draft = json.loads((workspace / 'outputs/paper-audits/task-a/draft.json').read_text())
    row = draft['report']['references'][0]
    assert row == {'number': 1, 'key': 'alpha', 'short_title': 'A Current Title',
                   'status': '存疑', 'priority': 'P2', 'source_ids': [],
                   'explanation': '原始 BibTeX 条目 #1；尚未完成权威来源核验。',
                   'evidence_files': ['references.bib']}
    with pytest.raises(ValueError, match='stale_paper_audit_draft'):
        output.stage_bibliography(citations, source_id,
                                  [dict(decision, index=2, key='beta')], 'bad')
    with pytest.raises(ValueError, match='assessment_invalid'):
        output.stage_bibliography(citations, source_id,
                                  [dict(decision, status='已确认', source_ids='invented')],
                                  first['draft_sha256'])
    wrong_key = output.stage_bibliography(citations, source_id,
                                          [dict(decision, index=2)], first['draft_sha256'])
    assert wrong_key['staged'] is False
    assert wrong_key['validation_error'] == 'paper_bibliography_index_key_mismatch'
    assert wrong_key['source_key'] == 'beta'
    assert wrong_key['draft_sha256'] == first['draft_sha256']
    missing = output.stage_bibliography(citations, source_id,
                                        [dict((key, value) for key, value in decision.items()
                                              if key != 'index') | {'key': 'not-in-bib'}],
                                        first['draft_sha256'])
    assert missing['validation_error'] == 'paper_bibliography_key_missing'
    second = output.stage_bibliography(citations, source_id,
                                       [dict(key='beta', status='存疑', priority='P2',
                                             explanation='尚未完成权威来源核验。')])
    assert second['reference_count'] == 2
    with pytest.raises(ValueError, match='stale_paper_audit_draft'):
        output.stage_bibliography(citations, source_id,
                                  [dict(key='beta', status='存疑', priority='P2',
                                        explanation='旧 SHA 不得自动绑定。')],
                                  first['draft_sha256'])
    needs_title = output.stage_bibliography(citations, source_id,
                                            [dict(decision, index=3, key='gamma')],
                                            second['draft_sha256'])
    assert needs_title['staged'] is False
    assert needs_title['validation_error'] == 'paper_bibliography_title_needs_review'
    assert needs_title['missing_title_index'] == 3
    assert needs_title['draft_sha256'] == second['draft_sha256']
    third = output.stage_bibliography(citations, source_id,
                                      [dict(decision, index=3, key='gamma', short_title='τ-bench')],
                                      second['draft_sha256'])
    assert third['staged'] is True and third['reference_count'] == 3
    with pytest.raises(ValueError, match='version changed|version_changed'):
        (inputs / 'references.bib').write_text('@article{changed, title={Wrong}}')
        output.stage_bibliography(citations, source_id, [decision], third['draft_sha256'])


def test_compact_bibliography_stages_many_unique_keys_in_one_request(tmp_path):
    workspace = tmp_path / 'session'
    inputs = workspace / 'inputs'
    inputs.mkdir(parents=True)
    (inputs / 'main.tex').write_text(r'\cite{k0}\bibliography{references}', encoding='utf-8')
    (inputs / 'references.bib').write_text('\n'.join(
        f'@article{{k{i}, title={{Real Title {i}}}}}' for i in range(34)), encoding='utf-8')
    approved = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    (workspace / 'approved-inputs.json').write_text(json.dumps({'files': approved}))
    (workspace / 'paper-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'task-many', 'allow_output': True, 'audit_sha256': None}))
    files = PaperEvidence(inputs)
    citations = create_citation_evidence(files)
    source_id = citations.pin('current', 'sources')['source_id']
    output = PaperOutput(files, None)
    unbacked = output.stage_bibliography(citations, source_id, [
        {'key': 'k0', 'status': '已确认', 'priority': '—',
         'explanation': '仅看上传原文。'}])
    assert unbacked['staged'] is False
    assert unbacked['validation_error'] == 'paper_audit_confirmed_without_source'
    assert unbacked['keys'] == ['k0']
    assert not (workspace / 'outputs/paper-audits/task-many/draft.json').exists()
    result = output.stage_bibliography(citations, source_id, [
        {'key': f'k{i}', 'status': '存疑', 'priority': 'P2',
         'explanation': '需要权威来源核验。'} for i in range(34)])
    assert result['staged'] is True and result['reference_count'] == 34
    report = json.loads((workspace / 'outputs/paper-audits/task-many/draft.json').read_text())['report']
    assert [r['number'] for r in report['references']] == list(range(1, 35))
    assert report['references'][-1]['short_title'] == 'Real Title 33'


def test_generated_report_duplicate_key_can_be_rejected_and_repaired(tmp_path):
    workspace = tmp_path / 'session'
    inputs = workspace / 'inputs'
    inputs.mkdir(parents=True)
    manuscript = b'\\cite{alpha,beta}'
    (inputs / 'main.tex').write_bytes(manuscript)
    (workspace / 'approved-inputs.json').write_text(json.dumps({
        'files': {'main.tex': hashlib.sha256(manuscript).hexdigest()}}))
    (workspace / 'paper-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'task-a', 'allow_output': True,
        'audit_sha256': None}))
    output = PaperOutput(PaperEvidence(inputs), None)
    checks = {key: {'result': 'not checked', 'evidence': 'main.tex',
                    'limitation': 'local source only'}
              for key in INPUT_SCHEMA['citation_checks_required']}

    def reference(number, key):
        return {'number': number, 'key': key, 'short_title': key,
                'status': '存疑', 'priority': 'P2', 'source_ids': [],
                'explanation': 'Local reference only', 'evidence_files': ['main.tex']}

    unsupported = reference(1, 'alpha') | {'status': '已确认'}
    unbacked = output.stage({'references': [unsupported]})
    assert unbacked['staged'] is False
    assert unbacked['validation_error'] == 'paper_audit_confirmed_without_source'
    assert unbacked['keys'] == ['alpha']
    control = output.stage({'notes': ['bad\bcontrol']})
    assert control['staged'] is False
    assert control['validation_error'] == 'paper_audit_control_character'
    assert control['fields'] == ['notes[0]']
    first = output.stage({'scope': 'Uploaded manuscript', 'citation_checks': checks,
                          'references': [reference(1, 'alpha'), reference(2, 'beta')]})
    rejected = output.stage({'references': [reference(3, 'alpha')]}, first['draft_sha256'])
    assert rejected['staged'] is False
    assert rejected['validation_error'] == 'paper_audit_duplicate_keys'
    assert rejected['duplicate_reference_numbers'] == [[1, 3]]
    assert rejected['draft_sha256'] == first['draft_sha256']

    # A draft produced by the previous append-only protocol must also be repairable.
    draft_path = workspace / 'outputs' / 'paper-audits' / 'task-a' / 'draft.json'
    draft = json.loads(draft_path.read_text())
    draft['report']['references'].append(reference(3, 'alpha'))
    draft['report']['reference_count'] = 3
    raw = json.dumps(draft, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':')).encode()
    draft_path.write_bytes(raw)
    legacy_sha = hashlib.sha256(raw).hexdigest()
    invalid = output.finalize(legacy_sha)
    assert invalid['finalized'] is False
    assert invalid['validation_error'] == 'renderer_input_duplicate_keys'
    assert invalid['duplicate_reference_numbers'] == [[1, 3]]
    assert invalid['draft_sha256'] == legacy_sha
    with pytest.raises(ValueError, match='stale_paper_audit_draft'):
        output.stage({'remove_reference_number': 3}, first['draft_sha256'])
    repaired = output.stage({'remove_reference_number': 3}, legacy_sha)
    assert repaired['staged'] is True and repaired['reference_count'] == 2
    with pytest.raises(ValueError, match='removal_invalid'):
        output.stage({'remove_reference_number': True}, repaired['draft_sha256'])
    extra = output.stage({'references': [reference(3, 'gamma'), reference(4, 'delta')]},
                         repaired['draft_sha256'])
    with pytest.raises(ValueError, match='removal_invalid'):
        output.stage({'remove_reference_numbers': [3, 3]}, extra['draft_sha256'])
    batch = output.stage({'remove_reference_numbers': [4, 3]}, extra['draft_sha256'])
    assert batch['removed_reference_numbers'] == [3, 4]
    assert batch['reference_count'] == 2
    finalized = output.finalize(batch['draft_sha256'])
    assert finalized['reference_count'] == 2
    assert [row['number'] for row in output.read_audit()['report']['references']] == [1, 2]
    with pytest.raises(ValueError, match='already_finalized'):
        output.stage({'remove_reference_number': 1}, batch['draft_sha256'])


def test_local_citation_batch_is_read_only_mcp_tool(tmp_path):
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    tool = next(tool for tool in asyncio.run(create_server(inputs).list_tools())
                if tool.name == 'collect_current_local_citation_evidence')
    assert tool.input_schema['type'] == 'object'
    assert tool.input_schema.get('required', []) == []


def test_local_citation_batch_real_stdio_uses_only_approved_task_sources(tmp_path):
    work = tmp_path / 'work'
    inputs = work / 'inputs'
    inputs.mkdir(parents=True)
    (inputs / 'main.tex').write_text(
        r'\documentclass{article}\begin{document}\cite{alpha}'
        r'\bibliography{references}\end{document}', encoding='utf-8')
    (inputs / 'references.bib').write_text('@article{alpha, title={A}, year={2020}}', encoding='utf-8')
    approved = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    (work / 'approved-inputs.json').write_text(json.dumps({'files': approved}))
    (work / 'paper-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'test-task', 'allow_output': False, 'audit_sha256': None}))
    root = Path(__file__).resolve().parents[1]

    async def call():
        params = StdioServerParameters(command=sys.executable,
            args=[str(root / 'scenarios/paper_proofreading/server.py'), str(inputs)],
            cwd=root, env=os.environ.copy())
        async with Client(params, read_timeout_seconds=30) as client:
            result = await client.call_tool('collect_current_local_citation_evidence', {})
            assert not result.is_error
            packet = json.loads(result.content[0].text)
            assert packet['diagnostic']['cited_keys'] == ['alpha']
            assert [row['key'] for row in packet['references']['records']] == ['alpha']
            assert packet['internal_steps'] == [
                'pin_sources', 'inspect_active_citations', 'read_original_bibliography']
            read = await client.call_tool('read_pinned_citation_records',
                                          {'citation_id': packet['citation_id']})
            assert not read.is_error
            assert json.loads(read.content[0].text)['version_sha256'] == packet['version_sha256']
    asyncio.run(call())


def test_original_directory_layout_in_approved_zip_is_read_without_flattening(tmp_path):
    work = tmp_path / 'work'
    inputs = work / 'inputs'
    inputs.mkdir(parents=True)
    archive = inputs / 'submission.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as out:
        out.writestr('main.tex', r'\documentclass{article}\begin{document}'
                     r'\input{sections/intro}\bibliography{references}\end{document}')
        out.writestr('sections/intro.tex', r'Current work~\cite{alpha}.')
        out.writestr('references.bib', '@article{alpha, title={A}, year={2020}}\n'
                     '@article{unused, title={B}, year={2021}}')
    version = hashlib.sha256(archive.read_bytes()).hexdigest()
    (work / 'approved-inputs.json').write_text(json.dumps({'files': {'submission.zip': version}}))
    (work / 'paper-output-grant.json').write_text(json.dumps({
        'schema_version': 1, 'task_id': 'zip-task', 'allow_output': False, 'audit_sha256': None}))
    root = Path(__file__).resolve().parents[1]

    async def call():
        params = StdioServerParameters(command=sys.executable,
            args=[str(root / 'scenarios/paper_proofreading/server.py'), str(inputs)],
            cwd=root, env=os.environ.copy())
        async with Client(params, read_timeout_seconds=30) as client:
            pin = await client.call_tool('pin_paper_sources', {'main': 'main.tex'})
            assert not pin.is_error
            source_id = json.loads(pin.content[0].text)['source_id']
            wrong_handle = await client.call_tool('read_pinned_bibliography_first_page',
                                                  {'source_id': source_id})
            assert wrong_handle.is_error
            local = await client.call_tool('read_pinned_paper_sources', {'source_id': source_id})
            assert not local.is_error
            diagnostic = json.loads(local.content[0].text)['diagnostic']
            assert diagnostic['active_files'] == ['main.tex', 'sections/intro.tex']
            assert diagnostic['bib_entry_count'] == 2
            packet = await client.call_tool('collect_current_local_citation_evidence', {})
            assert not packet.is_error
            result = json.loads(packet.content[0].text)
            assert result['diagnostic']['cited_keys'] == ['alpha']
            assert [row['key'] for row in result['references']['records']] == ['alpha']
            wrong_page = await client.call_tool('read_pinned_bibliography_page',
                                                {'source_id': result['source_id'], 'page': 1})
            assert wrong_page.is_error
            full = await client.call_tool('read_pinned_bibliography_first_page',
                                          {'source_id': result['source_id']})
            assert not full.is_error
            listing = json.loads(full.content[0].text)
            assert listing['entry_count'] == 2
            assert [row['key'] for row in listing['records']] == ['alpha', 'unused']
            derived = work / 'paper-archive' / version / 'files' / 'sections' / 'intro.tex'
            derived.write_text('changed')
            stale = await client.call_tool('read_pinned_citation_records',
                {'citation_id': result['citation_id']})
            assert stale.is_error
    asyncio.run(call())


def test_archive_rejects_traversal_and_ambiguous_source(tmp_path):
    from src.adapters.paper_archive import materialize_approved_archive
    work = tmp_path / 'work'
    inputs = work / 'inputs'
    inputs.mkdir(parents=True)
    archive = inputs / 'submission.zip'
    with ZipFile(archive, 'w') as out:
        out.writestr('main.tex', 'ok')
        out.writestr('../outside.tex', 'bad')
    version = hashlib.sha256(archive.read_bytes()).hexdigest()
    (work / 'approved-inputs.json').write_text(json.dumps({'files': {'submission.zip': version}}))
    with pytest.raises(ValueError, match='paper_archive_entry_invalid'):
        materialize_approved_archive(PaperEvidence(inputs))
    assert not (work / 'outside.tex').exists()
    (inputs / 'main.tex').write_text('also supplied')
    approved = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs.iterdir()}
    (work / 'approved-inputs.json').write_text(json.dumps({'files': approved}))
    with pytest.raises(ValueError, match='paper_source_scope_ambiguous'):
        PaperEvidence(inputs).paper_tree()


def test_pdf_export_receipt_can_check_literal_content_and_links_without_claiming_truth(tmp_path, monkeypatch):
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    # ASCII enums keep this PDF fixture independent of ReportLab/font packages.
    monkeypatch.setitem(INPUT_SCHEMA, 'status_enum', ['verified'])
    monkeypatch.setitem(INPUT_SCHEMA, 'priority_enum', ['low'])
    report = {'schema_version': 1, 'scope': 'Current report', 'reference_count': 1,
              'references': [{'number': 1, 'key': 'alpha', 'short_title': 'Study A',
                              'status': INPUT_SCHEMA['status_enum'][0],
                              'priority': INPUT_SCHEMA['priority_enum'][0],
                              'explanation': 'Explanation preserved',
                              'source_ids': ['source-1'], 'evidence_files': []}],
              'sources': [{'id': 'source-1', 'platform': 'Archive',
                           'url': 'https://example.org/study-a'}],
              'issues': [],
              'citation_checks': {key: {'result': 'not assessed', 'evidence': 'fixture',
                                        'limitation': 'human review'}
                                  for key in INPUT_SCHEMA['citation_checks_required']},
              'notes': ['No scientific review ' + 'A' * 160 + ' remains pending ' +
                        'B' * 160 + ' mechanically complete PDF receipt']}
    pdf = tmp_path / 'report.pdf'
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    resources = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): DictionaryObject({
            NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'),
            NameObject('/BaseFont'): NameObject('/Helvetica')})})})
    page[NameObject('/Resources')] = resources
    note = report['notes'][0]
    split = len(note) // 2
    fields = ['Study A', report['references'][0]['status'], report['references'][0]['priority'],
              'Explanation preserved', 'source-1', 'Archive', 'not assessed',
              'fixture', 'human review', note[:split]]
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 12 Tf 50 760 Td ' + ' '.join(
        '(' + field + ') Tj 0 -24 Td' for field in fields) + ' ET').encode())
    page[NameObject('/Contents')] = stream
    next_page = writer.add_blank_page(width=612, height=792)
    next_page[NameObject('/Resources')] = resources
    next_stream = DecodedStreamObject()
    next_stream.set_data(('BT /F1 12 Tf 50 760 Td (Page header) Tj 0 -24 Td (' +
                          note[split:] + ') Tj ET').encode())
    next_page[NameObject('/Contents')] = next_stream
    writer.add_uri(0, 'https://example.org/study-a', (50, 500, 120, 515))
    with pdf.open('wb') as output:
        writer.write(output)
    coverage = audit_pdf_content_coverage(pdf, report)
    assert coverage['all_fields_present'] and coverage['checked_fields'] == coverage['present_fields']
    assert coverage['pdf_pages'] == 2 and coverage['source_link_objects'] == 1
    assert coverage['semantic_quality_accepted'] is False
    report['notes'][0] = note.replace('mechanically', 'semantically')
    assert audit_pdf_content_coverage(pdf, report)['all_fields_present'] is False
    report['notes'][0] = 'bad\bcontrol'
    with pytest.raises(ValueError, match='renderer_input_control_character'):
        audit_pdf_content_coverage(pdf, report)
    report['notes'][0] = note
    report['references'][0]['explanation'] = 'Missing explanation'
    assert audit_pdf_content_coverage(pdf, report)['all_fields_present'] is False
