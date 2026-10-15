import hashlib
import json
from pathlib import Path
import pytest
from src.adapters.harless_rsi_bundle import load_ppt_bundle, load_product_bundle


def test_registered_ppt_compatibility_matches_current_source_and_original_artifacts():
    root = Path(__file__).resolve().parents[1]
    bundle = root / 'motif-libraries/ppt'
    entry = json.loads((bundle / 'entry.json').read_text())
    binding = json.loads((bundle / 'runtime-bindings.json').read_text())
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert entry['new_training'] is False and binding['validation']['new_training'] is False
    assert binding['original_certification_sha256'] == sha(bundle / 'certification.json')
    for name, expected in entry['files'].items():
        assert sha(bundle / name) == expected, name
    generated_missing = False
    for name, expected in binding['code_locks'].items():
        path = root / name
        # The root test command does not build optional PPT TypeScript. Source
        # locks must still fail immediately; deployments also verify the build.
        if '/dist/' in name and not path.exists():
            generated_missing = True
            continue
        assert sha(path) == expected, name
    if not generated_missing:
        admitted = load_product_bundle(root, bundle, 'ppt')
        assert admitted['binding_policy'] == 'ppt_uploaded_sources_v1'
        assert admitted['quality_cost_promoted'] is False


def test_bundle_freezes_runtime_code_artifacts_and_whole_schema(tmp_path):
    root=tmp_path/'project';root.mkdir();code=root/'core.mjs';code.write_text('version one')
    bundle=tmp_path/'runtime';bundle.mkdir()
    data={'online-manifest.json':{},'library.json':{},'task.json':{},'tool-schemas.json':[{'name':'mcp__ppt__read_source'}]}
    for name,value in data.items():(bundle/name).write_text(json.dumps(value))
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    cert={'schema_version':1,'scene':'ppt','binding_policy':'ppt_uploaded_sources_v1',
          'matching_policy':'structural_only','certification_scope':'independent_trace_structure',
          'source_evidence_sha256':'a'*64,'learning_report_sha256':'b'*64,
          'file_locks':{name:sha(bundle/name) for name in data},'code_locks':{'core.mjs':sha(code)}}
    (bundle/'certification.json').write_text(json.dumps(cert))
    got=load_ppt_bundle(root,bundle)
    assert got['matching_policy']=='structural_only' and not got['quality_cost_promoted']
    (bundle/'task.json').write_text('{"changed":true}')
    with pytest.raises(ValueError,match='artifact changed'):load_ppt_bundle(root,bundle)
    (bundle/'task.json').write_text('{}')
    code.write_text('version two')
    with pytest.raises(ValueError,match='code changed'):load_ppt_bundle(root,bundle)


@pytest.mark.parametrize('cert',[{},[],{'schema_version':1,'code_locks':[]},
    {'schema_version':1,'scene':'ppt','matching_policy':'fixed_vectors'}])
def test_uncertified_bundle_is_not_loadable(tmp_path,cert):
    (tmp_path/'certification.json').write_text(json.dumps(cert))
    with pytest.raises(ValueError):load_ppt_bundle(tmp_path,tmp_path)
