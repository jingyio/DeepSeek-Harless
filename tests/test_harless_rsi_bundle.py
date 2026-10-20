import hashlib
import json
from pathlib import Path
import pytest
from src.adapters.harless_rsi_bundle import load_ppt_bundle, load_product_bundle


def test_registered_ppt_compatibility_matches_current_source_and_original_artifacts():
    root = Path(__file__).resolve().parents[1]
    bundle = root / 'motif-libraries/ppt'
    entry = json.loads((bundle / 'entry.json').read_text(encoding='utf-8'))
    binding = json.loads((bundle / 'runtime-bindings.json').read_text(encoding='utf-8'))
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert entry['new_training'] is False and binding['validation']['new_training'] is False
    assert binding['original_certification_sha256'] == sha(bundle / 'certification.json')
    for name, expected in entry['files'].items():
        assert sha(bundle / name) == expected, name
    # Archived rollback bytes remain immutable. Changed current adapters must
    # reject the old runtime certificate rather than silently re-admit it.
    assert any((root/name).is_file() and sha(root/name)!=expected
               for name,expected in binding['code_locks'].items())
    with pytest.raises((ValueError,FileNotFoundError)):
        load_product_bundle(root,bundle,'ppt')


def test_new_ppt_release_keeps_artifact_and_current_source_locks():
    root=Path(__file__).resolve().parents[1]
    registry=json.loads((root/'config/harless-scenes.json').read_text(encoding='utf-8'))
    bundle=root/next(row for row in registry['scenes'] if row['id']=='ppt')['rsi']['runtime_bundle']
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    entry=json.loads((bundle/'entry.json').read_text());cert=json.loads((bundle/'certification.json').read_text())
    report=json.loads((bundle/'learning-report.json').read_text())
    assert entry['new_training'] is True and report['training_tasks']==2 and report['heldout_tasks']==1
    assert report['compilation_model_requests']==0 and report['quality_cost_promoted'] is False
    assert report['trace_collection_requests']>0
    for name,version in entry['files'].items():assert sha(bundle/name)==version,name
    for name,version in cert['code_locks'].items():assert sha(root/name)==version,name
    admitted=load_product_bundle(root,bundle,'ppt')
    assert admitted['binding_policy']=='ppt_master_sources_v1'
    assert len(admitted['certified_tool_schemas'])==5
    assert admitted['runtime_kind']=='ppt_master_v2'
    manifest=json.loads((bundle/'online-manifest.json').read_text())
    assert {tuple(a['tools']) for a in manifest['artifacts']}=={('mcp__ppt_master__pin_source','mcp__ppt_master__convert_source'),('mcp__ppt_master__convert_source','mcp__ppt_master__read_converted_source')}


@pytest.mark.parametrize('previous,release',[
    ('paper-web-v22','paper-web-v23'),('ppt-master-v19','ppt-master-v20')])
def test_gateway_polling_compatibility_preserves_certified_program_and_source_evidence(previous,release):
    root=Path(__file__).resolve().parents[1]
    old=root/'motif-libraries'/previous;new=root/'motif-libraries'/release
    for name in ['library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json']:
        assert (new/name).read_bytes()==(old/name).read_bytes(),name
    report=json.loads((new/'learning-report.json').read_text(encoding='utf-8'))
    compatibility=report['gateway_watcher_environment_compatibility']
    assert compatibility['previous_release']==previous
    assert compatibility['same_online_program'] and compatibility['same_tool_schema']
    assert not compatibility['new_capabilities'] and not compatibility['quality_cost_promoted']
    assert compatibility['model_requests']==compatibility['new_training_tasks']==0
    before=json.loads((old/'certification.json').read_text(encoding='utf-8'))['code_locks']
    after=json.loads((new/'certification.json').read_text(encoding='utf-8'))['code_locks']
    assert {name for name,value in before.items() if after.get(name)!=value}=={'scripts/harless_gateway.mjs'}
    assert set(after)-set(before)=={'scripts/reexport-gateway-polling-compat.py'}


@pytest.mark.parametrize('previous,release',[
    ('paper-web-v23','paper-web-v24'),('ppt-master-v20','ppt-master-v21')])
def test_public_context_continuation_preserves_certified_program_and_tool_schema(previous,release):
    root=Path(__file__).resolve().parents[1]
    old=root/'motif-libraries'/previous;new=root/'motif-libraries'/release
    for name in ['library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json']:
        assert (new/name).read_bytes()==(old/name).read_bytes(),name
    report=json.loads((new/'learning-report.json').read_text(encoding='utf-8'))
    compatibility=report['file_chat_public_context_compatibility']
    assert compatibility['previous_release']==previous
    assert compatibility['same_online_program'] and compatibility['same_tool_schema']
    assert not compatibility['new_capabilities'] and not compatibility['quality_cost_promoted']
    assert not compatibility['larger_concurrency_capacity_measured']
    assert compatibility['model_requests']==compatibility['new_training_tasks']==0
    before=json.loads((old/'certification.json').read_text(encoding='utf-8'))['code_locks']
    after=json.loads((new/'certification.json').read_text(encoding='utf-8'))['code_locks']
    assert {name for name,value in before.items() if after.get(name)!=value}=={
        'scripts/harless_gateway.mjs','src/adapters/dsh_web_tasks.ts'}
    assert set(after)-set(before)=={'scripts/reexport-file-chat-continuation-compat.py'}


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
    assert got['runtime_library']==str(bundle/'library.json')
    assert got['runtime_library_sha256']==sha(bundle/'library.json')
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
