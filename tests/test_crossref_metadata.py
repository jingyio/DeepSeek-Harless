import json
import pytest
from src.adapters.crossref_metadata import parse_response, literal_field, DOI


def body(rows):
    return json.dumps({'status':'ok','message':rows}).encode()


def test_identity_is_checked_without_claiming_work_or_formal_version_match():
    row={'DOI':'10.1234/example','title':['A deposited title'],'author':[{'family':'Smith'}],'issued':{'date-parts':[[2024]]}}
    result=parse_response(body(row),doi='10.1234/EXAMPLE')
    assert result['records'][0]==row
    assert not result['work_identity_confirmed'] and not result['formal_version_selected']
    with pytest.raises(ValueError,match='identity'):parse_response(body(row),doi='10.1234/other')


@pytest.mark.parametrize('row',[{'title':['A']},{'DOI':'10.1234/a','title':[]},{'DOI':'bad','title':['A']}])
def test_invalid_records_do_not_become_candidates(row):
    with pytest.raises(ValueError):parse_response(body(row),doi='10.1234/a')


def test_search_empty_is_explicit_and_oversized_or_non_json_is_rejected():
    assert parse_response(body({'items':[]}))['records']==[]
    with pytest.raises(ValueError):parse_response(b'<html>browser check</html>')
    with pytest.raises(ValueError):parse_response(body({'items':[{}]*4}))
    with pytest.raises(ValueError):parse_response(b' '*2000001)


def test_literal_fields_preserve_nested_title_but_do_not_evaluate_macros():
    assert literal_field('@article{a,title={A {Nested} Title},doi="10.1234/x"}','title')=='A Nested Title'
    assert literal_field('@article{a,title=unknown_macro}','title') is None
    assert literal_field('@article{a,title={Unclosed','title') is None
    assert DOI.fullmatch('10.1234/a?x=y')
    assert not DOI.fullmatch('10.1234/a\nsecret')
