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
