"""免费离线协议诊断；夹具不代表真实模型行为、质量或节省。"""
import copy
import json
from pathlib import Path

import pytest

from src.adapters.trace_rsi_batch_compiler import ADDITIONS, compile_trace_rsi_batches, _readonly_result
from src.adapters.trace_rsi_motif_compiler import PREFIX, file_sha256
from src.adapters.trace_tool_evidence import digest
from test_trace_rsi_motif_compiler import make_run, events, write_events, save, change_metadata


READ = PREFIX + 'read_observed_state'


@pytest.mark.parametrize('fault', [None, 'policy', 'path', 'sha', 'scope', 'extra', 'stale'])
def test_private_artifact_result_is_explicitly_bounded(fault):
    config = {'source_version': 'a' * 64, 'candidate_sha256': 'b' * 64,
              'session_id': 'diagnostic', 'private_export_policy': 'current_task_revision_report_only'}
    base = {'input_sha256': 'c' * 64, 'report_sha256': 'd' * 64,
            'source_version': config['source_version'], 'candidate_sha256': config['candidate_sha256'],
            'catalog_sha256': 'e' * 64}
    receipt = {'input_id': 'trace-input-' + digest({**base, 'session_id': config['session_id']}), **base}
    value = {**receipt, 'artifact_name': 'revision-report.md', 'artifact_sha256': 'f' * 64,
             'scope': 'structural_revision_not_full_bibliography_verification', 'output': {'diagnostic': True}}
    action = {'ok': True, 'name': PREFIX + 'export_revision_report',
              'arguments': {'input_id': receipt['input_id']}, 'value': value}
    if fault == 'policy':
        config.pop('private_export_policy')
    elif fault == 'path':
        value['artifact_name'] = '../original.md'
    elif fault == 'sha':
        value['artifact_sha256'] = 'z' * 64
    elif fault == 'scope':
        value['scope'] = 'full_bibliography_verified'
    elif fault == 'extra':
        value['path'] = '/tmp/report.md'
    elif fault == 'stale':
        action['arguments']['input_id'] = 'old'
    if fault:
        with pytest.raises(ValueError, match='bounded_private_artifact_contract_required'):
            _readonly_result(action, receipt, {}, [], config, '{}', base['catalog_sha256'])
    else:
        assert _readonly_result(action, receipt, {}, [], config, '{}', base['catalog_sha256']) == {
            'tool': action['name'], 'arguments_binding': {'input_id': '/input_id'},
            'result_kind': 'private_artifact_output', 'effect': 'private_current_report_export'}


def additions(root):
    result = {}
    for name in ADDITIONS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('diagnostic observer only\n')
        result[str(path)] = file_sha256(path)
    return result


def make_batch(root, name='a', *, order=('check', 'read'), reverse_results=False,
               anchor='inspect_state', **kwargs):
    run = make_run(root, name, anchor=anchor, **kwargs)
    config = json.loads((run / 'config.json').read_text())
    report = json.loads((run / 'work/triage.json').read_text())
    rows = events(run)
    first_result = next(r['event']['data']['message']['content'][0]
                        for r in rows if r['event']['type'] == 'tool/result'
                        and r.get('sessionId', r.get('session_id')) == config['session_id'])
    anchor_value = json.loads(first_result['content'][0]['text'])
    receipt = {k: v for k, v in anchor_value.items() if k not in ('report', 'input')}
    state = {**receipt, 'report': report, 'input': {'rows': report['rows']}}
    for path in (run / 'requests').glob('*.json'):
        provider = json.loads(path.read_text())
        wrapped = isinstance(provider, str)
        if wrapped:
            provider = json.loads(provider)
        provider['tools'].append({'type': 'function', 'function': {'name': READ,
            'parameters': {'type': 'object', 'properties': {}, 'required': [],
                           'additionalProperties': False}}})
        save(path, json.dumps(provider) if wrapped else provider)
    target = [i for i, r in enumerate(rows) if r['event']['type'] == 'assistant/message'
              and r['event']['data']['step'] == 2][0]
    message, call, result = copy.deepcopy(rows[target:target + 3])
    wrapper = 'sessionId' if 'sessionId' in message else 'session_id'
    declaration = {'type': 'tool-call', 'id': 'read-in-batch', 'name': READ, 'arguments': '{}'}
    read_call = {wrapper: config['session_id'], 'event': {'type': 'tool/call', 'data': {
        'step': 2, 'callId': 'read-in-batch', 'name': READ, 'arguments': {}}}}
    read_result = {wrapper: config['session_id'], 'event': {'type': 'tool/result', 'data': {
        'message': {'source': {'callId': 'read-in-batch'}, 'content': [{'type': 'tool-result',
        'toolCallId': 'read-in-batch', 'isError': False,
        'content': [{'type': 'text', 'text': json.dumps(state)}]}]}}}}
    blocks = message['event']['data']['message']['content']
    check_declaration = blocks[-1]
    text = blocks[:-1]
    declarations = {'check': check_declaration, 'read': declaration}
    calls, results = {'check': call, 'read': read_call}, {'check': result, 'read': read_result}
    message['event']['data']['message']['content'] = text + [declarations[k] for k in order]
    result_order = tuple(reversed(order)) if reverse_results else order
    rows[target:target + 3] = [message] + [calls[k] for k in order] + [results[k] for k in result_order]
    write_events(run, rows)
    return run


def compile_runs(root, runs, **kwargs):
    return compile_trace_rsi_batches(runs, root=root, code_additions=additions(root), **kwargs)


def test_complete_batch_keeps_dynamic_order_and_narration_and_versions(tmp_path):
    a = make_batch(tmp_path, 'a', generated='dynamic_observed_algorithm')
    b = make_batch(tmp_path, 'b', generated='dynamic_observed_algorithm', alias=True, double_request=True,
                   reverse_results=True)
    library = compile_runs(tmp_path, [a, b])
    motif, = library['motifs']
    assert motif['anchor'] == PREFIX + 'inspect_state'
    assert motif['batch'] == [
        {'tool': PREFIX + 'dynamic_observed_algorithm', 'arguments_binding': {'input_id': '/input_id'},
         'result_kind': 'candidate_output'},
        {'tool': READ, 'arguments': {}, 'result_kind': 'task_state'}]
    assert motif['training_session_count'] == 2
    assert all(w['anchor_request'] + 1 == w['next_request'] for w in motif['witnesses'])
    assert all(w['next_text_blocks'] == 1 and w['anchor_text_blocks'] == 1 for w in motif['witnesses'])
    assert all([i['tool'] for i in w['batch']] == [d['tool'] for d in motif['batch']]
               for w in motif['witnesses'])
    assert all('output_sha256' in w['batch'][0] and 'output_sha256' not in w['batch'][1]
               for w in motif['witnesses'])
    assert all(all(i['receipt'] == w['receipt'] for i in w['batch']) for w in motif['witnesses'])
    reversed_witness = next(w for w in motif['witnesses'] if w['run_id'] == 'b')
    assert reversed_witness['batch'][0]['result_line'] > reversed_witness['batch'][1]['result_line']
    assert library['kind'] == 'trace_rsi_batch_continuation_shadow'
    assert library['execution_policy'] == 'shadow_only'
    assert not set(library['code_files_sha256']) & set(library['code_additions_sha256'])
    assert library['manifest_digest'] == digest({k: v for k, v in library.items() if k != 'manifest_digest'})
    assert 'a-one' not in json.dumps(library) and '保留此旁白' not in json.dumps(library)


def test_alternate_order_is_observed_and_single_session_is_only_candidate(tmp_path):
    a = make_batch(tmp_path, order=('read', 'check'))
    motif, = compile_runs(tmp_path, [a])['motifs']
    assert [d['tool'] for d in motif['batch']] == [READ, PREFIX + 'measure_observed_rows']
    assert motif['training_session_count'] == 1 and motif['support'] == 'single_session_candidate'
    assert motif['status'] == 'shadow_candidate'


def test_successful_report_write_can_anchor_but_not_enter_readonly_batch(tmp_path):
    a = make_batch(tmp_path, anchor='replace_report')
    motif, = compile_runs(tmp_path, [a])['motifs']
    assert motif['anchor'] == PREFIX + 'replace_report'
    assert all(d['tool'] != motif['anchor'] for d in motif['batch'])


def test_check_to_read_singleton_is_learned_without_a_fixed_dag(tmp_path):
    run = make_run(tmp_path)
    rows = events(run)
    root_rows = rows[1:]
    first, second, final = root_rows[:3], root_rows[3:6], root_rows[6:]
    rows = rows[:1] + second + first + final
    for ordinal, group in enumerate((second, first), 1):
        for row in group:
            if row['event']['type'] in ('assistant/message', 'tool/call'):
                row['event']['data']['step'] = ordinal
    write_events(run, rows)
    motif, = compile_runs(tmp_path, [run])['motifs']
    assert motif['anchor'] == PREFIX + 'measure_observed_rows'
    assert motif['batch'] == [{'tool': PREFIX + 'inspect_state', 'arguments': {}, 'result_kind': 'task_state'}]


@pytest.mark.parametrize('fault', ['failed', 'handle', 'receipt', 'projection', 'unknown'])
def test_bad_member_rejects_entire_batch_without_salvaging_other_member(tmp_path, fault):
    run = make_batch(tmp_path)
    rows = events(run)
    check_call = next(r for r in rows if r['event']['type'] == 'tool/call'
                      and r['event']['data']['callId'] == 'call-2')
    check_result = next(r for r in rows if r['event']['type'] == 'tool/result'
                        and r['event']['data'].get('message', {}).get('source', {}).get('callId') == 'call-2')
    read_result = next(r for r in rows if r['event']['type'] == 'tool/result'
                       and r['event']['data'].get('message', {}).get('source', {}).get('callId') == 'read-in-batch')
    declaration = next(r for r in rows if r['event']['type'] == 'assistant/message'
                       and r['event']['data']['step'] == 2)['event']['data']['message']['content'][-2]
    if fault == 'failed':
        check_result['event']['data']['message']['content'][0]['isError'] = True
    elif fault == 'handle':
        check_call['event']['data']['arguments']['input_id'] = 'unregistered'
        declaration['arguments'] = json.dumps(check_call['event']['data']['arguments'])
    elif fault in ('receipt', 'projection'):
        block = read_result['event']['data']['message']['content'][0]
        value = json.loads(block['content'][0]['text'])
        if fault == 'receipt':
            value['input_sha256'] = 'f' * 64
        else:
            value['input'] = {'rows': []}
        block['content'][0]['text'] = json.dumps(value)
    else:
        declaration['name'] = 'native_diagnostic'
        declaration['arguments'] = '{}'
        check_call['event']['data']['name'] = 'native_diagnostic'
        check_call['event']['data']['arguments'] = {}
    write_events(run, rows)
    library = compile_runs(tmp_path, [run])
    assert library['motifs'] == [] and sum(library['rejected'].values()) == 1


@pytest.mark.parametrize('fault', ['missing_result', 'missing_dispatch', 'dispatch_order', 'orphan_result'])
def test_incomplete_or_misordered_request_lifecycle_fails_closed(tmp_path, fault):
    run = make_batch(tmp_path)
    rows = events(run)
    calls = [i for i, r in enumerate(rows) if r['event']['type'] == 'tool/call'
             and r['event']['data']['step'] == 2]
    results = [i for i, r in enumerate(rows) if r['event']['type'] == 'tool/result'
               and r['event']['data'].get('message', {}).get('source', {}).get('callId') == 'read-in-batch']
    if fault == 'missing_result':
        rows.pop(results[0])
    elif fault == 'missing_dispatch':
        rows.pop(calls[1])
    elif fault == 'dispatch_order':
        rows[calls[0]], rows[calls[1]] = rows[calls[1]], rows[calls[0]]
    else:
        rows.insert(results[0], copy.deepcopy(rows[results[0]]))
    write_events(run, rows)
    with pytest.raises(ValueError):
        compile_runs(tmp_path, [run])


@pytest.mark.parametrize('file,key,value', [('config.json', 'mode', 'shadow'),
    ('metrics.json', 'actual_model_skips', 1), ('verification.json', 'stage_output_passed', False),
    ('manifest.json', 'source_version', 'f' * 64)])
def test_only_verified_normal_baseline_can_train(tmp_path, file, key, value):
    run = make_batch(tmp_path)
    change_metadata(run, file, key, value)
    with pytest.raises(ValueError):
        compile_runs(tmp_path, [run])


def test_learning_or_duplicate_sessions_cannot_supply_independent_support(tmp_path):
    a = make_batch(tmp_path, 'a', session='learning-session')
    with pytest.raises(ValueError, match='learning_session'):
        compile_runs(tmp_path, [a])
    b = make_batch(tmp_path, 'b', session='same-session')
    c = make_batch(tmp_path, 'c', session='same-session')
    with pytest.raises(ValueError, match='independent_named'):
        compile_runs(tmp_path, [b, c])


def test_additions_are_explicit_actual_versions_and_cannot_replace_baseline(tmp_path):
    run = make_batch(tmp_path)
    with pytest.raises(ValueError, match='explicit_batch_observer'):
        compile_trace_rsi_batches([run], root=tmp_path)
    extra = additions(tmp_path)
    Path(next(iter(extra))).write_text('changed')
    with pytest.raises(ValueError, match='registered_file_version'):
        compile_trace_rsi_batches([run], root=tmp_path, code_additions=extra)
    extra = additions(tmp_path)
    for filename in ('config.json', 'manifest.json'):
        metadata = json.loads((run / filename).read_text())
        metadata['code_files'].update(extra)
        save(run / filename, metadata)
    with pytest.raises(ValueError, match='cannot_replace_training_code'):
        compile_trace_rsi_batches([run], root=tmp_path, code_additions=extra)


def test_source_versions_may_differ_but_tool_order_and_code_must_match(tmp_path):
    a = make_batch(tmp_path, 'a')
    b = make_batch(tmp_path, 'b')
    library = compile_runs(tmp_path, [a, b])
    assert library['sources']['a']['source_version'] != library['sources']['b']['source_version']
    for path in (b / 'requests').glob('*.json'):
        provider = json.loads(path.read_text())
        provider['tools'].reverse()
        save(path, provider)
    with pytest.raises(ValueError, match='training_tool_candidate_or_code_drift'):
        compile_runs(tmp_path, [a, b])


def test_different_observed_orders_do_not_fabricate_repeated_session_support(tmp_path):
    a = make_batch(tmp_path, 'a')
    b = make_batch(tmp_path, 'b', order=('read', 'check'))
    motifs = compile_runs(tmp_path, [a, b])['motifs']
    assert len(motifs) == 2
    assert all(m['training_session_count'] == 1 for m in motifs)


def test_failed_anchor_does_not_train_a_complete_successful_batch(tmp_path):
    run = make_batch(tmp_path, failed_anchor=True)
    library = compile_runs(tmp_path, [run])
    assert library['motifs'] == []
    assert library['rejected'] == {'unsupported_or_failed_batch_anchor': 1}


def test_intervening_text_request_breaks_local_anchor_instead_of_being_deleted(tmp_path):
    run = make_batch(tmp_path)
    rows = events(run)
    index = next(i for i, r in enumerate(rows) if r['event']['type'] == 'assistant/message'
                 and r['event']['data']['step'] == 2)
    rows.insert(index, {'sessionId': 'session-a', 'event': {'type': 'assistant/message',
        'data': {'step': 2, 'message': {'content': [{'type': 'text', 'text': '科研判断仍然保留'}]}}}})
    for row in rows[index + 1:]:
        if row['event']['type'] in ('assistant/message', 'tool/call'):
            row['event']['data']['step'] += 1
    write_events(run, rows)
    save(run / 'requests/4.json', json.loads((run / 'requests/3.json').read_text()))
    change_metadata(run, 'metrics.json', 'actual_requests', 4)
    library = compile_runs(tmp_path, [run])
    assert library['motifs'] == []
    assert library['rejected'] == {'single_complete_request_anchor_required': 1}


def test_batch_size_is_bounded_even_when_all_members_are_valid(tmp_path):
    run = make_batch(tmp_path)
    rows = events(run)
    index = next(i for i, r in enumerate(rows) if r['event']['type'] == 'assistant/message'
                 and r['event']['data']['step'] == 2)
    message = rows[index]
    check_call, check_result = copy.deepcopy(rows[index + 1]), copy.deepcopy(rows[index + 3])
    declaration = copy.deepcopy(message['event']['data']['message']['content'][-2])
    extra_calls, extra_results = [], []
    for n in range(63):
        call_id = f'additional-{n}'
        d, c, r = copy.deepcopy(declaration), copy.deepcopy(check_call), copy.deepcopy(check_result)
        d['id'] = call_id
        c['event']['data']['callId'] = call_id
        r['event']['data']['message']['source']['callId'] = call_id
        r['event']['data']['message']['content'][0]['toolCallId'] = call_id
        message['event']['data']['message']['content'].append(d)
        extra_calls.append(c)
        extra_results.append(r)
    rows[index:index + 5] = rows[index:index + 3] + extra_calls + rows[index + 3:index + 5] + extra_results
    write_events(run, rows)
    library = compile_runs(tmp_path, [run])
    assert library['motifs'] == [] and library['rejected'] == {'bounded_batch_size_required': 1}
