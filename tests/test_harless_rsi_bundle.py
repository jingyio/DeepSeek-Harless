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


def test_new_ppt_release_keeps_artifact_and_current_source_locks():
    root=Path(__file__).resolve().parents[1];bundle=root/'motif-libraries/ppt-web-v2-r3'
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    entry=json.loads((bundle/'entry.json').read_text());cert=json.loads((bundle/'certification.json').read_text())
    report=json.loads((bundle/'learning-report.json').read_text());missing_build=False
    assert entry['new_training'] is True and report['training_tasks']==2 and report['heldout_tasks']==1
    assert report['compilation_model_requests']==0 and report['quality_cost_promoted'] is False
    for name,version in entry['files'].items():assert sha(bundle/name)==version,name
    for name,version in cert['code_locks'].items():
        path=root/name
        if '/dist/' in name and not path.exists():missing_build=True;continue
        assert sha(path)==version,name
    if not missing_build:
        admitted=load_product_bundle(root,bundle,'ppt')
        assert admitted['binding_policy']=='ppt_uploaded_sources_v2'
        assert len(admitted['certified_tool_schema_variants'])==30


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


def learned_fixture(root):
    root.mkdir();(root/'core.mjs').write_text('locked runtime')
    bundle=root/'motif-libraries/ppt-web-v2';bundle.mkdir(parents=True)
    schemas=[{'name':'mcp__ppt__tool_'+str(i)} for i in range(21)]
    identity=lambda n:{'research_decision_id':'decision-'+str(n),'question_sha256':str(n)*64}
    values={'library.json':{},'online-manifest.json':{},'task.json':{},'tool-schemas.json':schemas,
            'tool-schema-variants.json':[schemas],
            'source-evidence.json':{'train':[identity(1),identity(2)],'heldout':[identity(3)]},
            'learning-report.json':{'new_training':True,'training_tasks':2,'heldout_tasks':1,'quality_cost_promoted':False}}
    def seal():
        for name,value in values.items():(bundle/name).write_text(json.dumps(value))
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        cert={'schema_version':1,'scene':'ppt','binding_policy':'ppt_uploaded_sources_v2',
              'matching_policy':'structural_only','certification_scope':'independent_trace_structure',
              'source_evidence_sha256':sha(bundle/'source-evidence.json'),
              'learning_report_sha256':sha(bundle/'learning-report.json'),
              'file_locks':{n:sha(bundle/n) for n in values},'code_locks':{'core.mjs':sha(root/'core.mjs')}}
        (bundle/'certification.json').write_text(json.dumps(cert))
        (bundle/'entry.json').write_text(json.dumps({'schema_version':1,'scene':'ppt','runtime_kind':'ppt_read_v2',
            'mode':'execute','new_training':True,'files':{n:sha(bundle/n) for n in [*values,'certification.json']}}))
    seal();return bundle,values,seal


def test_learned_ppt_keeps_independent_decisions_and_rejects_relabelled_duplicates(tmp_path):
    root=tmp_path/'repo';bundle,values,seal=learned_fixture(root)
    assert load_product_bundle(root,bundle,'ppt')['binding_policy']=='ppt_uploaded_sources_v2'
    values['source-evidence.json']['heldout'][0]['question_sha256']='1'*64;seal()
    with pytest.raises(ValueError,match='identical research questions'):load_product_bundle(root,bundle,'ppt')


def test_learned_ppt_rejects_changed_schema_and_runtime(tmp_path):
    root=tmp_path/'repo';bundle,values,seal=learned_fixture(root)
    (bundle/'tool-schema-variants.json').write_text('[]')
    with pytest.raises(ValueError,match='artifact changed'):load_product_bundle(root,bundle,'ppt')
    seal();(root/'core.mjs').write_text('changed')
    with pytest.raises(ValueError,match='code changed'):load_product_bundle(root,bundle,'ppt')
