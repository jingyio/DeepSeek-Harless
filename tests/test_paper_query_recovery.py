import json
import pytest
from src.adapters.paper_query_recovery import words,query_payload,validate_queries,recover_queries
from src.adapters.native_motif_compiler import digest


def library():
    p={'service':'crossref','base':'https://api.crossref.org/works','query_key':'query.title',
       'title_transform':'all_words','constants':{'rows':'5','select':'DOI,title'},'read_only':True}
    lib={'schema_version':1,'scope':'source_title_query_recovery','execution_policy':'bounded_readonly_tool',
         'source_traces':{'r':{'session_id':'s'}},'prototypes':[{'id':'query-'+digest(p)[:12],'protocol':p,
         'witnesses':[{'run_id':'r','session_id':'s'}],'training_session_count':1}]}
    lib['manifest_digest']=digest(lib);return lib


def test_caps_invalid_sources_and_unwitnessed_provenance_are_rejected():
    lib=library();validate_queries(lib)
    lib['prototypes'][0]['protocol']['base']='http://127.0.0.1/private'
    lib['prototypes'][0]['id']='query-'+digest(lib['prototypes'][0]['protocol'])[:12]
    lib['manifest_digest']=digest({k:v for k,v in lib.items() if k!='manifest_digest'})
    with pytest.raises(ValueError):validate_queries(lib)
    assert words('A: {Source}-Bound TITLE')==['a','source','bound','title']
    rows=[{'DOI':'10.1234/a','title':['Example']}]*5
    assert len(query_payload(json.dumps({'status':'ok','message':{'items':rows}}).encode())['records'])==5
    with pytest.raises(ValueError):query_payload(json.dumps({'status':'ok','message':{'items':rows+[rows[0]]}}).encode())


def test_ambiguous_duplicate_keys_are_not_silently_selected(monkeypatch):
    def forbidden(*args):raise AssertionError('no network for duplicates')
    monkeypatch.setattr('src.adapters.paper_query_recovery.fetch_query',forbidden)
    records={'citation_id':'current','version_sha256':'a'*64,'required_reference_pairs':[{'key':'k','arxiv_id':'2401.02954'}],
             'records':[{'key':'k'},{'key':'k'}]}
    out=recover_queries(records,library())
    assert out['items']==[] and out['ambiguous_keys']==['k'] and not out['work_identity_confirmed']
