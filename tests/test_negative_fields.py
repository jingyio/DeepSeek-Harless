"""Read-only validator slicing and intervention diagnostics, no provider."""
import inspect
import pytest
from src.adapters.negative_field_compiler import extract_guards, certify_field_guard, evaluate, UnsupportedGuard


def sample_validator(document):
    rows = document['records']
    tags = [row['tag'] for row in rows]
    if len(tags) != len(set(tags)):
        raise ValueError('collision')


def compiled_sample():
    failed = {'owner': 'current', 'report': {'records': [{'tag': 'a'}, {'tag': 'a'}], 'notes': ['first', 'second'], 'title': 'sample'}}
    valid = {'records': [{'tag': 'a'}, {'tag': 'b'}], 'notes': [], 'title': 'contrast'}
    return certify_field_guard(sample_validator, 'collision', [failed], [valid])


def test_field_names_and_error_names_are_extracted_not_registered():
    guard = compiled_sample()
    assert guard['state_root'] == ['report']
    assert guard['read_paths'] == [['records', '*', 'tag']]
    assert len(guard['certification']['unrelated_edit_paths']) >= 2
    assert evaluate(guard['predicate'], {'records': [{'tag': 'a'}, {'tag': 'a'}]}) is True
    assert evaluate(guard['predicate'], {'records': [{'tag': 'a'}, {'tag': 'b'}]}) is False


def test_paper_validator_uses_the_same_generic_def_use_compiler():
    from src.adapters.paper_renderer import validate_audit
    guard = extract_guards(inspect.getsource(validate_audit), 'validate_audit')
    assert guard['renderer_input_duplicate_source_ids']['read_paths'] == [['sources', '*', 'id']]
    assert 'renderer_input_invalid_status_priority' not in guard


@pytest.mark.parametrize('source', [
    "def v(x):\n if x['flag']: return\n if len(x['r']) != len(set(x['r'])): raise ValueError('e')",
    "def v(x):\n x['r'] = []\n if len(x['r']) != len(set(x['r'])): raise ValueError('e')",
    "def v(x):\n x['r'].clear()\n if len(x['r']) != len(set(x['r'])): raise ValueError('e')",
])
def test_mutation_or_early_exit_cannot_be_promoted(source):
    with pytest.raises(UnsupportedGuard): extract_guards(source, 'v')


@pytest.mark.parametrize('assignment', ["if x['flag']: ids = []", 'ids = other = []', 'ids: list = []'])
def test_unsupported_assignment_invalidates_the_old_alias(assignment):
    source = "def v(x):\n ids = [r['key'] for r in x['r']]\n " + assignment + "\n if len(ids) != len(set(ids)): raise ValueError('e')"
    assert 'e' not in extract_guards(source, 'v')


def test_shadowed_builtin_is_not_lowered_as_a_builtin():
    with pytest.raises(UnsupportedGuard):
        extract_guards("def v(x):\n len = custom\n if len(x['r']) != 0: raise ValueError('e')", 'v')


OPTIONS = {'states': ['ready', 'done'], 'max_rows': 3}


def heterogeneous_validator(document):
    rows = document['items']
    for row in rows:
        if row['state'] not in OPTIONS['states']:
            raise ValueError('unsupported_state')
        if row['enabled']:
            if not isinstance(row['payload'], list) or not all(isinstance(v, str) for v in row['payload']):
                raise ValueError('payload_shape')
        if not set(row['links']) <= set(document['allowed']):
            raise ValueError('dangling_link')
    if len(rows) > OPTIONS['max_rows']:
        raise ValueError('collection_bound')


def shape_validator(document):
    for row in document['entries']:
        if not isinstance(row, dict) or not set(('label', 'links')) <= row.keys():
            raise ValueError('missing_fields')
        if not isinstance(row['label'], str):
            raise ValueError('label_type')


def gated_validator(document):
    if document['strict']:
        for row in document['entries']:
            if row['amount'] > 5:
                raise ValueError('range_violation')
    else:
        for row in document['entries']:
            if row['amount'] < 0:
                raise ValueError('range_violation')


def heterogeneous_cases():
    import copy
    valid = {'items': [{'state': 'ready', 'enabled': True, 'payload': ['x'], 'links': ['a']}], 'allowed': ['a'], 'notes': ['one', 'two']}
    cases = []
    for code, field, value in [('unsupported_state', 'state', 'invalid'), ('payload_shape', 'payload', None), ('dangling_link', 'links', ['absent'])]:
        failed = copy.deepcopy(valid);failed['items'][0][field] = value
        cases.append((heterogeneous_validator, code, failed, valid))
    failed = copy.deepcopy(valid);failed['items'] *= 4
    cases.append((heterogeneous_validator, 'collection_bound', failed, valid))
    shape = {'entries': [{'label': 'x', 'links': []}], 'notes': ['one', 'two']}
    for code, row in [('missing_fields', {'links': []}), ('label_type', {'label': None, 'links': []})]:
        failed = copy.deepcopy(shape);failed['entries'] = [row]
        cases.append((shape_validator, code, failed, shape))
    cases.append((gated_validator, 'range_violation', {'strict': True, 'entries': [{'amount': 7}], 'notes': ['one', 'two']}, {'strict': True, 'entries': [{'amount': 2}], 'notes': ['one', 'two']}))
    return cases


def compiled_cases():
    return [{'guard': certify_field_guard(fn, code, [{'report': failed}], [valid]), 'failed': {'report': failed}, 'valid': {'report': valid}}
            for fn, code, failed, valid in heterogeneous_cases()]


@pytest.mark.parametrize('fn,code,failed,valid', heterogeneous_cases(), ids=lambda x: x.__name__ if callable(x) else x if isinstance(x, str) else '')
def test_multiple_error_families_learn_without_error_field_registration(fn, code, failed, valid):
    guard = certify_field_guard(fn, code, [{'report': failed}], [valid])
    assert guard['version'] == 2
    assert evaluate(guard['predicate'], failed) is True
    assert evaluate(guard['predicate'], valid) is False
    evidence = guard['certification']['cause_interventions']
    assert evidence['repair']['result_error'] != code
    assert evidence['reintroduction']['result_error'] == code
    assert evidence['repair']['changed_paths']
    assert evidence['reintroduction']['changed_paths']


def test_nested_control_dependency_and_shared_error_branches_are_preserved():
    guards = extract_guards(inspect.getsource(gated_validator), 'gated_validator')
    guard = guards['range_violation']
    assert ['strict'] in guard['read_paths']
    assert evaluate(guard['predicate'], {'strict': True, 'entries': [{'amount': 7}]}) is True
    assert evaluate(guard['predicate'], {'strict': False, 'entries': [{'amount': 7}]}) is False
    assert evaluate(guard['predicate'], {'strict': False, 'entries': [{'amount': -1}]}) is True
    # Payload is checked only when enabled: a false gate is not an error.
    guards = extract_guards(inspect.getsource(heterogeneous_validator), 'heterogeneous_validator', {'OPTIONS': OPTIONS})
    assert ['items', '*', 'enabled'] in guards['payload_shape']['read_paths']
    assert evaluate(guards['payload_shape']['predicate'], {'items': [{'enabled': False, 'payload': None}]}) is False


def test_swallowed_exception_and_ambiguous_numeric_identity_do_not_compile():
    with pytest.raises(UnsupportedGuard):
        extract_guards("def v(x):\n try:\n  if x['bad']: raise ValueError('e')\n except ValueError: pass", 'v')
    assert not extract_guards("def v(x):\n if type(x['n']) is not int: raise ValueError('e')", 'v')


def test_literal_schema_cannot_be_replaced_without_recertification(monkeypatch):
    monkeypatch.setitem(heterogeneous_validator.__globals__, 'OPTIONS', {'states': ['different'], 'max_rows': 3})
    fn, code, failed, valid = heterogeneous_cases()[0]
    with pytest.raises(UnsupportedGuard, match='no_supported_failure_slice'):
        certify_field_guard(fn, code, [{'report': failed}], [valid])


def test_profile_module_loaded_without_sys_modules_registration_is_supported():
    import importlib.util
    spec = importlib.util.spec_from_file_location('diagnostic_unregistered_validator', __file__)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    failed = {'records': [{'tag': 'a'}, {'tag': 'a'}], 'notes': ['one', 'two']}
    valid = {'records': [{'tag': 'a'}, {'tag': 'b'}], 'notes': ['one', 'two']}
    guard = certify_field_guard(module.sample_validator, 'collision', [{'report': failed}], [valid])
    assert guard['version'] == 2


def container_validator(document):
    if isinstance(tuple(document['values']), list) or document['bad']:
        raise ValueError('container_gate')


def compiled_container_case():
    failed = {'values': ['x'], 'bad': True, 'notes': ['one', 'two']}
    valid = {'values': ['x'], 'bad': False, 'notes': ['one', 'two']}
    return {'guard': certify_field_guard(container_validator, 'container_gate', [{'report': failed}], [valid]), 'failed': {'report': failed}, 'valid': {'report': valid}}


def test_python_tuple_identity_does_not_turn_into_a_json_list_condition():
    case = compiled_container_case()
    assert evaluate(case['guard']['predicate'], case['failed']['report']) is True
    assert evaluate(case['guard']['predicate'], case['valid']['report']) is False
    for source in [
        "def v(x):\n gen = (v for v in x['r'])\n if gen == x['r'] or x['bad']: raise ValueError('e')",
        "def v(x):\n if (v for v in x['r']) == x['r'] or x['bad']: raise ValueError('e')",
    ]:
        assert not extract_guards(source, 'v')
