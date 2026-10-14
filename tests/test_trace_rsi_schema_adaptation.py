import copy
import pytest
from src.adapters.trace_rsi_schema_adaptation import adapt_required_fields


def schema():
    return {'type': 'array', 'maxItems': 2000, 'items': {'type': 'object',
        'properties': {'key': {'type': 'string'}, 'status': {'type': 'string'},
                       'notes': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['key', 'status', 'notes'], 'additionalProperties': False}}


def test_qualified_minimal_output_becomes_next_input_without_inventing_fields():
    original = schema();saved = copy.deepcopy(original)
    result = adapt_required_fields(original, [[{'key': 'a', 'status': 'checked', 'notes': ['old']},
                                             {'key': 'b', 'status': 'pending'}]])
    assert result['schema']['items']['required'] == ['key', 'status']
    assert result['schema']['items']['additionalProperties'] is False
    assert result['schema']['maxItems'] == 2000
    assert result['schema']['items']['properties'] == original['items']['properties']
    assert original == saved and len(result['changes']) == 1


def test_empty_arrays_do_not_remove_unobserved_requirements():
    original = schema()
    assert adapt_required_fields(original, [[], []])['schema'] == original


def test_unknown_fields_and_type_changes_are_not_implicitly_accepted():
    with pytest.raises(ValueError, match='unknown_witness'):
        adapt_required_fields(schema(), [[{'key': 'a', 'status': 'p', 'foreign': True}]])
    with pytest.raises(ValueError, match='type_change'):
        adapt_required_fields(schema(), [[{'key': 7, 'status': 'p'}]])
