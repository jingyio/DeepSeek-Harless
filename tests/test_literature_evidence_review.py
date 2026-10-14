"""Native mechanical review is not scientific quality or paid-model evidence."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import shutil
from uuid import uuid4

import pytest
from test_literature_pdf import POPPLER, module
from test_literature_pdf_evidence import HERE, ROOT, CHECK, evidence_corpus
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance
from src.adapters.tool_contract_loader import parse_tool_contracts

REVIEW = module(HERE / 'review-evidence.py', 'mechanical_evidence_review_test')


@pytest.fixture(scope='module')
def native_protocol():
    # Real local Harness/tool events, simulated provider: never mark as paid training.
    from test_literature_pdf import make_pdf
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT / '.local') as temporary:
        directory = Path(temporary) / 'papers'; directory.mkdir()
        make_pdf(directory / 'A.pdf', ['A mechanical source fixture with verifiable provenance and bounded read permissions. '
                                     'It provides enough visible text for the existing low-text guard and does not certify scientific claims.'])
        result = CHECK.check(directory)
        run = Path(result['arms'][0]['task_directory'])
        events = [json.loads(line) for line in (run / 'agent-events.jsonl').read_text().splitlines()]
        contracts = parse_tool_contracts(json.loads((HERE / 'pdf-evidence-contracts.json').read_text()))
        trace = extract_dsh_trace(events, contracts, trace_id=run.name,
                                 provenance_by_call_id=infer_dsh_provenance(events, contracts))
        yield run, trace, json.loads((run / 'evidence-packet-receipt.json').read_text())


@POPPLER
def test_only_exact_contiguous_native_successor_receipts_are_reviewed(native_protocol):
    _, trace, receipt = native_protocol
    chain = REVIEW.audit_chain(trace, receipt)
    assert len(chain) == 3
    wrong = copy.deepcopy(receipt); wrong['packet_id'] = 'result-invented'
    with pytest.raises(ValueError, match='missing native'):
        REVIEW.audit_chain(trace, wrong)
    records = list(trace.records); index = records.index(chain[1])
    records[index] = replace(chain[1], arguments={'extraction_id': 'source-invented'})
    with pytest.raises(ValueError):
        REVIEW.audit_chain(replace(trace, records=records), receipt)
    records = list(trace.records); records.insert(index, records[0])
    with pytest.raises(ValueError, match='interleaved'):
        REVIEW.audit_chain(replace(trace, records=records), receipt)


@POPPLER
def test_local_provider_trace_cannot_be_promoted_to_real_paid_training(native_protocol):
    original, _, _ = native_protocol
    run = ROOT / '.local/runs' / uuid4().hex
    try:
        shutil.copytree(original, run)
        with pytest.raises(ValueError, match='real-model'):
            REVIEW.review(run)
        assert not (run / 'evidence-structural-review.json').exists()
    finally:
        shutil.rmtree(run)
