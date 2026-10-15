"""The historical citation tool chain only sees a task's approved input copy."""
from pathlib import Path
import hashlib
import json

import pytest

from scenarios.paper_proofreading.server import PaperEvidence, PaperOutput, create_citation_evidence
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
