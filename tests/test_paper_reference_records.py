"""Read-only tool extraction, duplicate preservation and provenance failures."""
import hashlib
import importlib.util
from pathlib import Path
import pytest
from src.adapters.paper_bibliography import bib_records

spec = importlib.util.spec_from_file_location('paper_record_checks', Path(__file__).parents[1] /
                                             'scenarios/paper-submission/checks.py')
checks = importlib.util.module_from_spec(spec); spec.loader.exec_module(checks)


def test_formal_lookup_is_bound_prior_evidence_and_preserves_ambiguity(tmp_path, monkeypatch):
    e, pin, source = evidence(tmp_path, '@article{a,title={A},eprint={2401.02954},doi={10.1234/a}}\n'
                                      '@article{b,title={B},eprint={2401.02954}}')
    handle=e.inspect_citations(pin['source_id'])['citation_id']
    with pytest.raises(ValueError,match='before formal'):e.read_formal_metadata(handle)
    monkeypatch.setattr(checks,'fetch_metadata',lambda ids:{'items':[{'requested_id':ids[0], 'doi':'10.1234/a'}]})
    e.read_preprints(handle)
    queries=[]
    monkeypatch.setattr(checks,'fetch_crossref',lambda **args:queries.append(args) or {'records':[],'status':'empty'})
    result=e.read_formal_metadata(handle)
    assert queries==[{'doi':'10.1234/a'}]
    assert len(result['items'])==2 and not result['formal_publication_confirmed']
    (source/'refs.bib').write_text('@article{a,title={Changed}}')
    with pytest.raises(ValueError,match='changed'):e.read_formal_metadata(handle)
    e, pin, _=evidence(tmp_path/'second', '@article{a,title={A},eprint={2401.02954}}\n'
                                       '@article{a,title={Other},eprint={2401.02954}}')
    handle=e.inspect_citations(pin['source_id'])['citation_id'];e.read_preprints(handle)
    queries.clear();result=e.read_formal_metadata(handle)
    assert queries==[] and result['items'][0]['status']=='ambiguous_original_records'


def evidence(tmp_path, bib):
    root = tmp_path/'case'; root.mkdir(parents=True); source = root/'source'; source.mkdir()
    (source/'main.tex').write_text(r'\input{active}\bibliography{refs}')
    (source/'active.tex').write_text(r'\cite{a,b}')
    (source/'unused.tex').write_text(r'\bibliography{outside}')
    (source/'refs.bib').write_text(bib, encoding='utf-8')
    e = checks.PaperEvidence({'sample': {'root':str(root),'source_dir':'source','main':'main.tex'}}, tmp_path)
    return e, e.pin('sample','sources'), source


def test_batch_keeps_original_bib_order_raw_text_and_duplicates(tmp_path):
    e, pin, source = evidence(tmp_path, '@article{a,title={A {Nested} Title}}\n'
                             '@article{b,title={中文标题}}\n@article{a,title={Other}}')
    result = e.read_references(pin['source_id'], ['b','missing','a'])
    assert [r['key'] for r in result['records']] == ['a','b','a']
    assert [r['entry_index_in_bib'] for r in result['records']] == [0,1,2]
    assert result['missing_keys'] == ['missing'] and result['duplicate_keys'] == {'a':2}
    assert result['reference_authenticity_checked'] is False
    for row in result['records']:
        assert row['record_sha256'] == hashlib.sha256(row['raw_bibtex'].encode()).hexdigest()
        assert row['bib_file_sha256'] == hashlib.sha256((source/'refs.bib').read_bytes()).hexdigest()


def test_wrong_view_unknown_handle_changed_source_and_invalid_batch_fail(tmp_path):
    e, pin, source = evidence(tmp_path, '@article{a,title={A}}')
    for keys in [[], ['a','a'], ['a']*65, ['a\n'], 'a']:
        with pytest.raises(ValueError): e.read_references(pin['source_id'], keys)
    with pytest.raises(ValueError): e.read_references('invented',['a'])
    wrong = e.pin('sample','build')
    with pytest.raises(ValueError, match='view'): e.read_references(wrong['source_id'],['a'])
    (source/'refs.bib').write_text('@article{a,title={Changed}}')
    with pytest.raises(ValueError, match='changed'): e.read_references(pin['source_id'],['a'])


def test_comment_content_never_creates_a_reference_and_macros_remain_raw():
    text='''@comment{ignore
@article{fake,title={Not a work}}
}
@string{venue="An Abbreviation"}
@article{real,title={Title},journal=venue}
'''
    rows = bib_records(text)
    assert [r['key'] for r in rows] == ['real']
    assert 'journal=venue' in rows[0]['raw']


@pytest.mark.parametrize('bib', ['@article{a,title={broken}', '@article(a,title={A})'])
def test_unsupported_or_incomplete_records_do_not_silently_pass(tmp_path, bib):
    e, pin, _ = evidence(tmp_path, bib)
    with pytest.raises(ValueError): e.read_references(pin['source_id'],['a'])


def test_source_change_during_read_is_rejected(tmp_path, monkeypatch):
    e, pin, source = evidence(tmp_path, '@article{a,title={A}}')
    parser = checks.bib_records
    def altered(text):
        records = parser(text)
        (source/'refs.bib').write_text('@article{a,title={Changed}}')
        return records
    monkeypatch.setattr(checks, 'bib_records', altered)
    with pytest.raises(ValueError, match='during'): e.read_references(pin['source_id'],['a'])


def test_citation_batch_is_bound_to_active_keys_and_source_version(tmp_path):
    e, pin, source = evidence(tmp_path, '@article{a,title={A}}\n@article{b,title={B}}\n@article{unused,title={U}}')
    inspected = e.inspect_citations(pin['source_id'])
    result = e.read_citation_records(inspected['citation_id'])
    assert result['requested_keys'] == ['a', 'b']
    assert [r['key'] for r in result['records']] == ['a','b']
    assert result['scope'] == 'active_manuscript_literal_cite_keys_only'
    assert inspected['nocite_included'] is False
    with pytest.raises(ValueError): e.read_citation_records(pin['source_id'])
    other = checks.PaperEvidence(e.inputs, tmp_path)
    with pytest.raises(ValueError): other.read_citation_records(inspected['citation_id'])
    (source/'active.tex').write_text(r'\cite{unused}')
    with pytest.raises(ValueError, match='changed'): e.read_citation_records(inspected['citation_id'])


def test_citation_batch_preserves_missing_duplicates_and_empty_scope(tmp_path):
    e, pin, source = evidence(tmp_path, '@article{a,title={A}}\n@article{a,title={Again}}')
    result = e.read_citation_records(e.inspect_citations(pin['source_id'])['citation_id'])
    assert result['missing_keys'] == ['b'] and result['duplicate_keys'] == {'a':2}
    (source/'active.tex').write_text(r'\nocite{a}')
    fresh = e.pin('sample','sources')
    empty = e.read_citation_records(e.inspect_citations(fresh['source_id'])['citation_id'])
    assert empty['records'] == [] and empty['requested_keys'] == []


def test_citation_identifier_scope_is_explicit_not_an_authenticity_claim(tmp_path):
    e, pin, _ = evidence(tmp_path, '@article{a,title={A},eprint={2401.02954}}\n'
                         '@article{a,title={Again},url={https://arxiv.org/abs/2401.02954v2}}\n'
                         '@article{b,title={B},eprint={2402.12345}}\n'
                         '@article{unused,title={U},eprint={2501.99999}}')
    result=e.read_citation_records(e.inspect_citations(pin['source_id'])['citation_id'])
    assert result['required_reference_pairs']==[{'key':'a','arxiv_id':'2401.02954'}, {'key':'b','arxiv_id':'2402.12345'}]
    assert result['reference_authenticity_checked'] is False
    assert result['identifier_detection']=='literal_arxiv_syntax_candidates_not_authenticity_confirmation'


def test_metadata_fetch_is_source_bound_and_source_mutation_invalidates_return(tmp_path,monkeypatch):
    e, pin, source = evidence(tmp_path,'@article{a,title={A},eprint={2401.02954}}\n@article{b,title={B},eprint={2401.02954}}')
    handle=e.inspect_citations(pin['source_id'])['citation_id']
    calls=[]
    def fetched(ids):
        calls.append(ids); return {'fetch_status':'failed','items':[]}
    monkeypatch.setattr(checks,'fetch_metadata',fetched)
    result=e.read_preprints(handle)
    assert calls==[['2401.02954']] and len(result['required_reference_pairs'])==2
    assert result['metadata']['fetch_status']=='failed' and not result['formal_publication_confirmed']
    def changed(ids):
        (source/'active.tex').write_text(r'\cite{different}')
        return fetched(ids)
    monkeypatch.setattr(checks,'fetch_metadata',changed)
    with pytest.raises(ValueError,match='changed'): e.read_preprints(handle)
    with pytest.raises(ValueError): e.read_preprints('invented')


def test_composite_preserves_raw_records_diagnostics_and_one_deduplicated_fetch(tmp_path,monkeypatch):
    e, _, source = evidence(tmp_path,'@article{a,title={A},eprint={2401.02954}}\n'
                          '@article{a,title={Duplicate},eprint={2401.02954}}')
    calls=[]
    monkeypatch.setattr(checks,'fetch_metadata',lambda ids: calls.append(ids) or
                        {'fetch_status':'failed','items':[]})
    result=e.collect_citation_evidence('sample')
    assert calls==[['2401.02954']]
    assert result['references']['missing_keys']==['b']
    assert result['references']['duplicate_keys']=={'a':2}
    assert len(result['references']['records'])==2
    assert result['references']['citation_id']==result['citation_id']
    assert result['references']['version_sha256']==result['version_sha256']
    assert result['required_reference_pairs']==[{'key':'a','arxiv_id':'2401.02954'}]
    assert result['metadata']['fetch_status']=='failed'
    assert not result['formal_publication_confirmed'] and not result['bibliography_match_confirmed']
    with pytest.raises(ValueError,match='authorised'): e.collect_citation_evidence('other')
    def mutate(ids):
        (source/'active.tex').write_text(r'\cite{other}')
        return {'fetch_status':'obtained','items':[]}
    monkeypatch.setattr(checks,'fetch_metadata',mutate)
    with pytest.raises(ValueError,match='changed'): e.collect_citation_evidence('sample')


def test_empty_composite_has_no_arxiv_request_and_keeps_empty_scope(tmp_path,monkeypatch):
    e,_,source=evidence(tmp_path,'@article{a,title={A}}')
    (source/'active.tex').write_text(r'\nocite{a}')
    calls=[]
    monkeypatch.setattr(checks,'fetch_metadata',lambda ids: calls.append(ids) or
                        {'fetch_status':'no_identifiers','items':[]})
    result=e.collect_citation_evidence('sample')
    assert calls==[[]] and result['required_reference_pairs']==[]
    assert result['references']['records']==[]
