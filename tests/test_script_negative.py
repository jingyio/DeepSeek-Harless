"""Compiler diagnostics. Real trace learning is recorded separately."""
from copy import deepcopy
from src.adapters.script_negative_compiler import compile_negative, digest


def witness(code='invalid_shape', call='a'):
    return dict(tool='mcp__docs__finalize', code=code, tools_sha256='a'*64,
                anchors=[(['version'], ['current_version'])], argument_shape=['version'],
                binding_sha256='b'*64, call_id=call, task_id='task', events_sha256='c'*64)


def test_repeated_failures_compile_but_a_single_witness_does_not():
    assert not compile_negative([witness()], {}, {})['rules']
    x = compile_negative([witness(), witness(call='b')], {}, {})
    assert x['rules'][0]['retry_policy'] == 'prompt_only'
    assert 'binding_sha256' not in str(x['rules'])
    body = {k:v for k,v in x.items() if k!='digest'}
    assert x['digest'] == digest(body)


def test_early_stop_candidate_requires_version_echo_and_nonfailure_contrast():
    rows = [witness(), witness(call='b'), witness(None, 'success')]
    rows[0]['false_paths'] = rows[1]['false_paths'] = [['done'], ['semantic_quality_accepted']]
    rows[2]['false_paths'] = [['semantic_quality_accepted']]
    assert compile_negative(rows, {}, {})['rules'][0]['retry_policy'] == 'warn_then_exact_version_block'
    assert compile_negative(rows, {}, {})['rules'][0]['failure_flags'] == [['done']]
    changed = deepcopy(rows); changed[1]['anchors'] = []
    assert compile_negative(changed, {}, {})['rules'][0]['retry_policy'] == 'prompt_only'
    changed = deepcopy(rows); changed[-1]['tools_sha256'] = 'd'*64
    assert compile_negative(changed, {}, {})['rules'][0]['retry_policy'] == 'prompt_only'


def test_repeated_copy_of_one_execution_is_not_recurrence():
    assert not compile_negative([witness(), witness()], {}, {})['rules']
