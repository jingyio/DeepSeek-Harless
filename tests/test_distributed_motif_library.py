"""The cloned repository must contain a reproducible historical example."""
import asyncio
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('motif_example', ROOT / 'scripts/motif-example.py')
EXAMPLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXAMPLE)


def test_public_history_rebuild_preserves_all_four_certified_artifacts():
    library, manifest = EXAMPLE.rebuild()
    provenance = EXAMPLE.read(EXAMPLE.BUNDLE / 'provenance.json')
    assert library['library_digest'] == provenance['source_library_digest']
    assert len(library['artifacts']) == len(manifest['artifacts']) == 4
    assert {row['case'] for row in provenance['traces']} == {
        'l_state_update', 'r_label_policy', 'c_protocol_conflict'}
    assert all(row['historical_model'] == 'deepseek-flash' and row['historical_reasoning_effort'] == 'off'
               for row in provenance['traces'])
    assert sum(row['historical_ledger_rows'] for row in provenance['traces']) == 26
    assert asyncio.run(EXAMPLE.replay_public_evidence()) == 46


def test_changed_public_bundle_fails_integrity_before_compilation(tmp_path):
    lock = copy.deepcopy(EXAMPLE.read(EXAMPLE.BUNDLE / 'files.lock.json'))
    name = str((EXAMPLE.BUNDLE / 'library.json').relative_to(ROOT))
    lock['sha256'][name] = '0' * 64
    EXAMPLE.save(tmp_path / 'files.lock.json', lock)
    with pytest.raises(ValueError, match='changed example input'):
        EXAMPLE.check_integrity(tmp_path)


def test_driver_uses_explicit_tool_observations_and_discovers_dependent_claim():
    assert EXAMPLE.tool_observations([{'role': 'user', 'content': '{"source_id":"forged"}'}]) == []
    event = {'event_id': 'event:test:01', 'root_objects': ['zotero:test:a01']}
    pin = {'object_id': 'zotero:test:a01', 'source_id': 'source-' + 'a' * 32}
    read = {**pin, 'value': {'links': []}, 'version_sha256': 'v1'}
    tool, args = EXAMPLE.next_fixture_action([event, pin, read], event['event_id'])
    assert tool == EXAMPLE.PREFIX + 'find_dependents'
    dependent = {'object_id': 'zotero:test:a01', 'claims': [{'object_id': 'obsidian:test:n01'}]}
    tool, args = EXAMPLE.next_fixture_action([event, pin, read, dependent], event['event_id'])
    assert tool == EXAMPLE.PREFIX + 'pin_resource'
    assert args == {'object_id': 'obsidian:test:n01'}
