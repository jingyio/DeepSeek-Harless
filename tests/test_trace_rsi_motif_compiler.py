"""免费协议诊断：完整正常轨迹、动态工具边和版本失败；非效果评测。"""
import copy
import hashlib
import json

import pytest

from src.adapters.trace_rsi_motif_compiler import (
    PREFIX, compile_trace_rsi_motifs, file_sha256, load_provider_tools,
)
from src.adapters.trace_tool_evidence import digest


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n', encoding='utf8')


def frozen(root, name='measure_observed_rows'):
    path = root / (name + '.frozen.json')
    if path.exists():
        return path, json.loads(path.read_text())
    candidate = {'schema_version': 1, 'name': name, 'description': '诊断夹具：不是模型生成效果证据',
        'input_schema': {'type': 'object', 'properties': {'rows': {'type': 'array',
            'items': {'type': 'string'}}}, 'required': ['rows'], 'additionalProperties': False},
        'output_schema': {'type': 'object', 'properties': {'count': {'type': 'integer'}},
            'required': ['count'], 'additionalProperties': False},
        'program': ['object', {'count': ['count', ['get', ['var', 'input'], ['lit', 'rows']]]}]}
    provenance = {'learning_session_id': 'learning-session', 'proposal': {'input_bindings': {
        'rows': {'file': 'triage.json', 'pointer': '/rows'}}}}
    certification = {'status': 'passed', 'kind': 'source_replay', 'heldout_cases': 2}
    body = {'schema_version': 1, 'kind': 'model_generated_trace_tool', 'candidate': candidate,
        'candidate_sha256': digest(candidate), 'provenance': provenance,
        'provenance_sha256': digest(provenance), 'certification': certification,
        'certification_sha256': digest(certification)}
    value = {**body, 'manifest_digest': digest(body)}
    save(path, value)
    return path, value


def make_run(root, name='a', *, anchor='inspect_state', session=None,
             generated='measure_observed_rows', narration=True, repeats=1,
             interleave=False, failed_anchor=False, double_request=False, alias=False):
    run = root / name
    work = run / 'work'
    work.mkdir(parents=True)
    (run / 'requests').mkdir()
    code = root / 'engine.ts'
    code.write_text('export const diagnostic = true;\n')
    source = run / 'immutable-source.json'
    save(source, {'case': name})
    catalog = {'case': name, 'version': 1}
    report = {'rows': [name + '-one', name + '-two']}
    save(work / 'catalog.json', catalog)
    save(work / 'triage.json', report)
    library, artifact = frozen(root, generated)
    schema = lambda properties: {'type': 'object', 'properties': properties,
        'required': list(properties), 'additionalProperties': False}
    definitions = [
        {'name': 'native_diagnostic', 'parameters': schema({})},
        {'name': PREFIX + anchor, 'parameters': schema({}) if anchor != 'replace_report' else
            schema({'report_sha256': {'type': 'string'}, 'report': {'type': 'object'}})},
        {'name': PREFIX + generated, 'parameters': schema({'input_id': {'type': 'string'}})},
    ]
    config = {'mode': 'baseline', 'case_id': name, 'session_id': session or 'session-' + name,
        'work': str(work), 'library_path': str(library), 'tool_digest': artifact['manifest_digest'],
        'candidate_sha256': artifact['candidate_sha256'],
        'source_files': {str(source): file_sha256(source),
                         str(work / 'catalog.json'): file_sha256(work / 'catalog.json')},
        'catalog_path': str(work / 'catalog.json'), 'catalog_sha256': file_sha256(work / 'catalog.json'),
        'code_files': {str(code): file_sha256(code)}, 'prompt_sha256': hashlib.sha256(name.encode()).hexdigest(),
        'policy_files_sha256': {'diagnostic-policy': 'd' * 64}}
    config['source_version'] = digest(config['source_files'])
    receipt = {'input_sha256': digest({'rows': report['rows']}),
        'report_sha256': file_sha256(work / 'triage.json'),
        'catalog_sha256': file_sha256(work / 'catalog.json'),
        'candidate_sha256': artifact['candidate_sha256'], 'source_version': config['source_version']}
    receipt['input_id'] = 'trace-input-' + digest({**receipt, 'session_id': config['session_id']})
    operations = []
    for _ in range(repeats):
        args = {} if anchor != 'replace_report' else {'report_sha256': 'a' * 64, 'report': report}
        output = receipt if anchor == 'replace_report' else {**receipt, 'report': report, 'input': {'rows': report['rows']}}
        operations.append((PREFIX + anchor, args, output, not failed_anchor))
        if interleave:
            operations.append(('native_diagnostic', {}, {'unrelated': True}, True))
        operations.append((PREFIX + generated, {'input_id': receipt['input_id']},
                           {**receipt, 'output': {'count': 2}}, True))
    provider = {'tools': [{'type': 'function', 'function': t} for t in definitions]}
    rows = []
    wrapper = 'session_id' if alias else 'sessionId'
    for ordinal, (tool, args, output, ok) in enumerate(operations, 1):
        call_id = 'call-' + str(ordinal)
        content = ([{'type': 'text', 'text': '保留此旁白；不将局部边当成整请求。'}] if narration else [])
        content.append({'type': 'tool-call', 'id': call_id, 'name': tool, 'arguments': json.dumps(args)})
        events = [
            {'type': 'assistant/message', 'data': {'step': ordinal, 'message': {'content': content}}},
            {'type': 'tool/call', 'data': {'step': ordinal, 'callId': call_id, 'name': tool, 'arguments': args}},
            {'type': 'tool/result', 'data': {'message': {'source': {'callId': call_id}, 'content': [
                {'type': 'tool-result', 'toolCallId': call_id, 'isError': not ok,
                 'content': [{'type': 'text', 'text': json.dumps(output)}]}]}}},
        ]
        rows.extend({wrapper: config['session_id'], 'event': e} for e in events)
        save(run / 'requests' / f'{ordinal}.json', json.dumps(provider) if double_request else provider)
    ordinal = len(operations) + 1
    rows.append({wrapper: config['session_id'], 'event': {'type': 'assistant/message',
        'data': {'step': ordinal, 'message': {'content': [{'type': 'text', 'text': '阶段完成'}]}}}})
    # A contradictory child event must never become root training evidence.
    rows.insert(0, {wrapper: 'child-session', 'event': {'type': 'tool/result', 'data': {}}})
    save(run / 'requests' / f'{ordinal}.json', json.dumps(provider) if double_request else provider)
    for filename, value in [
        ('config.json', config), ('manifest.json', config),
        ('metrics.json', {'status': 'completed', 'actual_requests': ordinal, 'actual_model_skips': 0}),
        ('verification.json', {'completed': True, 'normal_case_valid': True,
                              'source_unchanged': True, 'stage_output_passed': True}),
    ]:
        save(run / filename, value)
    write_events(run, rows)
    return run


def events(run):
    return [json.loads(line) for line in (run / 'events.jsonl').read_text().splitlines()]


def write_events(run, rows):
    (run / 'events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))


def change_metadata(run, filename, key, value):
    path = run / filename
    data = json.loads(path.read_text())
    data[key] = value
    save(path, data)


def test_real_model_declarations_mine_dynamic_tool_names_and_keep_narration(tmp_path):
    a = make_run(tmp_path, 'a', generated='another_observed_program')
    b = make_run(tmp_path, 'b', generated='another_observed_program', alias=True, double_request=True)
    library = compile_trace_rsi_motifs([a, b])
    motif, = library['motifs']
    assert motif['anchor'] == PREFIX + 'inspect_state'
    assert motif['next'] == PREFIX + 'another_observed_program'
    assert motif['parameter_binding'] == {'input_id': '/input_id'}
    assert motif['training_session_count'] == 2
    assert {w['case_id'] for w in motif['witnesses']} == {'a', 'b'}
    assert all(w['next_text_blocks'] == 1 and w['anchor_text_blocks'] == 1 for w in motif['witnesses'])
    assert all(w['anchor_request'] + 1 == w['next_request'] for w in motif['witnesses'])
    assert library['execution_policy'] == 'shadow_only'
    assert library['manifest_digest'] == digest({k: v for k, v in library.items() if k != 'manifest_digest'})


def test_repetitions_inside_one_session_remain_single_session_candidate(tmp_path):
    library = compile_trace_rsi_motifs([make_run(tmp_path, repeats=2)])
    motif, = library['motifs']
    assert len(motif['witnesses']) == 2 and motif['training_session_count'] == 1
    assert motif['support'] == 'single_session_candidate'


def test_anchor_is_observed_not_a_handwritten_write_check_edge(tmp_path):
    read = make_run(tmp_path, 'a')
    write = make_run(tmp_path, 'b', anchor='replace_report')
    # Different ordered contracts cannot be silently combined into one library.
    with pytest.raises(ValueError, match='drift'):
        compile_trace_rsi_motifs([read, write])
    motif, = compile_trace_rsi_motifs([write])['motifs']
    assert motif['anchor'] == PREFIX + 'replace_report'


@pytest.mark.parametrize('kwargs', [{'interleave': True}, {'failed_anchor': True}])
def test_unknown_interleaving_and_failure_break_local_edge(tmp_path, kwargs):
    library = compile_trace_rsi_motifs([make_run(tmp_path, **kwargs)])
    assert library['motifs'] == [] and library['rejected']


@pytest.mark.parametrize('field', ['input_sha256', 'report_sha256', 'source_version',
                                 'candidate_sha256', 'catalog_sha256'])
def test_anchor_and_check_cannot_use_different_receipt_versions(tmp_path, field):
    run = make_run(tmp_path)
    rows = events(run)
    for row in rows:
        e = row['event']
        if e['type'] == 'tool/result' and e.get('data', {}).get('message', {}).get('source', {}).get('callId') == 'call-1':
            block = e['data']['message']['content'][0]
            value = json.loads(block['content'][0]['text'])
            value[field] = 'f' * 64
            base = {k: value[k] for k in ('input_sha256', 'report_sha256', 'source_version',
                                         'candidate_sha256', 'catalog_sha256')}
            value['input_id'] = 'trace-input-' + digest({**base, 'session_id': 'session-a'})
            block['content'][0]['text'] = json.dumps(value)
    write_events(run, rows)
    assert compile_trace_rsi_motifs([run])['motifs'] == []


def test_check_arguments_must_use_the_observed_anchor_handle(tmp_path):
    run = make_run(tmp_path)
    rows = events(run)
    for row in rows:
        e = row['event']
        if e['type'] == 'assistant/message':
            for block in e['data']['message']['content']:
                if block.get('id') == 'call-2':
                    block['arguments'] = json.dumps({'input_id': 'guessed'})
        elif e['type'] == 'tool/call' and e['data']['callId'] == 'call-2':
            e['data']['arguments'] = {'input_id': 'guessed'}
    write_events(run, rows)
    assert compile_trace_rsi_motifs([run])['motifs'] == []


@pytest.mark.parametrize('failure', ['declaration', 'orphan', 'duplicate', 'missing'])
def test_unpaired_or_changed_model_call_evidence_rejects_trace(tmp_path, failure):
    run = make_run(tmp_path)
    rows = events(run)
    if failure == 'declaration':
        next(r['event']['data'] for r in rows if r['event']['type'] == 'tool/call')['arguments'] = {'forged': True}
    else:
        index = next(i for i, r in enumerate(rows) if r['event']['type'] == 'tool/result' and
                     r['event']['data'].get('message', {}).get('source', {}).get('callId') == 'call-1')
        if failure == 'orphan':
            rows[index]['event']['data']['message']['content'][0]['toolCallId'] = 'not-called'
        elif failure == 'duplicate':
            rows.insert(index + 1, copy.deepcopy(rows[index]))
        else:
            del rows[index]
    write_events(run, rows)
    with pytest.raises(ValueError, match='declaration|unpaired|completion'):
        compile_trace_rsi_motifs([run])


@pytest.mark.parametrize('filename,key,value', [
    ('config.json', 'mode', 'shadow'), ('config.json', 'mode', 'learning'),
    ('metrics.json', 'actual_model_skips', 1), ('metrics.json', 'status', 'failed'),
    ('verification.json', 'normal_case_valid', False), ('verification.json', 'source_unchanged', False),
    ('verification.json', 'stage_output_passed', False), ('verification.json', 'completed', False),
])
def test_evaluation_learning_and_failed_deliveries_cannot_train(tmp_path, filename, key, value):
    run = make_run(tmp_path)
    change_metadata(run, filename, key, value)
    with pytest.raises(ValueError, match='normal_baseline'):
        compile_trace_rsi_motifs([run])


def test_ordered_schema_and_actual_files_are_dependency_guards(tmp_path):
    run = make_run(tmp_path, double_request=True)
    path = run / 'requests' / '2.json'
    request = json.loads(json.loads(path.read_text()))
    request['tools'].reverse()
    save(path, json.dumps(request))
    with pytest.raises(ValueError, match='contract_drift'):
        compile_trace_rsi_motifs([run])
    run2 = make_run(tmp_path, 'b')
    (run2 / 'immutable-source.json').write_text('changed')
    with pytest.raises(ValueError, match='file_version_changed'):
        compile_trace_rsi_motifs([run2])


def test_duplicate_sessions_and_learning_producer_are_not_independent(tmp_path):
    a = make_run(tmp_path, 'a', session='same')
    b = make_run(tmp_path, 'b', session='same')
    with pytest.raises(ValueError, match='independent'):
        compile_trace_rsi_motifs([a, b])
    c = make_run(tmp_path, 'c', session='learning-session')
    with pytest.raises(ValueError, match='learning_session'):
        compile_trace_rsi_motifs([c])


def test_manifest_policy_candidate_and_final_report_are_preserved(tmp_path):
    run = make_run(tmp_path)
    change_metadata(run, 'manifest.json', 'policy_files_sha256', {})
    with pytest.raises(ValueError, match='policy_mismatch'):
        compile_trace_rsi_motifs([run])
    run2 = make_run(tmp_path, 'b')
    with pytest.raises(ValueError, match='supplied_candidate'):
        compile_trace_rsi_motifs([run2], {'name': 'different_program'})
    (run2 / 'work' / 'triage.json').write_text('{"rows":[]}\n')
    with pytest.raises(ValueError, match='final_report'):
        compile_trace_rsi_motifs([run2])


def test_double_encoded_provider_receipts_are_loaded_only_as_objects(tmp_path):
    path = tmp_path / 'request.json'
    save(path, json.dumps({'tools': [{'function': {'name': 'x', 'parameters': {'type': 'object'}}}]}))
    assert load_provider_tools(path) == [{'name': 'x', 'parameters': {'type': 'object'}}]
    save(path, json.dumps(json.dumps({'tools': []})))
    with pytest.raises(ValueError, match='request_object'):
        load_provider_tools(path)
