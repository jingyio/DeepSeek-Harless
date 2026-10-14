"""The historical citation tool chain only sees a task's approved input copy."""
from pathlib import Path
import hashlib
import json

import pytest

from scenarios.paper_proofreading.server import PaperEvidence, PaperOutput, create_citation_evidence
from src.adapters.paper_renderer import INPUT_SCHEMA


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
