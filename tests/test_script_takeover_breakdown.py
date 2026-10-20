"""离线诊断正确性；不替代真实模型收益验收。"""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('takeover', Path(__file__).resolve().parents[1] / 'scripts/analyze-script-takeover.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_components_accept_only_ledger_rounding_not_unexplained_cost():
    row = {'model': 'deepseek-flash', 'response_usage': {
        'prompt_tokens': 13, 'prompt_cache_hit_tokens': 11,
        'prompt_cache_miss_tokens': 2, 'completion_tokens': 7},
        'observed_peak_usd': .00000907}
    values = m.components(row)
    assert values is not None
    assert abs(sum(values.values()) - .000009066) < 1e-12
    assert m.components({**row, 'observed_peak_usd': .01}) is None
    row['response_usage']['prompt_tokens'] += 1
    assert m.components(row) is None


def test_malformed_arguments_do_not_disappear_as_empty_dispatch():
    detail = m.diagnose_call({'name': 'mcp__report__stage', 'arguments': '{"rows":['}, '.', set())
    assert detail['blocker'] == 'invalid_tool_argument_json'
    assert not detail['arguments_valid']


def test_embedded_python_measurement_never_promotes_shell_sequence(tmp_path):
    (tmp_path / 'inputs').mkdir()
    command = "echo preparing && python3 - <<'PY'\nprint('" + 'a' * 220 + "')\nPY"
    detail = m.diagnose_call({'name': 'bash', 'arguments': {'command': command}}, tmp_path, set())
    assert detail['python_fragments'] == 1
    assert detail['long_string_value_chars'] == 220
    assert detail['blocker'] == 'shell_form_not_mined'


def test_equal_skeletons_do_not_imply_equal_values_or_certification():
    a = m.source_features('python3 -c "print(123)"')
    b = m.source_features('python3 -c "print(999)"')
    assert a['skeletons'] == b['skeletons']
    assert 'certified' not in a


def test_only_frozen_program_identity_is_marked_present(tmp_path):
    (tmp_path / 'inputs').mkdir()
    source = tmp_path / 'inputs' / 'document.txt'
    source.write_text('content')
    command = "python3 - <<'PY'\ns=open('/work/inputs/document.txt').read()\nprint(len(s))\nPY"
    block = {'name': 'bash', 'arguments': {'command': command}}
    first = m.diagnose_call(block, tmp_path, set())
    assert first['blocker'] == 'candidate_not_in_frozen_library'
    second = m.diagnose_call(block, tmp_path, {first['candidate_id']})
    assert second['blocker'] == 'frozen_program_requires_current_activation'
    assert 'not_certification' in second['admission_scope']


def test_shell_exit_marker_is_separate_from_native_tool_exception():
    block = {'isError': False, 'content': [{'type': 'text', 'text': 'Traceback\n[exit code: 1]'}]}
    assert m.shell_exit_marker(block) == 1
    assert m.shell_exit_marker({'content': [{'type': 'text', 'text': 'HTTPError handled successfully'}]}) is None
    assert m.shell_exit_marker({'content': [{'type': 'text', 'text': '[exit code: 0]'}]}) == 0


def test_multi_call_request_is_charged_once_and_unknown_usage_stays_visible(tmp_path):
    (tmp_path / 'effective-config.json').write_text(json.dumps({'workspace': str(tmp_path)}))
    calls = [{'type': 'tool-call', 'name': 'mcp__docs__read', 'arguments': {'id': x}}
             for x in ['first', 'second']]
    event = {'type': 'assistant/message', 'time': 1000, 'data': {
        'usage': {'outputTokens': 1}, 'message': {'content': calls}}}
    (tmp_path / 'events.jsonl').write_text(json.dumps(event))
    ledger = [{'request_id': 1, 'request_utc_epoch': 1, 'model': 'deepseek-flash',
               'observed_peak_usd': .0000015, 'response_usage': {
                   'prompt_tokens': 1, 'prompt_cache_hit_tokens': 0,
                   'prompt_cache_miss_tokens': 1, 'completion_tokens': 1}},
              {'request_id': 2, 'request_utc_epoch': 2,
               'observed_peak_usd': .001, 'response_usage': {}}]
    (tmp_path / 'ledger.jsonl').write_text('\n'.join(map(json.dumps, ledger)))
    result = m.analyze(tmp_path, {'programs': [], 'digest': 'diagnostic'})
    assert result['accounting']['requests'] == 1
    assert result['accounting']['unknown_usage_requests'] == 1
    assert result['accounting']['cost_components_verified_requests'] == 1
    assert len(result['requests'][0]['calls']) == 2
    assert result['blockers']['scene_tool_not_script_operator']['requests'] == 1
    assert result['accounting']['estimated_usd'] == .0000015
