"""Offline protocol checks; these are synthetic diagnostics, not model results."""
import importlib.util
import json
from pathlib import Path

import pytest

from src.adapters.rsi_protocol import validate_record, validate_file, write_record, provider_ledger_record

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = json.loads((ROOT / 'examples/rsi-protocol-v1/fixtures.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('record', FIXTURES['records'])
def test_valid_wire_records(record):
    assert validate_record(record) == record


@pytest.mark.parametrize('case', FIXTURES['invalid'], ids=lambda case: case['name'])
def test_invalid_wire_records(case):
    with pytest.raises(ValueError):
        validate_record(case['record'])


def test_exact_written_bytes_are_digest_basis(tmp_path):
    import hashlib
    target = tmp_path / 'record.json'
    digest = write_record(target, FIXTURES['records'][0])
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    assert validate_file(target) == FIXTURES['records'][0]


def test_shared_schema_matches_builder():
    spec = importlib.util.spec_from_file_location('build_rsi_schema', ROOT / 'scripts/build-rsi-schema.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert json.loads((ROOT / 'schemas/rsi-protocol-v1.schema.json').read_text()) == module.build()


def test_unknown_provider_usage_remains_unknown_and_reservation_is_preserved():
    row = dict(request_id=1, model='deepseek-flash', response_status=502, reserved_upper_usd=0.03)
    record = provider_ledger_record(row, task_id='diagnostic', ledger_ref='private-ledger')
    assert record['payload']['phase'] == 'failed'
    assert record['payload']['prompt_tokens'] is None
    assert record['payload']['observed_peak_usd'] is None
    assert record['payload']['reserved_upper_usd'] == 0.03
