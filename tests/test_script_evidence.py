"""No provider/network calls: admission and HTTP authority diagnostics."""
import importlib.util
from pathlib import Path
import pytest
from src.adapters.script_motif_compiler import extract, compile_script
spec=importlib.util.spec_from_file_location('script_http',Path(__file__).resolve().parents[1]/'scripts/fetch-script-evidence.py')
http=importlib.util.module_from_spec(spec);spec.loader.exec_module(http)

def test_saved_script_arguments_are_bound_not_historical_constants(tmp_path):
    (tmp_path/'code').mkdir();source='import sys\nprint(sys.argv[1:])\n'
    (tmp_path/'code/query.py').write_text(source)
    one=extract("cat > query.py <<'PY'\n"+source+"PY\npython3 query.py first",tmp_path)
    two=extract('python3 query.py different another',tmp_path)
    p=compile_script(one[1],{},argv=one[2]);q=compile_script(two[1],{},argv=two[2])
    assert p['id']==q['id'] and 'first' not in p['template']
    assert p['argv_contract']['kind']=='explicit_model_selected_scalars'
    with pytest.raises(ValueError):extract('python3 query.py first | head',tmp_path)
    with pytest.raises(ValueError):extract("cat > query.py <<'PY'\nprint('changed')\nPY\npython3 query.py first",tmp_path)

@pytest.mark.parametrize('source', ['import sys\nprint(sys.modules)','import sys\nsys.argv=[]\nprint(sys.argv)','import urllib.request\nurllib.request.urlopen=lambda x: x'])
def test_intrinsics_not_mutable(source):
    with pytest.raises(ValueError):compile_script(source,{},argv=['value'])

@pytest.mark.parametrize('url', ['https://127.0.0.1/works','http://export.arxiv.org/api/query?id_list=1606.08415','https://export.arxiv.org/api/query','https://export.arxiv.org/api/query?id_list=1606.08415&max_results=-1','https://export.arxiv.org/api/query?id_list=1606.08415&start=1','https://export.arxiv.org/api/query?id_list=1606.08415&id_list=1910.07467','https://api.crossref.org/works?rows=100','https://api.crossref.org/works?rows=1&mailto=private@example.com','https://api.crossref.org@evil.test/works?rows=1'])
def test_only_bounded_fresh_public_metadata(url):
    with pytest.raises(ValueError):http.validate(url)

def test_existing_read_authorities_supported():
    http.validate('https://export.arxiv.org/api/query?id_list=1606.08415,1910.07467&max_results=2')
    http.validate('https://api.crossref.org/works?query.title=example&rows=3')


def test_vector_cache_preserves_order_and_evicts_without_caching_decisions():
    from src.adapters.embedding_cache import VectorCache
    seen=[];cache=VectorCache(2)
    def encode(texts):
        seen.append(texts);return [[len(t)] for t in texts]
    assert cache.resolve(['a','bb','a'],encode)==[[1],[2],[1]]
    assert cache.resolve(['bb','ccc'],encode)==[[2],[3]]
    assert seen==[['a','bb'],['ccc']]
    assert 'a' not in cache.entries
    assert cache.resolve(['a','ccc'],encode)==[[1],[3]]
