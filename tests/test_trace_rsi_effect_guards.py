"""免费合成状态诊断，不代表真实模型质量或跳过。
"""
from src.adapters.trace_rsi_effect_guards import allows, certify_conditions, learn_conjunction


def sample(name, output, allowed):
    return {'case_id': name, 'output': output, 'allowed': allowed}


def test_generic_conjunction_uses_negative_states_and_rejects_unknowns():
    rows = [sample('valid', {'complete': True, 'changed': [], 'added': 1}, True),
            sample('no-add', {'complete': True, 'changed': [], 'added': 0}, True),
            sample('missing', {'complete': False, 'changed': [], 'added': 1}, False),
            sample('field', {'complete': True, 'changed': ['a'], 'added': 1}, False)]
    learnt = learn_conjunction(rows)
    assert learnt == {'status': 'candidate', 'conditions': [
        {'feature': 'changed:empty', 'equals': True}, {'feature': 'complete:true', 'equals': True}]}
    assert all(allows(learnt['conditions'], r['output']) == r['allowed'] for r in rows)
    assert not allows(learnt['conditions'], {'complete': True})
    assert not allows(learnt['conditions'], {'complete': 'true', 'changed': []})
    assert not allows([], rows[0]['output'])


def test_independent_no_add_case_rejects_spurious_training_rule():
    learnt = learn_conjunction([sample('p', {'added': 1}, True), sample('n', {'added': 0}, False)])
    assert learnt['conditions'] == [{'feature': 'added:zero', 'equals': False}]
    assert certify_conditions(learnt['conditions'], [sample('no-add', {'added': 0}, True)])['status'] == 'failed'


def test_ambiguous_or_positive_only_states_cannot_create_a_guard():
    assert learn_conjunction([sample('p', {'x': True}, True), sample('n', {'x': True}, False)])['status'] == 'not_separable'
    assert learn_conjunction([sample('a', {'x': True}, True), sample('b', {'x': True}, True)])['status'] == 'insufficient_classes'


def test_certification_retains_every_counterexample():
    conditions = [{'feature': 'x:true', 'equals': True}]
    result = certify_conditions(conditions, [sample('a', {'x': False}, True), sample('b', {'x': True}, False)])
    assert result['status'] == 'failed' and len(result['failures']) == 2
