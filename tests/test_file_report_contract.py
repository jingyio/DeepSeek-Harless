"""Reject false successful search delivery; validate exact scope, query, receipts and stale evidence."""
import importlib.util,json,sys
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parents[1]/'scenarios/file-management'
saved={n:sys.modules.get(n) for n in ('common','file_tools','collection_tools')}
mods={}
for name in ('common','file_tools','collection_tools','report_tools'):
    s=importlib.util.spec_from_file_location(name,HERE/(name+'.py'));m=importlib.util.module_from_spec(s)
    sys.modules[name]=m;s.loader.exec_module(m);mods[name]=m
for name,previous in saved.items():
    if previous is None:sys.modules.pop(name,None)
    else:sys.modules[name]=previous
fm=mods['file_tools'];rc=mods['report_tools'];common=mods['common'];collection=mods['collection_tools']
sys.modules.pop('report_tools',None)

@pytest.fixture
def scene(tmp_path,monkeypatch):
    monkeypatch.setattr(fm,'ROOT',tmp_path);monkeypatch.setattr(fm,'DATA',tmp_path/'data')
    root=tmp_path/'data/copy';(root/'stage_a').mkdir(parents=True);(root/'stage_b').mkdir()
    (root/'.experiment-copy').write_text('test');(root/'stage_a/followup.txt').write_text('{"query":"Orbit","followup_extensions":["*"]}')
    (root/'stage_a/context.txt').write_text('Orbit first-stage context')
    (root/'stage_b/hit.txt').write_text('An ORBIT result')
    (root/'stage_b/miss.txt').write_text('other contents');(root/'stage_b/opaque.bin').write_bytes(b'no parser')
    spec={'workspace':str(root),'task_id':'test','family':'content_search','objective':'test','rules':{},
          'initial_snapshot':common.snapshot(root),'allowed_operations':[],
          'report_contract':{'version':rc.CONTRACT_VERSION,'kind':'literal_search','collection_count':2,
                             'query_notice_path':'stage_a/followup.txt','inspection_stages':[{'path_prefix':'stage_a/'},{'path_prefix':'stage_b/','extensions_notice_path':'stage_a/followup.txt'}]}}
    s=rc.ReportScene(spec,tmp_path/'.local/output');s.read_task();return s

def gather(scene,prefix):
    rows=[r for r in scene.list_files()['files'] if r['path'].startswith(prefix)]
    p=scene.select_files([r['file_id'] for r in rows]);reads=[scene.read_file(scene.pin_file(r['file_id'])['source_id']) for r in rows]
    scene.collect_reads(p['collection_id'],[r['source_id'] for r in reads]);return reads

def ready(scene,query='Orbit'):
    first=gather(scene,'stage_a/');second=gather(scene,'stage_b/')
    scene.build_index([r['source_id'] for r in second]);return first,second,scene.search_index(query)

def test_inspection_ids_rejected_without_publishing_then_recovered(scene):
    first,second,search=ready(scene)
    with pytest.raises(fm.ToolError,match='not all inspected'):
        scene.submit_report('search',[r['file_id'] for r in first+second],[],'literal_search',search['search_receipt_id'])
    assert not (scene.output/'report.json').exists()
    result=scene.submit_report('search',search['file_ids'],['unsupported text'],'literal_search',search['search_receipt_id'])
    report=json.loads((scene.output/'report.json').read_text());assert result['artifact_sha256']==common.digest(report)
    assert report['search_receipt']['unsearchable'][0]['status']=='unsupported'
    assert len(report['file_ids'])==1

def test_wrong_scope_index_and_early_search_rejected(scene):
    first=gather(scene,'stage_a/')
    with pytest.raises(fm.ToolError):scene.search_index('Orbit')
    second=gather(scene,'stage_b/')
    with pytest.raises(fm.ToolError,match='exactly'):scene.build_index([r['source_id'] for r in first+second])
    assert not scene.index

def test_query_receipt_and_kind_are_bound(scene):
    _,_,search=ready(scene)
    with pytest.raises(fm.ToolError):scene.search_index('graph')
    with pytest.raises(fm.ToolError):scene.submit_report('x',search['file_ids'],[],'task_result')
    with pytest.raises(fm.ToolError):scene.submit_report('x',search['file_ids'],[],'literal_search','invented')
    with pytest.raises(fm.ToolError):scene.submit_report('x',search['file_ids']*2,[],'literal_search',search['search_receipt_id'])

def test_empty_literal_result_is_deliverable(scene):
    scene.path('stage_a/followup.txt').write_text('{"query":"absent[23]","followup_extensions":["*"]}')
    scene.expected=common.snapshot(scene.root);scene.spec['initial_snapshot']=scene.expected
    _,_,search=ready(scene,'absent[23]');assert search['file_ids']==[]
    assert scene.submit_report('no literal hit',[],['not semantic absence'],'literal_search',search['search_receipt_id'])['status']=='delivered_with_gaps'

def test_receipt_cannot_follow_new_target_or_changed_bytes(scene):
    _,second,search=ready(scene);scene.report_contract.pop('collection_count');scene.report_contract.pop('inspection_stages')
    p=scene.select_files([second[0]['file_id']]);scene.collect_reads(p['collection_id'],[second[0]['source_id']])
    with pytest.raises(fm.ToolError,match='changed'):scene.submit_report('x',search['file_ids'],[],'literal_search',search['search_receipt_id'])
    scene.path('stage_b/hit.txt').write_text('later mutation')
    with pytest.raises(fm.ToolError):scene.submit_report('x',search['file_ids'],[],'literal_search',search['search_receipt_id'])

def test_empty_query_rejected(scene):
    scene.report_contract.pop('query_notice_path');scene.report_contract['query']=' '
    first=gather(scene,'stage_a/');second=gather(scene,'stage_b/');scene.build_index([r['source_id'] for r in second])
    with pytest.raises(fm.ToolError):scene.search_index(' ')

def test_scope_guard_has_a_new_read_execution_version(scene):
    for name in ('pin_file','read_file','collect_reads'):
        assert getattr(rc.ReportScene,name) is getattr(collection.CollectionScene,name)
    assert rc.ReportScene.select_files is not collection.CollectionScene.select_files
    assert scene.execution_version==rc.report_version()!=collection.execution_version()
    assert scene.read_task()['report_execution_version_sha256']==scene.execution_version


def test_stage_scope_rejected_before_reads_or_collection_creation(scene):
    rows=scene.list_files()['files']
    with pytest.raises(fm.ToolError,match='declared stage'):scene.select_files([r['file_id'] for r in rows])
    assert scene.collections=={} and scene.reads=={}
    gather(scene,'stage_a/')
    with pytest.raises(fm.ToolError,match='exclude'):scene.select_files([r['file_id'] for r in rows])
    assert len(scene.collections)==1
    gather(scene,'stage_b/')
    with pytest.raises(fm.ToolError,match='already complete'):scene.select_files([r['file_id'] for r in rows])


def test_inspection_requires_all_completed_members_then_recovers(scene):
    scene.report_contract['kind']='inspection'
    first=gather(scene,'stage_a/');second=gather(scene,'stage_b/')
    with pytest.raises(fm.ToolError,match='every member'):
        scene.submit_report('only last stage',[r['file_id'] for r in second],[],'inspection')
    assert not (scene.output/'report.json').exists()
    result=scene.submit_report('all inspected',[r['file_id'] for r in first+second],[],'inspection')
    report=json.loads((scene.output/'report.json').read_text());assert result['artifact_sha256']==common.digest(report)
    assert len(report['inspection_receipts'])==2


def test_inspection_cannot_publish_before_all_stages(scene):
    scene.report_contract['kind']='inspection';first=gather(scene,'stage_a/')
    with pytest.raises(fm.ToolError,match='complete all'):
        scene.submit_report('premature',[r['file_id'] for r in first],[],'inspection')
