"""The historical citation tool chain only sees a task's approved input copy."""
from pathlib import Path
import asyncio
import hashlib
import json
import os
import sys

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
    assert first.read_citation_records(packet['citation_id'])['version_sha256'] == packet['version_sha256']
    with pytest.raises(ValueError, match='unknown|expired'):
        second.read_citation_records(packet['citation_id'])
    (tmp_path / 'first' / 'references.bib').write_text('@article{alpha, title={Changed}}')
    with pytest.raises(ValueError, match='version changed'):
        first.read_citation_records(packet['citation_id'])


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
    finalized = output.finalize(repaired['draft_sha256'])
    assert finalized['reference_count'] == 2
    assert [row['number'] for row in output.read_audit()['report']['references']] == [1, 2]
    with pytest.raises(ValueError, match='already_finalized'):
        output.stage({'remove_reference_number': 1}, repaired['draft_sha256'])


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
              'notes': ['No scientific review']}
    pdf = tmp_path / 'report.pdf'
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject('/Resources')] = DictionaryObject({
        NameObject('/Font'): DictionaryObject({NameObject('/F1'): DictionaryObject({
            NameObject('/Type'): NameObject('/Font'),
            NameObject('/Subtype'): NameObject('/Type1'),
            NameObject('/BaseFont'): NameObject('/Helvetica')})})})
    fields = ['Study A', report['references'][0]['status'], report['references'][0]['priority'],
              'Explanation preserved', 'source-1', 'Archive', 'not assessed',
              'fixture', 'human review', 'No scientific review']
    stream = DecodedStreamObject()
    stream.set_data(('BT /F1 12 Tf 50 760 Td ' + ' '.join(
        '(' + field + ') Tj 0 -24 Td' for field in fields) + ' ET').encode())
    page[NameObject('/Contents')] = stream
    writer.add_uri(0, 'https://example.org/study-a', (50, 500, 120, 515))
    with pdf.open('wb') as output:
        writer.write(output)
    coverage = audit_pdf_content_coverage(pdf, report)
    assert coverage['all_fields_present'] and coverage['checked_fields'] == coverage['present_fields']
    assert coverage['pdf_pages'] == 1 and coverage['source_link_objects'] == 1
    assert coverage['semantic_quality_accepted'] is False
    report['references'][0]['explanation'] = 'Missing explanation'
    assert audit_pdf_content_coverage(pdf, report)['all_fields_present'] is False
