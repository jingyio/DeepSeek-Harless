"""Evidence preparation boundaries, not scientific-quality or efficiency tests."""
import copy
import json
from pathlib import Path
import sys
import tempfile

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import POPPLER, make_pdf, module, task

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'scenarios/literature-notes'
sys.path.insert(0, str(HERE))
from pdf_tools import digest, save_private
import pdf_evidence_tools as tools
from pdf_evidence_tools import EvidenceScene, PREFIX

RUN = module(HERE / 'run-evidence.py', 'evidence_test_entry')
LEARN = module(HERE / 'learn-evidence.py', 'evidence_test_learner')
CHECK = module(HERE / 'check-evidence.py', 'evidence_test_check')


@pytest.fixture
def evidence_corpus():
    with tempfile.TemporaryDirectory(dir=ROOT / '.local') as temporary:
        root = Path(temporary)
        directory = root / 'papers'
        directory.mkdir()
        text = ('A public protocol fixture describes independent trials, experimental conditions, '
                'verified source provenance and explicit limits. It does not establish scientific truth.')
        make_pdf(directory / 'A.pdf', [text, text + ' A second selected page.'])
        make_pdf(directory / 'B.pdf', [text + ' Another study.'])
        yield directory, root / 'cache', root / 'delivery'


def scene(fixture, *, script=False, question=None):
    directory, cache, delivery = fixture
    frozen = task(directory) if question is None else task(directory, question)
    return EvidenceScene(directory, cache, frozen, delivery=delivery, script_chain=script)


def plan(s, *, allowed=True):
    return {'schema_version': 1, 'task_sha256': digest(s.task),
            'allow_deterministic_continuation': allowed,
            'windows': [{'paper_id': pid, 'page': '1', 'start': 0, 'length': 500,
                         'purpose': 'Public protocol test; no relevance assertion.'} for pid in s.rows]}


def extract(s, value=None):
    return s.extract_evidence_windows(json.dumps(value or plan(s)))


def packet(s):
    first = extract(s)
    second = s.verify_evidence_windows(first['extraction_id'])
    return s.build_evidence_packet(second['verification_id'])


@POPPLER
def test_connected_chain_delivers_exact_source_windows_and_stops_before_interpretation(evidence_corpus):
    s = scene(evidence_corpus)
    result = packet(s)
    assert result['status'] == 'packet_ready'
    body = json.loads(Path(result['artifact']).read_text())
    assert result['packet'] == body and digest(body) == result['artifact_sha256']
    assert len(body['windows']) == 2
    assert body['claim_support_assessed'] is False and body['research_quality'] == 'unreviewed'
    for w in body['windows']:
        assert w['text'] == s.read_pinned_pdf_context(w['source_id'])['text']
    s.validate_packet(body)
    assert all(p.stat().st_mode & 0o077 == 0 for p in s.delivery.glob('*.json'))


@POPPLER
def test_declined_permission_mints_no_executable_receipt(evidence_corpus):
    s = scene(evidence_corpus)
    result = extract(s, plan(s, allowed=False))
    assert result['status'] == 'needs_review' and 'extraction_id' not in result
    assert not s.receipts and not s.handles and s.stats['parser_runs'] == 0


@POPPLER
@pytest.mark.parametrize('bad', ['task', 'bool', 'page', 'negative_start', 'unknown_paper', 'budget', 'extra'])
def test_malformed_or_unbound_plan_rejected(evidence_corpus, bad, monkeypatch):
    s = scene(evidence_corpus)
    value = plan(s)
    if bad == 'task': value['task_sha256'] = '0' * 64
    elif bad == 'bool': value['allow_deterministic_continuation'] = 'true'
    elif bad == 'page': value['windows'][0]['page'] = '01'
    elif bad == 'negative_start': value['windows'][0]['start'] = -1
    elif bad == 'unknown_paper': value['windows'][0]['paper_id'] = 'unselected'
    elif bad == 'budget':
        monkeypatch.setattr(s, '_document', lambda pid: {'pages': ['a' * 7000, 'a' * 7000]})
        value['windows'][0]['length'] = value['windows'][1]['length'] = 6000
        value['windows'].append({**value['windows'][0], 'page': '2', 'length': 1})
    else: value['extra'] = 'unauthorized'
    with pytest.raises(ToolError): extract(s, value)


@POPPLER
@pytest.mark.parametrize('bounds', ['page', 'offset'])
def test_window_outside_pdf_does_not_issue_extraction_receipt(evidence_corpus, bounds):
    s = scene(evidence_corpus)
    value = plan(s)
    if bounds == 'page': value['windows'][0]['page'] = '500'
    else: value['windows'][0]['start'] = 1000000
    with pytest.raises(ToolError): extract(s, value)
    assert not s.receipts


@POPPLER
@pytest.mark.parametrize('stage', ['verify', 'build'])
def test_source_change_between_nodes_rejects_old_receipts(evidence_corpus, stage):
    s = scene(evidence_corpus)
    first = extract(s)
    second = s.verify_evidence_windows(first['extraction_id']) if stage == 'build' else None
    directory, _, _ = evidence_corpus
    (directory / 'A.pdf').write_bytes((directory / 'A.pdf').read_bytes() + b'\n% changed version\n')
    with pytest.raises(ToolError, match='changed'):
        if stage == 'verify': s.verify_evidence_windows(first['extraction_id'])
        else: s.build_evidence_packet(second['verification_id'])


@POPPLER
@pytest.mark.parametrize('dependency', ['parser', 'question', 'implementation', 'selection'])
def test_dependency_changes_stop_the_chain(evidence_corpus, monkeypatch, dependency):
    s = scene(evidence_corpus)
    first = extract(s)
    if dependency == 'parser': s.profile['extractor'] = 'changed'
    elif dependency == 'question': s.task['question'] = 'changed research question'
    elif dependency == 'implementation': monkeypatch.setattr(tools, 'implementation_version', lambda: {'changed': 'version'})
    else: make_pdf(evidence_corpus[0] / 'C.pdf', ['New source selection.'])
    with pytest.raises(ToolError, match='changed'): s.verify_evidence_windows(first['extraction_id'])


@POPPLER
def test_tampered_artifact_and_unverified_or_other_session_receipts_rejected(evidence_corpus):
    s = scene(evidence_corpus)
    first = extract(s)
    with pytest.raises(ToolError, match='kind'): s.build_evidence_packet(first['extraction_id'])
    other = scene(evidence_corpus)
    with pytest.raises(ToolError, match='other-session'): other.verify_evidence_windows(first['extraction_id'])
    _, path, _ = s.receipts[first['extraction_id']]
    content = json.loads(path.read_text())
    content['windows'][0]['text'] = 'Invented replacement.'
    save_private(path, content)
    with pytest.raises(ToolError, match='changed'): s.verify_evidence_windows(first['extraction_id'])


@POPPLER
@pytest.mark.parametrize('empty', [True, False])
def test_low_text_or_too_short_window_returns_gap_not_a_verified_handle(evidence_corpus, empty):
    if empty: make_pdf(evidence_corpus[0] / 'A.pdf', [''])
    s = scene(evidence_corpus)
    value = plan(s)
    if not empty: value['windows'][0]['length'] = 12
    first = extract(s, value)
    result = s.verify_evidence_windows(first['extraction_id'])
    assert result['status'] == 'needs_review' and 'verification_id' not in result
    assert result['issues'][0]['window_index'] == 0
    with pytest.raises(ToolError): s.build_evidence_packet('verification-invented')


@POPPLER
def test_ordinary_script_uses_identical_checks_and_packet(evidence_corpus):
    baseline = packet(scene(evidence_corpus))
    script = scene(evidence_corpus, script=True)
    direct = extract(script)['script_packet']
    assert baseline['packet'] == direct['packet']
    assert baseline['artifact_sha256'] == direct['artifact_sha256']
    declined = extract(script, plan(script, allowed=False))
    assert 'script_packet' not in declined


@POPPLER
def test_delivery_rejects_other_question_even_with_unchanged_pdfs(evidence_corpus):
    body = packet(scene(evidence_corpus))['packet']
    other = scene(evidence_corpus, question='A different research question')
    with pytest.raises(ToolError, match='invalid'): other.validate_packet(body)


@POPPLER
def test_free_preview_does_not_load_key_and_schema_matches_whitelist(evidence_corpus, monkeypatch):
    from src.adapters.scenario import prepare_scenario
    monkeypatch.setenv('DEEPSEEK_API_KEY', '')
    output, env = RUN.prepare_task(evidence_corpus[0], 'A protocol question')
    prepared = prepare_scenario(output / 'scenario.json')
    contracts = json.loads((HERE / 'pdf-evidence-contracts.json').read_text())
    assert set(prepared['allowed_tools']) == set(contracts)
    assert env['SSS_EVIDENCE_SCRIPT_CHAIN'] == '0'
    snapshot = json.loads((output / 'input-snapshot.json').read_text())
    assert snapshot['execution_options']['model_call_enabled'] is False
    assert 'DEEPSEEK_API_KEY' not in json.dumps(snapshot)


def test_learning_rejects_non_independent_split_and_existing_output(tmp_path):
    split = tmp_path / 'split.json'
    split.write_text('[]')
    with pytest.raises(ValueError, match='two training'): LEARN.learn(split, ROOT / '.local/new-output')
    split.write_text(json.dumps([{'role': r} for r in ('train', 'train', 'certify')]))
    with pytest.raises(ValueError, match='new private'): LEARN.learn(split, ROOT / '.local')


@POPPLER
def test_actual_mcp_harness_budget_baseline_and_script_have_identical_packets(evidence_corpus):
    result = CHECK.check(evidence_corpus[0])
    assert result['paid_api_requests'] == 0 and result['identical_packets']
    assert [arm['model_requests'] for arm in result['arms']] == [8, 6]
    assert all(arm['mcp']['unknown_receipt_rejected'] for arm in result['arms'])


@POPPLER
def test_long_approved_plan_has_short_bound_handle_and_identical_packet(evidence_corpus):
    direct = scene(evidence_corpus)
    value = plan(direct)
    value['windows'][0]['purpose'] += ' Additional bounded reading-plan metadata, not scientific interpretation.'
    initial = extract(direct, value)
    checked = direct.verify_evidence_windows(initial['extraction_id'])
    expected = direct.build_evidence_packet(checked['verification_id'])['packet']
    s = scene(evidence_corpus)
    assert len(json.dumps(value)) > 500
    registered = s.register_reading_plan(json.dumps(value))
    assert len(registered['plan_id']) < 500 and registered['relevance_assessed'] is False
    extracted = s.extract_evidence_windows(registered['plan_id'])
    verified = s.verify_evidence_windows(extracted['extraction_id'])
    assert s.build_evidence_packet(verified['verification_id'])['packet'] == expected
    other = scene(evidence_corpus)
    with pytest.raises(ToolError, match='other-session'):
        other.extract_evidence_windows(registered['plan_id'])
    declined = s.register_reading_plan(json.dumps(plan(s, allowed=False)))
    assert 'plan_id' not in declined


@POPPLER
@pytest.mark.parametrize('frozen', [False, True])
def test_actual_mcp_harness_two_verified_skips_with_compiler_certified_fixture(evidence_corpus, frozen):
    from src.adapters.dsh_trajectory import DshTrace, ToolRecord, mine_witnessed_parameter_edges
    from src.adapters.tool_contract_loader import parse_tool_contracts
    from src.motif_core.offline.chain_compiler import compile_witnessed_chain_motif, certify_witnessed_chain_motif
    from src.motif_core.offline.library_builder import library_from_certified
    contracts_raw = json.loads((HERE / 'pdf-evidence-contracts.json').read_text())
    contracts = parse_tool_contracts(contracts_raw)
    policy = tools.continuation_policy()
    traces = []
    for i in range(3):
        s = scene(evidence_corpus, question=f'Protocol fixture decision {i}; not scientific evaluation')
        registered = s.register_reading_plan(json.dumps(plan(s)))
        arguments = [{'plan': registered['plan_id']}]
        values = [s.extract_evidence_windows(registered['plan_id'])]
        arguments.append({'extraction_id': values[0]['extraction_id']})
        values.append(s.verify_evidence_windows(**arguments[-1]))
        arguments.append({'verification_id': values[1]['verification_id']})
        values.append(s.build_evidence_packet(**arguments[-1]))
        records = []
        for j, step in enumerate(policy['steps']):
            origin = None if j == 0 else {step['param']: {'from_tool': policy['steps'][j - 1]['tool'],
                                                'from_field': policy['steps'][j - 1]['receipt_field']}}
            records.append(ToolRecord(step['tool'], arguments[j], digest(values[j]), True,
                                      'eligible_read', j, values[j], origin))
        traces.append(DshTrace(str(i), tuple(records), (tuple(r.name for r in records),), f'fixture-{i}'))
    edges = mine_witnessed_parameter_edges(traces[:2])
    first = next(e for e in edges if e['from_tool'] == policy['steps'][0]['tool'] and e['to_tool'] == policy['steps'][1]['tool'])
    second = next(e for e in edges if e['from_tool'] == policy['steps'][1]['tool'] and e['to_tool'] == policy['steps'][2]['tool'])
    artifact = certify_witnessed_chain_motif(compile_witnessed_chain_motif(first, second, traces[:2], contracts), traces[2], contracts)
    exporter = module(ROOT / 'scripts/export-online-motif-manifest.py', 'evidence_fixture_exporter')
    manifest = exporter.export_manifest(library_from_certified([artifact]), contracts_raw,
                     version_fields={s['tool']: 'execution_version_sha256' for s in policy['steps']})
    path = evidence_corpus[2] / 'synthetic-test-only-manifest.json'
    save_private(path, manifest)
    value = plan(scene(evidence_corpus)) if frozen else None
    result = CHECK.check(evidence_corpus[0], manifest=path, frozen_plan=value)
    assert [a['model_requests'] for a in result['arms']] == ([6, 4, 4] if frozen else [8, 6, 6])
    assert result['arms'][2]['verified_skips'] == 2
    assert result['arms'][2]['unavailable_embedding_requests'] == 0
    assert result['identical_packets'] and result['sources_unchanged']


@POPPLER
def test_legacy_inline_plan_issues_no_grant_and_registered_plan_binds_all_steps(evidence_corpus):
    s = scene(evidence_corpus)
    inline = extract(s)
    assert 'continuation_grant' not in inline
    registered = s.register_reading_plan(json.dumps(plan(s)))
    first = s.extract_evidence_windows(registered['plan_id'])
    second = s.verify_evidence_windows(first['extraction_id'])
    last = s.build_evidence_packet(second['verification_id'])
    assert [r['continuation_grant']['completed_steps'] for r in (first, second, last)] == [1, 2, 3]
    assert all(r['continuation_grant']['plan_id'] == registered['plan_id'] for r in (first, second, last))
