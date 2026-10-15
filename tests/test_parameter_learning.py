import json
from pathlib import Path

import pytest

from src.adapters.parameter_learning import advance_round, latest_round
from src.adapters.parameter_motif_compiler import crossref_payload, compile_parameter_runs


def trace(base, name, *, crossref=False, query_field='query.bibliographic', mode='baseline', failed=False):
    run = base / name; run.mkdir()
    session = 'root-' + name
    (run / 'work').mkdir(); (run / 'work/a.bib').write_text('title={An Example Study}\n')
    manifest = {'session_id': session, 'mode': mode, 'model': 'diagnostic-fixture', 'input_sha256': 'a' * 64}
    (run / 'manifest.json').write_text(json.dumps(manifest))
    (run / 'metrics.json').write_text(json.dumps({'status': 'completed', 'actual_requests': 2,
                                                 'verified_skips': 0, 'unverified_bypasses': 0}))
    calls = [('read', {'file_path': str(run / 'work/a.bib')}, 'raw read diagnostic')]
    if crossref:
        url = 'https://api.crossref.org/works?' + query_field + '=An+Example+Study&rows=3&select=DOI,title,author'
        payload = {'status': 'ok', 'message': {'items': [{'DOI': '10.1234/example', 'title': ['An Example Study']}]}}
        calls.append(('web_fetch', {'url': url}, 'Fetched ' + url + ' (HTTP 200)\n' + json.dumps(payload)))
    events = []
    for i, (tool, args, body) in enumerate(calls):
        events += [{'session_id': session, 'event': {'type': 'tool/call', 'data': {
            'name': tool, 'arguments': args, 'callId': str(i), 'step': i}}},
                   {'session_id': session, 'event': {'type': 'tool/result', 'data': {'message': {'content': [{
                       'type': 'tool-result', 'toolCallId': str(i), 'isError': failed and i == 1,
                       'content': [{'type': 'text', 'text': body}]}]}}}}]
    (run / 'session-events.jsonl').write_text('\n'.join(map(json.dumps, events)))
    (run / 'file-versions.jsonl').write_text(json.dumps({'session_id': session, 'call_id': '0',
        'snapshot': {'complete': True, 'files': {'a.bib': 'b' * 64}}}))
    return run


def test_new_normal_evidence_adds_contract_and_preserves_old_round(tmp_path):
    one = trace(tmp_path, 'one'); two = trace(tmp_path, 'two', crossref=True)
    validation = trace(tmp_path, 'validation', crossref=True)
    store = tmp_path / 'store'
    path1, r1, lib1 = advance_round(store, [one], [validation])
    frozen = (path1 / 'library.json').read_bytes()
    assert len(lib1['motifs']) == 1  # Heldout Crossref never selects a new type.
    path2, r2, lib2 = advance_round(store, [two], [validation])
    assert len(lib2['motifs']) == 2
    assert len(r2['added_motifs']) == 1 and r2['parent_library_digest'] == r1['library_digest']
    assert r2['training'][0] == r1['training'][0]
    assert (path1 / 'library.json').read_bytes() == frozen
    assert latest_round(store)[0] == path2
    assert not r2['production_activation'] and not r2['independent_task_certification']


def test_validation_only_contract_variation_is_not_promoted(tmp_path):
    train = trace(tmp_path, 'train', crossref=True)
    heldout = trace(tmp_path, 'heldout', crossref=True, query_field='query.title')
    lib = compile_parameter_runs([(train, 'training'), (heldout, 'heldout')], source_experiment='diagnostic')
    cross = [m for m in lib['motifs'] if m['prototype']['contract'] == 'crossref-search-fetch-v1']
    assert len(cross) == 1 and cross[0]['heldout_witnesses'] == []


@pytest.mark.parametrize('case', ['duplicate', 'overlap', 'session_alias'])
def test_learning_rejects_duplicate_or_contaminated_split(tmp_path, case):
    one = trace(tmp_path, 'one'); two = trace(tmp_path, 'two')
    store = tmp_path / 'store'; advance_round(store, [one])
    if case == 'duplicate': train, valid = [one], []
    elif case == 'overlap': train, valid = [two], [one]
    else:
        p = two / 'manifest.json'; m = json.loads(p.read_text()); m['session_id'] = 'root-one'; p.write_text(json.dumps(m))
        train, valid = [two], []
    with pytest.raises(ValueError, match='duplicate|overlapping'): advance_round(store, train, valid)
    assert latest_round(store)[1]['round_index'] == 1


@pytest.mark.parametrize('mode', ['execute', 'error'])
def test_only_completed_native_modes_enter_learning(tmp_path, mode):
    run = trace(tmp_path, 'run', mode=mode)
    with pytest.raises(ValueError, match='completed native'): advance_round(tmp_path / 'store', [run])


def test_synthetic_tool_cannot_become_its_own_training_evidence(tmp_path):
    run = trace(tmp_path, 'run'); p = run / 'session-events.jsonl'
    p.write_text(p.read_text().replace('"callId": "0"', '"callId": "sss-parameter-synthetic"'))
    with pytest.raises(ValueError, match='synthetic'): advance_round(tmp_path / 'store', [run])


@pytest.mark.parametrize('change', ['trace', 'library', 'parent'])
def test_changed_evidence_or_library_blocks_next_round(tmp_path, change):
    one = trace(tmp_path, 'one'); two = trace(tmp_path, 'two'); three = trace(tmp_path, 'three')
    store = tmp_path / 'store'; p1, _, _ = advance_round(store, [one]); advance_round(store, [two])
    if change == 'trace': (one / 'session-events.jsonl').write_text((one / 'session-events.jsonl').read_text() + '\n')
    elif change == 'library': (p1 / 'library.json').write_text('{}')
    else: (p1 / 'round.json').write_text('{}')
    with pytest.raises((ValueError, KeyError)): advance_round(store, [three])
    assert not (store / 'round-0003').exists()


def test_failed_fetch_and_malformed_metadata_do_not_add_contract(tmp_path):
    run = trace(tmp_path, 'run', crossref=True, failed=True)
    _, _, library = advance_round(tmp_path / 'store', [run])
    assert len(library['motifs']) == 1
    assert crossref_payload('{"status":"ok","message":{"items":[{"DOI":"wrong","title":["a"]}]}}') is None
    assert crossref_payload('{"status":"ok","message":{"items":[]}}') is not None


def test_reserved_validation_is_retained_and_never_recycled_as_training(tmp_path):
    one=trace(tmp_path,'one');two=trace(tmp_path,'two');heldout=trace(tmp_path,'heldout')
    store=tmp_path/'store';advance_round(store,[one],[heldout]);_,record,_=advance_round(store,[two])
    assert len(record['validation'])==1 and record['validation'][0]['path']==str(heldout)
    with pytest.raises(ValueError,match='reserved validation'):advance_round(store,[heldout],[])
